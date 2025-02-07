import asyncio
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Literal

import tweepy
import twikit
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from twikit.utils import Result as TwikitResult

from .cache import Base, TweetRecord, TwitterMediaRecord, TwitterUserRecord, TweetTimelineRecord
from .conversion import convert_twitter_objects


storage_path = Path(__file__).parent.parent.parent / "storage"
cache_db_path = storage_path / "twitter.sqlite"

logger = logging.getLogger('ingress.twitter.ingress')


class TwitterIngressController:
    def __init__(self, client: twikit.Client):
        self.engine = create_engine(f"sqlite:///{cache_db_path.absolute()}")
        Base.metadata.create_all(self.engine)
        self.client = client

    def session(self) -> Session:
        return Session(self.engine)

    def _cache_all(
        self,
        session: Session,
        media: list[tweepy.Media],
        tweets: list[tweepy.Tweet],
        users: list[tweepy.User],
    ):
        self._cache_media(session, media)
        self._cache_tweets(session, tweets)
        self._cache_users(session, users)

    def _cache_media(self, session: Session, media: list[tweepy.Media]):
        # Important: The ID of the media object is called `media_key` and it's not an int
        for new in media:
            cached = session.get(TwitterMediaRecord, new.media_key)
            if cached:
                cached.data = merge_dicts(cached.data, new.data)
            else:
                cached = TwitterMediaRecord(key=new.media_key, data=new.data, alt_text=new.alt_text)
            session.add(cached)

    def _cache_tweets(self, session: Session, tweets: list[tweepy.Tweet], *, force_update_timestamp: bool = False):
        for new in tweets:
            cached = session.get(TweetRecord, int(new.id))
            if cached:
                cached.data = merge_dicts(cached.data, new.data)
                if force_update_timestamp:
                    cached.fetched_at = func.now()
            else:
                cached = TweetRecord(id=int(new.id), author_id=new.author_id, data=new.data)
                if new.referenced_tweets:
                    for rt in new.referenced_tweets:
                        if rt.type == 'replied_to':
                            cached.reply_to_tweet_id = int(rt.id)
                        elif rt.type == 'quoted':
                            cached.quoted_tweet_id = int(rt.id)
            session.add(cached)

    def _cache_users(self, session: Session, users: list[tweepy.User]):
        for new in users:
            cached = session.get(TwitterUserRecord, int(new.id))
            if cached:
                cached.data = merge_dicts(cached.data, new.data)
            else:
                cached = TwitterUserRecord(id=int(new.id), username=new.username, data=new.data)
            session.add(cached)

    def _convert_and_cache_tweets(self, session: Session, result: TwikitResult[twikit.Tweet]) -> list[tweepy.Tweet]:
        converted = convert_twitter_objects(tweets=result)
        self._cache_all(session, **converted)
        return converted['tweets']

    def _get_home_timeline(
        self,
        session: Session,
        timeline_id: str,
    ) -> TweetTimelineRecord | None:
        return session.execute(
            select(TweetTimelineRecord) \
                .where(TweetTimelineRecord.timeline_id == timeline_id) \
                .order_by(TweetTimelineRecord.fetch_seq.desc()) \
                .limit(1)
        ).scalar_one_or_none()

    def add_tweet(self, tweet: tweepy.Tweet, *, outbound: bool = False):
        with self.session() as session:
            self._cache_tweets(session, [tweet], force_update_timestamp=outbound)
            session.commit()

    def iterate_unanalyzed_tweets(self, *, batch_size: int = 30) -> Iterable[list[tweepy.Tweet]]:
        with self.session() as session:
            while True:
                tweets = session.execute(
                    select(TweetRecord).where(TweetRecord.warehouse_post_id == None).order_by(TweetRecord.id.asc()).limit(batch_size)
                ).scalars().all()

                if tweets:
                    yield [t.tweet for t in tweets]
                if len(tweets) < batch_size:
                    break

    def get_home_timeline_tweets(
        self,
        user_id: int,
        *,
        count: int = 40,
    ) -> list[tweepy.Tweet]:
        timeline_id = TweetTimelineRecord.home_timeline_id(user_id)
        with self.session() as session:
            tweets = self._get_home_timeline(session, timeline_id).get_tweets(session)
            return [t.tweet for t in tweets[:count]]

    async def fetch_home_timeline(
        self,
        user_id: int,
        *,
        count: int = 40,
    ):
        timeline_id = TweetTimelineRecord.home_timeline_id(user_id)

        with self.session() as session:
            prev_timeline = self._get_home_timeline(session, timeline_id)

            result = await self.client.get_latest_timeline(count=count)
            tweets = self._convert_and_cache_tweets(session, result)
            session.commit()

            new_tweet_ids = [tweet.id for tweet in tweets]
            logger.debug(f"Fetched {len(tweets)} tweets from timeline {timeline_id}. {len(new_tweet_ids)} new tweets.")

            if prev_timeline:
                max_prev_timeline_tweet_id = max(prev_timeline.tweet_ids)
                new_tweet_ids = [id for id in new_tweet_ids if id > max_prev_timeline_tweet_id]

            if not prev_timeline or len(new_tweet_ids) > 4 or len(prev_timeline.tweet_ids) > 1000:
                timeline = TweetTimelineRecord(timeline_id=timeline_id)
                timeline.tweet_ids = new_tweet_ids
            else:
                timeline = prev_timeline
                timeline.tweet_ids.extend(new_tweet_ids)
                if len(timeline.tweet_ids) > 1000:
                    timeline.tweet_ids = timeline.tweet_ids[-1000:]

            timeline.persist(session)
            tweets = timeline.get_tweets(session)

            return [tweet.tweet for tweet in tweets]

    def get_tweet_by_id(self, tweet_id: int) -> tweepy.Tweet | None:
        with self.session() as session:
            cached = session.get(TweetRecord, tweet_id)
            return cached.tweet if cached else None

    def get_recent_tweets_by_user(self, user_id: int, *, count: int = 40, include_replies: bool = False, include_mid_thread: bool = False) -> list[tweepy.Tweet]:
        """Get the most recent tweets by a given user. Returns from the most recent to the least recent tweets."""
        query = select(TweetRecord).where(TweetRecord.author_id == user_id).order_by(TweetRecord.id.desc()).limit(count)
        if not include_replies:
            query = query.where(TweetRecord.reply_to_tweet_id == None)

        with self.session() as session:
            records = session.execute(query).scalars().all()
            tweets = [tweet.tweet for tweet in records]

        if include_replies and not include_mid_thread:
            tweets = [t for t in tweets if t.in_reply_to_user_id != user_id]

        return tweets

    def get_thread_by_id(self, tweet_id: int) -> list[tweepy.Tweet]:
        """Get a thread of tweets by the first tweet's ID. Does not include the first tweet. Returns an empty list if the tweet is not found or is not part of a thread."""
        with self.session() as session:
            cached = session.get(TweetRecord, tweet_id)
            if not cached:
                return []

            prev_tweet = cached.tweet
            thread: list[tweepy.Tweet] = []

            while (next_tweet := self._get_next_tweet(session, prev_tweet)):
                thread.append(next_tweet)
                prev_tweet = next_tweet

            return thread

    def _get_next_tweet(self, session: Session, tweet: tweepy.Tweet) -> tweepy.Tweet | None:
        query = select(TweetRecord).where(TweetRecord.reply_to_tweet_id == tweet.id).where(TweetRecord.author_id == tweet.author_id).order_by(TweetRecord.id.asc()).limit(1)
        record = session.execute(query).scalar_one_or_none()
        return record.tweet if record else None

    def get_user_by_id(self, user_id: int) -> tweepy.User | None:
        with self.session() as session:
            cached = session.get(TwitterUserRecord, user_id)
            return cached.user if cached else None

    def _get_recent_tweets_of(self, my_user_id: int, count: int) -> list[tweepy.Tweet]:
        """Return a list of recent tweets by a given user, but ensuring to include enough non-reply tweets."""
        def is_a_reply(tweet: tweepy.Tweet) -> bool:
            return tweet.referenced_tweets and any(rt.type == 'replied_to' for rt in tweet.referenced_tweets)

        my_recent_tweets = self.get_recent_tweets_by_user(my_user_id, count=50)

        scan_count = min(8, count)
        recent_count = math.floor(scan_count / 2)
        shortlist = my_recent_tweets[:recent_count]
        shortlist += [t for t in my_recent_tweets[recent_count:] if not is_a_reply(t)][:scan_count - recent_count]
        return shortlist

    def _get_replies_to_tweet(self, session: Session, tweet_id: int, *, count: int = 40) -> list[tweepy.Tweet]:
        """Return a list of replies to a given tweet."""
        cached_items = session.execute(
            select(TweetRecord).where(TweetRecord.reply_to_tweet_id == tweet_id).order_by(TweetRecord.id.desc()).limit(count)
        ).scalars().all()
        return [item.tweet for item in cached_items]

    def get_recent_replies(self, my_user_id: int, *, count: int = 40) -> list[tweepy.Tweet]:
        shortlist = self._get_recent_tweets_of(my_user_id, count)

        with self.session() as session:
            replies: list[tweepy.Tweet] = []

            for tweet in shortlist:
                replies += self._get_replies_to_tweet(session, tweet.id, count=count)

            return replies

    async def fetch_recent_replies(self, my_user_id: int, *, count: int = 40):
        shortlist = self._get_recent_tweets_of(my_user_id, count)

        with self.session() as session:
            new_replies: list[twikit.Tweet] = []
            for tweepy_tweet in shortlist:
                twikit_tweet = await self.client.get_tweet_by_id(tweepy_tweet.id)
                if twikit_tweet.replies and twikit_tweet.user.id == str(my_user_id):
                    new_replies.extend([r for r in twikit_tweet.replies if r.user.id != str(my_user_id)])
                await asyncio.sleep(1)

            new_replies_users = [r.user for r in new_replies]

            converted = convert_twitter_objects(
                tweets=TwikitResult(new_replies),
                users=TwikitResult(new_replies_users),
            )
            self._cache_all(session, **converted)
            session.commit()

    async def fetch_tweet(self, tweet_id: int) -> tweepy.Tweet | None:
        """Get a tweet by its ID. If prefer_cache is True, return the cached tweet if available."""
        min_fetch_interval = timedelta(minutes=2)

        with self.session() as session:
            if (tweet := session.get(TweetRecord, tweet_id)) and datetime.now() - tweet.fetched_at < min_fetch_interval:
                return tweet.tweet
            else:
                tweet = await self.client.get_tweet_by_id(tweet_id)
                if not tweet:
                    return None
                tweets = self._convert_and_cache_tweets(session, TwikitResult([tweet]))
                session.commit()
                return tweets[0]

    def get_user_by_username(self, username: str) -> tweepy.User | None:
        with self.session() as session:
            cached = session.execute(
                select(TwitterUserRecord).where(TwitterUserRecord.username == username).limit(1)
            ).scalar_one_or_none()
            return cached.user if cached else None

    async def fetch_user_by_id(self, id: int) -> tweepy.User | None:
        min_fetch_interval = timedelta(minutes=10)

        with self.session() as session:
            cached = session.get(TwitterUserRecord, id)
            if cached and datetime.now() - cached.fetched_at < min_fetch_interval:
                return cached.user
            else:
                user = await self.client.get_user_by_id(id)
                if not user:
                    return None
                converted = convert_twitter_objects(users=[user])
                self._cache_all(session, **converted)
                session.commit()
                return converted['users'][0]

    async def fetch_user_by_username(self, username: str) -> tweepy.User | None:
        min_fetch_interval = timedelta(minutes=10)

        with self.session() as session:
            cached = session.execute(
                select(TwitterUserRecord).where(TwitterUserRecord.username == username).limit(1)
            ).scalar_one_or_none()
            if cached and datetime.now() - cached.fetched_at < min_fetch_interval:
                return cached.user
            else:
                user = await self.client.get_user_by_screen_name(username)
                if not user:
                    return None
                converted = convert_twitter_objects(users=[user])
                self._cache_all(session, **converted)
                session.commit()
                return converted['users'][0]

    async def fetch_user_tweets(self, user_id: int, *, count: int = 50, batch_size: int = 50, delay_secs: float = 4, tweet_type: Literal['Tweets', 'Replies'] = 'Tweets') -> list[tweepy.Tweet]:
        with self.session() as session:
            # TODO: Prevent rapid re-fetching
            result_batch = await self.client.get_user_tweets(user_id, tweet_type=tweet_type, count=min(batch_size, count))
            result = result_batch

            while len(result) < count and result_batch.next_cursor:
                await asyncio.sleep(delay_secs)
                result_batch = await result_batch.next()
                result = twikit.utils.Result(list(result) + list(result_batch))

            converted = self._convert_and_cache_tweets(session, result)
            session.commit()
            return converted


def merge_dicts(a: dict, b: dict) -> dict:
    a = a.copy()
    for key, value in b.items():
        if value is not None:
            a[key] = value
    return a

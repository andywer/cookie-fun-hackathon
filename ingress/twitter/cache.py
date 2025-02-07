import logging

import tweepy

from sqlalchemy import Column, DateTime, Integer, JSON, String, func, select
from sqlalchemy.orm import Session, declarative_base


Base = declarative_base()

logger = logging.getLogger('ingress.twitter.cache')


class TwitterMediaRecord(Base):
    __tablename__ = 'twitter_media'

    # Important: The ID of the media object is called `media_key` and it's not an int
    key = Column(String, primary_key=True)
    data = Column(JSON)
    fetched_at = Column(DateTime, default=func.now())
    alt_text = Column(String, nullable=True)
    transcript = Column(String, nullable=True)

    @property
    def media(self) -> tweepy.Media:
        return tweepy.Media(self.data)


class TweetRecord(Base):
    __tablename__ = 'twitter_tweets'

    id = Column(Integer, primary_key=True)
    data = Column(JSON)
    fetched_at = Column(DateTime, default=func.now())

    author_id = Column(Integer, index=True)
    reply_to_tweet_id = Column(Integer, index=True, nullable=True)
    quoted_tweet_id = Column(Integer, index=True, nullable=True)

    @property
    def tweet(self) -> tweepy.Tweet:
        return tweepy.Tweet(self.data)


class TwitterUserRecord(Base):
    __tablename__ = 'twitter_users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    data = Column(JSON)
    fetched_at = Column(DateTime, default=func.now())

    @property
    def user(self) -> tweepy.User:
        return tweepy.User(self.data)


class TweetTimelineRecord(Base):
    __tablename__ = 'tweet_timelines'

    timeline_id = Column(String, primary_key=True)
    """The ID of the timeline cache entry."""

    fetch_seq = Column(Integer, primary_key=True)
    """The fetch number/sequence for this timeline cache entry."""

    fetched_at = Column(DateTime, default=func.now())
    """The datetime when this timeline was fetched."""

    tweet_ids: list[int] = Column(JSON)
    """The IDs of the tweets in the home timeline."""

    @staticmethod
    def home_timeline_id(user_id: int) -> str:
        """
        The ID of the home timeline cache entry for a given user.
        The home timeline contains tweets from the accounts the user follows and the user's own tweets.
        """
        return f"home:{user_id}"

    @staticmethod
    def list_timeline_id(list_id: str) -> str:
        """The ID of the list timeline cache entry for a given list."""
        return f"list:{list_id}"

    def persist(self, session: Session):
        if not self.timeline_id:
            raise ValueError("Cannot persist timeline cache without a timeline ID")

        if not self.fetch_seq:
            # Subquery to get MAX(fetch_seq) for the specified timeline_id and add 1
            self.fetch_seq = select(
                func.coalesce(func.max(TweetTimelineRecord.fetch_seq), 0) + 1
            ).where(TweetTimelineRecord.timeline_id == self.timeline_id).scalar_subquery()

        session.add(self)
        session.commit()

    def get_tweets(self, session: Session) -> list[TweetRecord]:
        tweets = session.execute(
            select(TweetRecord).where(TweetRecord.id.in_(self.tweet_ids))
        ).scalars().all()
        # Sort by the order of tweet_ids
        tweets.sort(key=lambda t: self.tweet_ids.index(t.id))
        return tweets

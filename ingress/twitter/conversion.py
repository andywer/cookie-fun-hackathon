from datetime import datetime

import tweepy
import twikit
from twikit.utils import Result as TwikitResult


def convert_twitter_timestamp(timestamp_str: str) -> str:
    # Convert from 'Sun Oct 27 13:00:32 +0000 2024' to '%Y-%m-%dT%H:%M:%S.000Z'
    dt = datetime.strptime(timestamp_str, '%a %b %d %H:%M:%S %z %Y')
    return dt.isoformat(timespec="milliseconds")


def merge_list_dicts(*dicts: dict[str, list]) -> dict[str, list]:
    result = {**dicts[0]}
    for dict in dicts[1:]:
        for k, v in dict.items():
            result[k] = result.get(k, []) + v
    return result


def convert_twitter_objects(
    media: TwikitResult[dict] | None = None,
    tweets: TwikitResult[twikit.Tweet] | None = None,
    users: TwikitResult[twikit.User] | None = None,
) -> dict[str, TwikitResult]:
    result = {
        'media': [],
        'tweets': [],
        'users': [],
    }

    for media_item in (media or []):
        converted = tweepy.Media({
            'media_key': media_item['media_key'],
            'type': media_item['type'],
            'url': media_item['media_url_https'],
            'duration_ms': media_item.get('duration_ms', None),
            'height': media_item.get('height', None),
            'width': media_item.get('width', None),
            'non_public_metrics': media_item.get('non_public_metrics', None),
            'organic_metrics': media_item.get('organic_metrics', None),
            'preview_image_url': media_item.get('preview_image_url', None),
            'promoted_metrics': {},
            'public_metrics': {},
            'alt_text': media_item.get('alt_text', None),
            'variants': media_item.get('variants', None),
        })
        result['media'].append(converted)

    tweets_by_id: dict[str, twikit.Tweet] = {}

    # Expand the list of tweets to include all embedded tweets
    tweets_to_expand: list[twikit.Tweet] = list(tweets) if tweets else []
    while tweets_to_expand:
        tweet = tweets_to_expand.pop(0)
        tweets_by_id[tweet.id] = tweet

        if hasattr(tweet, 'quote') and tweet.quote:
            tweets_to_expand.append(tweet.quote)
        if hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet:
            tweets_to_expand.append(tweet.retweeted_tweet)
        if hasattr(tweet, 'replies') and tweet.replies:
            for reply in tweet.replies:
                if reply.id not in tweets_by_id:
                    tweets_to_expand.append(reply)
        if hasattr(tweet, 'reply_to') and tweet.reply_to:
            for reply in tweet.reply_to:
                if reply.id not in tweets_by_id:
                    tweets_to_expand.append(reply)

    for tweet in tweets_by_id.values():
        converted = tweepy.Tweet({
            'id': tweet.id,
            'text': tweet.text,
            'author_id': tweet.user.id,
            'created_at': convert_twitter_timestamp(tweet.created_at),
            'edit_history_tweet_ids': [],
            'lang': tweet.lang,
            'in_reply_to_status_id_str': tweet.in_reply_to,
            'is_quote_status': tweet.is_quote_status,
            'possibly_sensitive': tweet.possibly_sensitive,
            'possibly_sensitive_editable': tweet.possibly_sensitive_editable,
            'public_metrics': {
                'retweet_count': tweet.retweet_count,
                'reply_count': tweet.reply_count,
                'like_count': tweet.favorite_count,
                'quote_count': tweet.quote_count,
            },
            'referenced_tweets': [
                *([{ 'type': 'quoted', 'id': tweet.quote.id }] if hasattr(tweet, 'quote') and tweet.quote else []),
                *([{ 'type': 'replied_to', 'id': tweet.in_reply_to }] if hasattr(tweet, 'in_reply_to') and tweet.in_reply_to else []),
                *([{ 'type': 'retweeted', 'id': tweet.retweeted_tweet.id }] if hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet else []),
            ],
            'attachments': {
                'media_keys': [media['media_key'] for media in tweet.media] if tweet.media else [],
            },
        })
        result['tweets'].append(converted)

        if tweet.user:
            result = merge_list_dicts(result, convert_twitter_objects(users=TwikitResult([tweet.user])))
        if hasattr(tweet, 'quote') and tweet.quote:
            result = merge_list_dicts(result, convert_twitter_objects(tweets=TwikitResult([tweet.quote])))
        if hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet:
            result = merge_list_dicts(result, convert_twitter_objects(tweets=TwikitResult([tweet.retweeted_tweet])))
        if hasattr(tweet, 'media') and tweet.media:
            result = merge_list_dicts(result, convert_twitter_objects(media=TwikitResult(tweet.media)))

    for user in (users or []):
        converted = tweepy.User({
            'id': user.id,
            'name': user.name,
            'username': user.screen_name,
            'created_at': convert_twitter_timestamp(user.created_at),
            'description': user.description,
            'entities': None,
            'location': user.location,
            'pinned_tweet_id': user.pinned_tweet_ids[0] if user.pinned_tweet_ids else None,
            'profile_image_url': user.profile_image_url,
            'protected': user.protected,
            'public_metrics': {
                'followers_count': user.followers_count,
                'following_count': user.following_count,
            },
            'url': user.url,
            'verified': user.verified,
        })
        result['users'].append(converted)

    return result
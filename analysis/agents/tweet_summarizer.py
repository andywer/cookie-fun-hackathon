import asyncio
from textwrap import indent
from typing import List, Protocol

import tweepy
import yaml
from langchain.chat_models.base import BaseChatModel
from langsmith import traceable
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from pydantic import BaseModel


class TwitterCache(Protocol):
    def get_tweet_by_id(self, id: int) -> tweepy.Tweet | None:
        ...

    def get_user_by_id(self, id: int) -> tweepy.User | None:
        ...

    def get_thread_by_id(self, tweet_id: int) -> list[tweepy.Tweet]:
        ...


class DiscardIrrelevantTweets(BaseModel):
    """Discard tweets that are not relevant to the objective."""
    tweet_ids: List[int]


class TweetSerializer:
    def __init__(self, cache: TwitterCache, include_tweet_ids: bool = True):
        self.cache = cache
        self.include_tweet_ids = include_tweet_ids

    def serialize(self, tweet: tweepy.Tweet, resolve_thread: bool = True, ignore_ids: set[int] = set()) -> dict:
        if tweet.id in ignore_ids:
            return None

        author = self.cache.get_user_by_id(tweet.author_id)
        output = {
            "created_at": tweet.created_at.isoformat(),
            "author": f"{author.name} (@{author.username})" if author else f"Uncached user {tweet.author_id}",
            "text": tweet.text,
        }

        if self.include_tweet_ids:
            output["id"] = tweet.id

        if tweet.referenced_tweets:
            referenced_tweets = [
                self.serialize(self.cache.get_tweet_by_id(referenced_tweet.id), resolve_thread=False, ignore_ids=ignore_ids | {tweet.id})
                if self.cache.get_tweet_by_id(referenced_tweet.id)
                else f"Uncached tweet {referenced_tweet.id}"
                for referenced_tweet in tweet.referenced_tweets
                if referenced_tweet.id not in ignore_ids
            ]
            if referenced_tweets:
                output["referenced_tweets"] = referenced_tweets

        if resolve_thread:
            thread = self.cache.get_thread_by_id(tweet.id)
            if thread:
                output["thread"] = [self.serialize(reply, resolve_thread=False, ignore_ids=ignore_ids | {tweet.id} | {t.id for t in thread if t.id != reply.id}) for reply in thread]

        return output


def create_filtering_prompt(serializer: TweetSerializer, tweets: List[tweepy.Tweet], objective: str, tool_name: str) -> ChatCompletionMessageParam:
    return {
        "role": "user",
        "content": f"""
Your task is to filter the tweets below to only include the ones that are relevant to the objective.
Go through the tweets one by one and call the function `{tool_name}` with the tweet ids of all the tweets that are not relevant and should be discarded.

<objective>
{objective}
</objective>

Filter the following tweets:
<tweets>
{indent(yaml.dump([serializer.serialize(tweet) for tweet in tweets], indent=2, allow_unicode=True), "    ")}
</tweets>
""".strip(),
    }


def create_summarization_prompt(serializer: TweetSerializer, tweets: List[tweepy.Tweet], objective: str) -> ChatCompletionMessageParam:
    return {
        "role": "user",
        "content": f"""
Your task is to summarize the tweets below in a way that is useful for a finance professional.
Respond with nothing but the summary.

<objective>
{objective}
</objective>

Summarize the following tweets:
<tweets>
{indent(yaml.dump([serializer.serialize(tweet) for tweet in tweets], indent=2, allow_unicode=True), "    ")}
</tweets>
""".strip(),
    }


class TweetSummarizerAgent:
    def __init__(self, model: BaseChatModel, cache: TwitterCache):
        self.model = model
        self.cache = cache

    @traceable(name="TweetSummarizerAgent.filter_tweets")
    async def filter_tweets(self, tweets: List[tweepy.Tweet], objective: str, batch_size: int = 100) -> List[tweepy.Tweet]:
        batches = [tweets[i:i + batch_size] for i in range(0, len(tweets), batch_size)]
        filtered_batches = await asyncio.gather(*[
            self._filter_tweets(batch, objective) for batch in batches
        ])
        return [tweet for batch in filtered_batches for tweet in batch]

    async def _filter_tweets(self, tweets: List[tweepy.Tweet], objective: str) -> List[tweepy.Tweet]:
        serializer = TweetSerializer(self.cache, include_tweet_ids=True)

        response: DiscardIrrelevantTweets = await self.model \
            .with_structured_output(DiscardIrrelevantTweets) \
            .ainvoke([create_filtering_prompt(serializer, tweets, objective, DiscardIrrelevantTweets.__name__)])

        return [tweet for tweet in tweets if tweet.id not in response.tweet_ids]

    @traceable(name="TweetSummarizerAgent.summarize_tweets")
    async def summarize_tweets(self, tweets: List[tweepy.Tweet], objective: str, include_tweet_ids: bool = True) -> str:
        serializer = TweetSerializer(self.cache, include_tweet_ids=include_tweet_ids)

        response = await self.model \
            .ainvoke([create_summarization_prompt(serializer, tweets, objective)])

        summary = response.content.strip()
        if summary.startswith("```") and summary.endswith("```"):
            first_newline_index = summary.find("\n")
            summary = summary[first_newline_index + 1:-3].strip()

        return summary

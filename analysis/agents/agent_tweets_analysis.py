from textwrap import indent
from typing import List

import tweepy
import yaml
from langchain.chat_models.base import BaseChatModel
from langsmith import traceable
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from app.storage.agent_output_analyses import AgentOutputAnalysisRecord
from .tweet_summarizer import TweetSerializer, TwitterCache


def create_analysis_prompt(serializer: TweetSerializer, author: tweepy.User, tweets: List[tweepy.Tweet], objective: str, context: str) -> ChatCompletionMessageParam:
    return {
        "role": "user",
        "content": f"""
<purpose>
Your task is to analyze the tweets below in a way that is useful for a professional in the field of AI and finance.
Respond with nothing but the analysis.
</purpose>

<objective>
{objective}
</objective>

Analyze the following tweets:
<tweets>
{indent(yaml.dump([serializer.serialize(tweet) for tweet in tweets], indent=2, allow_unicode=True), "    ")}
</tweets>

The tweets are from the following account:
<account>
{indent(yaml.dump({
    "name": author.name,
    "username": author.username,
    "description": author.description,
    "location": author.location,
    "url": author.url,
    "created_at": author.created_at.isoformat(),
}, indent=2, allow_unicode=True), "    ")}
</account>

<additional_context>
{indent(context, "    ")}
</additional_context>
""".strip(),
    }


class AgentTweetsAnalysisAgent:
    def __init__(self, model: BaseChatModel, cache: TwitterCache):
        self.model = model
        self.cache = cache

    @traceable(name="AgentTweetsAnalysisAgent.analyze_tweets")
    async def analyze_tweets(self, author: tweepy.User, tweets: List[tweepy.Tweet], context: str, objective: str, include_tweet_ids: bool = True) -> AgentOutputAnalysisRecord:
        source_url = f"https://x.com/{author.username}"
        serializer = TweetSerializer(self.cache, include_tweet_ids=include_tweet_ids)

        response = await self.model \
            .ainvoke([create_analysis_prompt(serializer, author, tweets, objective, context)])

        summary = response.content.strip()
        if summary.startswith("```") and summary.endswith("```"):
            first_newline_index = summary.find("\n")
            summary = summary[first_newline_index + 1:-3].strip()

        return AgentOutputAnalysisRecord(
            source_url=source_url,
            analysis=summary,
            meta={"context": context},
        )

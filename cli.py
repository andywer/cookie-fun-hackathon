import asyncio
import asyncclick as click
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Literal
load_dotenv()

from langchain_openai import ChatOpenAI
from twikit import Client as TwikitClient

from analysis.agents.tweet_summarizer import TweetSummarizerAgent
from analysis.agents.agent_tweets_analysis import AgentTweetsAnalysisAgent
from analysis.pipelines.cookie_fun_runs import CookieFunSpecificRunPipeline
from app.analysis.cookie_fun import create_recursion_pipeline, load_prompt
from app.storage.agent_output_analyses import open_agent_output_analyses_db
from app.storage.cookie_fun import open_cookiefun_db, BatchAnalysisRecord, HistoricAgentRecord
from ingress.social.cookie_fun import AgentDetails, CookieFunIngestion
from ingress.twitter.controller import TwitterIngressController


gpt4o_mini = ChatOpenAI(model="gpt-4o-mini")

o3_mini = ChatOpenAI(model="o3-mini", max_completion_tokens=30_000)
o3_mini_high = ChatOpenAI(model="o3-mini", reasoning_effort="high", max_completion_tokens=30_000)


@click.group()
def cli():
    """CLI tool for ingestion and analysis of cookie.fun data."""
    pass


@cli.command("ingest:cookie.fun")
@click.option('--delta-interval', type=click.Choice(['_3Days', '_7Days']), default='_3Days', help='Data point to ingest')
async def ingest_cookie_fun(delta_interval: Literal["_3Days", "_7Days"]):
    """Ingest data from Cookie Fun API."""
    ingestion = CookieFunIngestion()
    run = await ingestion.ingest(delta_interval=delta_interval)

    for agent_record in run.agents:
        agent = AgentDetails(**agent_record.data)
        click.echo(f"- Name: {agent.agentName}")
        click.echo(f"  Price: ${agent.price:,.4f}")
        click.echo(f"  Market Cap: ${agent.marketCap:,.0f}")
        click.echo(f"  Twitter: @{agent.twitterUsernames[0]}")


@cli.command("ingest:twitter")
@click.argument('username')
@click.option('--count', type=int, default=50, help='Number of tweets to ingest')
@click.option('--replies', is_flag=True, help='Whether to ingest replies')
async def ingest_twitter(username: str, count: int, replies: bool):
    """Ingest data from Twitter API."""
    twikit_client = TwikitClient('en-US')
    twikit_client.load_cookies(str(Path(__file__).parent / os.getenv('TWITTER_COOKIES_FILE')))

    controller = TwitterIngressController(twikit_client)
    user = await controller.fetch_user_by_username(username)
    click.echo(user)

    timeline = await controller.fetch_user_tweets(user.id, count=count, delay_secs=4, tweet_type='Tweets' if not replies else 'Replies')
    click.echo(timeline)


@cli.command("analyze")
@click.argument('prompt_file', type=Path)
@click.option('--run-id', type=int, default=None, help='Specific run ID to analyze')
@click.option('--context-path', type=Path, default=None, help='Path to a file containing additional context for the analysis')
@click.option('--ignore-cached', is_flag=True, help='Ignore cached data')
async def analyze(prompt_file: Path, run_id, context_path, ignore_cached):
    """Analyze Cookie Fun data with specified parameters."""

    ingestion = CookieFunIngestion()
    ingestion_run = ingestion.get_ingestion_run_by_id(run_id) if run_id is not None else ingestion.get_last_ingestion_run()

    if not ingestion_run:
        raise ValueError("No ingestion run found")

    if context_path:
        with open(context_path, 'r') as f:
            context = f.read()
    else:
        context = None

    analysis_pipeline = load_prompt(prompt_file, ingestion_run, context, ignore_cached)
    pipeline = CookieFunSpecificRunPipeline(ingestion_run) | create_recursion_pipeline(analysis_pipeline)
    latest_analysis_record: BatchAnalysisRecord | None = None

    async for analysis_record, input_records in pipeline.run(None):
        click.echo(f"Created analysis record {analysis_record.id} for {len(input_records)} agents")
        latest_analysis_record = analysis_record

    click.echo(latest_analysis_record.analysis)

@cli.command("summarize:tweets")
@click.argument('usernames', nargs=-1)
@click.option('--focus-ai', is_flag=True, help='Whether to focus on Web3xAI-related tweets')
async def summarize_tweets(usernames: list[str], focus_ai: bool):
    """Summarize previously ingested tweets for a list of Twitter users."""
    import tweepy

    controller = TwitterIngressController(TwikitClient('en-US'))
    tweets: list[tweepy.Tweet] = []

    for username in usernames:
        user = controller.get_user_by_username(username)
        if user is None:
            raise ValueError(f"User {username} not found in local cache")

        tweets += controller.get_recent_tweets_by_user(user.id, count=200)

    agent = TweetSummarizerAgent(gpt4o_mini, controller)
    objective = "Provide a detailed overview over the current state of the cryptocurrency market. Highlight current narratives and trends, including social media activity, and technological developments. Briefly mention major events and news relevant to the broader market, if any. \n\nTime span: Last few weeks. \n\nDo not reference specific tweets.\n\nOutput as a markdown document, with sections for each topic."

    if focus_ai:
        objective += "\n\nFocus on the topic of AI in web3, and the impact of AI on the market."

    click.echo(f"Filtering {len(tweets)} tweets…")
    tweets = await agent.filter_tweets(tweets, objective)

    click.echo(f"Summarizing {len(tweets)} tweets…")
    summary = await agent.summarize_tweets(tweets, objective, include_tweet_ids=False)
    click.echo(summary)


@cli.command("analyze:agent_tweets")
@click.argument('username')
@click.option('--context', 'context_path', type=Path, help='Path to a file containing context for the analysis')
@click.option('--count', type=int, default=20, help='Number of recent tweets to analyze')
async def analyze_tweets(username: str, context_path: Path, count: int):
    """Analyze previously ingested tweets."""
    controller = TwitterIngressController(TwikitClient('en-US'))
    agent = AgentTweetsAnalysisAgent(o3_mini_high, controller)

    user = controller.get_user_by_username(username)
    if user is None:
        raise ValueError(f"User {username} not found in local cache")

    tweets = controller.get_recent_tweets_by_user(user.id, count=count, include_replies=True)
    if not tweets:
        raise ValueError(f"No tweets found in local cache for user {username}")

    with open(context_path, 'r') as f:
        context = f.read()

    with open_cookiefun_db() as session:
        agent_record = HistoricAgentRecord.get_by_twitter_handle(session, username)
        if agent_record is None:
            raise ValueError(f"No agent found in local cache for user {username}")

    click.echo("Summarizing agent data…")
    response = await gpt4o_mini.ainvoke([
        ("user", "Provide a concise summary of the following market and social media impact data in markdown format. Respond with nothing but the summary.\n\n" + json.dumps(agent_record.data, indent=2, ensure_ascii=False)),
    ])
    context += "\n\n---\n\n" + response.content

    objective = f"""Provide a detailed critical evaluation of the AI agent @{user.username}, based on the tweets it has posted (see below). \n\nJudge the quality of the agent's tweets, the consistency of its messages, and estimate the effort required for someone to launch a similar agent. \n\nDoes the agent do what it claims to do, does the agent's purpose warrant any investment? \n\nState your confidence in your assessments and what more information you would need to make a more informed assessment. \n\nOutput as a markdown document, with sections for each topic."""

    click.echo(f"Analyzing {len(tweets)} tweets…")
    analysis = await agent.analyze_tweets(user, tweets, context, objective, include_tweet_ids=False)

    with open_agent_output_analyses_db() as session:
        session.add(analysis)
        session.commit()
        session.refresh(analysis)

    click.echo(analysis.analysis)


def main():
    """Entry point for the CLI application."""
    asyncio.run(cli())


if __name__ == '__main__':
    main()

import yaml
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Callable

from langchain_openai import ChatOpenAI
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from analysis.agents.cookie_fun_identify_top_projects import CookieFunTopAgentsIdentificationAgent
from analysis.agents.cookie_fun_agents import CookieFunAgentsAnalysisAgent
from analysis.pipelines.cookie_fun_batched_analysis import CookieFunBatchedAnalysisPipeline
from analysis.pipelines.recursion_pipeline import RecursionPipeline
from app.storage.cookie_fun import HistoricAgentRecord, IngestionRunRecord
from ingress.social.cookie_fun import AgentDetails


def large_caps_filter(record: HistoricAgentRecord) -> bool:
    agent = AgentDetails(**record.data)
    return agent.marketCap >= 100_000_000

def small_caps_filter(record: HistoricAgentRecord) -> bool:
    agent = AgentDetails(**record.data)
    return agent.marketCap < 5_000_000

def resilience_filter(record: HistoricAgentRecord) -> bool:
    agent = AgentDetails(**record.data)
    return agent.marketCapDeltaPercent > -10


filters = {
    "unfiltered": lambda _: True,
    "small_caps": small_caps_filter,
    "large_caps": large_caps_filter,
    "resilient": resilience_filter,
}


openai_client = wrap_openai(AsyncOpenAI())

gpt4o_mini = ChatOpenAI(model="gpt-4o-mini")


identify_top_projects_agent = CookieFunTopAgentsIdentificationAgent(model=gpt4o_mini)

output_prompt = "Present an overview of the projects. Then provide an in-depth analysis for each of the top projects. Make sure to include the name, twitter handle, and market cap of each top project. Explain why each top project is interesting to investors and how it compares to other projects.\n\nLimit your analysis to at most 5 top projects. Provide a confidence level for each of your assessments and a brief summary of what additional contextual information would be required to make a more confident assessment."


def create_analysis_pipeline(
    ingestion_run: IngestionRunRecord,
    analysis_type: str,
    prompt: str,
    filter: Callable[[HistoricAgentRecord], bool],
    context: str | None = None,
    ignore_cached: bool = False,
):
    analysis_agent = CookieFunAgentsAnalysisAgent(
        client=openai_client,
        model="o3-mini",
        model_kwargs={"reasoning_effort": "medium", "max_completion_tokens": 30_000},
        analysis_prompt=prompt,
        output_prompt=output_prompt,
    )

    return CookieFunBatchedAnalysisPipeline(
        analysis_type=analysis_type,
        agent=partial(analysis_agent.analyze_agents, context=context, ingestion_run=ingestion_run),
        identify_top_agents=identify_top_projects_agent.identify_top_agents,
        filter_agents=filter,
        batch_size=15,
        ignore_cached=ignore_cached,
        extra_metadata={"model": analysis_agent.model},
    )


def create_recursion_pipeline(pipeline: CookieFunBatchedAnalysisPipeline):
    return RecursionPipeline(
        pipeline=pipeline,
        mapper=lambda analysis_records: [next(rec for rec in record.ingestion_run.agents if rec.id == project_id) for record in analysis_records for project_id in record.top_agent_ids],
        stopper=lambda analysis_records: len(analysis_records) <= 5,
        max_depth=8,
    )


def load_prompt(prompt_file: Path, ingestion_run: IngestionRunRecord, context: str | None = None, ignore_cached: bool = False):
    with open(prompt_file, "r") as f:
        prompt_file_content = f.read()

    # Add a newline to the beginning of the file, so we can always assume a separator line, even if the frontmatter is empty
    prompt_file_content = "\n" + prompt_file_content

    if "\n---\n" in prompt_file_content:
        separator_index = prompt_file_content.find("\n---\n")
        yaml_frontmatter = prompt_file_content[:separator_index]
        config = yaml.safe_load(yaml_frontmatter)
        prompt = prompt_file_content[separator_index + 4:]
    else:
        prompt = prompt_file_content
        config = None

    filter_name = config.get("filter", "unfiltered")
    filter = filters.get(filter_name, None)

    if filter is None:
        raise ValueError(f"Filter '{filter_name}' not found")

    return create_analysis_pipeline(ingestion_run, f"{filter_name}:" + sha256(prompt.encode()).hexdigest()[:6], prompt, filter, context, ignore_cached)

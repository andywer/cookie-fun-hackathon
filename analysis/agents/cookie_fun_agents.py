import json
from typing import List

from langsmith import traceable
from openai import AsyncOpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from app.storage.cookie_fun import IngestionRunRecord


def create_analysis_message(
    agents: List[dict], analysis_prompt: str, output_prompt: str, delta_interval_time: str, context: str | None = None
) -> ChatCompletionMessageParam:
    return {
        "role": "user",
        "content": f"""
<purpose>
Analyze the agents stated below based on the provided data.
The data is collected from the Cookie Fun API, all delta values are between {delta_interval_time} ago and now.

{analysis_prompt}
</purpose>

<format_rules>
- Use markdown to format the output.
- Structure the output using headings and subheadings.
</format_rules>

<output>
{output_prompt}
</output>

--

<agents>
{json.dumps(agents, indent=2, ensure_ascii=False)}
</agents>
""".strip() + ("""

<context>
{context}
</context>
""".strip() if context else ""),
    }


class CookieFunAgentsAnalysisAgent:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        analysis_prompt: str,
        output_prompt: str,
        model_kwargs: dict = {},
    ):
        self.client = client
        self.model = model
        self.analysis_prompt = analysis_prompt
        self.output_prompt = output_prompt
        self.model_kwargs = model_kwargs

    @traceable(name="CookieFunAgentsAnalysisAgent.analyze_agents")
    async def analyze_agents(self, agents: List[dict], ingestion_run: IngestionRunRecord, context: str | None = None) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[create_analysis_message(agents, self.analysis_prompt, self.output_prompt, ingestion_run.delta_interval_time, context)],
            **self.model_kwargs,
        )
        message = response.choices[0].message
        output = message.content
        if not hasattr(message, "reasoning_content") and "<think>" in message.content and "</think>" in message.content:
            index = message.content.index("</think>")
            output = message.content[index + len("</think>") :].lstrip()
        return output

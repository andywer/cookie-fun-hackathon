import json
from textwrap import indent
from typing import List

from pydantic import BaseModel
from langchain.chat_models.base import BaseChatModel
from langsmith import traceable
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from app.storage.cookie_fun import HistoricAgentRecord


class TopAgentsOutput(BaseModel):
    """Report the top agents to invest in"""
    agent_ids: List[int]


def create_user_message(records: List[HistoricAgentRecord], analysis: str, output_model: BaseModel) -> ChatCompletionMessageParam:
    return {
        "role": "user",
        "content": f"""
Identify the top agents to invest in based on the provided analysis.
If none of the agents are good investments, return an empty list.

Call the `{output_model.__name__}` function to return the top agents.

---

<agents>
{json.dumps([
    {"id": record.id, "name": record.agent_name}
    for record in records
], indent=2, ensure_ascii=False)}
</agents>

<analysis>
{indent(analysis, "    ")}
</analysis>
""".strip(),
    }


class CookieFunTopAgentsIdentificationAgent:
    def __init__(self, model: BaseChatModel):
        self.model = model

    @traceable(name="CookieFunTopProjectsIdentificationAgent.identify_top_agents")
    async def identify_top_agents(self, records: List[HistoricAgentRecord], analysis: str) -> List[int]:
        response: TopAgentsOutput = await self.model \
            .with_structured_output(TopAgentsOutput) \
            .ainvoke([create_user_message(records, analysis, TopAgentsOutput)])

        return response.agent_ids

from typing import AsyncIterable

from app.storage.cookie_fun import HistoricAgentRecord, IngestionRunRecord

from ._base import Pipeline


class CookieFunSpecificRunPipeline(Pipeline[None, HistoricAgentRecord]):
    def __init__(self, ingestion_run: IngestionRunRecord):
        self.ingestion_run = ingestion_run

    async def run(self, input: None = None, metadata: dict = {}) -> AsyncIterable[HistoricAgentRecord]:
        for agent in self.ingestion_run.agents:
            yield agent

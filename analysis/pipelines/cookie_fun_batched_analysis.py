import asyncio
from typing import AsyncIterable, Awaitable, Callable, List

from langsmith import traceable

from app.storage.cookie_fun import BatchAnalysisRecord, HistoricAgentRecord, open_cookiefun_db

from ._base import Pipeline


Agent = Callable[[List[dict]], Awaitable[str]]

class CookieFunBatchedAnalysisPipeline(Pipeline[HistoricAgentRecord, BatchAnalysisRecord]):
    """
    Pipeline that batchs the project data dicts into batchs of size `batch_size` and
    runs an agent on each batch.
    """

    def __init__(
        self,
        analysis_type: str,
        agent: Agent,
        identify_top_agents: Callable[[List[HistoricAgentRecord], str], List[int]],
        filter_agents: Callable[[HistoricAgentRecord], bool] = lambda _: True,
        ignore_cached: bool = False,
        batch_size: int = 15,
        max_batches: int = 20,
        concurrency: int = 10,
        extra_metadata: dict = {},
    ):
        self.analysis_type = analysis_type
        self.agent = agent
        self.identify_top_agents = identify_top_agents
        self.filter_agents = filter_agents
        self.batch_size = batch_size
        self.concurrency = concurrency
        self.max_batches = max_batches
        self.ignore_cached = ignore_cached
        self.extra_metadata = extra_metadata

    async def run(self, input: AsyncIterable[HistoricAgentRecord], metadata: dict = {}) -> AsyncIterable[BatchAnalysisRecord]:
        current_batch: List[HistoricAgentRecord] = []
        batches: List[List[HistoricAgentRecord]] = []

        metadata = {
            "batch_size": self.batch_size,
            "max_batches": self.max_batches,
            "concurrency": self.concurrency,
            "ignore_cached": self.ignore_cached,
            **self.extra_metadata,
            **metadata,
        }

        async for record in input:
            if not self.filter_agents(record):
                # Skip projects that don't match the filter
                continue

            current_batch.append(record)
            if len(current_batch) >= self.batch_size:
                # Process batch in a separate task context
                batches.append(current_batch)
                current_batch = []

            if len(batches) >= self.max_batches:
                break

        if current_batch:
            batches.append(current_batch)

        # Run batches in parallel, collecting results
        async for record in self._run_batches(batches, metadata):
            yield record

    @traceable(name="CookieFunBatchedAnalysisPipeline._run_batches")
    async def _run_batches(self, batches: List[List[HistoricAgentRecord]], metadata: dict) -> AsyncIterable[BatchAnalysisRecord]:
        for index in range(0, len(batches), self.concurrency):
            print(f"Running batch {index} of {len(batches)}, size {len(batches[index])}")

            batch_chunk = batches[index:index + self.concurrency]
            tasks = []

            async with asyncio.TaskGroup() as tg:
                for batch in batch_chunk:
                    task = tg.create_task(self._run_agent(batch, metadata))
                    tasks.append(task)

            for task in asyncio.as_completed(tasks):
                yield await task

    @traceable(name="CookieFunBatchedAnalysisPipeline._run_agent")
    async def _run_agent(self, batch: List[HistoricAgentRecord], metadata: dict) -> BatchAnalysisRecord:
        if not batch:
            raise ValueError("Batch is empty")

        run_id=batch[0].ingestion_run_id
        input_agent_ids=BatchAnalysisRecord.serialize_agent_ids([record.id for record in batch])

        with open_cookiefun_db() as session:
            record = BatchAnalysisRecord.query(session, analysis_type=self.analysis_type, run_id=run_id, input_agent_ids=input_agent_ids)
            if record and not self.ignore_cached:
                record.eagerly_load_all()
                return record

        analysis = await self.agent([record.data for record in batch])
        top_agent_ids = await self.identify_top_agents(batch, analysis)

        record = BatchAnalysisRecord(
            ingestion_run_id=run_id,
            input_agent_ids=input_agent_ids,
            analysis_type=self.analysis_type,
            analysis=analysis,
            top_agent_ids=top_agent_ids,
            meta=metadata,
        )

        with open_cookiefun_db() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            record.eagerly_load_all()

        return record

from typing import AsyncIterable, Callable, Generic, List, Tuple, TypeVar

from ._base import Pipeline


I = TypeVar("I")
O = TypeVar("O")

class RecursionPipeline(Generic[I, O], Pipeline[I, Tuple[O, List[I]]]):
    def __init__(
        self,
        pipeline: Pipeline[I, O],
        mapper: Callable[[List[O]], List[I]],
        stopper: Callable[[List[O]], bool],
        max_depth: int = 10,
    ):
        self.pipeline = pipeline
        self.mapper = mapper
        self.stopper = stopper
        self.max_depth = max_depth

    async def run(self, input: AsyncIterable[I], metadata: dict = {}) -> AsyncIterable[Tuple[O, List[I]]]:
        async for item in self._run(input, metadata):
            yield item

    async def _run(self, input: AsyncIterable[I], metadata: dict = {}, depth: int = 0) -> AsyncIterable[Tuple[O, List[I]]]:
        if depth >= self.max_depth:
            raise ValueError(f"Max depth of {self.max_depth} reached while recursing {self.pipeline.__class__.__name__}")

        input_list = [item async for item in input]
        results = []

        metadata = {
            **metadata,
            "recursion_depth": depth,
        }

        print(f"Running pipeline {self.pipeline.__class__.__name__} at depth {depth} on {len(input_list)} items before filtering")

        # Need to re-create the now-consumed input
        async def generate_input():
            for item in input_list:
                yield item
        input = generate_input()

        async for item in self.pipeline.run(input, metadata):
            results.append(item)
            yield (item, input_list)

        if self.stopper(results):
            return

        sub_input_list = self.mapper(results)

        # Need to create an async iterable from the list
        async def generate_sub_input():
            for item in sub_input_list:
                yield item
        sub_input = generate_sub_input()

        async for item in self._run(sub_input, metadata, depth + 1):
            yield (item, sub_input_list)

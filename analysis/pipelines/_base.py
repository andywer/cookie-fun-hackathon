from abc import ABC, abstractmethod
from typing import AsyncIterable, Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")
T = TypeVar("T")

class Pipeline(Generic[I, O], ABC):
    @abstractmethod
    async def run(self, input: AsyncIterable[I], metadata: dict = {}) -> AsyncIterable[O]:
        """Run the pipeline. Should normally be a prefect flow."""
        pass

    def __ror__(self, first_pipeline: 'Pipeline[T, I]') -> 'Pipeline[T, O]':
        class ComposedPipeline(Pipeline[T, O]):
            def __init__(self, first_pipeline: Pipeline[T, I], second_pipeline: Pipeline[I, O]):
                self.first_pipeline = first_pipeline
                self.second_pipeline = second_pipeline

            async def run(self, input: AsyncIterable[T], metadata: dict = {}) -> AsyncIterable[O]:
                stream = self.first_pipeline.run(input, metadata)
                async for item in self.second_pipeline.run(stream, metadata):
                    yield item

        return ComposedPipeline(first_pipeline, self)

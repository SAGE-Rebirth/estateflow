import asyncio
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.services.hf import hf_client


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class HuggingFaceEmbedder:
    """Sentence embeddings from the HF Inference API (feature-extraction pipeline)."""

    CONCURRENCY = 8

    def __init__(self) -> None:
        s = get_settings()
        self._model = s.hf_embedding_model
        self._client = hf_client(s.hf_embedding_provider)
        self._sem = asyncio.Semaphore(self.CONCURRENCY)

    async def _one(self, text: str) -> list[float]:
        async with self._sem:
            vec = await self._client.feature_extraction(text, model=self._model, normalize=True)
        arr = vec.tolist() if hasattr(vec, "tolist") else vec
        # Some models return [1, dim] (or token-level [1, n, dim]); reduce to one vector.
        while isinstance(arr[0], list):
            arr = arr[0] if len(arr) == 1 else [sum(c) / len(arr) for c in zip(*arr, strict=True)]
        return [float(x) for x in arr]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self._one(t) for t in texts)))

    async def embed_query(self, text: str) -> list[float]:
        return await self._one(text)


@lru_cache
def get_embedder() -> Embedder:
    return HuggingFaceEmbedder()

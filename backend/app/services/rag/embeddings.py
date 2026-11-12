import math
from functools import lru_cache
from typing import Any, Protocol

from google.genai import types

from app.core.config import get_settings
from app.services.gemini import gemini_client


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class GeminiEmbedder:
    """Text embeddings from the Gemini API, truncated to `embedding_dim`."""

    MAX_BATCH = 100  # API limit per request

    def __init__(self, client: Any = None) -> None:
        s = get_settings()
        self._model = s.gemini_embedding_model
        self._dim = s.embedding_dim
        self._client = client or gemini_client()

    async def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.MAX_BATCH):
            batch = texts[i : i + self.MAX_BATCH]
            response = await self._client.aio.models.embed_content(
                model=self._model,
                # One Content per text: a bare list of strings is embedded as ONE input.
                contents=[types.Content(parts=[types.Part(text=t)]) for t in batch],
                config=types.EmbedContentConfig(output_dimensionality=self._dim, task_type=task),
            )
            vectors = [list(e.values or []) for e in response.embeddings or []]
            if len(vectors) != len(batch) or any(len(v) != self._dim for v in vectors):
                raise RuntimeError(
                    f"Embedding API returned {len(vectors)} vectors for {len(batch)} texts"
                )
            # Truncated (Matryoshka) vectors are not unit-length on every model.
            out += [_normalize(v) for v in vectors]
        return out

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


@lru_cache
def get_embedder() -> Embedder:
    return GeminiEmbedder()

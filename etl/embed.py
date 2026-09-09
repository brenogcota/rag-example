"""
Geração de embeddings: modelo local via sentence-transformers.
Roda na sua máquina (CPU é suficiente para esse modelo), sem precisar
de API key nem custo por chamada. O modelo é baixado uma vez e cacheado.
"""
import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    model_name = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Gera embeddings normalizados (norma L2 = 1) para uma lista de textos."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()

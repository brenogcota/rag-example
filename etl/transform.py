"""
Transformação (T do ETL): limpeza de texto e fragmentação (chunking) com
sobreposição, para não cortar uma ideia importante no meio.
"""
import re


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, max_words: int = 180, overlap_words: int = 30) -> list[str]:
    """
    Divide o texto em fragmentos de até `max_words` palavras, com
    `overlap_words` palavras de sobreposição entre fragmentos consecutivos.
    """
    words = clean_text(text).split(" ")
    if not words or words == [""]:
        return []

    chunks = []
    step = max(max_words - overlap_words, 1)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + max_words])
        if len(chunk) > 50:  # descarta fragmentos residuais irrelevantes
            chunks.append(chunk)
        if i + max_words >= len(words):
            break
    return chunks

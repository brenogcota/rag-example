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


def chunk_records(
    records: list[str],
    header: str = "",
    max_words: int = 180,
    overlap_rows: int = 1,
) -> list[str]:
    """
    Fragmenta dados tabulares agrupando linhas inteiras — nunca no meio de um
    registro, como `chunk_text` faria.

    Cada chunk repete o `header` (nome da tabela + colunas) porque o chunk é
    recuperado sozinho na busca: sem ele, "valor: 1200" não diz de que tabela
    veio. `overlap_rows` repete as últimas linhas no chunk seguinte, com o
    mesmo propósito da sobreposição de palavras em `chunk_text`.
    """
    rows = [clean_text(r) for r in records]
    rows = [r for r in rows if r]
    if not rows:
        return []

    header = clean_text(header)
    # O cabeçalho consome parte do orçamento de palavras de cada chunk.
    budget = max(max_words - len(header.split(" ")) if header else max_words, 40)

    chunks = []
    start = 0
    while start < len(rows):
        taken, words, end = [], 0, start
        while end < len(rows):
            row_words = len(rows[end].split(" "))
            if taken and words + row_words > budget:
                break
            taken.append(rows[end])
            words += row_words
            end += 1

        body = "\n".join(taken)
        chunks.append(f"{header}\n{body}" if header else body)

        if end >= len(rows):
            break
        # Recua `overlap_rows` linhas, garantindo avanço para não repetir chunk.
        start = max(end - overlap_rows, start + 1)

    return chunks

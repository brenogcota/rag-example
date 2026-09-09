"""
Recuperação: busca por similaridade vetorial no pgvector.

O operador `<=>` do pgvector calcula distância de cosseno (requer o índice
`vector_cosine_ops` criado no schema). similaridade = 1 - distância.
"""
from db import get_ragdb_connection
from etl.embed import embed_texts


def search(query: str, top_k: int = 4) -> list[dict]:
    query_embedding = embed_texts([query])[0]

    conn = get_ragdb_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.content, d.source_url, d.title,
                       1 - (c.embedding <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            "chunk_id": r[0],
            "content": r[1],
            "source_url": r[2],
            "title": r[3],
            "similarity": float(r[4]),
        }
        for r in rows
    ]

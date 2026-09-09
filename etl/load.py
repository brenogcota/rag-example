"""
Carga (L do ETL): salva documentos e chunks (com embeddings) no ragdb.
"""
from db import get_ragdb_connection


def load_document(url: str, title: str) -> int:
    """Insere (ou atualiza) um documento pela URL e retorna seu id."""
    conn = get_ragdb_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (source_url, title)
                VALUES (%s, %s)
                ON CONFLICT (source_url) DO UPDATE SET title = EXCLUDED.title
                RETURNING id
                """,
                (url, title),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def load_chunks(document_id: int, chunks: list[str], embeddings: list[list[float]]):
    """Substitui os chunks de um documento (idempotente: refaz do zero)."""
    conn = get_ragdb_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
            for idx, (content, embedding) in enumerate(zip(chunks, embeddings)):
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (document_id, idx, content, embedding),
                )
    finally:
        conn.close()

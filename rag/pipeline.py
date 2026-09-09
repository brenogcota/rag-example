"""
Pipeline RAG completo: recupera contexto no banco vetorial, gera resposta
via Groq, e persiste a conversa no banco de usuários (histórico + rastreio
de quais chunks embasaram cada resposta).
"""
from rag.retriever import search
from rag.generator import generate
from db import get_usersdb_connection


def get_or_create_user(username: str) -> int:
    conn = get_usersdb_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (username)
                VALUES (%s)
                ON CONFLICT (username) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
                """,
                (username,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def create_session(user_id: int) -> int:
    conn = get_usersdb_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (user_id) VALUES (%s) RETURNING id",
                (user_id,),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


def save_message(session_id: int, role: str, content: str, chunk_ids: list[int] | None = None):
    conn = get_usersdb_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, retrieved_chunk_ids)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, role, content, chunk_ids),
            )
    finally:
        conn.close()


def ask(username: str, question: str, session_id: int | None = None, top_k: int = 4) -> dict:
    user_id = get_or_create_user(username)
    if session_id is None:
        session_id = create_session(user_id)

    retrieved = search(question, top_k=top_k)

    if retrieved:
        answer = generate(question, retrieved)
    else:
        answer = "Não encontrei nenhum conteúdo relevante na base de conhecimento para responder isso."

    chunk_ids = [r["chunk_id"] for r in retrieved]
    save_message(session_id, "user", question, chunk_ids)
    save_message(session_id, "assistant", answer, chunk_ids)

    return {
        "session_id": session_id,
        "question": question,
        "retrieved": retrieved,
        "answer": answer,
    }

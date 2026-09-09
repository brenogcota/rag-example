"""
Conexões com os dois bancos Postgres do sistema:
  - ragdb   -> banco vetorial (documentos, chunks, embeddings)
  - usersdb -> banco de usuários (contas, sessões, mensagens)
"""
import os
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv

load_dotenv()


def get_ragdb_connection():
    """Conexão com o banco vetorial, com suporte a tipo VECTOR registrado."""
    url = os.environ.get("RAGDB_URL")
    if not url:
        raise RuntimeError("RAGDB_URL não definida. Copie .env.example para .env e configure.")
    conn = psycopg2.connect(url)
    register_vector(conn)
    return conn


def get_usersdb_connection():
    """Conexão com o banco de usuários."""
    url = os.environ.get("USERSDB_URL")
    if not url:
        raise RuntimeError("USERSDB_URL não definida. Copie .env.example para .env e configure.")
    return psycopg2.connect(url)

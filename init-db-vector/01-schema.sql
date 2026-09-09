-- Habilita a extensão pgvector neste banco
CREATE EXTENSION IF NOT EXISTS vector;

-- Um documento = uma página/fonte extraída da web
CREATE TABLE IF NOT EXISTS documents (
    id          SERIAL PRIMARY KEY,
    source_url  TEXT NOT NULL UNIQUE,
    title       TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Um chunk = um fragmento de texto de um documento, com seu embedding
-- Dimensão 384 = saída do modelo 'all-MiniLM-L6-v2' (sentence-transformers)
CREATE TABLE IF NOT EXISTS chunks (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    embedding    VECTOR(384),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice HNSW para busca aproximada por vizinhos mais próximos (cosine distance)
-- Requer pgvector >= 0.5.0 (já incluído na imagem pgvector/pgvector:pg16)
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON chunks (document_id);

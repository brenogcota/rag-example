# RAG de Produção — Postgres + pgvector + ETL Web + Groq

Sistema RAG completo e funcional: dois bancos Postgres via Docker Compose
(um vetorial com pgvector, outro de usuários), um ETL real que baixa
páginas da web, e geração via API real da Groq.

> ✅ Todo o SQL e a lógica de banco deste projeto foram testados contra uma
> instância real de Postgres 16 + pgvector 0.6 antes da entrega.

---

## Arquitetura

```
                    ┌─────────────────────────────────────────┐
                    │              docker-compose                │
                    │                                             │
                    │  ┌──────────────┐      ┌──────────────┐   │
                    │  │  db-vector    │      │  db-users     │   │
                    │  │  (pgvector)   │      │  (postgres)   │   │
                    │  │  porta 5433   │      │  porta 5434   │   │
                    │  └──────┬───────┘      └──────┬────────┘   │
                    └─────────┼──────────────────────┼───────────┘
                              │                        │
        ┌─────────────────────┼────────────────────────┼────────────┐
        │   ETL (etl/)          │                        │            │
        │  extract -> transform  │                        │            │
        │  -> embed -> load ─────┘                        │            │
        └───────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼──────────────────────────────────────┐
        │   RAG (rag/)          │                                      │
        │  retriever (busca) ────┘                                     │
        │  generator (Groq API) ──────────> resposta                   │
        │  pipeline (orquestra + salva no db-users) ────────────────────┘
        └───────────────────────────────────────────────────────────┘
```

**Por que dois bancos separados?** Em produção, dados de conhecimento
(RAG) e dados de conta/uso (usuários) costumam ter ciclos de vida, backup
e políticas de acesso diferentes — vale a pena separá-los desde cedo.

---

## Pré-requisitos

- Docker + Docker Compose
- Python 3.10+
- Uma conta gratuita na [Groq Console](https://console.groq.com/keys) para gerar sua `GROQ_API_KEY`

---

## Passo a passo

### 1. Suba os bancos de dados

```bash
docker compose up -d
```

Isso sobe:
- `db-vector` (Postgres + pgvector) na porta **5433**, com o schema de
  `documents`/`chunks` já criado automaticamente via `init-db-vector/01-schema.sql`
- `db-users` (Postgres) na porta **5434**, com o schema de
  `users`/`chat_sessions`/`chat_messages` via `init-db-users/01-schema.sql`
- `adminer` (UI web) em `http://localhost:8080` para inspecionar os bancos visualmente

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` e coloque sua `GROQ_API_KEY` real.

### 3. Instale as dependências Python

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> A primeira execução baixa o modelo de embedding local (`all-MiniLM-L6-v2`,
> ~90MB) automaticamente via `sentence-transformers`. Depois disso ele fica
> em cache local — não é chamado de novo pela rede.

### 4. Rode o ETL com páginas web reais

```bash
python main.py etl \
  "https://en.wikipedia.org/wiki/Retrieval-augmented_generation" \
  "https://en.wikipedia.org/wiki/Large_language_model"
```

Isso executa o pipeline completo:
1. **Extract** (`etl/extract.py`) — baixa o HTML e extrai o texto dos parágrafos
2. **Transform** (`etl/transform.py`) — limpa e fragmenta em chunks com overlap
3. **Embed** (`etl/embed.py`) — gera embeddings locais (384 dimensões)
4. **Load** (`etl/load.py`) — salva tudo em `db-vector`

### 5. Converse com o sistema (RAG real + LLM real)

```bash
python main.py chat joao.dev "O que é retrieval-augmented generation?"
```

Isso executa:
1. Busca vetorial no `db-vector` (`rag/retriever.py`, operador `<=>` do pgvector)
2. Geração da resposta com o modelo da Groq (`rag/generator.py`)
3. Persistência da pergunta + resposta em `db-users` (`rag/pipeline.py`), com
   rastreamento de quais `chunk_ids` embasaram a resposta

---

## Estrutura do projeto

```
.
├── docker-compose.yml          # dois bancos Postgres + Adminer
├── init-db-vector/01-schema.sql   # documents, chunks, embedding vector(384), índice HNSW
├── init-db-users/01-schema.sql    # users, chat_sessions, chat_messages
├── .env.example
├── requirements.txt
├── db.py                       # conexões com os dois bancos
├── etl/
│   ├── extract.py              # baixa páginas web reais (requests + BeautifulSoup)
│   ├── transform.py            # limpeza + chunking com overlap
│   ├── embed.py                # embeddings locais (sentence-transformers)
│   ├── load.py                 # grava em db-vector
│   └── run_etl.py              # orquestra o ETL completo
├── rag/
│   ├── retriever.py            # busca por similaridade de cosseno no pgvector
│   ├── generator.py            # chamada real à API da Groq
│   └── pipeline.py             # retrieve -> generate -> salva no db-users
└── main.py                     # CLI: `etl` e `chat`
```

---

## Detalhes técnicos que valem a pena entender

- **Índice HNSW** (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`):
  estrutura de grafo que permite busca aproximada por vizinhos mais
  próximos em tempo sub-linear — essencial quando você tem milhões de
  chunks, não apenas dezenas.
- **Operador `<=>`**: distância de cosseno nativa do pgvector. A
  consulta em `rag/retriever.py` ordena por essa distância e converte
  para "similaridade" (`1 - distância`) só para exibição.
- **Idempotência do ETL**: rodar o ETL de novo para a mesma URL
  atualiza o documento (`ON CONFLICT ... DO UPDATE`) e refaz os chunks
  do zero — seguro para reprocessar conteúdo que mudou.
- **Rastreabilidade**: cada mensagem salva em `chat_messages` guarda
  `retrieved_chunk_ids` — dá para auditar exatamente qual trecho da
  base gerou qual resposta, essencial para debugar alucinações.

---

## Próximos passos sugeridos (para produção de verdade)

| Tema | O que evoluir |
|---|---|
| Segurança | Hash de senha / OAuth para usuários; secrets fora do `.env` (Vault, AWS Secrets Manager) |
| Qualidade de recuperação | Busca híbrida (vetor + BM25) e re-ranking |
| Observabilidade | Logar latência de cada etapa (retrieval, geração), taxa de "sem contexto relevante" |
| Escala do ETL | Fila de jobs (ex.: Celery/RQ) em vez de execução síncrona por URL |
| Extração web | Trocar heurística de `<p>` por `trafilatura`/`readability-lxml` para páginas complexas |
| Avaliação | Testes automáticos de precisão de retrieval e fidelidade da resposta (faithfulness) |

Esses pontos conectam diretamente com o **Módulo 1** do curso (CI/CD,
observabilidade, monitoramento) — um sistema RAG em produção é, antes de
tudo, um sistema de software em produção.

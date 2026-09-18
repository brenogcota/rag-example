# RAG de Produção — Postgres + pgvector + ETL Web + Groq

Sistema RAG completo e funcional: dois bancos Postgres via Docker Compose
(um vetorial com pgvector, outro de usuários), um ETL real que baixa
páginas da web, geração via API real da Groq e um chat web com resposta
em streaming.

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
        │  web + planilhas       │                        │            │
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
                              │
        ┌─────────────────────┼──────────────────────────────────────┐
        │   Web (web/)          │                                      │
        │  app.py (FastAPI) ─── POST /stream ──> SSE token a token     │
        │  static/index.html ── widget de chat no navegador            │
        └───────────────────────────────────────────────────────────┘
```

**Por que dois bancos separados?** Em produção, dados de conhecimento
(RAG) e dados de conta/uso (usuários) costumam ter ciclos de vida, backup
e políticas de acesso diferentes — vale a pena separá-los desde cedo.

---

## Pré-requisitos

- Docker + Docker Compose
- Uma conta gratuita na [Groq Console](https://console.groq.com/keys) para gerar sua `GROQ_API_KEY`
- Python 3.10+ **apenas** se você quiser rodar fora do Docker (ver [Passo a passo](#passo-a-passo));
  pelo caminho Docker a versão do Python e as dependências vêm prontas na imagem

---

## Rodando tudo com Docker (qualquer máquina)

O `Dockerfile` cuida da versão do Python (3.12), do virtualenv e do
`requirements.txt` — a única coisa que a máquina precisa ter é Docker.
O modelo de embedding também já vem baixado dentro da imagem, então o
primeiro ETL não espera download.

```bash
cp .env.example .env        # preencha a GROQ_API_KEY
docker compose up --build   # bancos + aplicação
```

Chat web em <http://localhost:8000>, Adminer em <http://localhost:8080>.

O `ENTRYPOINT` da imagem é o próprio `main.py`, então os comandos da CLI
funcionam do mesmo jeito, em containers descartáveis:

```bash
# ETL de páginas reais
docker compose run --rm app etl https://pt.wikipedia.org/wiki/Aprendizado_de_máquina

# ETL de planilhas — coloque os arquivos em ./dados (montado como /app/dados)
docker compose run --rm app etl dados/vendas.xlsx dados/clientes.csv
docker compose run --rm app etl dados          # a pasta inteira de uma vez

# Pergunta via CLI
docker compose run --rm app chat breno "o que é aprendizado de máquina?"

# Logs da API e parada do ambiente
docker compose logs -f app
docker compose down          # acrescente -v para apagar também os dados
```

Detalhes que valem saber:

- **`RAGDB_URL` / `USERSDB_URL`** são sobrescritos no `docker-compose.yml` para
  `db-vector:5432` e `db-users:5432` (nomes de serviço da rede do Compose). Os
  valores `localhost:5433/5434` do seu `.env` continuam valendo para execução
  fora do Docker — não precisa manter dois arquivos.
- **`torch` é instalado na variante CPU-only**, o que evita ~2,5 GB de
  bibliotecas CUDA que não seriam usadas.
- **Build em dois estágios**: compilador e cache de pip ficam no estágio
  `builder`; a imagem final leva só o venv, o cache do modelo e o código.
- **O container roda como usuário sem privilégios** (`app`, uid 1000) e expõe um
  `HEALTHCHECK` em `/health` — o `depends_on` do Compose só sobe a aplicação
  depois que os dois Postgres estão saudáveis.
- **`.env` nunca entra na imagem** (está no `.dockerignore`); os segredos chegam
  em tempo de execução via `env_file`.
- **Cache dos modelos** fica no volume `hf_cache`, então trocar o
  `EMBEDDING_MODEL` não exige rebuild.

> As seções abaixo descrevem a execução local com virtualenv próprio, útil para
> desenvolver com hot reload ou depurar fora do container.

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

### 4. Rode o ETL com páginas web e planilhas reais

```bash
python main.py etl \
  "https://en.wikipedia.org/wiki/Retrieval-augmented_generation" \
  "https://en.wikipedia.org/wiki/Large_language_model"

# planilhas: arquivo, vários arquivos, pasta inteira ou URL
python main.py etl dados/vendas.xlsx dados/clientes.csv dados/legado.xls
python main.py etl dados
python main.py etl "https://exemplo.com/export/relatorio.csv"
```

Isso executa o pipeline completo:
1. **Extract** (`etl/extract.py`) — baixa o HTML e extrai o texto dos parágrafos,
   ou lê a planilha (`.csv`, `.tsv`, `.xlsx`, `.xlsm`, `.xls`) com pandas
2. **Transform** (`etl/transform.py`) — limpa e fragmenta em chunks com overlap
3. **Embed** (`etl/embed.py`) — gera embeddings locais (384 dimensões)
4. **Load** (`etl/load.py`) — salva tudo em `db-vector`

#### Como uma planilha vira texto buscável

Uma tabela não pode ir crua para o embedding: `Salvador,BA,1200` sozinho não
tem significado. Por isso cada linha é serializada com o nome da coluna junto
do valor, e cada chunk repete o cabeçalho da tabela:

```
Tabela: vendas.xlsx — Vendas | Colunas: produto, categoria, cep, preco
produto: Produto 1 | categoria: Eletrônico | cep: 01310-100 | preco: 13.50
produto: Produto 2 | categoria: Livro      | cep: 40010-000 | preco: 27.00
```

Decisões que importam nessa etapa:

- **Uma aba = um documento.** A `source_url` vira `caminho.xlsx#Vendas`, então a
  resposta do chat consegue citar a aba exata de onde veio o número.
- **Chunk por linha, nunca no meio dela** (`chunk_records` em `transform.py`):
  agrupa registros inteiros até o orçamento de palavras, com sobreposição de
  uma linha entre chunks vizinhos.
- **Tudo é lido como texto** (`dtype=str`): CEP, CPF e código de produto não
  viram float nem perdem o zero à esquerda no caminho.
- **Células vazias são omitidas** do registro, em vez de virar ruído `coluna: nan`.
- **CSV**: separador (`,` `;` `\t`) detectado automaticamente e fallback de
  encoding utf-8 -> latin-1, que cobre os exports do Excel em português.
- **Teto de 50 mil linhas por aba** (`MAX_ROWS` em `extract.py`), para um
  arquivo gigante não estourar memória nem a geração de embeddings.

### 5. Converse com o sistema (RAG real + LLM real)

```bash
python main.py chat joao.dev "O que é retrieval-augmented generation?"
```

Isso executa:
1. Busca vetorial no `db-vector` (`rag/retriever.py`, operador `<=>` do pgvector)
2. Geração da resposta com o modelo da Groq (`rag/generator.py`)
3. Persistência da pergunta + resposta em `db-users` (`rag/pipeline.py`), com
   rastreamento de quais `chunk_ids` embasaram a resposta

### 6. Abra o chat web (resposta em streaming)

```bash
python main.py serve          # ou: python main.py serve 8001
```

Abra `http://localhost:8000`. O widget de chat fica no canto inferior
direito: digite a pergunta, e a resposta aparece **token a token**,
com as fontes recuperadas exibidas antes mesmo de a geração começar.

**Como o streaming funciona:**

```
navegador ──POST /stream {"message": "..."}──> FastAPI
                                                  │
                                    rag.pipeline.ask_stream()
                                                  │
navegador <──── text/event-stream ────────────────┘
```

O endpoint devolve Server-Sent Events, um frame por evento do pipeline:

| Evento | Quando | Payload |
|---|---|---|
| `session` | logo no início | `{"session_id": 12}` — o front guarda para continuar a mesma conversa |
| `sources` | após a busca vetorial, antes da geração | lista de chunks com `title`, `source_url`, `similarity` |
| `token` | conforme a Groq produz | `{"text": "pedaço"}` |
| `done` | ao final | `{"session_id": 12, "answer": "resposta completa"}` |
| `error` | falha no meio do stream | `{"message": "..."}` |

Testando o endpoint direto no terminal:

```bash
curl -N -X POST http://localhost:8000/stream \
  -H 'Content-Type: application/json' \
  -d '{"message": "O que é retrieval-augmented generation?"}'
```

Há também `GET /stream?message=...`, compatível com a API `EventSource`
nativa do navegador. O widget usa o `POST` + `fetch`/`ReadableStream`
porque `EventSource` só faz `GET` — mandar a pergunta no corpo evita
limite de tamanho de URL e vaza menos conteúdo em logs de acesso.

> A conversa só é gravada em `chat_messages` quando o stream termina —
> aí a resposta completa já está montada, e a rastreabilidade por
> `retrieved_chunk_ids` continua igual à do modo CLI.

---

## Estrutura do projeto

```
.
├── Dockerfile                  # imagem da aplicação (Python + venv + deps + modelo)
├── .dockerignore
├── docker-compose.yml          # dois bancos Postgres + Adminer + a aplicação
├── dados/                      # planilhas locais p/ ingestão (montada em /app/dados)
├── init-db-vector/01-schema.sql   # documents, chunks, embedding vector(384), índice HNSW
├── init-db-users/01-schema.sql    # users, chat_sessions, chat_messages
├── .env.example
├── requirements.txt
├── db.py                       # conexões com os dois bancos
├── etl/
│   ├── extract.py              # páginas web (requests + BeautifulSoup) e planilhas (pandas)
│   ├── transform.py            # limpeza + chunking com overlap (texto e tabelas)
│   ├── embed.py                # embeddings locais (sentence-transformers)
│   ├── load.py                 # grava em db-vector
│   └── run_etl.py              # orquestra o ETL completo
├── rag/
│   ├── retriever.py            # busca por similaridade de cosseno no pgvector
│   ├── generator.py            # `generate` (bloco) e `generate_stream` (streaming)
│   └── pipeline.py             # `ask` (bloco) e `ask_stream` (eventos p/ a web)
├── web/
│   ├── app.py                  # FastAPI: GET /, POST|GET /stream (SSE), GET /health
│   └── static/index.html       # widget de chat, sem dependência de front-end
└── main.py                     # CLI: `etl` (URLs e planilhas), `chat` e `serve`
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
- **Streaming ponta a ponta**: a Groq entrega a resposta em pedaços
  (`stream=True`), `ask_stream` repassa cada pedaço como evento, e o
  FastAPI o escreve na conexão aberta. Nada fica bufferizado no meio do
  caminho — por isso o header `X-Accel-Buffering: no`, que impede o nginx
  (se houver um na frente) de segurar os frames até o fim.
- **Rastreabilidade**: cada mensagem salva em `chat_messages` guarda
  `retrieved_chunk_ids` — dá para auditar exatamente qual trecho da
  base gerou qual resposta, essencial para debugar alucinações.

---

## Próximos passos sugeridos (para produção de verdade)

| Tema | O que evoluir |
|---|---|
| Segurança | Hash de senha / OAuth para usuários; secrets fora do `.env` (Vault, AWS Secrets Manager); CORS e rate limit no `/stream` |
| Qualidade de recuperação | Busca híbrida (vetor + BM25) e re-ranking |
| Observabilidade | Logar latência de cada etapa (retrieval, geração), taxa de "sem contexto relevante" |
| Escala do ETL | Fila de jobs (ex.: Celery/RQ) em vez de execução síncrona por URL |
| Extração web | Trocar heurística de `<p>` por `trafilatura`/`readability-lxml` para páginas complexas |
| Avaliação | Testes automáticos de precisão de retrieval e fidelidade da resposta (faithfulness) |

Esses pontos conectam diretamente com o **Módulo 1** do curso (CI/CD,
observabilidade, monitoramento) — um sistema RAG em produção é, antes de
tudo, um sistema de software em produção.

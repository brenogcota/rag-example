# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Imagem da aplicação RAG (ETL + chat CLI + API web).
#
# Tudo que a máquina precisa é Docker: a versão do Python, o venv e as
# dependências do requirements.txt são resolvidos aqui dentro.
#
#   docker compose up --build            -> bancos + app em http://localhost:8000
#   docker compose run --rm app etl URL  -> roda o ETL
#   docker compose run --rm app chat breno "pergunta"
# ---------------------------------------------------------------------------

ARG PYTHON_VERSION=3.12

# =============================== build =====================================
# Monta o virtualenv em /opt/venv e baixa o modelo de embedding, para que o
# estágio final não precise de compilador, cache de pip nem rede.
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# build-essential só existe neste estágio: cobre pacotes sem wheel pronto.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

# torch CPU-only antes do resto: o wheel padrão do PyPI vem com CUDA e
# levaria ~2,5 GB de bibliotecas de GPU que não seriam usadas.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.txt .
RUN pip install -r requirements.txt

# Pré-baixa o modelo de embedding para a imagem: o primeiro `etl`/`chat`
# já sobe sem esperar download e o container roda offline.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# =============================== runtime ===================================
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/hf-cache \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# curl serve ao HEALTHCHECK abaixo.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /opt/hf-cache /opt/hf-cache

WORKDIR /app
COPY --chown=app:app . .

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# `docker run imagem etl <url>` / `chat <user> "<pergunta>"` / `serve`
ENTRYPOINT ["python", "main.py"]
CMD ["serve", "8000"]

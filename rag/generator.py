"""
Geração: chamada real à API da Groq (inferência muito rápida sobre modelos
open-weight como Llama). Requer GROQ_API_KEY no .env.
"""
import math
import os

from groq import Groq

_client: Groq | None = None

# A Groq cobra `prompt + max_tokens` contra o limite de tokens por minuto (TPM)
# da conta. Se a soma passar do teto, a resposta é um 413
# ("request too large for model ... tpm limit 8000, requested 8164") — e
# retentar não adianta: o único caminho é encolher o contexto enviado.
TPM_LIMIT = int(os.environ.get("GROQ_TPM_LIMIT", "8000"))
MAX_OUTPUT_TOKENS = int(os.environ.get("GROQ_MAX_OUTPUT_TOKENS", "600"))
# Folga para a diferença entre a estimativa local e o tokenizador real da Groq.
SAFETY_TOKENS = 256
# Abaixo disso um trecho truncado não carrega informação útil: melhor descartar.
MIN_CHUNK_TOKENS = 64

SYSTEM_PROMPT = "Você é um assistente técnico preciso e objetivo."

_TEMPLATE = """Responda à pergunta do usuário usando APENAS as informações do CONTEXTO abaixo.
Cite a fonte entre colchetes (ex.: [Fonte 1]) sempre que usar uma informação dela.
Se a resposta não estiver no contexto, diga claramente que não sabe — não invente.

CONTEXTO:
{context}

PERGUNTA: {query}

RESPOSTA:"""


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY não definida. Copie .env.example para .env e "
                "adicione sua key de https://console.groq.com/keys"
            )
        _client = Groq(api_key=api_key)
    return _client


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora: ~3 caracteres por token em português acentuado."""
    return math.ceil(len(text) / 3)


def context_budget(query: str) -> int:
    """Quantos tokens sobram para o CONTEXTO depois de instruções, pergunta e resposta."""
    fixed = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(_TEMPLATE.format(context="", query=query))
    return TPM_LIMIT - MAX_OUTPUT_TOKENS - SAFETY_TOKENS - fixed


def fit_context(retrieved: list[dict], budget: int) -> str:
    """
    Monta o bloco de CONTEXTO cabendo em `budget` tokens.

    Percorre os trechos na ordem em que o retriever os devolveu (mais similares
    primeiro), então o que sobra de fora é sempre o menos relevante. O trecho
    que cabe só pela metade entra truncado e marcado, em vez de ser descartado.
    """
    blocks: list[str] = []
    used = 0

    for i, r in enumerate(retrieved):
        head = f"[Fonte {i + 1}: {r['title']} ({r['source_url']})]\n"
        separator = estimate_tokens("\n\n") if blocks else 0
        room = budget - used - separator - estimate_tokens(head)
        if room < MIN_CHUNK_TOKENS:
            break

        content = r["content"]
        if estimate_tokens(content) > room:
            content = content[: room * 3].rstrip() + " […trecho truncado]"

        block = head + content
        blocks.append(block)
        used += separator + estimate_tokens(block)

    return "\n\n".join(blocks)


def build_prompt(query: str, retrieved: list[dict]) -> str:
    budget = context_budget(query)
    if budget < MIN_CHUNK_TOKENS:
        raise RuntimeError(
            f"A pergunta sozinha já consome o orçamento de {TPM_LIMIT} tokens/minuto "
            f"da conta Groq (sobraram {budget} tokens para o contexto). "
            "Encurte a pergunta ou aumente GROQ_TPM_LIMIT se seu plano permitir."
        )
    return _TEMPLATE.format(context=fit_context(retrieved, budget), query=query)


def _messages(query: str, retrieved: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(query, retrieved)},
    ]


def generate(query: str, retrieved: list[dict]) -> str:
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

    response = client.chat.completions.create(
        model=model,
        messages=_messages(query, retrieved),
        temperature=0.2,
        max_tokens=MAX_OUTPUT_TOKENS,
    )
    return response.choices[0].message.content


def generate_stream(query: str, retrieved: list[dict]):
    """
    Mesma geração de `generate`, mas em streaming: devolve os pedaços de
    texto conforme a Groq os produz, em vez de esperar a resposta completa.
    """
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

    stream = client.chat.completions.create(
        model=model,
        messages=_messages(query, retrieved),
        temperature=0.2,
        max_tokens=MAX_OUTPUT_TOKENS,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

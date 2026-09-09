"""
Geração: chamada real à API da Groq (inferência muito rápida sobre modelos
open-weight como Llama). Requer GROQ_API_KEY no .env.
"""
import os

from groq import Groq

_client: Groq | None = None


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


def build_prompt(query: str, retrieved: list[dict]) -> str:
    context = "\n\n".join(
        f"[Fonte {i + 1}: {r['title']} ({r['source_url']})]\n{r['content']}"
        for i, r in enumerate(retrieved)
    )
    return f"""Responda à pergunta do usuário usando APENAS as informações do CONTEXTO abaixo.
Cite a fonte entre colchetes (ex.: [Fonte 1]) sempre que usar uma informação dela.
Se a resposta não estiver no contexto, diga claramente que não sabe — não invente.

CONTEXTO:
{context}

PERGUNTA: {query}

RESPOSTA:"""


def generate(query: str, retrieved: list[dict]) -> str:
    prompt = build_prompt(query, retrieved)
    client = get_client()
    model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Você é um assistente técnico preciso e objetivo."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return response.choices[0].message.content

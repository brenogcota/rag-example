"""
API web do sistema RAG.

Expõe:
  GET  /          -> widget de chat (web/static/index.html)
  POST /stream    -> resposta em streaming (SSE) para uma mensagem
  GET  /stream    -> mesma coisa, via querystring (compatível com EventSource)
  GET  /health    -> checagem simples

O streaming usa Server-Sent Events: cada evento do `ask_stream` vira um
frame `event: <tipo>\\ndata: <json>\\n\\n`. Assim o front consegue mostrar a
resposta token a token, e as fontes antes mesmo de a geração começar.
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag.pipeline import ask_stream

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="RAG de Produção", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    username: str = "web.user"
    session_id: int | None = None
    top_k: int = 4


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_source(req: ChatRequest):
    """Traduz os eventos do pipeline para frames SSE."""
    try:
        for event in ask_stream(
            username=req.username,
            question=req.message,
            session_id=req.session_id,
            top_k=req.top_k,
        ):
            yield _sse(event.pop("type"), event)
    except Exception as exc:  # erro no meio do stream: o HTTP 200 já foi enviado
        yield _sse("error", {"message": str(exc)})


def _stream_response(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_source(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # evita buffering se houver nginx na frente
        },
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")}


@app.post("/stream")
def stream_post(req: ChatRequest):
    return _stream_response(req)


@app.get("/stream")
def stream_get(
    message: str,
    username: str = "web.user",
    session_id: int | None = None,
    top_k: int = 4,
):
    return _stream_response(
        ChatRequest(message=message, username=username, session_id=session_id, top_k=top_k)
    )

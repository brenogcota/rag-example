"""
Orquestra o pipeline ETL completo: Extração -> Transformação -> Embedding -> Carga.

Uso:
    python main.py etl https://exemplo.com/pagina1 https://exemplo.com/pagina2
    (ou diretamente: python -m etl.run_etl <url1> <url2> ...)
"""
import sys

from etl.extract import fetch_pages
from etl.transform import chunk_text
from etl.embed import embed_texts
from etl.load import load_document, load_chunks


def run(urls: list[str]):
    pages = fetch_pages(urls)

    for page in pages:
        chunks = chunk_text(page.text)
        if not chunks:
            print(f"[etl] nenhum conteúdo extraível em {page.url}, pulando.")
            continue

        embeddings = embed_texts(chunks)
        document_id = load_document(page.url, page.title)
        load_chunks(document_id, chunks, embeddings)

        print(f"[etl] {page.url} -> {len(chunks)} chunks salvos (documento #{document_id})")


if __name__ == "__main__":
    urls = sys.argv[1:]
    if not urls:
        print("Uso: python -m etl.run_etl <url1> <url2> ...")
        sys.exit(1)
    run(urls)

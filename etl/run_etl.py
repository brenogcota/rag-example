"""
Orquestra o pipeline ETL completo: Extração -> Transformação -> Embedding -> Carga.

Aceita na mesma chamada páginas web e planilhas (.csv, .tsv, .xlsx, .xlsm, .xls),
locais ou remotas; um diretório é expandido nas planilhas que contém.

Uso:
    python main.py etl https://exemplo.com/pagina1 dados/vendas.xlsx
    (ou diretamente: python -m etl.run_etl <fonte1> <fonte2> ...)
"""
import sys

from etl.extract import fetch_sources
from etl.transform import chunk_text, chunk_records
from etl.embed import embed_texts
from etl.load import load_document, load_chunks


def run(sources: list[str]):
    pages = fetch_sources(sources)

    for page in pages:
        # Planilha traz registros prontos: fragmenta por linha, não por palavra.
        if page.records:
            chunks = chunk_records(page.records, header=page.header)
        else:
            chunks = chunk_text(page.text)

        if not chunks:
            print(f"[etl] nenhum conteúdo extraível em {page.url}, pulando.")
            continue

        embeddings = embed_texts(chunks)
        document_id = load_document(page.url, page.title)
        load_chunks(document_id, chunks, embeddings)

        print(f"[etl] {page.url} -> {len(chunks)} chunks salvos (documento #{document_id})")


if __name__ == "__main__":
    sources = sys.argv[1:]
    if not sources:
        print("Uso: python -m etl.run_etl <fonte1> <fonte2> ...")
        sys.exit(1)
    run(sources)

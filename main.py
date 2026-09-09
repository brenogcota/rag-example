"""
CLI de entrada do sistema RAG de produção.

Uso:
    python main.py etl <url1> <url2> ...
    python main.py chat <username> "<pergunta>"
"""
import sys


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "etl":
        from etl.run_etl import run
        urls = sys.argv[2:]
        if not urls:
            print('Uso: python main.py etl <url1> <url2> ...')
            sys.exit(1)
        run(urls)

    elif command == "chat":
        if len(sys.argv) < 4:
            print('Uso: python main.py chat <username> "<pergunta>"')
            sys.exit(1)
        from rag.pipeline import ask
        username, question = sys.argv[2], sys.argv[3]
        result = ask(username, question)

        print("\n--- Trechos recuperados ---")
        for r in result["retrieved"]:
            print(f"  [{r['similarity']:.3f}] {r['title']} — {r['source_url']}")

        print("\n--- Resposta ---")
        print(result["answer"])

    else:
        print(f"Comando desconhecido: {command}\n")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

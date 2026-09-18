"""
Extração (E do ETL): baixa páginas web reais e extrai o texto principal,
descartando script/style/nav/footer.
"""
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

USER_AGENT = "rag-etl-demo/1.0 (+uso educacional)"


@dataclass
class ExtractedPage:
    url: str
    title: str
    text: str


def fetch_page(url: str, timeout: int = 15) -> ExtractedPage:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url

    # Heurística simples: concatena parágrafos com texto substancial.
    # Para produção, considere um extrator mais robusto (ex.: trafilatura, readability-lxml).
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = "\n".join(p for p in paragraphs if len(p) > 40)

    return ExtractedPage(url=url, title=title, text=text)


def fetch_pages(urls: list[str]) -> list[ExtractedPage]:
    pages = []
    for url in urls:
        try:
            pages.append(fetch_page(url))
        except requests.RequestException as e:
            print(f"[extract] falha ao buscar {url}: {e}")
    return pages

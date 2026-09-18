"""
Extração (E do ETL): lê fontes reais e devolve o texto pronto para o chunking.

Duas famílias de fonte:
  - páginas web (http/https)  -> texto principal do HTML, descartando
    script/style/nav/footer;
  - planilhas (.csv/.tsv/.xlsx/.xlsm/.xls) -> um registro de texto por linha,
    no formato "coluna: valor | coluna: valor". Vale para arquivo local,
    diretório (todas as planilhas dentro dele) ou URL.
"""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

USER_AGENT = "rag-etl-demo/1.0 (+uso educacional)"

# Extensões tratadas como planilha (o resto vira página web).
TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xlsm", ".xls"}

# Limite de linhas lidas por planilha/aba: evita estourar a memória — e a conta
# de embeddings — com um arquivo de milhões de registros.
MAX_ROWS = 50_000


@dataclass
class ExtractedPage:
    url: str
    title: str
    text: str
    # Preenchidos só por planilhas: um registro por linha e o cabeçalho que dá
    # contexto a eles (nome da tabela + colunas).
    records: list[str] = field(default_factory=list)
    header: str = ""


# --------------------------------------------------------------------------
# Páginas web
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Planilhas (csv / tsv / xlsx / xlsm / xls)
# --------------------------------------------------------------------------
def _suffix(source: str) -> str:
    """Extensão da fonte, ignorando querystring quando for URL."""
    path = urlparse(source).path if _is_url(source) else source
    return Path(path).suffix.lower()


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def is_tabular_source(source: str) -> bool:
    return _suffix(source) in TABULAR_SUFFIXES


def _read_bytes(source: str, timeout: int = 30) -> BytesIO:
    """Baixa a planilha remota para memória; arquivos locais são lidos direto."""
    resp = requests.get(source, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return BytesIO(resp.content)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Colunas sem nome viram `coluna_N`; as demais perdem espaços sobrando."""
    df.columns = [
        f"coluna_{i + 1}" if str(c).startswith("Unnamed:") or not str(c).strip()
        else " ".join(str(c).split())
        for i, c in enumerate(df.columns)
    ]
    return df


def _frame_to_records(df: pd.DataFrame) -> list[str]:
    """
    Serializa cada linha como "coluna: valor | coluna: valor".

    Manter o nome da coluna junto do valor é o que faz a busca vetorial
    funcionar em tabela: o embedding de "cidade: Salvador | uf: BA" carrega o
    significado de cada célula, coisa que um "Salvador,BA" solto não carrega.
    """
    df = _normalize_columns(df.head(MAX_ROWS)).fillna("")
    records = []
    for row in df.itertuples(index=False, name=None):
        pairs = [
            f"{col}: {' '.join(str(value).split())}"
            for col, value in zip(df.columns, row)
            if str(value).strip()
        ]
        if pairs:
            records.append(" | ".join(pairs))
    return records


def _read_frames(source: str) -> dict[str, pd.DataFrame]:
    """
    Devolve {nome_da_aba: DataFrame}. CSV/TSV têm uma "aba" só.

    `dtype=str` mantém tudo como texto: CEP, CPF e código de produto não podem
    virar float e perder o zero à esquerda no caminho para o embedding.
    """
    suffix = _suffix(source)
    handle = _read_bytes(source) if _is_url(source) else source

    if suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else None  # None + engine python = detecta o separador
        for encoding in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(
                    handle,
                    sep=sep,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                    encoding=encoding,
                    nrows=MAX_ROWS,
                )
                return {"": df}
            except UnicodeDecodeError:
                if isinstance(handle, BytesIO):
                    handle.seek(0)
        raise ValueError("não foi possível decodificar o CSV (tentado utf-8 e latin-1)")

    # sheet_name=None -> lê todas as abas do arquivo Excel
    return pd.read_excel(handle, sheet_name=None, dtype=str)


def fetch_table(source: str) -> list[ExtractedPage]:
    """
    Lê uma planilha e devolve uma `ExtractedPage` por aba (CSV gera uma só).

    Cada aba vira um documento próprio — a `source_url` recebe o sufixo
    `#<aba>` — para que a resposta do chat consiga citar de onde veio o dado.
    """
    name = Path(urlparse(source).path if _is_url(source) else source).name
    pages = []

    for sheet, df in _read_frames(source).items():
        df = _normalize_columns(df)
        records = _frame_to_records(df)
        if not records:
            continue

        url = f"{source}#{sheet}" if sheet else source
        title = f"{name} — {sheet}" if sheet else name
        columns = ", ".join(df.columns)
        pages.append(
            ExtractedPage(
                url=url,
                title=title,
                text="\n".join(records),
                records=records,
                header=f"Tabela: {title} | Colunas: {columns}",
            )
        )
    return pages


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------
def expand_sources(sources: list[str]) -> list[str]:
    """Diretório na lista vira todas as planilhas dentro dele (não recursivo)."""
    expanded = []
    for src in sources:
        if not _is_url(src) and Path(src).is_dir():
            found = sorted(
                str(p) for p in Path(src).iterdir() if p.suffix.lower() in TABULAR_SUFFIXES
            )
            if not found:
                print(f"[extract] nenhuma planilha em {src}")
            expanded.extend(found)
        else:
            expanded.append(src)
    return expanded


def fetch_sources(sources: list[str]) -> list[ExtractedPage]:
    """Lê URLs e planilhas na mesma chamada; uma fonte quebrada não derruba as outras."""
    pages = []
    for src in expand_sources(sources):
        try:
            if is_tabular_source(src):
                pages.extend(fetch_table(src))
            else:
                pages.append(fetch_page(src))
        except Exception as e:  # rede, arquivo ausente, planilha corrompida...
            print(f"[extract] falha ao ler {src}: {e}")
    return pages


# Nome antigo, mantido para quem já chamava a extração só de páginas web.
fetch_pages = fetch_sources

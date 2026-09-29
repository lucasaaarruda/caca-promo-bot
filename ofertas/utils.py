import re

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def sessao() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"})
    return s


def parse_preco_br(texto: str | None) -> float | None:
    """Converte "R$ 1.234,56" / "1.234" / "56,43" em float."""
    t = re.sub(r"[^\d,.]", "", texto or "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.rsplit(".", 1)[1]) == 3):
        t = t.replace(".", "")  # ponto de milhar, sem centavos
    try:
        return float(t)
    except ValueError:
        return None


def extrair_urls(texto: str | None) -> list[str]:
    return re.findall(r"https?://\S+", texto or "")


def parse_vendas(texto: str | None) -> int | None:
    """"+5mil vendidos" -> 5000, "+10mil" -> 10000, "+500 vendidos" -> 500, "1,2 mil" -> 1200."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mil|k)?\s*vendidos?", texto or "", re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return int(n * 1000) if m.group(2) else int(n)


def parse_nota(texto: str | None) -> float | None:
    m = re.search(r"(\d(?:[.,]\d)?)", texto or "")
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return n if 0 < n <= 5 else None

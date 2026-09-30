"""Mercado Livre pela API OFICIAL (opcional).

Precisa de um aplicativo gratuito em https://developers.mercadolivre.com.br (App ID + Secret, no .env).
Com ele o bot passa a: (1) buscar produtos por palavra-chave, coisa que o site bloqueia sem captcha,
(2) ler título, preço e foto de um link colado no conversor. O link de afiliado continua sendo gerado
pelo Linkbuilder (navegador logado), como antes.

Sem as credenciais, tudo aqui fica desligado e o bot funciona como sempre.
"""
import logging
import re
import time

import requests

from ..config import config
from ..models import Oferta

log = logging.getLogger("ofertas.mlapi")

API = "https://api.mercadolibre.com"
_token = {"valor": None, "expira": 0.0}
_rodizio = 0

_RE_ID = re.compile(r"MLB-?(\d{6,})")


def disponivel() -> bool:
    return bool(config.ml_app_id and config.ml_app_secret)


def _access_token() -> str:
    if _token["valor"] and time.time() < _token["expira"] - 60:
        return _token["valor"]
    r = requests.post(f"{API}/oauth/token", timeout=30,
                      headers={"accept": "application/json", "content-type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials", "client_id": config.ml_app_id,
                            "client_secret": config.ml_app_secret})
    if r.status_code != 200:
        raise RuntimeError(f"token da API do ML falhou (HTTP {r.status_code}): {r.text[:200]}")
    dados = r.json()
    _token["valor"] = dados["access_token"]
    _token["expira"] = time.time() + int(dados.get("expires_in", 21600))
    return _token["valor"]


def _get(caminho: str, **params) -> dict:
    r = requests.get(API + caminho, params=params or None, timeout=30,
                     headers={"Authorization": f"Bearer {_access_token()}", "accept": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"API do ML {caminho} respondeu HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


# ── conversão de respostas em Oferta ─────────────────────────────────

def _br(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _imagem_grande(url: str | None) -> str | None:
    """A miniatura vem pequena (…-I.jpg); trocar o sufixo dá a imagem original."""
    if not url:
        return None
    return re.sub(r"-[A-Z]\.(jpg|jpeg|webp)$", r"-O.\1", url.replace("http://", "https://"))


def oferta_de_item(d: dict) -> Oferta | None:
    """Resposta de /items/{id} ou de um resultado de /sites/MLB/search."""
    id_ = d.get("id")
    titulo = d.get("title") or d.get("name")
    preco = d.get("price")
    if not (id_ and titulo and preco):
        return None
    original = d.get("original_price")
    fotos = d.get("pictures") or []
    imagem = (fotos[0].get("secure_url") or fotos[0].get("url")) if fotos else _imagem_grande(d.get("secure_thumbnail") or d.get("thumbnail"))

    partes = []
    if (d.get("shipping") or {}).get("free_shipping"):
        partes.append("🚚 Frete grátis")
    parcela = d.get("installments") or {}
    if parcela.get("rate") in (0, 0.0) and (parcela.get("quantity") or 0) >= 2 and parcela.get("amount"):
        partes.append(f"💳 {parcela['quantity']}x de R$ {_br(float(parcela['amount']))} sem juros")

    vendas = d.get("sold_quantity")
    return Oferta(
        plataforma="mercadolivre",
        id_produto=str(id_).replace("-", ""),
        titulo=titulo,
        url_afiliado="",  # preenchido pelo Linkbuilder, depois
        url_produto=(d.get("permalink") or "").split("#")[0].split("?")[0],
        preco=float(preco),
        preco_original=float(original) if original and float(original) > float(preco) else None,
        imagem=imagem,
        extra=" · ".join(partes) or None,
        vendas=int(vendas) if vendas else None,
        categoria=d.get("category_id"),
    )


def oferta_de_produto_catalogo(d: dict) -> Oferta | None:
    """Resposta de /products/{id} (página de catálogo, as URLs ".../p/MLB123")."""
    vencedor = d.get("buy_box_winner") or {}
    preco = vencedor.get("price")
    titulo = d.get("name")
    if not (d.get("id") and titulo and preco):
        return None
    fotos = d.get("pictures") or []
    original = vencedor.get("original_price")
    return Oferta(
        plataforma="mercadolivre",
        id_produto=str(d["id"]).replace("-", ""),
        titulo=titulo,
        url_afiliado="",
        url_produto=f"https://www.mercadolivre.com.br/p/{d['id']}",
        preco=float(preco),
        preco_original=float(original) if original and float(original) > float(preco) else None,
        imagem=(fotos[0].get("url") if fotos else None),
        categoria=d.get("main_category") or d.get("category_id"),
    )


# ── o que o bot usa ──────────────────────────────────────────────────

def buscar(termo: str, limite: int = 20) -> list[Oferta]:
    dados = _get("/sites/MLB/search", q=termo, limit=limite, condition="new")
    return [o for o in (oferta_de_item(r) for r in dados.get("results") or []) if o]


def buscar_rodada() -> list[Oferta]:
    """Palavras-chave da fonte (fontes.mercadolivre.buscas_api) em rodízio, poucas por rodada."""
    global _rodizio
    termos = [str(t) for t in (config.fonte_ml.get("buscas_api") or [])]
    if not termos:
        return []
    por_rodada = int(config.fonte_ml.get("buscas_api_por_ciclo", 6)) or len(termos)
    if por_rodada < len(termos):
        inicio = _rodizio % len(termos)
        _rodizio += por_rodada
        termos = (termos + termos)[inicio:inicio + por_rodada]
    achadas: dict[str, Oferta] = {}
    for termo in termos:
        try:
            for o in buscar(termo):
                achadas.setdefault(o.id_produto, o)
        except Exception as e:
            log.error("Busca '%s' na API do ML: %s", termo, e)
            if "HTTP 403" in str(e) or "HTTP 401" in str(e):
                break  # sem permissão: não adianta insistir nos outros termos
        time.sleep(1)
    log.info("Mercado Livre (API): %d ofertas em %d busca(s)", len(achadas), len(termos))
    return list(achadas.values())


def oferta_de_url(url: str) -> Oferta | None:
    """Título, preço e foto de um link do ML (item ou página de catálogo). None se a API não conseguir."""
    m = _RE_ID.search(url)
    if not (disponivel() and m):
        return None
    id_ = f"MLB{m.group(1)}"
    for caminho, conv in ((f"/items/{id_}", oferta_de_item), (f"/products/{id_}", oferta_de_produto_catalogo)):
        try:
            oferta = conv(_get(caminho))
            if oferta:
                return oferta
        except Exception as e:
            log.info("API do ML %s: %s", caminho, e)
    return None


def diagnostico() -> list[str]:
    """Roda os 3 usos da API e diz o que o ML liberou para o seu aplicativo."""
    if not disponivel():
        return ["❌ Preencha ML_APP_ID e ML_APP_SECRET (painel → Mercado Livre) e salve."]
    linhas = []
    try:
        _access_token()
        linhas.append("✅ Token: o ML aceitou o seu App ID e Secret.")
    except Exception as e:
        return [f"❌ Token: {e}"]
    item_id = None
    try:
        achadas = buscar("boina de polimento", limite=5)
        linhas.append(f"✅ Busca por palavra-chave: {len(achadas)} resultado(s)" +
                      (f", ex.: {achadas[0].titulo[:60]} — R$ {achadas[0].preco}" if achadas else ""))
        item_id = achadas[0].id_produto if achadas else None
    except Exception as e:
        linhas.append(f"❌ Busca por palavra-chave: {e}")
    if item_id:
        try:
            o = oferta_de_item(_get(f"/items/{item_id}"))
            linhas.append(f"✅ Leitura de anúncio: {o.titulo[:60]} — R$ {o.preco}" if o else "⚠️ Leitura de anúncio: resposta sem preço")
        except Exception as e:
            linhas.append(f"❌ Leitura de anúncio: {e}")
    try:
        o = oferta_de_produto_catalogo(_get("/products/MLB75836344"))
        linhas.append(f"✅ Leitura de página de catálogo: {o.titulo[:60]} — R$ {o.preco}" if o else "⚠️ Catálogo: resposta sem preço")
    except Exception as e:
        linhas.append(f"❌ Leitura de página de catálogo: {e}")
    return linhas

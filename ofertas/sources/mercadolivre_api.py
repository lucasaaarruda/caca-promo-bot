"""Mercado Livre pela API OFICIAL (opcional).

Precisa de um aplicativo gratuito em https://developers.mercadolivre.com.br (App ID + Secret, no .env).
O ML libera para apps novos estas rotas (verificado em 2026-09-29), e nega as de anúncios avulsos:

  ✅ /highlights/MLB/category/{cat}   os MAIS VENDIDOS de cada categoria
  ✅ /products/search                 busca de produtos de catálogo por palavra-chave
  ✅ /products/{id}                   nome, fotos e página de catálogo
  ✅ /products/{id}/items             as ofertas do produto: preço, preço original, frete, etiquetas
  ❌ /sites/MLB/search, /items/{id}   403

Com elas o bot descobre produtos que a página de "ofertas" não mostra e lê título/preço/foto de links
colados no conversor. O link de afiliado continua sendo gerado pelo Linkbuilder (navegador logado).
Sem as credenciais, tudo aqui fica desligado e o bot funciona como sempre.
"""
import logging
import re
import time
from dataclasses import replace

import requests

from .. import rodizio
from ..config import config
from ..models import Oferta

log = logging.getLogger("ofertas.mlapi")

API = "https://api.mercadolibre.com"
TTL = 2 * 3600            # reaproveita o que já consultou por 2h (preço é reconferido depois disso)
PAUSA = 0.3               # entre chamadas
_token = {"valor": None, "expira": 0.0}
_cache: dict[str, tuple[float, Oferta | None]] = {}   # id do produto -> (quando, oferta ou None se sem vendedor)
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


def _get_ou_none(caminho: str, **params) -> dict | None:
    """Como _get, mas 404 (ex.: "No winners found", produto sem vendedor) vira None."""
    try:
        return _get(caminho, **params)
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return None
        raise


# ── conversão de respostas em Oferta ─────────────────────────────────

def _br(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _imagem_grande(url: str | None) -> str | None:
    """A miniatura vem pequena (…-I.jpg); trocar o sufixo dá a imagem original."""
    if not url:
        return None
    return re.sub(r"-[A-Z]\.(jpg|jpeg|webp)$", r"-O.\1", url.replace("http://", "https://"))


def oferta_de_item(d: dict) -> Oferta | None:
    """Anúncio no formato de /items/{id} (mantido: útil se o ML liberar essa rota no futuro)."""
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


# categorias onde falsificação é comum: ali só vale vendedor verificável (e escolhemos a melhor oferta entre eles)
CATEGORIAS_SENSIVEIS = {"MLB6284"}  # Perfumes
_TTL_VENDEDOR = 12 * 3600
_vendedores: dict[int, tuple[float, bool]] = {}


def _vendedor_lider(seller_id) -> bool:
    """MercadoLíder Platinum com reputação verde (cache de 12h)."""
    agora = time.time()
    acerto = _vendedores.get(seller_id)
    if acerto and agora - acerto[0] < _TTL_VENDEDOR:
        return acerto[1]
    u = _get_ou_none(f"/users/{seller_id}")
    rep = (u or {}).get("seller_reputation") or {}
    ok = rep.get("power_seller_status") == "platinum" and str(rep.get("level_id", "")).startswith("5")
    _vendedores[seller_id] = (agora, ok)
    time.sleep(PAUSA)
    return ok


def _loja_ml(item: dict, consultar: bool = True) -> tuple[bool, str | None]:
    """(vendedor verificado?, selo). Loja oficial vem no próprio item; MercadoLíder exige consultar o vendedor."""
    if item.get("official_store_id"):
        return True, "🏪 Loja oficial"
    if consultar and config.lojas_confiaveis == "oficial+lider" and item.get("seller_id")             and _vendedor_lider(item["seller_id"]):
        return True, "🏅 MercadoLíder Platinum"
    return False, None


def _melhor_oferta(itens: dict | None) -> dict | None:
    """Das ofertas de /products/{id}/items, a de menor preço entre as novas. Em categoria sensível
    (perfumes), a de menor preço entre os vendedores verificados, se houver."""
    validas = [i for i in (itens or {}).get("results") or []
               if isinstance(i, dict) and i.get("price") and i.get("condition", "new") == "new"]
    if not validas:
        return None
    barato = min(validas, key=lambda i: float(i["price"]))
    if barato.get("category_id") in CATEGORIAS_SENSIVEIS:
        confiaveis = [i for i in validas if _loja_ml(i)[0]]
        if confiaveis:
            return min(confiaveis, key=lambda i: float(i["price"]))
    return barato


def oferta_de_catalogo(prod: dict, item: dict, categoria: str | None = None, campeao: bool = False) -> Oferta | None:
    """Produto de catálogo (/products/{id}) + a melhor oferta dele (/products/{id}/items)."""
    nome, id_ = prod.get("name"), prod.get("id")
    if not (nome and id_ and item and item.get("price")):
        return None
    preco = float(item["price"])
    original = item.get("original_price")
    fotos = prod.get("pictures") or []

    partes = []
    if campeao:
        partes.append("🏆 Mais vendido na categoria")
    tags = item.get("tags") or []
    if "lightning_deal" in tags:
        partes.append("⚡ Oferta relâmpago")
    elif "deal_of_the_day" in tags:
        partes.append("🔥 Oferta do dia")
    if (item.get("shipping") or {}).get("free_shipping"):
        partes.append("🚚 Frete grátis")
    sensivel = (categoria or item.get("category_id")) in CATEGORIAS_SENSIVEIS or item.get("category_id") in CATEGORIAS_SENSIVEIS
    confiavel, selo = _loja_ml(item, consultar=sensivel)
    if selo:
        partes.append(selo)

    return Oferta(
        plataforma="mercadolivre",
        id_produto=str(id_).replace("-", ""),
        titulo=nome,
        url_afiliado="",  # preenchido pelo Linkbuilder, depois
        url_produto=f"https://www.mercadolivre.com.br/p/{id_}",
        preco=preco,
        preco_original=float(original) if original and float(original) > preco else None,
        imagem=(fotos[0].get("url") if fotos else None),
        extra=" · ".join(partes) or None,
        categoria=categoria or item.get("category_id"),
        mais_vendido=campeao,
        # só afirma "não verificado" onde importa (perfumes); nas demais categorias fica "não informado"
        loja_confiavel=True if confiavel else (False if sensivel else None),
    )


# ── descoberta e consulta ────────────────────────────────────────────

def produto_para_oferta(pid: str, categoria: str | None = None, campeao: bool = False) -> Oferta | None:
    """Oferta atual de um produto de catálogo, ou None (sem vendedor ativo, inativo...). Usa cache de 2h."""
    agora = time.time()
    acerto = _cache.get(pid)
    if acerto and agora - acerto[0] < TTL:
        o = acerto[1]
        return replace(o, categoria=categoria or o.categoria, mais_vendido=campeao or o.mais_vendido) if o else None
    oferta = None
    prod = _get_ou_none(f"/products/{pid}")
    if prod and prod.get("status", "active") == "active":
        time.sleep(PAUSA)
        item = _melhor_oferta(_get_ou_none(f"/products/{pid}/items"))
        oferta = oferta_de_catalogo(prod, item, categoria, campeao) if item else None
    _cache[pid] = (agora, oferta)
    return oferta


def destaques(categoria: str, limite: int = 12) -> list[str]:
    """Ids dos produtos mais vendidos da categoria (só os de catálogo; anúncios avulsos o ML nega)."""
    conteudo = _get(f"/highlights/MLB/category/{categoria}").get("content") or []
    return [c["id"] for c in conteudo if c.get("type") == "PRODUCT"][:limite]


def buscar_produtos(termo: str, limite: int = 8) -> list[str]:
    dados = _get("/products/search", status="active", site_id="MLB", q=termo, limit=limite)
    return [r["id"] for r in dados.get("results") or [] if r.get("id")][:limite]


def buscar_rodada() -> list[Oferta]:
    """Descobre produtos em rodízio: mais vendidos das categorias do canal + palavras-chave.

    fontes.mercadolivre.buscas_api_por_ciclo = quantas fontes por rodada (padrão 6);
    fontes.mercadolivre.produtos_por_rodada = teto de produtos NOVOS consultados por rodada (padrão 30)."""
    global _rodizio
    fontes: list[tuple[str, str]] = []
    if config.fonte_ml.get("destaques_api", True):
        fontes += [("destaque", str(c)) for c in (config.fonte_ml.get("categorias") or {})]
    fontes += [("busca", str(t)) for t in (config.fonte_ml.get("buscas_api") or [])]
    if not fontes:
        return []
    por_rodada = int(config.fonte_ml.get("buscas_api_por_ciclo", 6)) or len(fontes)
    if por_rodada < len(fontes):
        grupos = []
        for g in config.fonte_ml.get("grupos") or []:  # uma lista de fontes por canal
            lista = ([("destaque", str(c)) for c in g.get("categorias", [])] if config.fonte_ml.get("destaques_api", True) else [])
            lista += [("busca", str(t)) for t in g.get("buscas", [])]
            if lista:
                grupos.append(lista)
        if len(grupos) > 1:
            fontes = rodizio.escolher(grupos, por_rodada, "api")
        else:
            inicio = _rodizio % len(fontes)
            _rodizio += por_rodada
            fontes = (fontes + fontes)[inicio:inicio + por_rodada]
    teto_novos = int(config.fonte_ml.get("produtos_por_rodada", 30))

    achadas: dict[str, Oferta] = {}
    consultados = 0
    for tipo, chave in fontes:
        try:
            ids = destaques(chave) if tipo == "destaque" else buscar_produtos(chave)
        except Exception as e:
            log.error("API do ML (%s '%s'): %s", tipo, chave, e)
            if "HTTP 403" in str(e) or "HTTP 401" in str(e):
                break  # sem permissão: não adianta insistir
            continue
        for pid in ids:
            if pid in achadas:
                continue
            novo = pid not in _cache or time.time() - _cache[pid][0] >= TTL
            if novo and consultados >= teto_novos:
                continue
            try:
                # sem passar a categoria de origem: a lista de mais vendidos traz itens fora do nicho (ex.: produto de cabelo em
                # "Limpeza Automotiva"), então aqui o título é que precisa provar o nicho (termos), não a categoria
                o = produto_para_oferta(pid, campeao=tipo == "destaque")
            except Exception as e:
                log.error("API do ML (produto %s): %s", pid, e)
                continue
            consultados += novo
            if o:
                achadas[pid] = o
            if novo:
                time.sleep(PAUSA)
        time.sleep(PAUSA)
    log.info("Mercado Livre (API): %d ofertas de %d fonte(s) (%d produtos consultados)", len(achadas), len(fontes), consultados)
    return list(achadas.values())


def oferta_de_url(url: str) -> Oferta | None:
    """Título, preço e foto de um link ".../p/MLB123" (catálogo). Links de anúncio avulso o ML nega."""
    m = _RE_ID.search(url)
    if not (disponivel() and m):
        return None
    try:
        return produto_para_oferta(f"MLB{m.group(1)}")
    except Exception as e:
        log.info("API do ML (link %s): %s", url[:60], e)
        return None


def diagnostico() -> list[str]:
    """Roda os usos da API e diz o que o ML liberou para o seu aplicativo."""
    if not disponivel():
        return ["❌ Preencha ML_APP_ID e ML_APP_SECRET (painel → Mercado Livre) e salve."]
    try:
        _access_token()
    except Exception as e:
        return [f"❌ Token: {e}"]
    linhas = ["✅ Token: o ML aceitou o seu App ID e Secret."]
    try:
        ids = buscar_produtos("boina de polimento", 5)
        linhas.append(f"✅ Busca por palavra-chave (catálogo): {len(ids)} produto(s)")
    except Exception as e:
        linhas.append(f"❌ Busca por palavra-chave (catálogo): {e}")
    try:
        ids = destaques("MLB188063", 10)
        linhas.append(f"✅ Mais vendidos da categoria Limpeza Automotiva: {len(ids)} produto(s)")
        achou = None
        for pid in ids:
            achou = produto_para_oferta(pid)
            if achou:
                break
        if achou:
            linhas.append(f"✅ Preço de um produto: {achou.titulo[:55]} — R$ {achou.preco}"
                          + (f" (de R$ {achou.preco_original})" if achou.preco_original else ""))
        else:
            linhas.append("⚠️ Preço: nenhum dos destaques testados tinha vendedor ativo agora")
    except Exception as e:
        linhas.append(f"❌ Mais vendidos / preço: {e}")
    try:
        o = produto_para_oferta("MLB75836344")
        linhas.append(f"✅ Leitura de link de catálogo: {o.titulo[:55]} — R$ {o.preco}" if o else
                      "⚠️ Leitura de link de catálogo: produto sem vendedor ativo agora")
    except Exception as e:
        linhas.append(f"❌ Leitura de link de catálogo: {e}")
    return linhas

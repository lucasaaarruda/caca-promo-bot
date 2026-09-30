from html import escape

from .config import config
from .models import Oferta

_PLATAFORMA = {
    "mercadolivre": "💛 Mercado Livre",
    "shopee": "🧡 Shopee",
    "amazon": "📦 Amazon",
}

# textos do botão: variam de oferta para oferta (fixo por produto, para não mudar ao reenviar)
_BOTOES = ["🛒 Pegar oferta", "🔥 Aproveitar agora", "🛍 Ver preço e comprar", "⚡ Garantir o meu"]


def preco_br(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def texto_botao(o: Oferta) -> str:
    return _BOTOES[sum(o.uid.encode()) % len(_BOTOES)]


def titulo_curto(titulo: str, limite: int = 95) -> str:
    """Títulos de marketplace vêm entupidos de palavras-chave: corta numa palavra inteira."""
    t = " ".join(titulo.split())
    if len(t) <= limite:
        return t
    corte = t[:limite].rsplit(" ", 1)[0].rstrip(" ,;:-|/")
    return corte + "…"


def _selo(desconto: int | None) -> str:
    """Cabeçalho pela força da oferta."""
    if not desconto:
        return "🔥"
    if desconto >= 50:
        return "🚨 SUPER OFERTA"
    if desconto >= 35:
        return "🔥 OFERTA IMPERDÍVEL"
    return "⚡ OFERTA"


def _vendas(n: int) -> str:
    if n >= 1000:
        mil = n / 1000
        return f"+{mil:.0f} mil vendidos" if mil == int(mil) else f"+{mil:.1f} mil vendidos".replace(".", ",")
    return f"+{n} vendidos"


def _detalhes(o: Oferta) -> list[str]:
    """Linhas de prova social e vantagens (nota, vendas, frete, Pix, cupom...)."""
    prova = []
    if o.nota:
        prova.append(f"⭐ {o.nota:.1f}".replace(".", ","))
    if o.vendas:
        prova.append(f"🔥 {_vendas(o.vendas)}")

    vantagens = []
    for parte in (o.extra or "").split(" · "):
        parte = parte.strip()
        # nota e vendas já saíram estruturadas acima; o resto do "extra" são as vantagens
        if not parte or parte.startswith("⭐") or "vendidos" in parte:
            continue
        vantagens.append(escape(parte))

    linhas = []
    if prova:
        linhas.append("  ·  ".join(prova))
    if vantagens:
        linhas.append("  ·  ".join(vantagens))
    return linhas


def _linha_link(o: Oferta) -> str | None:
    """"🛍 Compre aqui: link" — link curto aparece inteiro; longo (Amazon) vira texto clicável."""
    if not (config.link_visivel and o.url_afiliado):
        return None
    if len(o.url_afiliado) <= 45:
        return f"🛍 Compre aqui: {escape(o.url_afiliado)}"
    return f'🛍 <a href="{escape(o.url_afiliado, quote=True)}">Compre aqui</a>'


def montar_caption(o: Oferta) -> str:
    tem_desconto = bool(o.preco and o.preco_original and o.preco_original > o.preco)
    desconto = o.desconto if tem_desconto else None
    linhas = [_selo(desconto), f"<b>{escape(titulo_curto(o.titulo))}</b>", ""]

    if tem_desconto:
        linhas.append(f"❌ De: <s>{preco_br(o.preco_original)}</s>")
        selo = f"   🔻 <b>-{desconto}%</b>" if desconto else ""
        linhas.append(f"✅ Por: <b>{preco_br(o.preco)}</b>{selo}")
        linhas.append(f"💰 Você economiza {preco_br(o.preco_original - o.preco)}")
    elif o.preco:
        linhas.append(f"✅ <b>{preco_br(o.preco)}</b>")

    if o.cupom:
        linhas += ["", f"🎟 Use o cupom: <code>{escape(o.cupom)}</code>"]  # <code>: toque para copiar

    detalhes = _detalhes(o)
    if detalhes:
        linhas += [""] + detalhes

    if link := _linha_link(o):
        linhas += ["", link]

    linhas += ["", _PLATAFORMA.get(o.plataforma, o.plataforma)]
    if o.plataforma == "amazon" and config.aviso_amazon:  # frase exigida pelo contrato da Amazon
        linhas.append(f"<i>{escape(config.aviso_amazon)}</i>")
    return "\n".join(linhas)

"""Relatório para o dono: o que o bot postou, onde, e o que deu errado. Vai para o seu privado no Telegram."""
import datetime as dt

from . import db
from .config import config

_PLATAFORMA = {"mercadolivre": "ML", "shopee": "Shopee", "amazon": "Amazon"}
_FONTES = {"mercadolivre": "Mercado Livre", "shopee": "Shopee", "amazon": "Amazon"}


def _pl(n: int, singular: str, plural: str) -> str:
    """Concordância: 1 rodada, 2 rodadas."""
    return singular if n == 1 else plural


def _problemas(eventos: dict[str, int]) -> list[str]:
    linhas = []
    if n := eventos.get("ml_sessao"):
        linhas.append(f"🔑 Mercado Livre sem sessão ({n}x): refaça o login no painel")
    if n := eventos.get("ml_bloqueio"):
        linhas.append(f"🛑 Mercado Livre bloqueou a leitura de ofertas ({n}x): o bot usou só a API oficial do ML")
    if n := eventos.get("ml_link_falhou"):
        linhas.append(f"🔗 Falha ao gerar link do ML ({n}x): veja data/logs/run.log")
    if n := eventos.get("falha_rede"):
        linhas.append(f"📡 Queda de conexão com o Telegram ({n}x): as ofertas foram tentadas de novo; confira a internet/VPN")
    if n := eventos.get("falha_post"):
        linhas.append(f"📵 Falha ao postar ({n}x): confira se o bot é administrador dos canais")
    for tipo, n in sorted(eventos.items()):
        if tipo.startswith("fonte_vazia:"):
            fonte = _FONTES.get(tipo.split(":", 1)[1], tipo.split(":", 1)[1])
            linhas.append(f"🚫 {fonte} não trouxe ofertas em {n} {_pl(n, 'rodada', 'rodadas')} (bloqueio ou fora do ar)")
    return linhas


def montar(desde: dt.datetime, titulo: str) -> str:
    r = db.resumo(desde)
    nomes = {c.id: c.rotulo for c in config.canais}
    linhas = [titulo, ""]

    if r["posts"]:
        linhas.append(f"📨 {r['posts']} {_pl(r['posts'], 'post', 'posts')} no período")
        for canal, plat in sorted(r["por_canal"].items(), key=lambda kv: -sum(kv[1].values())):
            det = " · ".join(f"{_PLATAFORMA.get(p, p)} {n}" for p, n in sorted(plat.items(), key=lambda kv: -kv[1]))
            linhas.append(f"  {nomes.get(canal, canal)}: {sum(plat.values())}  ({det})")
    else:
        linhas.append("📨 Nenhum post no período.")
    for c in config.canais:
        if c.id not in r["por_canal"]:
            linhas.append(f"  {c.rotulo}: 0 ⚠️")

    if m := r["melhor"]:
        linhas += ["", f"🏆 Maior desconto: -{m['desconto']}% em {nomes.get(m['canal'], m['canal'])}",
                   f"   {m['titulo'][:70]}"]

    linhas += ["", f"🔄 {r['ciclos']} {_pl(r['ciclos'], 'rodada', 'rodadas')} · média de {r['coletadas_media']} "
                       f"{_pl(r['coletadas_media'], 'oferta coletada', 'ofertas coletadas')} por rodada"]
    for canal, n in sorted(r["boas_media"].items()):
        linhas.append(f"  {nomes.get(canal, canal)}: ~{n} {_pl(n, 'oferta boa', 'ofertas boas')} por rodada")
    if r["ciclos"] and not r["posts"] and r["coletadas_media"]:
        linhas.append("  💡 Coletou mas nada passou nos filtros: afrouxe vendas_minimas ou nota_minima no config.yaml.")

    if p := _problemas(r["eventos"]):
        linhas += ["", "⚠️ Problemas:"] + [f"  {x}" for x in p]

    medindo = [c.rotulo for c in config.canais if c.ml_etiqueta or c.amazon_tag]
    linhas += [""]
    if medindo:
        linhas.append("📈 Cliques e vendas: veja nos painéis de afiliado; canais medidos em separado: " + ", ".join(medindo))
    else:
        linhas.append("💡 Para saber qual canal rende mais, dê uma etiqueta (ML) e/ou uma tag (Amazon) própria "
                      "a cada canal, na tela Canais. Os cliques ficam nos painéis de afiliado.")
    return "\n".join(linhas)


def hoje() -> dt.datetime:
    return dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def relatorio_do_dia() -> str:
    return montar(hoje(), f"📊 Relatório de {dt.datetime.now():%d/%m} (até {dt.datetime.now():%H:%M})")

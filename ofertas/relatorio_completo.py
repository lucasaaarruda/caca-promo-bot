"""Relatório completo para análise: o que foi postado, por que o resto foi descartado, qualidade das ofertas,
problemas e observações automáticas. Gera um .md (leitura) e um .csv (todos os posts, para planilha) em
data/relatorios/."""
import csv
import datetime as dt
import json
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from . import db
from .caminhos import DATA_DIR
from .config import config

PASTA = DATA_DIR / "relatorios"

_MOTIVOS = {
    "fora_do_nicho": "fora do nicho do canal",
    "vendedor_nao_verificado": "vendedor não verificado (loja comum)",
    "mesmo_produto_ja_postado": "mesmo produto já postado (últimos dias)",
    "ja_postado": "link idêntico já postado",
    "desconto_baixo": "desconto abaixo do mínimo",
    "desconto_suspeito": "desconto suspeito (alto demais)",
    "nota_baixa": "nota baixa",
    "poucas_vendas": "poucas vendas",
    "preco_fora_da_faixa": "preço fora da faixa",
    "palavra_bloqueada": "palavra bloqueada",
    "amazon_vendedor_nao_confirmado": "Amazon: não confirmado como vendido pela Amazon",
}
_LOJAS = {"mercadolivre": "Mercado Livre", "shopee": "Shopee", "amazon": "Amazon"}


def _canal_de(uid: str) -> str:
    return uid.split("|", 1)[0] if "|" in uid else "principal"


def _ler(desde: dt.datetime):
    d = desde.isoformat(timespec="seconds")
    with closing(db._conn()) as c:
        posts = c.execute(
            "SELECT uid, plataforma, titulo, preco, postada_em, desconto, preco_original, loja_oficial "
            "FROM postadas WHERE postada_em >= ? ORDER BY postada_em", (d,)).fetchall()
        ciclos = c.execute("SELECT ts, coletadas, postadas, detalhe FROM ciclos WHERE ts >= ? ORDER BY ts", (d,)).fetchall()
        eventos = c.execute("SELECT ts, tipo, detalhe FROM eventos WHERE ts >= ? ORDER BY ts", (d,)).fetchall()
    return posts, ciclos, eventos


def _pct(parte: int, total: int) -> str:
    return f"{100 * parte / total:.0f}%" if total else "-"


def _brl(v) -> str:
    return "-" if v is None else "R$ " + f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _tabela(cabecalho: list[str], linhas: list[list]) -> list[str]:
    out = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    out += ["| " + " | ".join(str(x) for x in l) + " |" for l in linhas]
    return out


def montar(desde: dt.datetime, ate: dt.datetime) -> tuple[str, list[tuple]]:
    posts, ciclos, eventos = _ler(desde)
    dias = max(1, (ate.date() - desde.date()).days + 1)
    nomes = {c.id: c.rotulo for c in config.canais}
    canais_ids = list(nomes) or sorted({_canal_de(p[0]) for p in posts})
    L: list[str] = [f"# Relatório completo — {desde:%d/%m/%Y} a {ate:%d/%m/%Y %H:%M}", ""]

    # ── resumo por canal
    por_canal: dict[str, list] = defaultdict(list)
    for p in posts:
        por_canal[_canal_de(p[0])].append(p)
    L += ["## Resumo por canal", ""]
    linhas = []
    for cid in canais_ids:
        ps = por_canal.get(cid, [])
        conhecidos = [p for p in ps if p[7] is not None]
        descontos = [p[5] for p in ps if p[5]]
        precos = [p[3] for p in ps if p[3]]
        linhas.append([nomes.get(cid, cid), len(ps), f"{len(ps) / dias:.1f}",
                       _pct(sum(1 for p in conhecidos if p[7]), len(conhecidos)) if conhecidos else "n/d",
                       f"{statistics.mean(descontos):.0f}%" if descontos else "-",
                       _brl(statistics.median(precos)) if precos else "-"])
    linhas.append(["**Total**", len(posts), f"{len(posts) / dias:.1f}", "", "", ""])
    L += _tabela(["Canal", "Posts", "Posts/dia", "Loja oficial*", "Desconto médio", "Preço mediano"], linhas)
    L += ["", "*% dos posts com vendedor verificado, entre os que têm essa informação registrada "
          "(posts anteriores à regra de loja oficial aparecem como n/d).", ""]

    # ── por loja
    L += ["## Posts por loja", ""]
    lojas = sorted({p[1] for p in posts})
    linhas = [[nomes.get(cid, cid)] + [sum(1 for p in por_canal.get(cid, []) if p[1] == lj) for lj in lojas] for cid in canais_ids]
    if lojas:
        L += _tabela(["Canal"] + [_LOJAS.get(x, x) for x in lojas], linhas)
    else:
        L.append("Nenhum post no período.")
    L.append("")

    # ── funil por canal
    L += ["## Funil por canal (soma das rodadas do período)", ""]
    boas, postadas, descartes = Counter(), Counter(), defaultdict(Counter)
    geral_plataforma: dict[str, list[int]] = defaultdict(list)
    so_api = 0
    for _, _, _, detalhe in ciclos:
        for cid, v in json.loads(detalhe or "{}").items():
            if cid == "_geral":
                for plat, n in (v.get("por_plataforma") or {}).items():
                    geral_plataforma[plat].append(n)
                so_api += 1 if v.get("ml_so_pela_api") else 0
                continue
            boas[cid] += v.get("boas", 0)
            postadas[cid] += v.get("postadas", 0)
            for m, n in (v.get("descartes") or {}).items():
                descartes[cid][m] += n
    L.append(f"Rodadas no período: **{len(ciclos)}**.")
    L.append("")
    for cid in canais_ids:
        if not descartes[cid] and not boas[cid]:
            continue
        total_desc = sum(descartes[cid].values())
        L += [f"### {nomes.get(cid, cid)}",
              f"- Ofertas aprovadas nos filtros: **{boas[cid]}** (média {boas[cid] / max(1, len(ciclos)):.1f} por rodada)",
              f"- Postadas: **{postadas[cid]}**"]
        if total_desc:
            L.append(f"- Descartadas: **{total_desc}**")
        for m, n in descartes[cid].most_common():
            L.append(f"  - {_MOTIVOS.get(m, m)}: {n} ({_pct(n, total_desc)})")
        L.append("")
    if not ciclos or not any(descartes.values()):
        L += ["_Os motivos de descarte só são registrados a partir da versão que criou este relatório; "
              "períodos anteriores aparecem vazios._", ""]

    # ── coleta
    if geral_plataforma:
        L += ["## Coleta por rodada (média de ofertas brutas)", ""]
        L += _tabela(["Loja", "Média/rodada", "Rodadas sem nenhuma"],
                     [[_LOJAS.get(k, k), f"{statistics.mean(v):.0f}", sum(1 for x in v if x == 0)]
                      for k, v in sorted(geral_plataforma.items())])
        if so_api:
            L += ["", f"Rodadas em que o ML não pôde ser lido pelas páginas (só API): **{so_api}**."]
        L.append("")

    # ── qualidade
    L += ["## Qualidade das ofertas postadas", ""]
    faixas = Counter()
    for p in posts:
        d = p[5] or 0
        faixas["menos de 25%" if d < 25 else "25–39%" if d < 40 else "40–59%" if d < 60 else "60% ou mais"] += 1
    if posts:
        L += _tabela(["Faixa de desconto", "Posts"], [[k, faixas[k]] for k in ("menos de 25%", "25–39%", "40–59%", "60% ou mais")])
        L += ["", "**Maiores descontos:**", ""]
        for p in sorted(posts, key=lambda p: p[5] or 0, reverse=True)[:8]:
            L.append(f"- -{p[5] or 0}% · {_brl(p[3])} · {nomes.get(_canal_de(p[0]), _canal_de(p[0]))} · {p[2][:70]}")
        L += ["", "**Maiores preços:**", ""]
        for p in sorted(posts, key=lambda p: p[3] or 0, reverse=True)[:5]:
            L.append(f"- {_brl(p[3])} · -{p[5] or 0}% · {nomes.get(_canal_de(p[0]), _canal_de(p[0]))} · {p[2][:70]}")
    L.append("")

    # ── horários
    if posts:
        horas = Counter(int(p[4][11:13]) for p in posts)
        pico = max(horas.values())
        L += ["## Posts por hora do dia", "", "```"]
        for h in range(24):
            if horas[h]:
                L.append(f"{h:02d}h {'█' * max(1, round(20 * horas[h] / pico))} {horas[h]}")
        L += ["```", ""]

    # ── problemas
    L += ["## Problemas registrados", ""]
    if eventos:
        cont = Counter(t for _, t, _ in eventos)
        for t, n in cont.most_common():
            ultimo = next(d for _, tt, d in reversed(eventos) if tt == t)
            L.append(f"- **{t}**: {n}x" + (f" (último: {ultimo[:110]})" if ultimo else ""))
    else:
        L.append("Nenhum problema registrado.")
    L.append("")

    # ── observações automáticas
    obs: list[str] = []
    for cid in canais_ids:
        n = len(por_canal.get(cid, []))
        if n == 0:
            obs.append(f"**{nomes.get(cid, cid)}** não postou nada no período: veja os motivos de descarte acima.")
            continue
        if n / dias < 8:
            obs.append(f"**{nomes.get(cid, cid)}** postou só {n / dias:.1f} por dia. Para mais volume: afrouxar `desconto_minimo` do canal "
                       "ou ampliar o nicho/buscas.")
        total_desc = sum(descartes[cid].values())
        relevantes = total_desc - descartes[cid].get("fora_do_nicho", 0)
        if relevantes > 20:
            m, q = max(((m, q) for m, q in descartes[cid].items() if m != "fora_do_nicho"), key=lambda x: x[1])
            if q / relevantes >= 0.5:
                dica = {"vendedor_nao_verificado": "A regra de loja oficial é o maior filtro. Para mais volume, "
                                                   "`lojas_confiaveis: oficial+lider` ou `aceitar_loja_comum` no canal (menos seguro).",
                        "mesmo_produto_ja_postado": "O canal está esgotando o que existe no nicho: amplie buscas/categorias.",
                        "desconto_baixo": "Considere baixar o desconto mínimo deste canal.",
                        }.get(m, "")
                obs.append(f"**{nomes.get(cid, cid)}**: {_pct(q, relevantes)} dos descartes (fora o nicho) são “{_MOTIVOS.get(m, m)}”. {dica}".strip())
    if so_api:
        obs.append("O Mercado Livre bloqueou a leitura simples de páginas em algumas rodadas; o bot usou o Chrome ou só a API.")
    for plat, v in geral_plataforma.items():
        if v and sum(1 for x in v if x == 0) / len(v) > 0.3:
            obs.append(f"{_LOJAS.get(plat, plat)} não trouxe nenhuma oferta em {sum(1 for x in v if x == 0)} de {len(v)} rodadas.")
    L += ["## Observações automáticas", ""] + ([f"- {o}" for o in obs] or ["Nada fora do normal."]) + [""]

    linhas_csv = [(p[4], nomes.get(_canal_de(p[0]), _canal_de(p[0])), _LOJAS.get(p[1], p[1]), p[2], p[3], p[6], p[5],
                   {1: "sim", 0: "não"}.get(p[7], "")) for p in posts]
    return "\n".join(L), linhas_csv


def gerar(dias: int = 1) -> tuple[Path, Path]:
    """Gera o relatório dos últimos `dias` (1 = hoje) e devolve (arquivo .md, arquivo .csv)."""
    agora = dt.datetime.now()
    desde = (agora - dt.timedelta(days=max(1, dias) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    texto, linhas = montar(desde, agora)
    PASTA.mkdir(parents=True, exist_ok=True)
    sufixo = f"{agora:%Y-%m-%d}" if dias <= 1 else f"{agora:%Y-%m-%d}_{dias}dias"
    md, csv_ = PASTA / f"relatorio-{sufixo}.md", PASTA / f"posts-{sufixo}.csv"
    md.write_text(texto, encoding="utf-8")
    with csv_.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: o Excel abre os acentos certos
        w = csv.writer(f, delimiter=";")
        w.writerow(["data_hora", "canal", "loja", "titulo", "preco", "preco_original", "desconto_pct", "loja_oficial"])
        w.writerows(linhas)
    return md, csv_

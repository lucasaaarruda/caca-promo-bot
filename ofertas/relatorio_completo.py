"""Relatório completo para análise: o que foi postado, por que o resto foi descartado, qualidade das ofertas,
problemas e observações automáticas. Gera dois PDFs (o relatório e a lista de todos os posts) em
data/relatorios/."""
import datetime as dt
import json
import re
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
    "sem_preco": "loja não informou o preço",
    "preco_acima_do_menor_visto": "sem desconto listado e preço mais de 10% acima do menor já visto",
    "desconto_suspeito": "desconto suspeito (alto demais)",
    "nota_baixa": "nota baixa",
    "poucas_vendas": "poucas vendas",
    "preco_fora_da_faixa": "preço fora da faixa",
    "palavra_bloqueada": "palavra bloqueada",
    "amazon_vendedor_nao_confirmado": "Amazon: não confirmado como vendido pela Amazon",
    "muito_parecido_em_sequencia": "adiado por variedade (mesmo tipo de produto que acabou de sair)",
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
    if not total:
        return "-"
    p = 100 * parte / total
    return f"{p:.1f}%" if 0 < p < 1 else f"{p:.0f}%"


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
        sem = len(ps) - len(descontos)  # sem preço "de" (jeans importado): fora da média, mas avisado
        media = f"{statistics.mean(descontos):.0f}%" if descontos else "-"
        linhas.append([nomes.get(cid, cid), len(ps), f"{len(ps) / dias:.1f}",
                       _pct(sum(1 for p in conhecidos if p[7]), len(conhecidos)) if conhecidos else "n/d",
                       media + (f" ({sem} sem desconto)" if sem else ""),
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
        recusadas = descartes[cid].get("amazon_vendedor_nao_confirmado", 0)
        if boas[cid] and recusadas >= 0.5 * boas[cid]:
            obs.append(f"**{nomes.get(cid, cid)}**: {_pct(recusadas, boas[cid])} das ofertas aprovadas pararam na conferência "
                       "do vendedor da Amazon (a página não mostra “vendido pela Amazon”). A mesma oferta conta uma vez por rodada.")
        relevantes = total_desc - descartes[cid].get("fora_do_nicho", 0)
        if relevantes > 20:
            m, q = max(((m, q) for m, q in descartes[cid].items() if m != "fora_do_nicho"), key=lambda x: x[1])
            if q / relevantes >= 0.5:
                dica = {"vendedor_nao_verificado": "A regra de loja oficial é o maior filtro. Para mais volume, "
                                                   "`lojas_confiaveis: oficial+lider` ou `aceitar_loja_comum` no canal (menos seguro).",
                        "mesmo_produto_ja_postado": "O canal está esgotando o que existe no nicho: amplie buscas/categorias.",
                        "desconto_baixo": "Considere baixar o desconto mínimo deste canal.",
                        "muito_parecido_em_sequencia": "É a regra de variedade funcionando: essas ofertas esperam a vez para não repetir o tipo de produto em sequência.",
                        }.get(m, "")
                obs.append(f"**{nomes.get(cid, cid)}**: {_pct(q, relevantes)} dos descartes (fora o nicho) são “{_MOTIVOS.get(m, m)}”. {dica}".strip())
    if so_api:
        obs.append("O Mercado Livre bloqueou a leitura simples de páginas em algumas rodadas; o bot usou o Chrome ou só a API.")
    for plat, v in geral_plataforma.items():
        if v and not any(p[1] == plat for p in posts):
            obs.append(f"{_LOJAS.get(plat, plat)} trouxe em média {statistics.mean(v):.0f} ofertas por rodada mas **não postou nada** no período: "
                       "só passa vendedor verificado (na Shopee, só Shopee Mall) e o que já saiu nos últimos dias fica de fora.")
        if v and sum(1 for x in v if x == 0) / len(v) > 0.3:
            obs.append(f"{_LOJAS.get(plat, plat)} não trouxe nenhuma oferta em {sum(1 for x in v if x == 0)} de {len(v)} rodadas.")
    L += ["## Observações automáticas", ""] + ([f"- {o}" for o in obs] or ["Nada fora do normal."]) + [""]

    linhas_csv = [(p[4], nomes.get(_canal_de(p[0]), _canal_de(p[0])), _LOJAS.get(p[1], p[1]), p[2], p[3], p[6], p[5],
                   {1: "sim", 0: "não"}.get(p[7], "")) for p in posts]
    return "\n".join(L), linhas_csv


def _inline(t: str) -> str:
    """Markdown inline (negrito, itálico, código) -> marcação do reportlab."""
    t = t.encode("cp1252", "ignore").decode("cp1252").strip()  # fontes padrão do PDF: sem emojis/símbolos fora do Latin-1
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", t)
    t = re.sub(r"(?<![\w*])[_*]([^_*]+)[_*](?![\w*])", r"<i>\1</i>", t)
    return t


def _estilos():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    base = getSampleStyleSheet()["BodyText"]
    return {
        "p": ParagraphStyle("p", parent=base, fontSize=9.5, leading=13),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=2),
        "li": ParagraphStyle("li", parent=base, fontSize=9.5, leading=13, leftIndent=14, bulletIndent=4),
        "li2": ParagraphStyle("li2", parent=base, fontSize=9.5, leading=13, leftIndent=28, bulletIndent=18),
        "cel": ParagraphStyle("cel", parent=base, fontSize=8, leading=10),
        "celh": ParagraphStyle("celh", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10),
        "code": ParagraphStyle("code", parent=base, fontName="Courier", fontSize=8.5, leading=10.5),
    }


def _tabela_pdf(cabecalho: list[str], linhas: list[list[str]], largura: float, est, pesos: list[float] | None = None):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle
    dados = [[Paragraph(_inline(str(c)), est["celh"]) for c in cabecalho]]
    dados += [[Paragraph(_inline(str(c)), est["cel"]) for c in l] for l in linhas]
    pesos = pesos or [1] * len(cabecalho)
    t = Table(dados, colWidths=[largura * w / sum(pesos) for w in pesos], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eaf0")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b0b4c0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _pdf(arquivo: Path, titulo: str, elementos_fn, paisagem: bool = False) -> None:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate
    tam = landscape(A4) if paisagem else A4
    doc = SimpleDocTemplate(str(arquivo), pagesize=tam, title=titulo, author="Bot de Ofertas",
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    est = _estilos()
    doc.build(elementos_fn(tam[0] - 3 * cm, est))


def _md_para_pdf(texto: str, arquivo: Path) -> None:
    """Converte o markdown deste relatório (títulos, tabelas, listas, bloco de código) em PDF."""
    from reportlab.platypus import Paragraph, Preformatted, Spacer

    def elementos(larg, est):
        out, linhas, i = [], texto.split("\n"), 0
        while i < len(linhas):
            ln = linhas[i]
            if ln.startswith("```"):
                bloco = []
                i += 1
                while i < len(linhas) and not linhas[i].startswith("```"):
                    bloco.append(linhas[i].replace("█", "#"))
                    i += 1
                out.append(Preformatted("\n".join(bloco), est["code"]))
            elif ln.startswith("|"):
                tab = []
                while i < len(linhas) and linhas[i].startswith("|"):
                    tab.append([c.strip() for c in linhas[i].strip().strip("|").split("|")])
                    i += 1
                i -= 1
                out += [_tabela_pdf(tab[0], tab[2:], larg, est), Spacer(1, 6)]
            elif ln.startswith("### "):
                out.append(Paragraph(_inline(ln[4:]), est["h3"]))
            elif ln.startswith("## "):
                out.append(Paragraph(_inline(ln[3:]), est["h2"]))
            elif ln.startswith("# "):
                out.append(Paragraph(_inline(ln[2:]), est["h1"]))
            elif ln.lstrip().startswith("- "):
                fundo = ln.startswith("  ")
                out.append(Paragraph(_inline(ln.lstrip()[2:]), est["li2" if fundo else "li"], bulletText="•" if not fundo else "–"))
            elif ln.strip():
                out.append(Paragraph(_inline(ln), est["p"]))
            else:
                out.append(Spacer(1, 4))
            i += 1
        return out

    _pdf(arquivo, texto.split("\n", 1)[0].lstrip("# "), elementos)


def _posts_para_pdf(linhas: list[tuple], arquivo: Path, titulo: str) -> None:
    from reportlab.platypus import Paragraph, Spacer

    def elementos(larg, est):
        out = [Paragraph(_inline(titulo), est["h1"]), Spacer(1, 4)]
        if not linhas:
            return out + [Paragraph("Nenhum post no período.", est["p"])]
        dados = [[str(d)[:16].replace("T", " "), canal, loja, t, _brl(p), _brl(po), f"{d_ or 0}%", of]
                 for d, canal, loja, t, p, po, d_, of in linhas]
        return out + [_tabela_pdf(["Data/hora", "Canal", "Loja", "Título", "Preço", "Preço original", "Desc.", "Oficial"],
                                  dados, larg, est, pesos=[2.2, 2, 1.8, 9, 2, 2.2, 1.1, 1.2])]

    _pdf(arquivo, titulo, elementos, paisagem=True)


def gerar(dias: int = 1) -> tuple[Path, Path]:
    """Gera o relatório dos últimos `dias` (1 = hoje) e devolve (PDF do relatório, PDF com todos os posts)."""
    agora = dt.datetime.now()
    desde = (agora - dt.timedelta(days=max(1, dias) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    texto, linhas = montar(desde, agora)
    PASTA.mkdir(parents=True, exist_ok=True)
    sufixo = f"{agora:%Y-%m-%d}" if dias <= 1 else f"{agora:%Y-%m-%d}_{dias}dias"
    rel, posts = PASTA / f"relatorio-{sufixo}.pdf", PASTA / f"posts-{sufixo}.pdf"
    _md_para_pdf(texto, rel)
    _posts_para_pdf(linhas, posts, f"Posts — {desde:%d/%m/%Y} a {agora:%d/%m/%Y}")
    return rel, posts

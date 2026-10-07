import asyncio
import logging
import random
import re
import time
import unicodedata
from collections import Counter
from dataclasses import replace

from telegram import Bot
from telegram.error import NetworkError, TimedOut

from . import db
from .canais import Canal
from .nichos import exige_loja_confiavel, relevante
from .config import config, dentro_do_horario
from .models import Oferta
from .sources import amazon, mercadolivre, mercadolivre_api, shopee
from .telegram_poster import postar_oferta

log = logging.getLogger("ofertas.pipeline")
DIAS_SIMILAR = 7  # não repete o mesmo produto (mesmo de outro vendedor, com outro título) no canal por este tempo


_estado = {"ml_bloqueado": False}


def coletar() -> list[Oferta]:
    """Busca ofertas nas fontes automáticas ativas (sem link de afiliado ainda, no caso do ML)."""
    todas: list[Oferta] = []

    if config.fonte_shopee.get("ativa"):
        if config.shopee_app_id and config.shopee_app_secret:
            try:
                todas += shopee.buscar_ofertas(int(config.fonte_shopee.get("limite", 30)))
            except Exception as e:
                log.error("Shopee: %s", e)
        else:
            log.warning("Shopee ativa no config.yaml mas sem credenciais no .env — pulando")

    if config.fonte_amazon.get("ativa"):
        if config.amazon_tag:
            try:
                todas += amazon.buscar_ofertas()
            except Exception as e:
                log.error("Amazon: %s", e)
        else:
            log.warning("Amazon ativa no config.yaml mas sem AMAZON_TAG no .env — pulando")

    if config.fonte_ml.get("ativa"):
        if mercadolivre.tem_sessao():
            try:
                todas += mercadolivre.buscar_ofertas()
                _estado["ml_bloqueado"] = False
            except mercadolivre.BloqueioML as e:
                log.warning("%s — seguindo só com a API oficial", e)
                db.registrar_evento("ml_bloqueio", str(e))
                _estado["ml_bloqueado"] = True
            except Exception as e:
                log.error("Mercado Livre: %s", e)
            if mercadolivre_api.disponivel():
                try:
                    todas += mercadolivre_api.buscar_rodada()
                except Exception as e:
                    log.error("Mercado Livre (API): %s", e)
        else:
            log.warning("Mercado Livre ativo mas sem sessão de afiliado — rode: uv run python -m ofertas ml-login")

    por_plataforma = {o.plataforma for o in todas}
    ativas = [("shopee", config.shopee_app_id and config.shopee_app_secret and config.fonte_shopee.get("ativa")),
              ("amazon", config.amazon_tag and config.fonte_amazon.get("ativa")),
              ("mercadolivre", mercadolivre.tem_sessao() and config.fonte_ml.get("ativa"))]
    for nome, ligada in ativas:
        if ligada and nome not in por_plataforma:
            db.registrar_evento(f"fonte_vazia:{nome}")
    return todas


def filtrar(ofertas: list[Oferta], canal: Canal | None = None, motivos: Counter | None = None) -> list[Oferta]:
    """Ofertas que servem para o canal: relevantes ao nicho, não repetidas, com desconto e preço ok.
    `motivos` (opcional) conta por que cada oferta foi descartada, para o relatório."""
    def no(motivo: str) -> None:
        if motivos is not None:
            motivos[motivo] += 1

    canal_id = canal.id if canal else "principal"
    nichos = canal.nichos if canal else []
    palavras = canal.palavras if canal else []
    excluir = canal.excluir if canal else []
    desconto_min = canal.desconto_minimo if canal and canal.desconto_minimo is not None else config.desconto_minimo
    exige_loja = _exige_loja(canal)
    dias = max(DIAS_SIMILAR, config.nao_repetir_dias)
    recentes = [(_nucleo(t), p) for t, p in db.produtos_recentes(canal_id, dias)]
    aprovadas = []
    for o in ofertas:
        if not o.titulo:
            continue
        if not relevante(o.titulo, nichos, palavras, excluir, o.categoria):
            no("fora_do_nicho")
            continue
        if exige_loja and not _loja_aceita(o):
            no("vendedor_nao_verificado")
            continue  # só vendedor verificado (loja oficial)
        if _repetido(_nucleo(o.titulo), o.preco, recentes):
            no("mesmo_produto_ja_postado")
            continue  # o mesmo produto (outro vendedor, cor, tamanho) que este canal já postou há pouco
        if db.ja_postada(f"{canal_id}|{o.uid}", config.nao_repetir_dias):
            no("ja_postado")
            continue
        if desconto_min and (o.desconto or 0) < desconto_min:
            if not (canal and canal.aceitar_sem_desconto and not o.desconto and _muito_vendido(o)):
                no("desconto_baixo")
                continue
        if config.desconto_maximo and (o.desconto or 0) > config.desconto_maximo:
            no("desconto_suspeito")
            continue  # desconto irreal: quase sempre preço "de" inflado
        # nota/vendas desconhecidas (a fonte não informa) não reprovam; só as conhecidas e baixas
        if config.nota_minima and o.nota is not None and o.nota < config.nota_minima:
            no("nota_baixa")
            continue
        if config.vendas_minimas and o.vendas is not None and o.vendas < config.vendas_minimas:
            no("poucas_vendas")
            continue
        if o.preco is not None:
            if config.preco_minimo and o.preco < config.preco_minimo:
                no("preco_fora_da_faixa")
                continue
            if config.preco_maximo and o.preco > config.preco_maximo:
                no("preco_fora_da_faixa")
                continue
        titulo = o.titulo.lower()
        if any(p in titulo for p in config.palavras_bloqueadas):
            no("palavra_bloqueada")
            continue
        aprovadas.append(o)
    return aprovadas


def _exige_loja(canal: Canal | None) -> bool:
    """Todo canal exige vendedor verificado (config.exigir_loja_oficial), salvo os que optaram por aceitar
    vendedor comum. Nichos sensíveis a falsificação (perfumes) exigem sempre."""
    if canal is None:
        return config.exigir_loja_oficial
    if exige_loja_confiavel(canal.nichos):
        return True
    return config.exigir_loja_oficial and not canal.aceitar_loja_comum


def _loja_aceita(o: Oferta) -> bool:
    """Vendedor verificado. A Amazon só se confirma na página do produto, feito logo antes de postar."""
    return o.loja_confiavel is True or (o.loja_confiavel is None and o.plataforma == "amazon")


def _muito_vendido(o: Oferta) -> bool:
    """Para canais que aceitam produto sem desconto listado: só os campeões de venda e bem avaliados."""
    return o.mais_vendido or ((o.nota is None or o.nota >= 4.5) and (o.vendas or 0) >= 500)


def _chave_similar(titulo: str) -> str:
    """Variações do mesmo produto (cor, tamanho) costumam repetir as primeiras palavras."""
    return " ".join(re.findall(r"\w+", titulo.lower())[:5])


# palavras que enchem título de marketplace e não dizem qual é o produto
_RUIDO = set("""
kit jogo conjunto combo de da do das dos com sem para por em e a o um uma ao na no nas nos ou
peca unidade unidades original originais profissional completo completa premium novo nova promocao oferta
frete gratis barato qualidade alta alto resistente multiuso universal importado importada lancamento
top super reforcado reforcada portatil recarregavel potente forte leve pratico pratica ideal
masculino masculina feminino feminina unissex adulto cor cores sortido sortida varios varias
""".split())


def _nucleo(titulo: str) -> frozenset[str]:
    """As palavras que identificam o produto: sem acento, no singular, sem números soltos nem palavras
    de enfeite. "40 Peças / 46 Peças Jogo De Chave Catraca..." e "Kit Jogo 46 Peças Chaves Soquetes
    Catraca..." viram quase o mesmo conjunto: é o mesmo kit de outro vendedor."""
    t = unicodedata.normalize("NFKD", titulo.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palavras = set()
    for p in re.findall(r"[a-z0-9]+", t):
        if p.isdigit() or len(p) < 3 or re.fullmatch(r"\d+[a-z]{1,3}", p):
            continue  # quantidades e medidas (46 peças, 1/4, 100ml, 12v) não distinguem o produto
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        if p not in _RUIDO:
            palavras.add(p)
    return frozenset(palavras)


def _parecidos(a: frozenset[str], b: frozenset[str]) -> bool:
    """Títulos com muitas palavras em comum (Jaccard) ou um quase todo contido no outro?"""
    inter = len(a & b)
    if not inter:
        return False
    if inter / len(a | b) >= 0.5:
        return True
    menor = min(len(a), len(b))
    return menor >= 3 and inter / menor >= 0.65


def _mesmo_produto(a: frozenset[str], preco_a: float | None, b: frozenset[str], preco_b: float | None) -> bool:
    """Mesmo produto = título quase igual, ou título parecido E preço parecido. O mesmo kit anunciado por
    vendedores diferentes tem título diferente mas preço igual; uma marca ou versão diferente (outro
    perfume da mesma casa, outro auxiliar de partida) custa outra coisa e pode aparecer."""
    if not _parecidos(a, b):
        return False
    inter, uniao = len(a & b), len(a | b)
    if inter / uniao >= 0.75:
        return True  # praticamente o mesmo título
    if preco_a and preco_b:
        return abs(preco_a - preco_b) / max(preco_a, preco_b) <= 0.20
    return False


def _repetido(nucleo: frozenset[str], preco: float | None, outros) -> bool:
    """`outros`: lista de (núcleo, preço) do que já saiu."""
    return any(_mesmo_produto(nucleo, preco, n, p) for n, p in outros)


def escolher(ofertas: list[Oferta], n: int) -> list[Oferta]:
    """Top N por desconto, alternando plataformas e pulando variações do mesmo produto."""
    filas: dict[str, list[Oferta]] = {}
    for o in sorted(ofertas, key=lambda o: o.desconto or 0, reverse=True):
        filas.setdefault(o.plataforma, []).append(o)
    ordem = sorted(filas.values(), key=lambda f: f[0].desconto or 0, reverse=True)
    escolhidas: list[Oferta] = []
    vistas: list[tuple[frozenset[str], float | None]] = []
    while len(escolhidas) < n and any(ordem):
        for fila in ordem:
            while fila:
                o = fila.pop(0)
                nucleo = _nucleo(o.titulo)
                if not _repetido(nucleo, o.preco, vistas):
                    vistas.append((nucleo, o.preco))
                    escolhidas.append(o)
                    break
            if len(escolhidas) >= n:
                break
    return escolhidas


_ultimo_aviso: dict[str, float] = {}
_ciclos_vazios = 0


async def avisar_dono(bot: Bot, texto: str, repetir_apos_h: float = 6) -> None:
    """Manda um aviso no privado do dono (se configurado). O mesmo aviso só se repete após N horas."""
    if not config.owner_id:
        return
    agora = time.time()
    if agora - _ultimo_aviso.get(texto, 0) < repetir_apos_h * 3600:
        return
    _ultimo_aviso[texto] = agora
    try:
        await bot.send_message(config.owner_id, texto)
    except Exception as e:
        log.warning("Não consegui avisar o dono: %s", e)


def _tag_amazon(url: str, tag: str) -> str:
    """Troca a tag de afiliado do link da Amazon (para medir cada canal em separado)."""
    return re.sub(r"([?&]tag=)[^&#]+", lambda m: m.group(1) + tag, url) if tag else url


LOTE = 3  # ofertas por canal em cada passada (o ML gera os links do lote de uma vez só)


def _pausa(base: float) -> float:
    """Intervalo entre dois posts com variação (±X%), para não postar como um relógio: canais de
    promoção de verdade têm ritmo irregular (4 a 6 min, às vezes uma pausa maior)."""
    v = max(0.0, min(0.9, config.variacao_espacamento / 100))
    return base * random.uniform(1 - v, 1 + v)


def _prazo_ciclo() -> float:
    """Até quando esta rodada pode continuar postando; o que sobrar fica para a próxima."""
    if config.intervalo_minutos <= 0:
        return float("inf")
    return time.monotonic() + max(300, config.intervalo_minutos * 60 - 90)


async def executar_ciclo(bot: Bot) -> int:
    """Uma rodada: coleta (uma vez) e, enquanto houver oferta válida para algum canal e tempo,
    posta em lotes espaçados. Sem teto de posts (a menos que o config.yaml defina um)."""
    if not dentro_do_horario():
        log.info("Fora do horário ativo (%s) — ciclo pulado", config.horario_ativo)
        return 0
    canais = config.canais
    if not canais:
        log.warning("Nenhum canal ativo — crie um no painel (seção Canais)")
        return 0

    prazo = _prazo_ciclo()
    brutas = await asyncio.to_thread(coletar)
    await asyncio.to_thread(db.registrar_precos, brutas)
    global _ciclos_vazios
    _ciclos_vazios = 0 if brutas else _ciclos_vazios + 1
    if _ciclos_vazios >= 3:
        await avisar_dono(bot, "⚠️ 3 rodadas seguidas sem coletar nenhuma oferta "
                               "(fontes bloqueadas, fora do ar ou sem sessão?). Veja o log do bot.")
    if _estado["ml_bloqueado"]:
        await avisar_dono(bot, "⚠️ O Mercado Livre bloqueou a leitura da página de ofertas neste PC (tráfego suspeito). "
                               "O bot segue com a API oficial do ML, Shopee e Amazon. Costuma liberar sozinho; "
                               "se durar dias, abra mercadolivre.com.br/ofertas no navegador e resolva a verificação.",
                          repetir_apos_h=12)
    motivos = {c.id: Counter() for c in canais}
    boas = {c.id: filtrar(brutas, c, motivos[c.id]) for c in canais}
    total_boas = {c.id: len(boas[c.id]) for c in canais}

    def _etiqueta(c: Canal) -> str:
        return c.ml_etiqueta or config.ml_etiqueta

    limite = {c.id: c.max_posts_por_ciclo or config.max_posts_por_ciclo for c in canais}  # 0 = sem limite
    por_canal = {c.id: 0 for c in canais}
    chaves_postadas: dict[str, list[tuple[frozenset[str], float | None]]] = {c.id: [] for c in canais}  # produtos já postados nesta rodada
    ml_ok = True
    postadas = 0

    while time.monotonic() < prazo:
        # próximo lote de cada canal (respeitando o teto opcional)
        lote: dict[str, list[Oferta]] = {}
        for c in canais:
            boas[c.id] = [o for o in boas[c.id] if not _repetido(_nucleo(o.titulo), o.preco, chaves_postadas[c.id])
                          and (ml_ok or o.plataforma != "mercadolivre")]
            n = LOTE if not limite[c.id] else min(LOTE, limite[c.id] - por_canal[c.id])
            lote[c.id] = escolher(boas[c.id], n) if n > 0 else []
        if not any(lote.values()):
            break

        # Mercado Livre: link de afiliado só do lote (o linkbuilder é caro). Cada canal pode ter a sua
        # etiqueta, o que separa o desempenho por nicho no painel de afiliados do ML.
        grupos: dict[str, dict[str, Oferta]] = {}  # etiqueta -> uid -> cópia da oferta
        for c in canais:
            for o in lote[c.id]:
                if o.plataforma == "mercadolivre":
                    grupos.setdefault(_etiqueta(c), {})[o.uid] = replace(o, url_afiliado="")
        links: dict[tuple[str, str], str] = {}  # (canal_id, uid) -> link de afiliado do ML
        if grupos:
            try:
                await asyncio.to_thread(mercadolivre.gerar_links_por_etiqueta,
                                        {e: list(g.values()) for e, g in grupos.items()})
                for c in canais:
                    for o in lote[c.id]:
                        if o.plataforma == "mercadolivre":
                            links[(c.id, o.uid)] = grupos[_etiqueta(c)][o.uid].url_afiliado
            except Exception as e:
                log.error("Linkbuilder ML falhou: %s", e)
                db.registrar_evento("ml_sessao" if "Sessão" in str(e) else "ml_link_falhou", str(e))
                if "Sessão" in str(e):
                    await avisar_dono(bot, f"⚠️ Mercado Livre parou de gerar links: {e}")
                ml_ok = False  # sem link não há post: tira o ML do páreo e escolhe de novo
                continue

        # intercala os canais (1º de cada, 2º de cada...) para o feed de todos andar junto
        fila: list[tuple[Canal, Oferta]] = []
        for i in range(max(len(v) for v in lote.values())):
            fila += [(c, lote[c.id][i]) for c in canais if i < len(lote[c.id])]

        # cada canal recebe um post a cada `espacamento_segundos`; com vários canais ativos, eles se intercalam
        base_pausa = max(20.0, config.espacamento_segundos / max(1, len({c.id for c, _ in fila})))
        for c, o in fila:
            # tira da lista de candidatos de qualquer jeito, para a rodada nunca ficar presa numa oferta
            boas[c.id] = [x for x in boas[c.id] if x.uid != o.uid]
            if time.monotonic() >= prazo:
                break
            link = links.get((c.id, o.uid)) or o.url_afiliado
            if o.plataforma == "amazon":
                link = _tag_amazon(link, c.amazon_tag)
            if not link:
                log.warning("Sem link de afiliado, pulando: %s", o.titulo[:60])
                continue
            if _exige_loja(c) and o.loja_confiavel is not True:
                if not await asyncio.to_thread(amazon.vendedor_confiavel, o):
                    log.info("Amazon: vendedor não confirmado como Amazon, pulando (%s): %s", c.nome, o.titulo[:60])
                    motivos[c.id]["amazon_vendedor_nao_confirmado"] += 1
                    continue
                o = replace(o, loja_confiavel=True, extra=" · ".join(x for x in (o.extra, "📦 Vendido pela Amazon") if x))
            if postadas:
                await asyncio.sleep(_pausa(base_pausa))  # ritmo entre posts: não despeja tudo de uma vez
            chave = f"{c.id}|{o.uid}"
            db.registrar(o, c.id)  # antes de postar: se o processo cair no meio, não reposta
            try:
                extras = {"cupom": c.cupom} if c.cupom and o.plataforma == "mercadolivre" and not o.cupom else {}
                await postar_oferta(bot, replace(o, url_afiliado=link, **extras), c.chat_id)
            except (NetworkError, TimedOut) as e:
                # queda de conexão: não é problema do canal. A oferta volta na próxima rodada e o aviso é raro
                log.error("Falha de rede ao postar '%s' em %s: %s", o.titulo[:60], c.nome, e)
                db.esquecer(chave)
                db.registrar_evento("falha_rede", f"{c.id}: {e}")
                await avisar_dono(bot, "⚠️ A conexão com o Telegram caiu e algumas postagens falharam. "
                                       "Elas serão tentadas de novo na próxima rodada. Se isso se repetir muito, "
                                       "verifique a internet, a VPN ou o antivírus do PC.", repetir_apos_h=3)
                continue
            except Exception as e:
                log.error("Falha ao postar '%s' em %s: %s", o.titulo[:60], c.nome, e)
                db.esquecer(chave)
                db.registrar_evento("falha_post", f"{c.id}: {e}")
                await avisar_dono(bot, f"⚠️ Não consegui postar no canal {c.rotulo}: {e}\n"
                                       "Confira se o bot é administrador do canal e se o ID está certo.")
                continue
            postadas += 1
            por_canal[c.id] += 1
            chaves_postadas[c.id].append((_nucleo(o.titulo), o.preco))

    sobrou = {c.id: len(boas[c.id]) for c in canais}
    detalhe = {c.id: {"boas": total_boas[c.id], "postadas": por_canal[c.id], "descartes": dict(motivos[c.id])}
               for c in canais}
    detalhe["_geral"] = {"por_plataforma": dict(Counter(o.plataforma for o in brutas)),
                         "ml_so_pela_api": bool(_estado["ml_bloqueado"])}
    db.registrar_ciclo(len(brutas), postadas, detalhe)
    log.info("Ciclo: %d coletadas | %s | %d postadas%s", len(brutas),
             ", ".join(f"{c.nome}: {total_boas[c.id]} boas, {por_canal[c.id]} postadas" for c in canais), postadas,
             " | ficaram para a próxima rodada: " + ", ".join(f"{k}={v}" for k, v in sobrou.items() if v)
             if any(sobrou.values()) and time.monotonic() >= prazo else "")
    return postadas

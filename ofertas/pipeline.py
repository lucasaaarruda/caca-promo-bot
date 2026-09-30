import asyncio
import logging
import random
import re
import time
from dataclasses import replace

from telegram import Bot

from . import db
from .canais import Canal
from .nichos import relevante
from .config import config, dentro_do_horario
from .models import Oferta
from .sources import amazon, mercadolivre, mercadolivre_api, shopee
from .telegram_poster import postar_oferta

log = logging.getLogger("ofertas.pipeline")
DIAS_SIMILAR = 2  # não repete a mesma "família" de produto no canal por este tempo


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


def filtrar(ofertas: list[Oferta], canal: Canal | None = None) -> list[Oferta]:
    """Ofertas que servem para o canal: relevantes ao nicho, não repetidas, com desconto e preço ok."""
    canal_id = canal.id if canal else "principal"
    nichos = canal.nichos if canal else []
    palavras = canal.palavras if canal else []
    excluir = canal.excluir if canal else []
    desconto_min = canal.desconto_minimo if canal and canal.desconto_minimo is not None else config.desconto_minimo
    recentes = {_chave_similar(t) for t in db.titulos_recentes(canal_id, DIAS_SIMILAR)}
    aprovadas = []
    for o in ofertas:
        if not o.titulo:
            continue
        if not relevante(o.titulo, nichos, palavras, excluir, o.categoria):
            continue
        if _chave_similar(o.titulo) in recentes:
            continue  # variação (cor/tamanho) de algo que este canal já postou há pouco
        if db.ja_postada(f"{canal_id}|{o.uid}", config.nao_repetir_dias):
            continue
        if desconto_min and (o.desconto or 0) < desconto_min:
            if not (canal and canal.aceitar_sem_desconto and not o.desconto and _muito_vendido(o)):
                continue
        if config.desconto_maximo and (o.desconto or 0) > config.desconto_maximo:
            continue  # desconto irreal: quase sempre preço "de" inflado
        # nota/vendas desconhecidas (a fonte não informa) não reprovam; só as conhecidas e baixas
        if config.nota_minima and o.nota is not None and o.nota < config.nota_minima:
            continue
        if config.vendas_minimas and o.vendas is not None and o.vendas < config.vendas_minimas:
            continue
        if o.preco is not None:
            if config.preco_minimo and o.preco < config.preco_minimo:
                continue
            if config.preco_maximo and o.preco > config.preco_maximo:
                continue
        titulo = o.titulo.lower()
        if any(p in titulo for p in config.palavras_bloqueadas):
            continue
        aprovadas.append(o)
    return aprovadas


def _muito_vendido(o: Oferta) -> bool:
    """Para canais que aceitam produto sem desconto listado: só os campeões de venda e bem avaliados."""
    return o.mais_vendido or ((o.nota is None or o.nota >= 4.5) and (o.vendas or 0) >= 500)


def _chave_similar(titulo: str) -> str:
    """Variações do mesmo produto (cor, tamanho) costumam repetir as primeiras palavras."""
    return " ".join(re.findall(r"\w+", titulo.lower())[:5])


def escolher(ofertas: list[Oferta], n: int) -> list[Oferta]:
    """Top N por desconto, alternando plataformas e pulando variações do mesmo produto."""
    filas: dict[str, list[Oferta]] = {}
    for o in sorted(ofertas, key=lambda o: o.desconto or 0, reverse=True):
        filas.setdefault(o.plataforma, []).append(o)
    ordem = sorted(filas.values(), key=lambda f: f[0].desconto or 0, reverse=True)
    escolhidas: list[Oferta] = []
    vistas: set[str] = set()
    while len(escolhidas) < n and any(ordem):
        for fila in ordem:
            while fila:
                o = fila.pop(0)
                chave = _chave_similar(o.titulo)
                if chave not in vistas:
                    vistas.add(chave)
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
    boas = {c.id: filtrar(brutas, c) for c in canais}
    total_boas = {c.id: len(boas[c.id]) for c in canais}

    def _etiqueta(c: Canal) -> str:
        return c.ml_etiqueta or config.ml_etiqueta

    limite = {c.id: c.max_posts_por_ciclo or config.max_posts_por_ciclo for c in canais}  # 0 = sem limite
    por_canal = {c.id: 0 for c in canais}
    chaves_postadas: dict[str, set[str]] = {c.id: set() for c in canais}  # variações já postadas nesta rodada
    ml_ok = True
    postadas = 0

    while time.monotonic() < prazo:
        # próximo lote de cada canal (respeitando o teto opcional)
        lote: dict[str, list[Oferta]] = {}
        for c in canais:
            boas[c.id] = [o for o in boas[c.id] if _chave_similar(o.titulo) not in chaves_postadas[c.id]
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
            if postadas:
                await asyncio.sleep(_pausa(base_pausa))  # ritmo entre posts: não despeja tudo de uma vez
            chave = f"{c.id}|{o.uid}"
            db.registrar(o, c.id)  # antes de postar: se o processo cair no meio, não reposta
            try:
                await postar_oferta(bot, replace(o, url_afiliado=link), c.chat_id)
            except Exception as e:
                log.error("Falha ao postar '%s' em %s: %s", o.titulo[:60], c.nome, e)
                db.esquecer(chave)
                db.registrar_evento("falha_post", f"{c.id}: {e}")
                await avisar_dono(bot, f"⚠️ Não consegui postar no canal {c.rotulo}: {e}\n"
                                       "Confira se o bot é administrador do canal e se o ID está certo.")
                continue
            postadas += 1
            por_canal[c.id] += 1
            chaves_postadas[c.id].add(_chave_similar(o.titulo))

    sobrou = {c.id: len(boas[c.id]) for c in canais}
    db.registrar_ciclo(len(brutas), postadas,
                       {c.id: {"boas": total_boas[c.id], "postadas": por_canal[c.id]} for c in canais})
    log.info("Ciclo: %d coletadas | %s | %d postadas%s", len(brutas),
             ", ".join(f"{c.nome}: {total_boas[c.id]} boas, {por_canal[c.id]} postadas" for c in canais), postadas,
             " | ficaram para a próxima rodada: " + ", ".join(f"{k}={v}" for k, v in sobrou.items() if v)
             if any(sobrou.values()) and time.monotonic() >= prazo else "")
    return postadas

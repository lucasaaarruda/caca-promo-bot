import asyncio
import logging
import re
import time

from telegram import Bot

from . import db
from .canais import Canal
from .nichos import relevante
from .config import config, dentro_do_horario
from .models import Oferta
from .sources import amazon, mercadolivre, shopee
from .telegram_poster import postar_oferta

log = logging.getLogger("ofertas.pipeline")


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
        else:
            log.warning("Mercado Livre ativo mas sem sessão de afiliado — rode: uv run python -m ofertas ml-login")

    return todas


def filtrar(ofertas: list[Oferta], canal: Canal | None = None) -> list[Oferta]:
    """Ofertas que servem para o canal: relevantes ao nicho, não repetidas, com desconto e preço ok."""
    canal_id = canal.id if canal else "principal"
    nichos = canal.nichos if canal else []
    palavras = canal.palavras if canal else []
    excluir = canal.excluir if canal else []
    desconto_min = canal.desconto_minimo if canal and canal.desconto_minimo is not None else config.desconto_minimo
    aprovadas = []
    for o in ofertas:
        if not o.titulo:
            continue
        if not relevante(o.titulo, nichos, palavras, excluir):
            continue
        if db.ja_postada(f"{canal_id}|{o.uid}", config.nao_repetir_dias):
            continue
        if desconto_min and (o.desconto or 0) < desconto_min:
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


async def executar_ciclo(bot: Bot) -> int:
    """Um ciclo completo: coletar (uma vez) -> por canal: filtrar e escolher -> links -> postar."""
    if not dentro_do_horario():
        log.info("Fora do horário ativo (%s) — ciclo pulado", config.horario_ativo)
        return 0
    canais = config.canais
    if not canais:
        log.warning("Nenhum canal ativo — crie um no painel (seção Canais)")
        return 0

    brutas = await asyncio.to_thread(coletar)
    boas = {c.id: filtrar(brutas, c) for c in canais}

    def _escolher() -> dict[str, list[Oferta]]:
        return {c.id: escolher(boas[c.id], c.max_posts_por_ciclo or config.max_posts_por_ciclo)
                for c in canais}

    escolhidas = _escolher()

    # Mercado Livre: gerar link de afiliado só das escolhidas (linkbuilder é caro)
    ml_pendentes = {o.uid: o for lst in escolhidas.values() for o in lst
                    if o.plataforma == "mercadolivre" and not o.url_afiliado}
    if ml_pendentes:
        try:
            await asyncio.to_thread(mercadolivre.gerar_links_afiliado, list(ml_pendentes.values()))
        except Exception as e:
            log.error("Linkbuilder ML falhou: %s", e)
            if "Sessão" in str(e):
                await avisar_dono(bot, f"⚠️ Mercado Livre parou de gerar links: {e}")
            # sem link não há post: tira o ML do páreo e escolhe de novo, para não desperdiçar vagas
            for c in canais:
                boas[c.id] = [o for o in boas[c.id] if o.plataforma != "mercadolivre" or o.url_afiliado]
            escolhidas = _escolher()

    # intercala os canais (1º de cada, 2º de cada...) para o feed de todos andar junto
    fila: list[tuple[Canal, Oferta]] = []
    for i in range(max((len(v) for v in escolhidas.values()), default=0)):
        fila += [(c, escolhidas[c.id][i]) for c in canais if i < len(escolhidas[c.id])]

    pausa = max(20, config.espacamento_segundos // max(1, len(canais)))
    postadas = 0
    for n, (c, o) in enumerate(fila):
        if not o.url_afiliado:
            log.warning("Sem link de afiliado, pulando: %s", o.titulo[:60])
            continue
        chave = f"{c.id}|{o.uid}"
        db.registrar(o, c.id)  # antes de postar: se o processo cair no meio, não reposta
        try:
            await postar_oferta(bot, o, c.chat_id)
        except Exception as e:
            log.error("Falha ao postar '%s' em %s: %s", o.titulo[:60], c.nome, e)
            db.esquecer(chave)
            await avisar_dono(bot, f"⚠️ Não consegui postar no canal {c.rotulo}: {e}\n"
                                   "Confira se o bot é administrador do canal e se o ID está certo.")
            continue
        postadas += 1
        if n < len(fila) - 1:
            await asyncio.sleep(pausa)

    log.info("Ciclo: %d coletadas | %s | %d postadas", len(brutas),
             ", ".join(f"{c.nome}: {len(boas[c.id])} boas" for c in canais), postadas)
    return postadas

import asyncio
import datetime as dt
import html
import logging
import random
import re
import time
import unicodedata
from collections import Counter
from dataclasses import replace

from telegram import Bot
from telegram.error import NetworkError, TimedOut

from . import db, whatsapp
from .canais import Canal
from .nichos import (aceita_amazon_global, dias_sem_repetir, exige_loja_confiavel, parametros_diversidade, prioritaria,
                     relevante, tipo_de)
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
                achadas = amazon.buscar_ofertas()
                amazon.completar_titulos(achadas)
                todas += achadas
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

    for o in todas:
        o.titulo = limpar_titulo(o.titulo)
    por_plataforma = {o.plataforma for o in todas}
    ativas = [("shopee", config.shopee_app_id and config.shopee_app_secret and config.fonte_shopee.get("ativa")),
              ("amazon", config.amazon_tag and config.fonte_amazon.get("ativa")),
              ("mercadolivre", mercadolivre.tem_sessao() and config.fonte_ml.get("ativa"))]
    for nome, ligada in ativas:
        if ligada and nome not in por_plataforma:
            db.registrar_evento(f"fonte_vazia:{nome}")
    return todas


def limpar_titulo(titulo: str | None) -> str | None:
    """Defeitos que as lojas mandam no título: código HTML ("AW#8209;10CWBRVGU02", hífen do Hisense) e gênero
    grudado ("Wrangler AuthenticsMasculino", "ARIATFeminino")."""
    if not titulo:
        return titulo
    t = html.unescape(titulo)
    t = re.sub(r"&?#(\d{2,5});", lambda m: chr(int(m.group(1))), t)  # entidade que chegou sem o "&"
    t = t.replace("‑", "-")
    t = re.sub(r"(?<=[A-Za-zà-ú])(Masculino|Feminino|Unissex|Masculina|Feminina)\b", r" \1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


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
    dias_nicho = dias_sem_repetir(nichos)  # nicho de catálogo pequeno (ar condicionado) repete antes
    dias = dias_nicho or max(DIAS_SIMILAR, config.nao_repetir_dias)
    recentes = [(_nucleo(t), p) for t, p in db.produtos_recentes(canal_id, dias)]
    aprovadas = []
    for o in ofertas:
        if not o.titulo:
            continue
        if o.preco is None:
            no("sem_preco")
            continue  # post sem preço (saiu "Jeans Cinch, Tamanho 28W / 32L" em 20/10): a busca não trouxe o valor
        if not relevante(o.titulo, nichos, palavras, excluir, o.categoria):
            no("fora_do_nicho")
            continue
        if exige_loja and not _loja_aceita(o, canal):
            no("vendedor_nao_verificado")
            continue  # só vendedor verificado (loja oficial)
        if _repetido(_nucleo(o.titulo), o.preco, recentes):
            no("mesmo_produto_ja_postado")
            continue  # o mesmo produto (outro vendedor, cor, tamanho) que este canal já postou há pouco
        if db.ja_postada(f"{canal_id}|{o.uid}", dias_nicho or config.nao_repetir_dias):
            no("ja_postado")
            continue
        dmin = min(desconto_min, DESCONTO_MIN_PRIORITARIO) if desconto_min and prioritaria(o.titulo, nichos) else desconto_min
        if dmin and (o.desconto or 0) < dmin:
            if canal and canal.aceitar_sem_desconto and not o.desconto and _sem_desconto_ok(o, nichos):
                if not _muito_vendido(o) and _preco_alto(o):
                    no("preco_acima_do_menor_visto")
                    continue  # jeans importado sem preço "de": só posta se não estiver caro em relação ao que o bot já viu
            else:
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


def _loja_aceita(o: Oferta, canal: Canal | None = None) -> bool:
    """Vendedor verificado. A Amazon só se confirma na página do produto, feito logo antes de postar.
    MercadoLíder/Loja Indicada conta só para quem aceita esse nível (o global `lojas_confiaveis: oficial+lider`
    ou o canal com `aceitar_lider`)."""
    if o.loja_confiavel is True or (o.loja_confiavel is None and o.plataforma == "amazon"):
        return True
    aceita_lider = config.lojas_confiaveis == "oficial+lider" or (canal is not None and canal.aceitar_lider)
    return bool(aceita_lider and o.vendedor_lider)


def _muito_vendido(o: Oferta) -> bool:
    """Para canais que aceitam produto sem desconto listado: só os campeões de venda e bem avaliados."""
    return o.mais_vendido or ((o.nota is None or o.nota >= 4.5) and (o.vendas or 0) >= 500)


DESCONTO_MIN_PRIORITARIO = 10   # % mínimo do jeans importado quando a loja mostra o preço "de" (o do canal é 20)
TOLERANCIA_PRECO = 1.10         # sem preço "de": no máximo 10% acima do menor preço visto nos últimos 30 dias


def _preco_alto(o: Oferta) -> bool:
    """O preço está bem acima do menor que o bot já viu para este produto (últimos 30 dias)? Só julga com 3 ou
    mais observações; produto novo passa."""
    if not o.preco:
        return False
    vistos = [p for _, p in db.historico_preco(o.uid, 30)]
    return len(vistos) >= 3 and o.preco > TOLERANCIA_PRECO * min(vistos)


def _sem_desconto_ok(o: Oferta, nichos: list[str]) -> bool:
    """Produto sem desconto listado que o canal aceita postar: campeão de vendas, ou o que o nicho mais quer
    (jeans importado Ariat/Cinch/Wrangler no Country). A busca da Amazon não informa vendas nem preço "de": para
    esses jeans vale a nota (quando existe) e o vendedor ser a própria Amazon, conferido antes de postar."""
    if _muito_vendido(o):
        return True
    return (o.plataforma == "amazon" and o.vendas is None and (o.nota is None or o.nota >= 4.3)
            and prioritaria(o.titulo, nichos))


def _chave_similar(titulo: str) -> str:
    """Variações do mesmo produto (cor, tamanho) costumam repetir as primeiras palavras."""
    return " ".join(re.findall(r"\w+", titulo.lower())[:5])


# palavras que enchem título de marketplace e não dizem qual é o produto
_RUIDO = set("""
kit jogo conjunto combo de da do das dos com sem para por em e a o um uma ao na no nas nos ou
peca unidade unidades original originais profissional completo completa premium novo nova promocao oferta
frete gratis barato qualidade alta alto resistente multiuso universal importado importada lancamento
top super reforcado reforcada portatil recarregavel potente forte leve pratico pratica ideal
masculino masculina feminino feminina unissex adulto cor cores sortido sortida varios varias tamanho
""".split())


_RE_TAM = re.compile(r"(?:tamanho|tam)[.:]?\s*(?:no\s+br\s*)?(?P<n>\d{2}|[pgm]{1,2})\b")
_RE_CINTURA = re.compile(r"\b(?P<w>\d{2})\s*w\b")
_RE_COMPRIMENTO = re.compile(r"\b\d{2}\s*w\s*[x/]\s*(?P<l>\d{2})l?\b")


def _tamanho_calca(t: str) -> str:
    """Tamanho de calça/jeans no título já normalizado ("Tamanho 42 BR (32W x 36L), barra longa" -> "42|32w|36l|longa").
    Cada tamanho é um anúncio diferente e vende separado: quem procura o 44 não quer ver o 42."""
    if not re.search(r"\b(?:calca|jeans)\b", t):
        return ""
    partes = []
    if m := _RE_TAM.search(t):
        partes.append(m.group("n"))
    if m := _RE_CINTURA.search(t):
        partes.append(m.group("w") + "w")
    if m := _RE_COMPRIMENTO.search(t):
        partes.append(m.group("l") + "l")
    if m := re.search(r"barra\s+(regular|longa|curta)", t):
        partes.append(m.group(1))
    return "|".join(partes)


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
        if m := re.fullmatch(r"\d{1,2}([a-z]{4,})", p):
            p = m.group(1)  # quantidade grudada na palavra: "2Serra Mármore" -> "serra"
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        if p not in _RUIDO:
            palavras.add(p)
    if tam := _tamanho_calca(t):
        palavras.add("@tam:" + tam)  # marcador de tamanho: jeans de tamanhos diferentes não são "o mesmo produto"
    return frozenset(palavras)


def _parecidos(a: frozenset[str], b: frozenset[str]) -> bool:
    """Títulos com muitas palavras em comum (Jaccard) ou um quase todo contido no outro? O marcador de tamanho fica
    de fora (é tratado à parte): com ele, Ariat M5 Adkins e M7 Wessley no mesmo tamanho pareciam o mesmo jeans."""
    a = frozenset(p for p in a if not p.startswith("@"))
    b = frozenset(p for p in b if not p.startswith("@"))
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
    tam_a = next((p for p in a if p.startswith("@tam:")), None)
    tam_b = next((p for p in b if p.startswith("@tam:")), None)
    if tam_a and tam_b and tam_a != tam_b:
        return False  # mesmo jeans em outro tamanho: anúncio próprio, sai um post por tamanho
    preco_parecido = bool(preco_a and preco_b and abs(preco_a - preco_b) / max(preco_a, preco_b) <= 0.20)
    if preco_parecido and _mesmo_modelo(a, b):
        return True  # "2Serra Mármore ... 4100NH3ZX2 Makita" e "Serra Makita 4100nh3zx Mármore": títulos diferentes, mesmo modelo
    if not _parecidos(a, b):
        return False
    inter, uniao = len(a & b), len(a | b)
    if inter / uniao >= 0.75:
        return True  # praticamente o mesmo título
    return preco_parecido


def _codigos(nucleo: frozenset[str]) -> set[str]:
    """Códigos de modelo do título (letras e números, 6+ caracteres: 4100nh3zx2, smv1300s). Medida de pneu
    (55r16) não é modelo: pneus de marcas diferentes têm a mesma."""
    return {p for p in nucleo if len(p) >= 6 and re.search(r"\d", p) and re.search(r"[a-z]", p)
            and not re.fullmatch(r"\d{2,3}r\d{2}", p) and not p.startswith("@")}


def _mesmo_modelo(a: frozenset[str], b: frozenset[str]) -> bool:
    """Os dois títulos citam o mesmo código de modelo (igual, ou um é o outro com 1-2 caracteres a mais)?"""
    return any(x == y or (x.startswith(y) or y.startswith(x)) and abs(len(x) - len(y)) <= 2
               for x in _codigos(a) for y in _codigos(b))


def _repetido(nucleo: frozenset[str], preco: float | None, outros) -> bool:
    """`outros`: lista de (núcleo, preço) do que já saiu."""
    return any(_mesmo_produto(nucleo, preco, n, p) for n, p in outros)


# (tipo, família, instante) do que o canal já postou: base da regra de variedade
Historico = list[tuple[str, str, float]]

MAX_TAMANHOS_DIA = 3  # o mesmo jeans em tamanhos diferentes: no máximo 3 por dia, nunca dois seguidos


def _modelo(titulo: str) -> frozenset[str]:
    """O produto sem o tamanho: os 7 tamanhos do mesmo jeans dão o mesmo modelo."""
    return frozenset(p for p in _nucleo(titulo) if not p.startswith("@tam:"))


def _excesso_de_tamanhos(titulo: str, modelos: list[frozenset[str]]) -> bool:
    """`modelos`: o que o canal postou nas últimas 24h, do mais antigo ao mais novo. Na noite de 19/10 saíram 7
    tamanhos do mesmo Rock & Roll Double Barrel em 18 minutos: cada tamanho é um anúncio, mas em sequência vira spam."""
    if not any(p.startswith("@tam:") for p in _nucleo(titulo)):
        return False
    m = _modelo(titulo)
    igual = lambda x: bool(x) and len(m & x) / len(m | x) >= 0.75
    return bool(modelos) and igual(modelos[-1]) or sum(1 for x in modelos if igual(x)) >= MAX_TAMANHOS_DIA


def carregar_modelos(canal: Canal | None) -> list[frozenset[str]]:
    """Modelos (título sem tamanho) do que o canal postou nas últimas 24h, em ordem."""
    return [_modelo(t) for t, _ in db.historico_canal(canal.id, 24)] if canal else []


def carregar_historico(canal: Canal | None) -> Historico:
    """O que o canal postou nas últimas 24h (do banco), já classificado em tipo e família."""
    if canal is None or parametros_diversidade(canal.nichos) is None:
        return []
    hist: Historico = []
    for titulo, quando in db.historico_canal(canal.id, 24):
        tipo, familia = tipo_de(titulo, canal.nichos)
        hist.append((tipo, familia, dt.datetime.fromisoformat(quando).timestamp()))
    return hist


def _bloqueado_por_variedade(tipo: str, familia: str, hist: Historico, p: dict, agora: float | None = None,
                             prioritario: bool = False) -> bool:
    """Não repete o MESMO TIPO de produto em sequência (6 chaves de impacto seguidas, 3 compressores...).
    Bloqueia se: o tipo saiu num dos últimos `espaco` posts (dentro de `horas`); o tipo já saiu `max_dia` vezes
    nas últimas 24h; ou a família (elétricas, árabes...) já ocupa `familia_max` dos últimos `familia_janela` posts.
    O que o nicho mais quer (`prioritario`: jeans importado no Country) só respeita o teto do dia: esperar a vez
    travava o canal, que de 15 a 18/10 deixou de postar dezenas de jeans aprovados."""
    agora = time.time() if agora is None else agora
    if sum(1 for t, _, _ in hist if t == tipo) >= p.get("max_dia_por_tipo", {}).get(tipo, p["max_dia"]):
        return True
    if prioritario:
        return False
    recentes = [h for h in hist if agora - h[2] <= p["horas"] * 3600]
    if any(t == tipo for t, _, _ in recentes[-p["espaco"]:]):
        return True
    return sum(1 for _, f, _ in recentes[-p["familia_janela"]:] if f == familia) >= p["familia_max"]


def escolher(ofertas: list[Oferta], n: int, canal: Canal | None = None, hist: Historico | None = None,
             modelos: list[frozenset[str]] | None = None) -> list[Oferta]:
    """Top N por desconto, alternando plataformas, pulando variações do mesmo produto e (com `canal`) o mesmo
    TIPO de produto em sequência: o que sai agora e o que o canal já postou (`hist`) contam juntos. `modelos`
    (títulos sem tamanho das últimas 24h) limita os tamanhos do mesmo jeans."""
    params = parametros_diversidade(canal.nichos) if canal else None
    hist = list(hist or [])
    modelos = list(modelos or [])
    agora = time.time()
    filas: dict[str, list[Oferta]] = {}
    chaves = canal.nichos if canal else []
    ordem_de = lambda o: (prioritaria(o.titulo, chaves), o.desconto or 0)  # prioritárias (jeans importado) primeiro
    for o in sorted(ofertas, key=ordem_de, reverse=True):
        filas.setdefault(o.plataforma, []).append(o)
    ordem = sorted(filas.values(), key=lambda f: ordem_de(f[0]), reverse=True)
    escolhidas: list[Oferta] = []
    vistas: list[tuple[frozenset[str], float | None]] = []
    while len(escolhidas) < n and any(ordem):
        for fila in ordem:
            while fila:
                o = fila.pop(0)
                nucleo = _nucleo(o.titulo)
                if _repetido(nucleo, o.preco, vistas):
                    continue
                if _excesso_de_tamanhos(o.titulo, modelos):
                    continue
                if params:
                    tipo, familia = tipo_de(o.titulo, canal.nichos)
                    if _bloqueado_por_variedade(tipo, familia, hist, params, agora, prioritaria(o.titulo, chaves)):
                        continue
                    hist.append((tipo, familia, agora))
                vistas.append((nucleo, o.preco))
                modelos.append(_modelo(o.titulo))
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
    historico = {c.id: await asyncio.to_thread(carregar_historico, c) for c in canais}  # tipos postados nas últimas 24h
    modelos = {c.id: await asyncio.to_thread(carregar_modelos, c) for c in canais}  # para não repetir tamanhos do mesmo jeans
    ml_ok = True
    postadas = 0

    while time.monotonic() < prazo:
        # próximo lote de cada canal (respeitando o teto opcional)
        lote: dict[str, list[Oferta]] = {}
        for c in canais:
            boas[c.id] = [o for o in boas[c.id] if not _repetido(_nucleo(o.titulo), o.preco, chaves_postadas[c.id])
                          and (ml_ok or o.plataforma != "mercadolivre")]
            n = LOTE if not limite[c.id] else min(LOTE, limite[c.id] - por_canal[c.id])
            lote[c.id] = escolher(boas[c.id], n, c, historico[c.id], modelos[c.id]) if n > 0 else []
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
                # Timeout: se o Chrome do Linkbuilder travar (perfil preso, processo zumbi, rede
                # caindo no meio da automação), isso já derrubou o bot inteiro sem traceback nenhum
                # — melhor falhar essa rodada do que deixar a thread pendurada para sempre.
                await asyncio.wait_for(
                    asyncio.to_thread(mercadolivre.gerar_links_por_etiqueta,
                                      {e: list(g.values()) for e, g in grupos.items()}),
                    timeout=180,
                )
                for c in canais:
                    for o in lote[c.id]:
                        if o.plataforma == "mercadolivre":
                            links[(c.id, o.uid)] = grupos[_etiqueta(c)][o.uid].url_afiliado
            except TimeoutError:
                log.error("Linkbuilder ML travou (sem resposta em 180s) — pulando links desta rodada")
                db.registrar_evento("ml_link_falhou", "Linkbuilder travou (timeout de 180s)")
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
                if not await asyncio.to_thread(amazon.vendedor_confiavel, o, aceita_amazon_global(c.nichos)):
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
                o_final = replace(o, url_afiliado=link, **extras)
                await postar_oferta(bot, o_final, c.chat_id)
                if c.whatsapp_grupo and whatsapp.configurado():
                    try:
                        await asyncio.to_thread(whatsapp.postar_oferta, o_final, c.whatsapp_grupo)
                    except Exception as e:
                        log.error("Falha ao postar no WhatsApp (%s): %s", c.nome, e)
                        db.registrar_evento("falha_post_whatsapp", f"{c.id}: {e}")
            except (NetworkError, TimedOut) as e:
                # queda de conexão: não é problema do canal. A oferta volta na próxima rodada e o aviso é raro
                log.error("Falha de rede ao postar '%s' em %s: %s", o.titulo[:60], c.nome, e)
                db.esquecer(chave)
                db.registrar_evento("falha_rede", f"{c.id}: {type(e).__name__}: {e or 'sem detalhe'} | {o.titulo[:40]}")
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
            modelos[c.id].append(_modelo(o.titulo))
            if parametros_diversidade(c.nichos):
                historico[c.id].append((*tipo_de(o.titulo, c.nichos), time.time()))

    for c in canais:  # o que ficou de fora só por parecer demais com o que acabou de sair
        p = parametros_diversidade(c.nichos)
        if p:
            parecidas = sum(1 for o in boas[c.id] if _bloqueado_por_variedade(*tipo_de(o.titulo, c.nichos), historico[c.id], p,
                                                                               prioritario=prioritaria(o.titulo, c.nichos)))
            if parecidas:
                motivos[c.id]["muito_parecido_em_sequencia"] += parecidas
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

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut

from .formatter import montar_caption, texto_botao
from .models import Oferta

log = logging.getLogger("ofertas.poster")

TENTATIVAS = 3  # queda de rede momentânea (httpx.ConnectError etc.): tenta de novo em vez de perder o post


def teclado_oferta(o: Oferta) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(texto_botao(o), url=o.url_afiliado)]])


async def _com_retentativa(enviar):
    """Repete o envio se a rede cair. Erros do Telegram em si (BadRequest etc.) não são repetidos."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return await enviar()
        except (NetworkError, TimedOut) as e:
            if isinstance(e, BadRequest) or tentativa == TENTATIVAS:
                raise
            espera = 5 * tentativa
            log.warning("Rede instável ao enviar (%s); nova tentativa %d/%d em %ds", e, tentativa + 1, TENTATIVAS, espera)
            await asyncio.sleep(espera)


async def postar_oferta(bot: Bot, oferta: Oferta, chat_id: str | int,
                        teclado: InlineKeyboardMarkup | None = None) -> Message:
    caption = montar_caption(oferta)
    markup = teclado or teclado_oferta(oferta)
    if oferta.imagem:
        try:
            return await _com_retentativa(lambda: bot.send_photo(
                chat_id, oferta.imagem, caption=caption, parse_mode=ParseMode.HTML, reply_markup=markup))
        except (NetworkError, TimedOut) as e:
            # BadRequest também é NetworkError na biblioteca: imagem recusada pelo Telegram -> cai para texto.
            # Já queda de rede de verdade não adianta contornar: a oferta volta na próxima rodada.
            if not isinstance(e, BadRequest):
                raise
            log.warning("Imagem recusada pelo Telegram (%s), enviando como texto", e)
        except Exception as e:
            log.warning("send_photo falhou (%s), enviando como texto", e)
    return await _com_retentativa(lambda: bot.send_message(
        chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True))

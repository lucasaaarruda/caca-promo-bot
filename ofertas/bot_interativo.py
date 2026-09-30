"""Bot do Telegram: posta os ciclos automáticos e, no privado, converte
qualquer link colado (ML/Shopee/Amazon) em post com o seu link de afiliado.
"""
import asyncio
import logging
import secrets
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

from . import db, pipeline, relatorio
from .config import config
from .models import Oferta
from .sources import detectar_fonte
from .telegram_poster import postar_oferta
from .utils import extrair_urls

log = logging.getLogger("ofertas.bot")

PREVIA_VALIDADE = 3600  # segundos
_pendentes: dict[str, tuple[float, Oferta]] = {}


def _limpar_pendentes() -> None:
    agora = time.time()
    for t in [t for t, (criada, _) in _pendentes.items() if agora - criada > PREVIA_VALIDADE]:
        del _pendentes[t]


async def _cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot de ofertas no ar!\n\n"
        "• Cole aqui um link do Mercado Livre, Shopee ou Amazon e eu preparo o post "
        "com o seu link de afiliado.\n"
        "• /id — mostra o id deste chat (ou do canal, se você encaminhar um post dele)\n"
        "• /ciclo — roda uma busca de ofertas agora\n"
        "• /status — situação do bot\n"
        "• /relatorio — resumo do dia"
    )


async def _cmd_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Este chat: `{update.effective_chat.id}`\n"
        f"Seu user id: `{update.effective_user.id}`\n\n"
        "Para descobrir o id do canal, encaminhe aqui qualquer post dele.",
        parse_mode="Markdown",
    )


async def _cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fontes = [nome for nome, f in (("Mercado Livre", config.fonte_ml),
                                   ("Shopee", config.fonte_shopee),
                                   ("Amazon", config.fonte_amazon)) if f.get("ativa")]
    por_canal = "".join(f"   {c.rotulo}: {db.total_postadas(c.id)}\n" for c in config.canais)
    teto = f"máx. {config.max_posts_por_ciclo} posts por rodada" if config.max_posts_por_ciclo else "sem limite de posts"
    await update.message.reply_text(
        f"📊 {db.total_postadas()} ofertas postadas até agora\n{por_canal}"
        f"🔎 Fontes automáticas: {', '.join(fontes) or 'nenhuma'}\n"
        f"⏱ Rodada a cada {config.intervalo_minutos} min, {teto}\n"
        f"🎯 Desconto mínimo: {config.desconto_minimo}%"
    )


async def _cmd_relatorio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _e_dono(update):
        return
    await update.message.reply_text(relatorio.relatorio_do_dia())


async def _job_relatorio(ctx: ContextTypes.DEFAULT_TYPE):
    await pipeline.avisar_dono(ctx.bot, relatorio.relatorio_do_dia(), repetir_apos_h=0)


def _e_dono(update: Update) -> bool:
    return bool(config.owner_id) and update.effective_user.id == config.owner_id


async def _cmd_ciclo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _e_dono(update):
        return
    await update.message.reply_text("🔄 Rodando um ciclo de busca...")
    postadas = await pipeline.executar_ciclo(ctx.bot)
    await update.message.reply_text(f"✅ Ciclo terminou: {postadas} oferta(s) postada(s).")


async def _receber_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not config.owner_id:
        await update.message.reply_text(
            "⚠️ Defina TELEGRAM_OWNER_ID no .env para usar o conversor.\n"
            f"Seu user id é `{update.effective_user.id}`.", parse_mode="Markdown")
        return
    if not _e_dono(update):
        return

    msg = update.effective_message
    urls = extrair_urls(msg.text or msg.caption or "")
    fonte = url = None
    for u in urls:
        fonte = detectar_fonte(u)
        if fonte:
            url = u
            break
    if not fonte:
        await update.message.reply_text("Não reconheci nenhum link de ML, Shopee ou Amazon aí. 🤔")
        return

    aviso = await update.message.reply_text("🔎 Convertendo, um instante...")
    try:
        oferta = await asyncio.to_thread(fonte.converter, url)
    except Exception as e:
        await aviso.edit_text(f"❌ Não consegui converter: {e}")
        return
    await aviso.delete()

    token = secrets.token_hex(4)
    _limpar_pendentes()
    _pendentes[token] = (time.time(), oferta)
    if not config.canais:
        await update.message.reply_text("⚠️ Nenhum canal ativo. Crie um no painel (seção Canais).")
        return
    teclado = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛒 Pegar oferta", url=oferta.url_afiliado)]]
        + [[InlineKeyboardButton(f"✅ Postar em {c.rotulo}", callback_data=f"post:{token}:{c.id}")]
           for c in config.canais]
        + [[InlineKeyboardButton("🗑 Descartar", callback_data=f"drop:{token}")]])
    await postar_oferta(ctx.bot, oferta, update.effective_chat.id, teclado=teclado)


async def _receber_forward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    texto = msg.text or msg.caption or ""
    if any(detectar_fonte(u) for u in extrair_urls(texto)):
        await _receber_link(update, ctx)  # encaminhou uma oferta -> converte normalmente
        return
    origem = getattr(msg, "forward_origin", None)
    chat_origem = getattr(origem, "chat", None)
    if chat_origem:
        await msg.reply_text(
            f"📢 Id desse canal/grupo: `{chat_origem.id}`\n"
            "Use esse valor no campo “ID do canal” ao criar o canal no painel.",
            parse_mode="Markdown",
        )
    else:
        await msg.reply_text(
            "Não consegui ver de onde veio — encaminhe direto do canal, sem intermediários."
        )


async def _callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _e_dono(update):
        await q.answer()
        return
    await q.answer()
    acao, _, resto = q.data.partition(":")
    token, _, canal_id = resto.partition(":")
    _limpar_pendentes()
    # "post" mantém a prévia (dá para postar em vários canais); "drop" descarta
    item = _pendentes.get(token) if acao == "post" else _pendentes.pop(token, None)
    oferta = item[1] if item else None

    async def _status(texto: str):
        markup = q.message.reply_markup if acao == "post" and oferta else None
        if q.message.photo:
            await q.edit_message_caption((q.message.caption or "") + f"\n\n{texto}", reply_markup=markup)
        else:
            await q.edit_message_text((q.message.text or "") + f"\n\n{texto}", reply_markup=markup)

    if not oferta:
        await _status("⚠️ Essa prévia expirou — mande o link de novo.")
        return
    if acao == "post":
        canal = next((c for c in config.canais if c.id == canal_id), None)
        if not canal:
            await _status("⚠️ Esse canal não existe mais (reinicie o bot depois de editar canais).")
            return
        await postar_oferta(ctx.bot, oferta, canal.chat_id)
        db.registrar(oferta, canal.id)
        await _status(f"✅ Postada em {canal.rotulo}")
    else:
        await _status("🗑 Descartada.")


async def _job_ciclo(ctx: ContextTypes.DEFAULT_TYPE):
    try:
        await pipeline.executar_ciclo(ctx.bot)
    except Exception as e:
        log.exception("Ciclo automático falhou")
        await pipeline.avisar_dono(ctx.bot, f"⚠️ O ciclo automático falhou: {type(e).__name__}: {e}")


async def _avisar_online(app: Application) -> None:
    nomes = ", ".join(c.rotulo for c in config.canais) or "nenhum canal ativo"
    await pipeline.avisar_dono(app.bot, f"🟢 Bot online. Canais: {nomes}", repetir_apos_h=0)


def rodar():
    if not config.bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN não configurado — veja o README (passo 1).")

    app = Application.builder().token(config.bot_token).post_init(_avisar_online).build()
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("id", _cmd_id))
    app.add_handler(CommandHandler("status", _cmd_status))
    app.add_handler(CommandHandler("ciclo", _cmd_ciclo))
    app.add_handler(CommandHandler("relatorio", _cmd_relatorio))
    app.add_handler(CallbackQueryHandler(_callback))
    app.add_handler(MessageHandler(filters.FORWARDED & filters.ChatType.PRIVATE, _receber_forward))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.CAPTION) & filters.ChatType.PRIVATE & ~filters.COMMAND,
        _receber_link))

    tem_fonte = any(f.get("ativa") for f in
                    (config.fonte_ml, config.fonte_shopee, config.fonte_amazon))
    if tem_fonte and config.intervalo_minutos > 0 and config.canais:
        app.job_queue.run_repeating(_job_ciclo, interval=config.intervalo_minutos * 60, first=30)
        log.info("Ciclo automático a cada %d min", config.intervalo_minutos)
    else:
        log.info("Ciclo automático desligado (sem fonte ativa ou sem canal ativo)")

    if config.relatorio_hora and config.owner_id:
        try:
            import datetime as dt
            from tzlocal import get_localzone
            h, m = (int(x) for x in config.relatorio_hora.split(":"))
            app.job_queue.run_daily(_job_relatorio, time=dt.time(h, m, tzinfo=get_localzone()))
            log.info("Relatório diário às %s", config.relatorio_hora)
        except ValueError:
            log.warning("relatorio_hora inválida no config.yaml (%r): use HH:MM", config.relatorio_hora)

    log.info("Bot rodando — fale com ele no privado do Telegram")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

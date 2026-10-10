import argparse
import asyncio
import logging
import sys


def _log(nome: str = "bot"):
    """Log no console (se houver) e em data/logs/<comando>.log com rotação (1 MB x 5)."""
    from logging.handlers import RotatingFileHandler
    from .caminhos import DATA_DIR
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    if sys.stderr is not None:  # sem console (pythonw) não há onde escrever
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        raiz.addHandler(console)
    pasta = DATA_DIR / "logs"
    pasta.mkdir(exist_ok=True)
    arquivo = RotatingFileHandler(pasta / f"{nome}.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    arquivo.setFormatter(fmt)
    raiz.addHandler(arquivo)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_check(_):
    from .config import config, verificar
    pendencias = verificar()
    print("── Checagem da configuração ──")
    if config.bot_token:
        print("✅ Token do bot")
    for c in config.canais:
        print(f"✅ Canal {c.rotulo}: {c.chat_id}")
    if config.owner_id:
        print(f"✅ ID do dono: {config.owner_id}")
    if config.amazon_tag:
        print(f"✅ Tag da Amazon: {config.amazon_tag}")
    if config.shopee_app_id and config.shopee_app_secret:
        print("✅ Credenciais Shopee")
    from .sources import mercadolivre
    if mercadolivre.tem_sessao():
        print("✅ Sessão do Mercado Livre")
    for p in pendencias:
        print(f"⚠️  Falta: {p}")
    if not pendencias:
        print("\n🎉 Tudo pronto! Rode: uv run python -m ofertas run")


def cmd_run(_):
    import os
    from . import instancia
    # sob o supervisor, quem guarda a trava é ele; avulso, o próprio bot guarda
    if os.environ.get("OFERTAS_SOB_SUPERVISOR") != "1" and not instancia.adquirir():
        raise SystemExit(f"O bot já está rodando (PID {instancia.rodando()}). "
                         "Desligue-o antes (painel: Desligar bot) ou use o que já está no ar.")
    from .bot_interativo import rodar
    rodar()


def cmd_servico(_):
    from . import servico
    raise SystemExit(servico.executar())


def cmd_autostart(args):
    from . import autostart
    if args.acao == "instalar":
        ok, msg = autostart.instalar()
        print("✅ O bot vai iniciar junto com o Windows." if ok else f"❌ Não consegui instalar: {msg}")
    elif args.acao == "remover":
        ok, msg = autostart.remover()
        print("✅ Início automático removido." if ok else f"❌ Não consegui remover: {msg}")
    else:
        print("Ativo" if autostart.ativo() else "Desativado")


def cmd_ciclo(_):
    from telegram import Bot
    from . import pipeline
    from .config import config
    if not (config.bot_token and config.canais):
        raise SystemExit("Configure o token do bot e crie um canal no painel antes.")

    async def go():
        bot = Bot(config.bot_token)
        async with bot:
            await pipeline.executar_ciclo(bot)

    asyncio.run(go())


def _converter(url: str):
    from .sources import detectar_fonte
    fonte = detectar_fonte(url)
    if not fonte:
        raise SystemExit("Link não reconhecido (esperado: Mercado Livre, Shopee ou Amazon).")
    return fonte.converter(url)


def cmd_converter(args):
    o = _converter(args.url)
    print(f"Plataforma:  {o.plataforma}")
    print(f"Título:      {o.titulo}")
    print(f"Preço:       {o.preco}  (de {o.preco_original})  -{o.desconto or 0}%")
    print(f"Imagem:      {o.imagem}")
    print(f"Link de afiliado: {o.url_afiliado}")


def cmd_postar(args):
    from telegram import Bot
    from . import db
    from .config import config
    from .telegram_poster import postar_oferta
    if not (config.bot_token and config.canais):
        raise SystemExit("Configure o token do bot e crie um canal no painel antes.")
    canal = next((c for c in config.canais if c.id == args.canal), None) if args.canal else config.canais[0]
    if not canal:
        raise SystemExit("Canal desconhecido. Disponíveis: " + ", ".join(c.id for c in config.canais))
    o = _converter(args.url)

    async def go():
        bot = Bot(config.bot_token)
        async with bot:
            await postar_oferta(bot, o, canal.chat_id)
        db.registrar(o, canal.id)
        print(f"✅ Postada: {o.titulo[:60]}")

    asyncio.run(go())


def cmd_relatorio(args):
    from . import relatorio_completo
    rel, posts = relatorio_completo.gerar(args.dias)
    print(f"Relatório: {rel}\nPosts: {posts}")


def cmd_painel(_):
    from .painel import painel
    painel()


def cmd_instalar_navegador(_):
    import subprocess
    from . import config  # noqa: F401 — define PLAYWRIGHT_BROWSERS_PATH (data/pw-browsers)
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
    if r.returncode == 0:
        print("✅ Chromium instalado em data\\pw-browsers")
    raise SystemExit(r.returncode)


def cmd_ml_login(_):
    from .sources import mercadolivre
    mercadolivre.ml_login()


def cmd_testar(args):
    if args.fonte == "mlapi":
        from .sources import mercadolivre_api
        for linha in mercadolivre_api.diagnostico():
            print(linha)
        return
    if args.fonte == "ml":
        from .sources import mercadolivre
        ofertas = mercadolivre.buscar_ofertas()
    elif args.fonte == "shopee":
        from .sources import shopee
        ofertas = shopee.buscar_ofertas(10)
    elif args.fonte == "amazon":
        from .sources import amazon
        from .config import config
        if not config.amazon_tag:
            raise SystemExit("Preencha AMAZON_TAG no .env")
        ofertas = amazon.buscar_ofertas()
    else:
        raise SystemExit("Fontes testáveis: ml, shopee, amazon")
    ofertas.sort(key=lambda o: o.desconto or 0, reverse=True)
    from .config import config
    from .pipeline import filtrar

    # o que o bot realmente postaria: passa nos filtros de algum canal ativo (nicho, nota, vendas, desconto...)
    destinos = {id(o): [c.rotulo for c in config.canais if filtrar([o], c)] for o in ofertas}
    aprovadas = [o for o in ofertas if destinos[id(o)]]
    if config.canais:
        print(f"✅ Postaria: {len(aprovadas)} de {len(ofertas)} ofertas coletadas\n")
    for o in (aprovadas if config.canais else ofertas)[:10]:
        print(f"[-{o.desconto or 0:>2}%] R$ {o.preco} (de {o.preco_original}) — {o.titulo[:60]}")
        if o.extra:
            print(f"       {o.extra}")
        if config.canais:
            print(f"       → canal: {', '.join(destinos[id(o)])}")
    if config.canais:
        print(f"\n⛔ Barradas pelos filtros: {len(ofertas) - len(aprovadas)} "
              "(fora do nicho, nota ou vendas baixas, desconto fora da faixa, ou já postadas)")
    print(f"Total coletado: {len(ofertas)} ofertas")


def main():
    for saida in (sys.stdout, sys.stderr):  # o log (stderr) também: sem isso o painel mostra "Ve�culos"
        try:
            saida.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(prog="ofertas",
                                description="Bot de ofertas para Telegram com links de afiliado")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("painel", help="abre o painel de controle gráfico no navegador").set_defaults(fn=cmd_painel)
    sub.add_parser("check", help="mostra o que falta configurar").set_defaults(fn=cmd_check)
    pr = sub.add_parser("relatorio", help="gera o relatório completo (data/relatorios/): 2 PDFs (relatório + todos os posts)")
    pr.add_argument("--dias", type=int, default=1, help="quantos dias incluir (padrão: só hoje)")
    pr.set_defaults(fn=cmd_relatorio)
    sub.add_parser("run", help="roda o bot (conversor no privado + ciclos automáticos)").set_defaults(fn=cmd_run)
    sub.add_parser("ciclo", help="roda um único ciclo de busca e postagem").set_defaults(fn=cmd_ciclo)

    pc = sub.add_parser("converter", help="converte um link e mostra o resultado (não posta)")
    pc.add_argument("url")
    pc.set_defaults(fn=cmd_converter)

    pp = sub.add_parser("postar", help="converte um link e posta no canal")
    pp.add_argument("url")
    pp.add_argument("--canal", help="ID do canal (padrão: o primeiro)")
    pp.set_defaults(fn=cmd_postar)

    sub.add_parser("instalar-navegador", help="baixa o Chromium usado pelo Linkbuilder (fica em data/)").set_defaults(fn=cmd_instalar_navegador)
    sub.add_parser("ml-login", help="login único no Mercado Livre (salva a sessão)").set_defaults(fn=cmd_ml_login)

    pt = sub.add_parser("testar", help="testa uma fonte sem postar nada")
    pt.add_argument("fonte", choices=["ml", "shopee", "amazon", "mlapi"])
    pt.set_defaults(fn=cmd_testar)

    sub.add_parser("servico", help="roda o bot com reinício automático (usado pelo início com o Windows)"
                   ).set_defaults(fn=cmd_servico)
    pa = sub.add_parser("autostart", help="iniciar o bot junto com o Windows")
    pa.add_argument("acao", choices=["instalar", "remover", "status"])
    pa.set_defaults(fn=cmd_autostart)

    args = p.parse_args()
    _log(args.cmd)
    args.fn(args)

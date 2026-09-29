"""Supervisor: roda o bot como subprocesso e o reinicia se cair (com espera crescente),
avisando você no Telegram. É o que a tarefa do Windows executa ao ligar o PC."""
import logging
import os
import subprocess
import sys
import time

import requests

from . import instancia
from .caminhos import BASE_DIR
from .config import config

log = logging.getLogger("ofertas.servico")


def espera_apos_falha(falhas_seguidas: int) -> int:
    """10s, 20s, 40s... até 5 min entre tentativas, para não martelar se algo estiver quebrado."""
    return min(300, 10 * 2 ** max(0, falhas_seguidas - 1))


def _avisar(texto: str) -> None:
    """Direto pela API HTTP do Telegram: funciona mesmo com o bot filho morto."""
    if not (config.bot_token and config.owner_id):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{config.bot_token}/sendMessage",
                      json={"chat_id": config.owner_id, "text": texto}, timeout=15)
    except Exception as e:
        log.warning("Não consegui avisar o dono: %s", e)


def executar() -> int:
    if not instancia.adquirir():
        log.error("Já existe um bot rodando (PID %s) — este supervisor não vai iniciar outro.",
                  instancia.rodando())
        return 1
    env = {**os.environ, "OFERTAS_SOB_SUPERVISOR": "1"}  # o filho não disputa a trava de instância
    falhas = 0
    while True:
        inicio = time.time()
        log.info("Iniciando o bot...")
        r = subprocess.run([sys.executable, "-m", "ofertas", "run"], cwd=str(BASE_DIR), env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            log.info("Bot encerrado normalmente.")
            return 0
        falhas = falhas + 1 if time.time() - inicio < 300 else 1  # rodou >5min: não é loop de falha
        espera = espera_apos_falha(falhas)
        log.error("O bot caiu (código %s). Falha seguida nº %d; reiniciando em %ds.", r.returncode, falhas, espera)
        if falhas in (1, 5) or falhas % 20 == 0:
            _avisar(f"⚠️ O bot caiu (código {r.returncode}) e será reiniciado em {espera}s. "
                    f"Falhas seguidas: {falhas}. Veja data/logs/run.log.")
        time.sleep(espera)

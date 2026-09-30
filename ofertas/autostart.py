"""Iniciar o bot junto com o Windows, sem janela: uma tarefa agendada do próprio Windows que,
quando você entrar na sessão, roda `python -m ofertas servico` (o supervisor que reinicia o bot se cair).
Não precisa de administrador: a tarefa é do seu usuário."""
import base64
import subprocess
import sys

from .caminhos import BASE_DIR

NOME_TAREFA = "BotOfertasTelegram"


def _powershell(script: str) -> subprocess.CompletedProcess:
    script = "$ProgressPreference = 'SilentlyContinue'; " + script  # sem lixo de progresso no stderr
    codificado = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _pythonw() -> str:
    """pythonw.exe (Python sem janela de console) do mesmo ambiente do bot."""
    exe = sys.executable
    return exe[:-len("python.exe")] + "pythonw.exe" if exe.lower().endswith("python.exe") else exe


def script_instalar(nome: str = NOME_TAREFA) -> str:
    return f"""
$ErrorActionPreference = 'Stop'
$acao = New-ScheduledTaskAction -Execute '{_pythonw()}' -Argument '-m ofertas servico' -WorkingDirectory '{BASE_DIR}'
$gatilho = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\\$env:USERNAME"
$cfg = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '{nome}' -Action $acao -Trigger $gatilho -Settings $cfg `
    -Description 'Bot de ofertas do Telegram (inicia ao entrar no Windows)' -Force | Out-Null
"""


def instalar(nome: str = NOME_TAREFA) -> tuple[bool, str]:
    r = _powershell(script_instalar(nome))
    return r.returncode == 0, (r.stderr or r.stdout).strip()[-400:]


def remover(nome: str = NOME_TAREFA) -> tuple[bool, str]:
    r = _powershell(f"Unregister-ScheduledTask -TaskName '{nome}' -Confirm:$false -ErrorAction Stop")
    return r.returncode == 0, (r.stderr or r.stdout).strip()[-400:]


def ativo(nome: str = NOME_TAREFA) -> bool:
    return _powershell(f"Get-ScheduledTask -TaskName '{nome}' -ErrorAction Stop | Out-Null").returncode == 0


def iniciar_agora(nome: str = NOME_TAREFA) -> tuple[bool, str]:
    r = _powershell(f"Start-ScheduledTask -TaskName '{nome}' -ErrorAction Stop")
    return r.returncode == 0, (r.stderr or r.stdout).strip()[-400:]

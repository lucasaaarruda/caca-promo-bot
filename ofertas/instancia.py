"""Instância única do bot: dois bots com o mesmo token brigam pelas mensagens do Telegram
(erro 409) e postam em dobro. O PID de quem está rodando fica em data/bot.pid."""
import atexit
import os
import sys

from .caminhos import DATA_DIR

ARQ = DATA_DIR / "bot.pid"


def _vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        codigo = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(codigo))
        k.CloseHandle(h)
        return bool(ok) and codigo.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def rodando() -> int | None:
    """PID do bot que está rodando (outro processo), ou None."""
    try:
        pid = int(ARQ.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid != os.getpid() and _vivo(pid) else None


def adquirir() -> bool:
    """Reserva a vaga de 'bot em execução'. False se já há outro rodando."""
    if rodando():
        return False
    ARQ.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(liberar)
    return True


def liberar() -> None:
    try:
        if ARQ.read_text(encoding="utf-8").strip() == str(os.getpid()):
            ARQ.unlink()
    except OSError:
        pass


def encerrar(pid: int) -> None:
    """Derruba o bot (e o supervisor, se houver) pelo PID, com toda a árvore de processos."""
    import subprocess
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        os.kill(pid, 15)

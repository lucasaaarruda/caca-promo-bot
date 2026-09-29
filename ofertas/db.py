import datetime as dt
import sqlite3
from contextlib import closing

from .config import DATA_DIR
from .models import Oferta

_DB = DATA_DIR / "ofertas.db"
_MARCADOR = DATA_DIR / "migrar_historico.txt"  # escrito por canais._migrar_legado


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB)
    c.execute(
        "CREATE TABLE IF NOT EXISTS postadas ("
        " uid TEXT PRIMARY KEY,"
        " plataforma TEXT,"
        " titulo TEXT,"
        " preco REAL,"
        " postada_em TEXT)"
    )
    _aplicar_migracao(c)
    return c


def _aplicar_migracao(c: sqlite3.Connection) -> None:
    """Se canais.py deixou o marcador, os registros antigos (sem canal, uid sem '|') passam a
    pertencer àquele canal. Feito aqui, e não em canais.py, para evitar import circular."""
    if not _MARCADOR.exists():
        return
    canal_id = _MARCADOR.read_text(encoding="utf-8").strip()
    if canal_id:
        with c:
            c.execute("UPDATE postadas SET uid = ? || '|' || uid WHERE uid NOT LIKE '%|%'", (canal_id,))
    _MARCADOR.unlink(missing_ok=True)


def ja_postada(uid: str, dentro_de_dias: int) -> bool:
    with closing(_conn()) as c:
        row = c.execute("SELECT postada_em FROM postadas WHERE uid = ?", (uid,)).fetchone()
    if not row:
        return False
    postada = dt.datetime.fromisoformat(row[0])
    return (dt.datetime.now() - postada) < dt.timedelta(days=dentro_de_dias)


def registrar(oferta: Oferta, canal_id: str = "principal") -> None:
    with closing(_conn()) as c, c:
        c.execute(
            "INSERT OR REPLACE INTO postadas (uid, plataforma, titulo, preco, postada_em)"
            " VALUES (?, ?, ?, ?, ?)",
            (f"{canal_id}|{oferta.uid}", oferta.plataforma, oferta.titulo, oferta.preco,
             dt.datetime.now().isoformat(timespec="seconds")),
        )


def esquecer(uid: str) -> None:
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM postadas WHERE uid = ?", (uid,))


def total_postadas(canal_id: str | None = None) -> int:
    with closing(_conn()) as c:
        if canal_id:
            return c.execute("SELECT COUNT(*) FROM postadas WHERE uid LIKE ?", (canal_id + "|%",)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM postadas").fetchone()[0]

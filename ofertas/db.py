import datetime as dt
import json
import sqlite3
from collections import Counter
from contextlib import closing

from .caminhos import DATA_DIR
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
    if "desconto" not in {r[1] for r in c.execute("PRAGMA table_info(postadas)")}:
        c.execute("ALTER TABLE postadas ADD COLUMN desconto INTEGER")  # bancos criados antes do relatório
    c.execute("CREATE TABLE IF NOT EXISTS ciclos (ts TEXT, coletadas INTEGER, postadas INTEGER, detalhe TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS eventos (ts TEXT, tipo TEXT, detalhe TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS precos (uid TEXT, ts TEXT, preco REAL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_precos_uid ON precos (uid)")
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


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


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
            "INSERT OR REPLACE INTO postadas (uid, plataforma, titulo, preco, postada_em, desconto)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (f"{canal_id}|{oferta.uid}", oferta.plataforma, oferta.titulo, oferta.preco, _agora(),
             oferta.desconto),
        )


def esquecer(uid: str) -> None:
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM postadas WHERE uid = ?", (uid,))


def total_postadas(canal_id: str | None = None) -> int:
    with closing(_conn()) as c:
        if canal_id:
            return c.execute("SELECT COUNT(*) FROM postadas WHERE uid LIKE ?", (canal_id + "|%",)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM postadas").fetchone()[0]


def titulos_recentes(canal_id: str, dias: int) -> list[str]:
    """Títulos já postados no canal nos últimos `dias` (para não repetir variações do mesmo produto)."""
    desde = (dt.datetime.now() - dt.timedelta(days=dias)).isoformat(timespec="seconds")
    with closing(_conn()) as c:
        return [r[0] for r in c.execute(
            "SELECT titulo FROM postadas WHERE uid LIKE ? AND postada_em >= ?", (canal_id + "|%", desde))]


# ── Histórico de preços (base para "menor preço que já vimos") ───────

def registrar_precos(ofertas: list[Oferta], reter_dias: int = 90) -> None:
    """Guarda o preço visto de cada oferta coletada. Só grava se mudou ou se a última leitura tem >3h."""
    agora = dt.datetime.now()
    limite = (agora - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    with closing(_conn()) as c, c:
        for o in ofertas:
            if not o.preco:
                continue
            ult = c.execute("SELECT ts, preco FROM precos WHERE uid = ? ORDER BY ts DESC LIMIT 1", (o.uid,)).fetchone()
            if ult and ult[0] > limite and ult[1] == o.preco:
                continue
            c.execute("INSERT INTO precos VALUES (?, ?, ?)", (o.uid, agora.isoformat(timespec="seconds"), o.preco))
        c.execute("DELETE FROM precos WHERE ts < ?", ((agora - dt.timedelta(days=reter_dias)).isoformat(timespec="seconds"),))


def historico_preco(uid: str, dias: int = 60) -> list[tuple[str, float]]:
    desde = (dt.datetime.now() - dt.timedelta(days=dias)).isoformat(timespec="seconds")
    with closing(_conn()) as c:
        return c.execute("SELECT ts, preco FROM precos WHERE uid = ? AND ts >= ? ORDER BY ts", (uid, desde)).fetchall()


# ── Histórico para o relatório ───────────────────────────────────────

def registrar_ciclo(coletadas: int, postadas: int, detalhe: dict) -> None:
    """detalhe: {canal_id: {"boas": n, "postadas": n}}"""
    with closing(_conn()) as c, c:
        c.execute("INSERT INTO ciclos VALUES (?, ?, ?, ?)",
                  (_agora(), coletadas, postadas, json.dumps(detalhe, ensure_ascii=False)))


def registrar_evento(tipo: str, detalhe: str = "") -> None:
    """Problemas que o relatório resume: ml_sessao, falha_post, fonte_vazia..."""
    with closing(_conn()) as c, c:
        c.execute("INSERT INTO eventos VALUES (?, ?, ?)", (_agora(), tipo, detalhe[:300]))


def resumo(desde: dt.datetime) -> dict:
    """Números do período [desde, agora] para o relatório."""
    d = desde.isoformat(timespec="seconds")
    with closing(_conn()) as c:
        posts = c.execute("SELECT uid, plataforma, titulo, desconto FROM postadas WHERE postada_em >= ?",
                          (d,)).fetchall()
        ciclos = c.execute("SELECT coletadas, postadas, detalhe FROM ciclos WHERE ts >= ?", (d,)).fetchall()
        eventos = c.execute("SELECT tipo, detalhe FROM eventos WHERE ts >= ?", (d,)).fetchall()

    por_canal: dict[str, Counter] = {}
    melhor = None
    for uid, plataforma, titulo, desconto in posts:
        canal = uid.split("|", 1)[0] if "|" in uid else "principal"
        por_canal.setdefault(canal, Counter())[plataforma] += 1
        if desconto and (melhor is None or desconto > melhor["desconto"]):
            melhor = {"desconto": desconto, "titulo": titulo, "canal": canal}

    boas: dict[str, list[int]] = {}
    for _, _, detalhe in ciclos:
        for canal, v in json.loads(detalhe or "{}").items():
            boas.setdefault(canal, []).append(v.get("boas", 0))

    return {
        "posts": len(posts),
        "por_canal": {k: dict(v) for k, v in por_canal.items()},
        "melhor": melhor,
        "ciclos": len(ciclos),
        "coletadas_media": round(sum(c[0] for c in ciclos) / len(ciclos)) if ciclos else 0,
        "boas_media": {k: round(sum(v) / len(v)) for k, v in boas.items()},
        "eventos": dict(Counter(t for t, _ in eventos)),
    }

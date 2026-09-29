"""Canais de destino: cada canal do Telegram tem seu próprio nicho, palavras-chave e filtros.

Ficam em data/canais.json, editados pelo painel. Na primeira execução, migra o canal único
antigo (TELEGRAM_CHAT_ID + data/nichos.json) para um canal só, sem perder o histórico.
"""
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from .config import DATA_DIR

ARQ = DATA_DIR / "canais.json"


@dataclass
class Canal:
    id: str
    nome: str
    chat_id: str
    emoji: str = "📢"
    ativo: bool = True
    nichos: list[str] = field(default_factory=list)    # chaves do catálogo (nichos.py)
    palavras: list[str] = field(default_factory=list)  # termos próprios: buscam e validam ofertas
    excluir: list[str] = field(default_factory=list)   # títulos com esses termos são barrados
    desconto_minimo: int | None = None                  # None = usa o do config.yaml
    max_posts_por_ciclo: int | None = None

    @property
    def rotulo(self) -> str:
        return f"{self.emoji} {self.nome}"

    @property
    def sem_filtro(self) -> bool:
        return not self.nichos and not self.palavras


def _slug(nome: str) -> str:
    t = unicodedata.normalize("NFKD", nome.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "canal"


def _lista(v) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,\n]", v)
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def _de_dict(d: dict) -> Canal:
    dm, mp = d.get("desconto_minimo"), d.get("max_posts_por_ciclo")
    return Canal(
        id=str(d.get("id") or _slug(d.get("nome", ""))), nome=str(d.get("nome", "")).strip(),
        chat_id=str(d.get("chat_id", "")).strip(), emoji=str(d.get("emoji") or "📢").strip(),
        ativo=bool(d.get("ativo", True)), nichos=_lista(d.get("nichos")),
        palavras=_lista(d.get("palavras")), excluir=_lista(d.get("excluir")),
        desconto_minimo=int(dm) if dm not in (None, "") else None,
        max_posts_por_ciclo=int(mp) if mp not in (None, "") else None,
    )


def validar(lista: list[dict]) -> list[Canal]:
    """Normaliza o que veio do painel: ids únicos, nome e ID do canal obrigatórios."""
    canais, usados = [], set()
    for d in lista:
        c = _de_dict(d)
        if not c.nome or not c.chat_id:
            raise ValueError("Todo canal precisa de nome e ID do canal.")
        base, n = c.id, 2
        while c.id in usados:
            c.id, n = f"{base}-{n}", n + 1
        usados.add(c.id)
        canais.append(c)
    return canais


def salvar(lista: list[dict]) -> list[Canal]:
    canais = validar(lista)
    ARQ.write_text(json.dumps([asdict(c) for c in canais], ensure_ascii=False, indent=2), encoding="utf-8")
    return canais


def _migrar_legado() -> list[Canal]:
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not chat_id:
        return []
    from .nichos import NICHOS, ler_selecao
    nichos = ler_selecao()
    nome = " + ".join(NICHOS[k]["nome"] for k in nichos[:2]) if nichos else "Canal principal"
    emoji = NICHOS[nichos[0]]["emoji"] if nichos else "📢"
    canal = Canal(id=_slug(nichos[0]) if nichos else "principal", nome=nome, chat_id=chat_id,
                  emoji=emoji, nichos=nichos)
    salvar([asdict(canal)])
    (DATA_DIR / "migrar_historico.txt").write_text(canal.id, encoding="utf-8")  # db.py aplica
    return [canal]


def ler() -> list[Canal]:
    if not ARQ.exists():
        return _migrar_legado()
    try:
        return [_de_dict(d) for d in json.loads(ARQ.read_text(encoding="utf-8"))]
    except (ValueError, TypeError):
        return []


def ativos() -> list[Canal]:
    return [c for c in ler() if c.ativo and c.chat_id]

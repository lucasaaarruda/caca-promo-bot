"""Integração com o WhatsApp via Evolution API (gateway não oficial, self-hosted: roda num Docker
seu, e automatiza uma sessão comum de WhatsApp Web por baixo — não é a API oficial da Meta).

Config fica em data/whatsapp.json, editada pelo painel. Use um número novo e dedicado (chip/eSim
separado do seu pessoal): o WhatsApp pode banir o número por automação, principalmente em volume
alto — ver aviso no card "WhatsApp" do painel.
"""
import json
import logging
import re
import time
from html import unescape

import requests

from .caminhos import DATA_DIR
from .formatter import montar_caption
from .models import Oferta

log = logging.getLogger("ofertas.whatsapp")

ARQ = DATA_DIR / "whatsapp.json"
TENTATIVAS = 3  # queda de rede momentânea: tenta de novo em vez de perder o post
TIMEOUT = 30
_CAMPOS = ("base_url", "instance", "apikey")


def ler() -> dict:
    padrao = {k: "" for k in _CAMPOS}
    if not ARQ.exists():
        return padrao
    try:
        d = json.loads(ARQ.read_text(encoding="utf-8"))
    except (ValueError, TypeError):
        return padrao
    return {**padrao, **{k: str(d.get(k, "")).strip() for k in _CAMPOS}}


def salvar(dados: dict) -> None:
    atuais = ler()
    for k in _CAMPOS:
        if k not in dados:
            continue
        v = str(dados[k]).strip()
        if k == "apikey" and not v:  # não sobrescreve a chave com vazio (campo em branco = manter a atual)
            continue
        atuais[k] = v
    atuais["base_url"] = atuais["base_url"].rstrip("/")
    ARQ.write_text(json.dumps(atuais, ensure_ascii=False, indent=2), encoding="utf-8")


def configurado() -> bool:
    c = ler()
    return bool(c["base_url"] and c["instance"] and c["apikey"])


def _chamar(metodo: str, caminho: str, **json_corpo) -> dict:
    c = ler()
    if not configurado():
        raise RuntimeError("Configure a Evolution API (URL, instância e chave) no painel primeiro.")
    try:
        r = requests.request(metodo, f"{c['base_url']}{caminho}",
                             headers={"apikey": c["apikey"], "Content-Type": "application/json"},
                             json=json_corpo or None, timeout=TIMEOUT)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise RuntimeError(f"Não consegui falar com a Evolution API em {c['base_url']} "
                           "— confira se ela está rodando e se a URL está certa.") from e
    try:
        dados = r.json() if r.content else {}
    except ValueError:
        dados = {}
    if r.status_code >= 400:
        raise RuntimeError(dados.get("message") or dados.get("error") or f"HTTP {r.status_code}")
    return dados


def criar_instancia() -> dict:
    c = ler()
    return _chamar("POST", "/instance/create",
                   instanceName=c["instance"], qrcode=True, integration="WHATSAPP-BAILEYS")


def conectar() -> dict:
    """Pede o QR code para parear o número — escaneie no WhatsApp do celular (Aparelhos conectados)."""
    c = ler()
    dados = _chamar("GET", f"/instance/connect/{c['instance']}")
    qr = dados.get("base64") or (dados.get("qrcode") or {}).get("base64", "")
    return {"qr": qr}


def status_conexao() -> str:
    c = ler()
    try:
        dados = _chamar("GET", f"/instance/connectionState/{c['instance']}")
    except RuntimeError:
        return "erro"
    return (dados.get("instance") or {}).get("state", "desconhecido")


def desconectar() -> None:
    c = ler()
    _chamar("DELETE", f"/instance/logout/{c['instance']}")


# ── Envio de ofertas ──────────────────────────────────────────────────

def _html_para_whatsapp(texto: str) -> str:
    """O formatter monta a legenda em HTML (padrão do Telegram); o WhatsApp usa marcação própria."""
    t = texto
    t = re.sub(r"<b>(.*?)</b>", r"*\1*", t, flags=re.S)
    t = re.sub(r"<i>(.*?)</i>", r"_\1_", t, flags=re.S)
    t = re.sub(r"<s>(.*?)</s>", r"~\1~", t, flags=re.S)
    t = re.sub(r"<code>(.*?)</code>", r"```\1```", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)  # qualquer outra tag HTML que tenha sobrado
    return unescape(t)


def postar_oferta(oferta: Oferta, grupo: str) -> None:
    """Envia a oferta para um grupo/contato do WhatsApp (JID, ex.: "120363...@g.us").
    Repete em caso de queda de rede ou instância reconectando, até TENTATIVAS vezes."""
    c = ler()
    texto = _html_para_whatsapp(montar_caption(oferta))
    if oferta.imagem:
        rota, corpo = f"/message/sendMedia/{c['instance']}", \
            {"number": grupo, "mediatype": "image", "media": oferta.imagem, "caption": texto}
    else:
        rota, corpo = f"/message/sendText/{c['instance']}", {"number": grupo, "text": texto}

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            _chamar("POST", rota, **corpo)
            return
        except RuntimeError as e:
            if tentativa == TENTATIVAS:
                raise
            espera = 5 * tentativa
            log.warning("Rede instável ao enviar pro WhatsApp (%s); nova tentativa %d/%d em %ds",
                       e, tentativa + 1, TENTATIVAS, espera)
            time.sleep(espera)

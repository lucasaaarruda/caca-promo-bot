"""Catálogo de nichos para o seletor de categorias do painel.

Cada nicho mapeia, de uma vez, as categorias equivalentes nas três plataformas:
- Mercado Livre: IDs de categoria (ofertas?category=MLB...), validados ao vivo
- Amazon: aliases de departamento (s?i=<alias>) e/ou termos de busca
- Shopee: palavras-chave (a Open API busca por keyword)

A seleção do usuário fica em data/nichos.json (lista de chaves). Nenhum nicho
marcado = todas as categorias (comportamento padrão).
"""
import json
import re
import unicodedata

from .caminhos import DATA_DIR

ARQ_SELECAO = DATA_DIR / "nichos.json"

# chave -> {emoji, nome, ml{id:nome}, amazon_dep{alias:nome}, amazon_buscas[], shopee[]}
NICHOS: dict[str, dict] = {
    "tecnologia": {
        "emoji": "💻", "nome": "Tecnologia e Eletrônicos",
        "ml": {"MLB1648": "Informática", "MLB1000": "Eletrônicos, Áudio e Vídeo"},
        "amazon_dep": {"electronics": "Eletrônicos", "computers": "Informática",
                       "amazon-devices": "Dispositivos Amazon"},
        "shopee": ["fone bluetooth", "smartwatch", "mouse gamer", "ssd", "carregador turbo"],
    },
    "celulares": {
        "emoji": "📱", "nome": "Celulares e Acessórios",
        "ml": {"MLB1051": "Celulares e Telefones"},
        "amazon_buscas": ["celular", "smartphone", "capa celular"],
        "shopee": ["capa celular", "power bank", "carregador", "película"],
    },
    "games": {
        "emoji": "🎮", "nome": "Games",
        "ml": {"MLB1144": "Games"},
        "amazon_dep": {"videogames": "Games"},
        "shopee": ["controle", "headset gamer", "teclado mecânico"],
    },
    "casa": {
        "emoji": "🏠", "nome": "Casa e Cozinha",
        "ml": {"MLB1574": "Casa, Móveis e Decoração"},
        "amazon_dep": {"home": "Casa", "kitchen": "Cozinha", "furniture": "Móveis"},
        "shopee": ["organizador", "panela", "utensílios de cozinha"],
    },
    "eletrodomesticos": {
        "emoji": "🔌", "nome": "Eletrodomésticos",
        "ml": {"MLB5726": "Eletrodomésticos"},
        "amazon_dep": {"appliances": "Eletrodomésticos"},
        "shopee": ["air fryer", "liquidificador", "aspirador de pó"],
    },
    "moda": {
        "emoji": "👗", "nome": "Moda e Acessórios",
        "ml": {"MLB1430": "Calçados, Roupas e Bolsas"},
        "amazon_dep": {"fashion": "Moda", "fashion-luggage": "Bolsas e Malas"},
        "shopee": ["tênis", "camiseta", "relógio", "mochila"],
    },
    "beleza": {
        "emoji": "💄", "nome": "Beleza e Cuidados",
        "ml": {"MLB1246": "Beleza e Cuidado Pessoal"},
        "amazon_dep": {"beauty": "Beleza", "luxury-beauty": "Beleza de Luxo"},
        "shopee": ["maquiagem", "perfume", "skincare"],
    },
    "esporte": {
        "emoji": "💪", "nome": "Esporte e Fitness",
        "ml": {"MLB1276": "Esportes e Fitness"},
        "amazon_dep": {"sporting": "Esportes"},
        "shopee": ["suplemento", "roupa academia", "garrafa térmica"],
    },
    "saude": {
        "emoji": "🩺", "nome": "Saúde e Bem-estar",
        "ml": {"MLB264586": "Saúde"},
        "amazon_buscas": ["vitamina", "suplemento"],
        "shopee": ["vitamina", "creatina", "massageador"],
    },
    "brinquedos": {
        "emoji": "🧸", "nome": "Brinquedos e Bebês",
        "ml": {"MLB1132": "Brinquedos e Hobbies"},
        "amazon_dep": {"toys": "Brinquedos", "baby": "Bebês"},
        "shopee": ["brinquedo", "lego", "fralda"],
    },
    "pet": {
        "emoji": "🐶", "nome": "Pet",
        "ml": {"MLB1071": "Animais"},
        "amazon_dep": {"pets": "Pet Shop"},
        "shopee": ["ração", "brinquedo pet", "coleira"],
    },
    "automotivo": {
        "emoji": "🚗", "nome": "Automotivo",
        "ml": {"MLB5672": "Acessórios para Veículos"},
        "amazon_dep": {"automotive": "Automotivo"},
        "shopee": ["acessório carro", "suporte veicular", "capacete"],
        # relevância: o título precisa conter um destes termos (palavra inteira, sem acento)...
        "termos": ["carro", "carros", "automotivo", "automotiva", "veicular", "veiculo", "veiculos",
                   "moto", "motos", "motocicleta", "capacete", "pneu", "pneus", "calibrador",
                   "compressor de ar", "auxiliar de partida", "carregador de bateria", "bateria automotiva",
                   "rastreador", "reboque", "guincho", "carplay", "android auto", "multimidia",
                   "central multimidia", "som automotivo", "volante", "tapete automotivo", "farol",
                   "limpador de para-brisa", "para-brisa", "parabrisa", "retrovisor", "oleo", "lubrificante",
                   "aditivo", "wd-40", "graxa", "cera", "polidor", "polimento", "vitrificador", "cristalizador",
                   "detailing", "snow foam", "shampoo automotivo", "lavagem", "lavadora", "lava jato",
                   "alta pressao", "pano de microfibra", "microfibra", "aspirador automotivo",
                   "aspirador de po portatil", "vonixx", "cadeira para auto", "cinta", "macaco hidraulico",
                   "chave de roda", "chave de impacto", "jogo de chaves", "ferramentas", "kit de ferramentas",
                   "caixa de ferramentas", "parafusadeira", "furadeira", "chave de fenda", "alicate",
                   "estepe", "triangulo", "extintor", "palheta", "sensor de re", "camera de re",
                   "dashcam", "camera veicular", "suporte celular carro", "suporte veicular",
                   "motoqueiro", "motoboy", "motociclista", "bebe conforto", "cadeirinha", "escapamento",
                   "alto falante", "falante", "triaxial", "subwoofer", "tweeter", "amplificador",
                   "amortecedor", "pastilha de freio", "disco de freio", "filtro de oleo", "filtro de ar",
                   "correia dentada", "silenciador", "carenagem", "lanterna traseira", "lampada led",
                   "kit xenon", "insulfilm", "alarme", "trava eletrica", "sensor de estacionamento",
                   "buzina", "cabo de bateria", "bomba de ar", "pneu", "aro de roda", "calota"],
        # ...e não pode conter nenhum destes (a página de "Automotivo" da Amazon vem misturada)
        "excluir": ["biblia", "livro", "livros", "colorir", "brinquedo", "brinquedos", "boneca", "pelucia",
                    "mobile", "hot wheels", "devocional", "romance", "cafe com deus"],
    },
    "country": {
        "emoji": "🤠", "nome": "Country (masculino e feminino)",
        "ml": {"MLB1430": "Calçados, Roupas e Bolsas"},
        "amazon_dep": {"fashion": "Moda"},
        "amazon_buscas": ["jaqueta country", "camisa country", "bota country", "boné country",
                          "calça country", "chapéu country", "cinto country"],
        "shopee": ["jaqueta country", "camisa country", "bota country", "boné country",
                   "calça country", "chapéu country", "cinto country"],
        "termos": ["country", "western", "texana", "texano", "vaqueiro", "vaqueira", "peao", "rodeio",
                   "boiadeiro", "sertanejo", "bota", "botas", "botina", "botinas", "chapeu", "cinto texano",
                   "fivela", "camisa xadrez", "colete country"],
        "excluir": ["infantil", "capa de celular", "brinquedo"],
    },
    "perfumes": {
        "emoji": "🧴", "nome": "Perfumes",
        "ml": {"MLB1246": "Beleza e Cuidado Pessoal"},
        "amazon_dep": {"beauty": "Beleza"},
        "amazon_buscas": ["perfume masculino", "perfume feminino", "eau de parfum", "body splash"],
        "shopee": ["perfume masculino", "perfume feminino", "body splash", "eau de parfum"],
        "termos": ["perfume", "perfumes", "colonia", "deo colonia", "eau de parfum", "eau de toilette",
                   "parfum", "body splash", "fragrancia", "edp", "edt", "kit perfume"],
        "excluir": ["porta perfume", "amostra", "atomizador vazio", "sabonete", "hidratante corporal"],
    },
    "livros": {
        "emoji": "📚", "nome": "Livros",
        "ml": {"MLB1196": "Livros, Revistas e Comics"},
        "amazon_dep": {"stripbooks": "Livros"},
        "shopee": ["livro"],
    },
}


def catalogo() -> list[dict]:
    """Lista para o painel: [{chave, emoji, nome}]."""
    return [{"chave": k, "emoji": v["emoji"], "nome": v["nome"]} for k, v in NICHOS.items()]


def ler_selecao() -> list[str]:
    """Chaves de nicho escolhidas no painel (data/nichos.json)."""
    if not ARQ_SELECAO.exists():
        return []
    try:
        dados = json.loads(ARQ_SELECAO.read_text(encoding="utf-8"))
        return [c for c in dados if c in NICHOS]
    except (ValueError, TypeError):
        return []


def salvar_selecao(chaves: list[str]) -> None:
    validas = [c for c in chaves if c in NICHOS]
    ARQ_SELECAO.write_text(json.dumps(validas), encoding="utf-8")


def _norm(texto: str) -> str:
    """minúsculas, sem acento, só letras/números/hífen/espaço."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\- ]+", " ", t)


def _casa(termo: str, titulo_norm: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(_norm(termo).strip())}(?:s|es)?(?![a-z0-9])", titulo_norm) is not None


def relevante(titulo: str, chaves: list[str], palavras=(), excluir=()) -> bool:
    """O título faz sentido para o canal? `chaves` são nichos do catálogo; `palavras`/`excluir`
    são termos próprios do canal. Sem nicho e sem palavras (ou nicho sem termos) = aceita."""
    if not chaves and not palavras:
        return True
    t = _norm(titulo)
    escolhidos = [NICHOS[c] for c in chaves if c in NICHOS]
    barrar = [x for n in escolhidos for x in n.get("excluir", [])] + list(excluir)
    if any(_casa(x, t) for x in barrar):
        return False
    termos = [x for n in escolhidos for x in n.get("termos", [])] + list(palavras)
    if not termos or any(not n.get("termos") for n in escolhidos):
        return True
    return any(_casa(x, t) for x in termos)


def expandir(chaves: list[str]) -> dict:
    """Junta os nichos escolhidos nas listas que cada fonte entende."""
    ml: dict[str, str] = {}
    amazon_dep: dict[str, str] = {}
    amazon_buscas: list[str] = []
    shopee: list[str] = []
    for k in chaves:
        n = NICHOS.get(k)
        if not n:
            continue
        ml.update(n.get("ml", {}))
        amazon_dep.update(n.get("amazon_dep", {}))
        for kw in n.get("amazon_buscas", []):
            if kw not in amazon_buscas:
                amazon_buscas.append(kw)
        for kw in n.get("shopee", []):
            if kw not in shopee:
                shopee.append(kw)
    return {"ml": ml, "amazon_dep": amazon_dep, "amazon_buscas": amazon_buscas, "shopee": shopee}

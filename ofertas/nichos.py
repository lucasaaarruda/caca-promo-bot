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
        "ml_buscas": ["boina de polimento", "lâmpada led h4", "lâmpada led h7", "bateria 20v ferramentas",
                      "kit ferramentas parafusadeira", "bicos lavadora alta pressão", "protetor solar para-brisa",
                      "selante de pneu", "cera automotiva", "aditivo diesel", "abafador esportivo", "kit detalhamento automotivo",
                      "espuma ativa lava jato", "aromatizante automotivo", "capa de volante", "carregador veicular"],
        # subcategorias do ML (árvore pública): cada uma tem a sua página de ofertas
        "ml": {"MLB188063": "Limpeza Automotiva", "MLB3381": "Som Automotivo", "MLB2227": "Ferramentas para Veículos",
               "MLB22693": "Peças de Carros", "MLB1747": "Acessórios de Carros", "MLB1771": "Acessórios de Motos",
               "MLB243551": "Peças de Motos", "MLB456111": "Lubrificantes e Fluidos", "MLB2239": "Segurança Veicular",
               "MLB2238": "Pneus e Acessórios",
               # subcategorias: cada uma tem a sua própria página de ofertas (a da categoria-mãe mostra só ~48)
               "MLB2228": "Iluminação", "MLB63532": "Escapamentos", "MLB191834": "Filtros", "MLB6789": "Freios",
               "MLB22648": "Suspensão e Direção", "MLB2220": "Baterias", "MLB440135": "Infladores",
               "MLB455304": "Ferramentas para Baterias", "MLB271120": "Guinchos", "MLB60657": "Chaves",
               "MLB114675": "Acessórios Exteriores", "MLB114676": "Acessórios Interiores",
               "MLB433258": "Boinas", "MLB263726": "Ceras", "MLB263728": "Polidor", "MLB263727": "Panos",
               "MLB431864": "Shampoo para Carros", "MLB363814": "Tratamentos", "MLB392348": "Seladores",
               "MLB430584": "Removedores de Arranhões", "MLB429409": "Abrilhantadores"},
        "ml_confiavel": True,  # a categoria já prova que é do nicho: só as exclusões valem
        "amazon_dep": {"automotive": "Automotivo"},
        "shopee": ["acessório carro", "suporte veicular", "capacete"],
        # relevância (Amazon/Shopee): o título precisa conter um destes termos (palavra inteira, sem acento)...
        "termos": ["carro", "carros", "automotivo", "automotiva", "automotivos", "veicular", "veiculo", "veiculos",
                   "moto", "motos", "motocicleta", "capacete", "pneu", "pneus", "calibrador",
                   "compressor de ar", "auxiliar de partida", "carregador de bateria", "bateria automotiva",
                   "rastreador", "reboque", "guincho", "carplay", "android auto", "multimidia",
                   "central multimidia", "som automotivo", "volante", "tapete automotivo", "farol",
                   "limpador de para-brisa", "para-brisa", "parabrisa", "retrovisor", "oleo de motor",
                   "lubrificante", "aditivo", "wd-40", "graxa", "cera automotiva", "cera liquida", "carnauba",
                   "polidor", "polimento", "vitrificador", "cristalizador", "detailing", "snow foam",
                   "shampoo automotivo", "lavagem", "lavadora de alta pressao", "lava jato", "alta pressao",
                   "pano de microfibra", "aspirador automotivo", "aspirador de po portatil", "vonixx",
                   "cadeira para auto", "macaco hidraulico", "chave de roda", "chave de impacto",
                   "jogo de chaves", "ferramentas", "kit de ferramentas", "caixa de ferramentas",
                   "parafusadeira", "furadeira", "estepe", "triangulo", "extintor", "palheta", "sensor de re",
                   "camera de re", "dashcam", "camera veicular", "suporte celular carro", "suporte veicular",
                   "motoqueiro", "motoboy", "motociclista", "bebe conforto", "cadeirinha", "escapamento",
                   "triaxial", "subwoofer automotivo", "amortecedor", "pastilha de freio", "disco de freio",
                   "filtro de oleo", "filtro de ar", "correia dentada", "silenciador", "carenagem",
                   "lanterna traseira", "lampada led", "kit xenon", "insulfilm", "alarme automotivo",
                   "alarme de carro", "trava eletrica", "sensor de estacionamento", "cabo de bateria",
                   "bomba de ar", "aro de roda", "calota", "fluido", "radiador",
                   "boina", "boinas", "politriz", "lampada h4", "lampada h7", "led h4", "led h7", "farol de milha",
                   "capa de volante", "capa de banco", "quebra-sol", "protetor solar para-brisa", "bicos para lavadora",
                   "engate rapido", "selante", "desengraxante", "aromatizante", "abafador", "ponteira", "catalisador",
                   "pastilha", "bateria 20v", "parafusadeira", "chave de impacto", "lavadora de pressao"],
        # ...e não pode conter nenhum destes (palavras que enganam: cueca "microfibra", celular "Moto G"...)
        "excluir": ["biblia", "livro", "livros", "colorir", "brinquedo", "brinquedos", "boneca", "pelucia",
                    "mobile", "hot wheels", "devocional", "romance", "cafe com deus", "motorola", "moto g",
                    "celular", "smartphone", "cueca", "cuecas", "badminton"],
    },
    "country": {
        "emoji": "🤠", "nome": "Country (masculino e feminino)",
        "ml_buscas": ["jaqueta country", "camisa country", "bota country", "boné country", "calça country feminina",
                      "chapéu country", "cinto country"],
        # categorias do ML onde ficam botas, bonés/chapéus, cintos, calças, camisas, jaquetas e camisetas
        "ml": {"MLB272202": "Botas", "MLB430275": "Bonés, Chapéus e Boinas", "MLB190393": "Cintos",
               "MLB188065": "Calças", "MLB107292": "Camisas", "MLB108803": "Casacos e Jaquetas",
               "MLB31447": "Camisetas e Regatas"},
        "amazon_dep": {"fashion": "Moda"},
        "amazon_buscas": ["jaqueta country", "camisa country", "bota country", "boné country",
                          "calça country", "chapéu country", "cinto country"],
        "shopee": ["jaqueta country", "camisa country", "bota country", "boné country",
                   "calça country", "chapéu country", "cinto country"],
        # estrito de propósito: "bota", "chapéu" e "fivela" sozinhos trazem bota de trabalho e chapéu de praia
        "termos": ["country", "western", "texana", "texano", "vaqueiro", "vaqueira", "peao", "rodeio",
                   "boiadeiro", "sertanejo", "cowboy", "cowgirl", "bico fino", "bico quadrado"],
        "excluir": ["infantil", "capa de celular", "capa para celular", "brinquedo"],
    },
    "perfumes": {
        "emoji": "🧴", "nome": "Perfumes",
        "ml_buscas": ["perfume árabe", "perfume masculino importado", "perfume feminino importado", "body splash"],
        "ml": {"MLB6284": "Perfumes"},
        "ml_confiavel": True,
        "amazon_dep": {"beauty": "Beleza"},
        "amazon_buscas": ["perfume masculino", "perfume feminino", "eau de parfum", "body splash"],
        "shopee": ["perfume masculino", "perfume feminino", "body splash", "eau de parfum"],
        "termos": ["perfume", "perfumes", "colonia", "deo colonia", "eau de parfum", "eau de toilette",
                   "parfum", "body splash", "fragrancia", "edp", "edt", "kit perfume"],
        "excluir": ["porta perfume", "amostra", "atomizador vazio", "sabonete", "hidratante corporal"],
    },
    "arcondicionado": {
        "emoji": "❄️", "nome": "Ar Condicionado",
        "ml_buscas": ["ar condicionado split 12000 btu", "ar condicionado inverter", "suporte ar condicionado"],
        "ml": {"MLB1646": "Ares Condicionados"},
        "ml_confiavel": True,
        "amazon_dep": {"appliances": "Eletrodomésticos"},
        "amazon_buscas": ["ar condicionado split", "ar condicionado inverter", "ar condicionado portátil"],
        "shopee": ["ar condicionado", "ar condicionado split", "ar condicionado portátil"],
        "termos": ["ar condicionado", "ar-condicionado", "split", "btu", "btus", "evaporadora", "condensadora",
                   "climatizador", "suporte para ar condicionado", "limpa ar condicionado"],
        "excluir": ["automotivo", "veicular", "carro", "capa protetora"],
        "desconto_sugerido": 10,  # ar condicionado raramente passa de 25% de desconto
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
    return [{"chave": k, "emoji": v["emoji"], "nome": v["nome"], "desconto_sugerido": v.get("desconto_sugerido")}
            for k, v in NICHOS.items()]


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


def categorias_confiaveis(chaves: list[str]) -> set[str]:
    """Categorias do ML que, por si só, provam que a oferta é do nicho (só as exclusões continuam valendo)."""
    return {cid for c in chaves if NICHOS.get(c, {}).get("ml_confiavel") for cid in NICHOS[c].get("ml", {})}


def relevante(titulo: str, chaves: list[str], palavras=(), excluir=(), categoria: str | None = None) -> bool:
    """O título faz sentido para o canal? `chaves` são nichos do catálogo; `palavras`/`excluir`
    são termos próprios do canal; `categoria` é a categoria do ML de onde a oferta veio.
    Sem nicho e sem palavras (ou nicho sem termos) = aceita."""
    if not chaves and not palavras:
        return True
    t = _norm(titulo)
    escolhidos = [NICHOS[c] for c in chaves if c in NICHOS]
    barrar = [x for n in escolhidos for x in n.get("excluir", [])] + list(excluir)
    if any(_casa(x, t) for x in barrar):
        return False
    if categoria and categoria in categorias_confiaveis(chaves):
        return True
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
    ml_buscas: list[str] = []
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
        for kw in n.get("ml_buscas", []):
            if kw not in ml_buscas:
                ml_buscas.append(kw)
    return {"ml": ml, "amazon_dep": amazon_dep, "amazon_buscas": amazon_buscas, "shopee": shopee, "ml_buscas": ml_buscas}

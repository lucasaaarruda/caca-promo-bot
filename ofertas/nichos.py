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
from functools import lru_cache

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
        "ml_buscas": ["boina de polimento", "lâmpada led h4", "lâmpada led h7", "bateria automotiva",
                      "bicos lavadora alta pressão", "protetor solar para-brisa",
                      "selante de pneu", "cera automotiva", "aditivo diesel", "kit detalhamento automotivo",
                      "espuma ativa lava jato", "aromatizante automotivo", "capa de volante", "carregador veicular",
                      "tweeter jbl selenium", "lavadora alta pressão wap", "shampoo automotivo",
                      "pneu aro 13", "pneu aro 14", "pneu aro 15", "fita led interior carro", "escova detalhamento automotivo",
                      "amortecedor porta-malas", "palheta limpador para-brisa", "pastilha de freio",
                      "espuma mágica proauto", "kit limpeza interna vonixx", "restaurax vonixx", "v-floc vonixx",
                      "liqui moly aditivo", "fluido de freio dot 4", "macaco hidráulico jacaré", "tacômetro conta-giros",
                      "difusor de escape eletrônico", "volante esportivo deep dish", "canhão de espuma snow foam",
                      "quebra-sol para-brisa", "inversor de energia automotivo", "carregador veicular retrátil",
                      "multimídia carplay 7 polegadas", "lavadora portátil alta pressão bateria",
                      "aspirador automotivo portátil", "luz led interior carro", "cheirinho para carro",
                      "kit lavagem caraíva", "cera alien", "selante de pneus gloss", "limpa alumínio vintex alumax"],
        # subcategorias do ML (árvore pública): cada uma tem a sua página de ofertas
        "ml": {"MLB188063": "Limpeza Automotiva", "MLB3381": "Som Automotivo",
               "MLB22693": "Peças de Carros", "MLB1747": "Acessórios de Carros",
               "MLB456111": "Lubrificantes e Fluidos", "MLB2239": "Segurança Veicular",
               "MLB2238": "Pneus e Acessórios",
               # subcategorias: cada uma tem a sua própria página de ofertas (a da categoria-mãe mostra só ~48)
               "MLB2228": "Iluminação", "MLB63532": "Escapamentos", "MLB191834": "Filtros", "MLB6789": "Freios",
               "MLB22648": "Suspensão e Direção", "MLB2220": "Baterias",
               "MLB271120": "Guinchos", "MLB60657": "Chaves",
               "MLB114675": "Acessórios Exteriores", "MLB114676": "Acessórios Interiores",
               "MLB433258": "Boinas", "MLB263726": "Ceras", "MLB263728": "Polidor", "MLB263727": "Panos",
               "MLB431864": "Shampoo para Carros", "MLB363814": "Tratamentos", "MLB392348": "Seladores",
               "MLB430584": "Removedores de Arranhões", "MLB429409": "Abrilhantadores"},
        "ml_confiavel": True,  # a categoria já prova que é do nicho: só as exclusões valem
        "amazon_dep": {"automotive": "Automotivo"},
        "amazon_buscas": ["shampoo automotivo", "cera automotiva", "aspirador automotivo", "multimídia carplay",
                          "kit lavagem automotiva", "aditivo combustível", "aromatizante carro"],
        "shopee": ["acessório carro", "suporte veicular", "capacete", "cheirinho carro", "aspirador automotivo",
                   "multimídia carplay", "capa de volante", "carregador veicular", "quebra-sol para-brisa",
                   "shampoo automotivo", "kit lavagem carro", "pneu aro 14", "lâmpada led carro",
                   "difusor de escape", "inversor de energia automotivo"],
        # relevância (Amazon/Shopee): o título precisa conter um destes termos (palavra inteira, sem acento)...
        "termos": ["carro", "carros", "automotivo", "automotiva", "automotivos", "veicular", "veiculo", "veiculos",
                   "moto", "motos", "motocicleta", "capacete", "pneu", "pneus", "calibrador",
                   "calibrador de pneu", "mini compressor", "inflador de pneu", "auxiliar de partida", "carregador de bateria", "bateria automotiva",
                   "rastreador", "reboque", "guincho", "carplay", "android auto", "multimidia",
                   "central multimidia", "som automotivo", "volante", "tapete automotivo", "farol",
                   "limpador de para-brisa", "para-brisa", "parabrisa", "retrovisor", "oleo de motor",
                   "lubrificante", "aditivo", "wd-40", "graxa", "cera automotiva", "cera liquida", "carnauba",
                   "polidor", "polimento", "vitrificador", "cristalizador", "detailing", "snow foam",
                   "shampoo automotivo", "lavagem", "lavadora de alta pressao", "lava jato", "alta pressao",
                   "pano de microfibra", "aspirador automotivo", "vonixx",
                   "cadeira para auto", "macaco hidraulico", "chave de roda",
                   "estepe", "triangulo", "extintor", "palheta", "sensor de re",
                   "camera de re", "dashcam", "camera veicular", "suporte celular carro", "suporte veicular",
                   "motoqueiro", "motoboy", "motociclista", "bebe conforto", "cadeirinha", "escapamento",
                   "triaxial", "subwoofer automotivo", "amortecedor", "pastilha de freio", "disco de freio",
                   "filtro de oleo", "filtro de ar", "correia dentada", "silenciador", "carenagem",
                   "lanterna traseira", "lampada led", "kit xenon", "insulfilm", "alarme automotivo",
                   "alarme de carro", "trava eletrica", "sensor de estacionamento", "cabo de bateria",
                   "bomba de ar", "aro de roda", "calota", "fluido", "radiador",
                   "boina de polimento", "boina de espuma", "boina de la", "boina de carneiro", "politriz", "lampada h4", "lampada h7", "led h4", "led h7", "farol de milha",
                   "capa de volante", "capa de banco", "quebra-sol", "protetor solar para-brisa", "bicos para lavadora",
                   "selante", "desengraxante", "aromatizante", "abafador de escape", "abafador de escapamento", "ponteira de escape", "ponteira de escapamento", "catalisador",
                   "lavadora de pressao",
                   "tweeter", "super tweeter", "selenium", "pneu aro", "kit lavagem", "carnauba",
                   # vistos em grupos de referência: marcas de estética/química automotiva
                   "proauto", "liqui moly", "vintex", "alumax", "restaurax", "caraiva", "easytech", "meguiars",
                   "menzerna", "autoglym", "motul", "castrol", "wurth", "tekna", "karcher",
                   # produtos
                   "espuma magica", "difusor de escape", "escape eletronico", "canhao de espuma", "pistola de espuma",
                   "inversor de energia", "inversor veicular", "tacometro", "conta giros", "conta-giros", "pneu pretinho", "pretinho para pneu",
                   "revitalizador de pneu", "revitalizador de plastico", "restaurador de plastico", "descontaminante",
                   "organizador de porta malas", "organizador de porta-malas", "macaco jacare",
                   "lavadora portatil", "mangueira para lavadora", "limpa estofado automotivo"],
        # ...e não pode conter nenhum destes (palavras que enganam: cueca "microfibra", celular "Moto G"...)
        "excluir": ["biblia", "livro", "livros", "colorir", "brinquedo", "brinquedos", "boneca", "pelucia",
                    "facial", "fps", "hidratante", "capilar", "cabelo", "finalizador",  # pele e cabelo ("selante" casava com selante capilar)
                    # "engate rapido" sozinho barrava lavadora ("com Engate Rápido EasyWash") e bico de lavadora
                    "compressor de ar direto", "pneumatico", "pneumatica", "hidropneumatico", "soquete", "soquetes", "adaptador de impacto", "borracheiro",  # ferramenta de oficina
                    "pra moto", "pneu traseiro", "pneu dianteiro", "2 tempos", "rocadeira", "motoserra",  # moto e jardinagem
                    # obra e casa que vêm por categoria cruzada do ML ou por um termo solto ("selante", "tekna", "cera liquida")
                    "espatula", "rejunte", "calafetagem", "porcelanato", "ar direto", "poco artesiano",
                    "poliflor", "moveis", "xixi", "cao e gato",
                    "poste de ferro", "limitador de vaga", "redutor de engrenagem", "fresa quimica",  # nada a ver com carro
                    "chapeu", "louca", "lava louca",  # boina de chapéu e detergente de louça casavam com "boina"/"pastilha" ("Ultra Fluido" casava com fluido de freio)
                    "mobile", "hot wheels", "devocional", "romance", "cafe com deus", "motorola", "moto g",
                    "celular", "smartphone", "cueca", "cuecas", "badminton", "oculos de sol", "aspirador vertical", "aspirador de po vertical", "passapano",
                    # moto é outro nicho (ver "moto" abaixo): modelos, peças e acessórios exclusivos de moto
                    "carenagem", "paralama", "cg", "titan", "bros", "biz", "pcx", "xre", "crf", "cbx", "ybr", "xtz", "nxr",
                    "yamaha", "suzuki", "kawasaki", "motocross", "enduro", "motoqueiro", "motoboy", "moto honda",
                    "para moto", "de moto", "capacete", "viseira", "bau moto", "top case", "intercomunicador",
                    # ferramenta e EPI têm canal próprio (nicho "ferramentas"): nunca no automotivo, nem pela categoria do ML
                    "parafusadeira", "furadeira", "esmerilhadeira", "esmeril", "lixadeira", "serra",
                    "serrote", "plaina", "martelete", "rompedor", "soprador termico", "solda", "soldador", "soldagem", "inversora",
                    "chave de impacto", "jogo de soquetes", "catraca", "bits", "broca", "brocas", "alicate", "torquimetro",
                    "jogo de chaves", "jogo de chave", "chave allen", "chave torx", "chave combinada", "chave de fenda",
                    "nivel laser", "nivel a laser", "trena", "multimetro", "pistola de pintura", "painel de secagem", "secagem",
                    "compressor de ar eletrico", "epi", "mascara", "mascaras", "respirador", "pff2", "protecao auditiva",
                    "protetor auricular", "tiro", "colete", "colete refletivo", "luva de trabalho", "luva de seguranca",
                    "luva nitrilica", "oculos de protecao", "botina de seguranca", "bota de seguranca", "capacete de seguranca"],
        # pneu de moto pela medida (140/70-17, 90/90-19: hífen antes do aro); pneu de carro usa "R" (175/70R14).
        # Bicicleta (pneu, câmara de ar, colete) vem pela categoria "Pneus e Acessórios" do ML: barra quando o título é de
        # bike e não cita carro ("Compressor Portátil para Carro, Moto e Bike" continua passando)
        "excluir_regex": [r"(?<!\d)\d{2,3} \d{2,3}-\d{2}(?!\d)",
                          r"^(?!.*\b(?:carro|carros|veicular|automotiv[ao]s?|automovel|automoveis|partida)\b)"
                          r".*\b(?:bike|bikes|bicicleta|bicicletas|mtb|ciclismo|ciclista)\b"],
        "diversidade": {"espaco": 6, "max_dia": 4, "familia_janela": 4, "familia_max": 2},
        "tipos": [
            ("lavadora", "estetica", ["lavadora", "lava jato", "hidrolavadora", "canhao de espuma", "snow foam", "pistola de espuma",
                                      "mangueira para lavadora", "bicos para lavadora"]),
            ("som-falante", "som", ["alto falante", "falante", "triaxial", "tweeter", "woofer", "subwoofer", "caixa amplificada",
                                    "amplificador", "som automotivo", "selenium"]),
            ("multimidia", "som", ["multimidia", "carplay", "android auto", "radio", "dvd", "camera de re", "dashcam",
                                   "camera veicular"]),
            ("fonte-carregador", "eletrica", ["fonte automotiva", "inversor", "carregador de bateria", "auxiliar de partida",
                                              "carregador veicular", "carregador veiculo", "wall box", "wallbox", "carregador"]),
            ("bateria", "eletrica", ["bateria"]),
            ("iluminacao", "eletrica", ["lampada", "led", "farol", "lanterna", "xenon"]),
            ("pneu", "pneus", ["pneu", "aro", "calibrador", "inflador", "mini compressor", "compressor", "pretinho",
                               "revitalizador de pneu"]),
            ("suspensao", "mecanica", ["amortecedor", "bucha", "coxim", "batente", "mola", "pivo", "terminal", "bandeja"]),
            ("freio", "mecanica", ["pastilha", "disco de freio", "fluido de freio", "freio"]),
            ("oleo-fluido", "mecanica", ["oleo", "lubrificante", "aditivo", "fluido", "wd-40", "graxa", "liqui moly", "motul",
                                         "castrol"]),
            ("escape-filtro", "mecanica", ["filtro", "correia", "vela", "radiador", "escapamento", "silenciador", "catalisador",
                                           "ponteira"]),
            ("cadeirinha", "seguranca", ["cadeira para auto", "cadeira para carro", "cadeira infantil", "cadeirinha",
                                         "bebe conforto", "isofix", "assento de carro", "assento"]),
            ("macaco-estepe", "seguranca", ["macaco", "estepe", "triangulo", "chave de roda", "extintor", "guincho", "reboque",
                                            "cinta"]),
            ("cera-polidor", "estetica", ["cera", "carnauba", "polidor", "polimento", "composto", "politriz", "boina de polimento", "boina de espuma",
                                          "vitrificador", "cristalizador", "descontaminante", "selante", "abrilhantador"]),
            ("shampoo-limpeza", "estetica", ["shampoo", "desengraxante", "limpa", "limpador", "vonixx", "detailing", "microfibra",
                                             "pano", "esponja", "aspirador", "kit lavagem"]),
            ("aromatizante", "acessorios", ["aromatizante", "cheirinho", "cheiro", "gel carro"]),
            ("volante-banco", "acessorios", ["volante", "capa de banco", "tapete", "quebra sol", "protetor solar", "para brisa",
                                             "suporte", "organizador"]),
            ("capa-chave", "acessorios", ["capa para chave", "chave"]),
        ],
    },
    "country": {
        "emoji": "🤠", "nome": "Country (masculino e feminino)",
        "ml_buscas": ["jaqueta country", "camisa country", "bota country", "boné country", "calça country feminina",
                      "chapéu country", "cinto country", "bota texana", "camisa western", "fivela rodeio",
                      "calça wrangler", "bolsa country", "chapéu cowboy", "colete country",
                      "calça jeans country masculina", "camisa agro brk", "calça ariat"],
        # categorias do ML onde ficam botas, bonés/chapéus, cintos, calças, camisas, jaquetas e camisetas
        "ml": {"MLB272202": "Botas", "MLB430275": "Bonés, Chapéus e Boinas", "MLB190393": "Cintos",
               "MLB188065": "Calças", "MLB107292": "Camisas", "MLB108803": "Casacos e Jaquetas",
               "MLB31447": "Camisetas e Regatas"},
        "amazon_dep": {"fashion": "Moda"},
        # a Amazon tem as marcas americanas de rodeio (Wrangler, Ariat, Cinch, Rock & Roll Denim)
        "amazon_buscas": ["calça jeans ariat", "calça jeans cinch", "calça jeans wrangler masculina",
                          "calça jeans ariat feminina", "calça rock and roll denim", "calça jeans country masculina",
                          "jaqueta country", "camisa country", "bota country", "boné country",
                          "chapéu country", "cinto country", "wrangler", "ariat",
                          "cinch", "bota western", "camisa western", "bolsa wrangler"],
        # Wrangler/Ariat/Cinch na Amazon vêm como "Enviado / Vendido Amazon Global" (a própria Amazon importando)
        "amazon_global": True,
        # o que mais vende e dá mais lucro no grupo: jeans importado das marcas de rodeio. Sai na frente de qualquer
        # outra oferta (mesmo sem desconto) e as buscas deles rodam TODA rodada, sem esperar o rodízio da Amazon
        "prioridade": {"marcas": ["ariat", "cinch", "wrangler", "rock and roll", "rock roll", "rock&roll"],
                       "produtos": ["calca", "jeans"]},
        "amazon_buscas_fixas": ["calça jeans ariat", "calça jeans cinch", "calça jeans wrangler masculina"],
        "shopee": ["jaqueta country", "camisa country", "bota country", "boné country",
                   "calça country", "chapéu country", "cinto country", "bota texana", "fivela rodeio"],
        # estrito de propósito: "bota", "chapéu" e "fivela" sozinhos trazem bota de trabalho e chapéu de praia, e
        # "bico fino" é só o formato do sapato (bota Chelsea, sapato social). O título precisa de um termo de ESTILO
        # (abaixo) E de um PRODUTO de moda ("produtos"): "Camisa Lampião Western" e "Encadernadora The Cinch" não passam.
        "termos": ["country", "western", "texana", "texano", "vaqueiro", "vaqueira", "peao", "rodeio",
                   "boiadeiro", "boiadeira", "sertanejo", "cowboy", "cowgirl",
                   # marcas de moda country/rodeio
                   "wrangler", "ariat", "cinch", "rock and roll", "rock roll", "rock&roll", "selff", "stetson",
                   "resistol", "justin boots", "tony lama", "twisted x", "durango", "ranch road", "tassa",
                   "zenz", "mcountry", "texas farm", "brk", "agro", "fazendeiro"],
        "produtos": ["bota", "botina", "boot", "bone", "chapeu", "hat", "camisa", "camiseta", "camisao", "shirt", "blusa",
                     "regata", "calca", "jeans", "bermuda", "jaqueta", "colete", "casaco", "cinto", "fivela", "bolsa",
                     "mochila", "lenco", "vestido", "saia", "macacao", "conjunto", "cueca", "meia", "gravata", "pochete"],
        "excluir": ["infantil", "capa de celular", "capa para celular", "brinquedo", "boneca", "boneco", "pelucia",
                    "franja", "livro", "fantasia", "menino", "meninos", "menina", "meninas", "kids", "juvenil",
                    "maquiagem", "necessaire", "chuva", "jardim", "jeep", "pneu", "estepe", "carro", "automotivo", "figurino",
                    # não é moda: lampião, artesanato/papelaria, bijuteria e decoração
                    "lampiao", "vela", "velas", "encadernadora", "craft", "artesanato", "scrapbook", "papel", "adesivo",
                    "berloque", "pingente", "banhado", "joia", "brinco", "colar", "pulseira", "anel", "chaveiro",
                    "miniatura", "quadro", "decoracao", "caneca", "toalha", "almofada", "cortina", "tapete",
                    # bota que não é country
                    "chelsea", "social", "galocha", "seguranca", "epi", "trabalho", "pvc", "safety"],
        # jeans é o que mais vende no country: o tipo pode repetir com mais folga que nos outros nichos. O jeans
        # importado (prioridade) nem espera a vez: só conta no teto do dia (o concorrente posta um por tamanho)
        "diversidade": {"espaco": 1, "max_dia": 15, "familia_max": 4, "max_dia_por_tipo": {"camisa-agro": 2, "calca": 30}},
        # a ordem importa (vale o primeiro que casar): "Jaqueta jeans" é jaqueta, "Jeans Boot Cut" é calça, não bota,
        # e "Cinto ... para Calça 38" é cinto
        "tipos": [
            ("jaqueta", "roupa", ["jaqueta", "colete", "casaco"]),
            ("cinto-fivela", "acessorio", ["cinto", "fivela"]),
            ("bone-chapeu", "acessorio", ["bone", "chapeu", "hat"]),
            ("camisa-agro", "roupa", ["agro", "trator", "fazenda", "roca"]),  # muito parecidas entre vendedores: máx. 2 por dia
            ("camisa", "roupa", ["camisa", "camiseta", "camisao", "shirt", "blusa", "regata"]),
            ("calca", "roupa", ["calca", "jeans", "bermuda", "macacao", "vestido", "saia"]),
            ("bota", "calcado", ["bota", "botina", "texana", "boot"]),
            ("bolsa", "acessorio", ["bolsa", "mochila", "lenco", "pochete"]),
        ],
        "desconto_sugerido": 20,
    },
    "perfumes": {
        "emoji": "🧴", "nome": "Perfumes",
        # busca por marca/linha: sem isso a Shopee devolve perfume genérico de R$ 20 e a ML devolve de tudo
        "ml_buscas": ["perfume árabe", "perfume lattafa", "perfume armaf", "perfume afnan", "perfume al haramain",
                      "perfume masculino importado", "perfume feminino importado", "perfume paco rabanne",
                      "perfume carolina herrera", "perfume jean paul gaultier", "perfume dior", "perfume azzaro",
                      "perfume versace", "perfume natura", "perfume boticário", "perfume issey miyake",
                      "perfume contratipo", "perfume nicho", "perfume oud", "perfume maison alhambra",
                      "perfume fragrance world", "perfume swiss arabian", "perfume calvin klein", "perfume gucci",
                      "perfume prada", "perfume tom ford", "perfume in the box", "perfume victoria's secret"],
        "ml": {"MLB6284": "Perfumes"},
        "ml_confiavel": True,
        "amazon_dep": {"beauty": "Beleza"},
        "amazon_buscas": ["perfume masculino", "perfume feminino", "eau de parfum", "perfume árabe",
                          "perfume lattafa", "perfume armaf", "perfume importado", "perfume nicho", "perfume árabe masculino",
                          "perfume árabe feminino", "perfume contratipo"],
        "shopee": ["perfume lattafa", "perfume armaf", "perfume árabe", "perfume afnan", "perfume importado original",
                   "eau de parfum", "perfume masculino importado", "perfume feminino importado",
                   "perfume contratipo", "perfume oud", "perfume nicho", "perfume maison alhambra",
                   "perfume calvin klein", "perfume in the box"],
        "termos": ["perfume", "perfumes", "colonia", "deo colonia", "eau de parfum", "eau de toilette",
                   "parfum", "body splash", "edp", "edt", "kit perfume",
                   # casas de perfumaria pura: valem sozinhas
                   "lattafa", "armaf", "afnan", "al haramain", "rasasi", "paco rabanne", "carolina herrera",
                   "jean paul gaultier", "azzaro", "issey miyake",
                   # árabes e orientais
                   "swiss arabian", "ajmal", "maison alhambra", "fragrance world", "orientica", "al rehab",
                   "arabian oud", "khadlaj", "french avenue", "zimaya", "pendora", "paris corner", "emper",
                   "ard al zaafaran", "nabeel", "rave now", "al wataniah", "ahmed al maghribi", "my perfumes",
                   "riiffs", "gulf orchid", "asgharali", "oudh", "oud",
                   # nicho e luxo (perfumaria pura)
                   "creed", "parfums de marly", "xerjoff", "amouage", "initio", "mancera", "montale", "nishane",
                   "kilian", "maison francis kurkdjian", "frederic malle", "penhaligon", "memo paris", "byredo",
                   "le labo", "roja", "nasomatto", "tiziana terenzi", "bond no 9", "juliette has a gun",
                   "maison crivelli", "orto parisi", "ex nihilo", "clive christian", "profumum roma",
                   # contratipos ("inspirado em...") e marcas brasileiras de perfumaria
                   "contratipo", "contratipos", "dumont", "hinode", "contem 1g"],
        # marcas que também vendem roupa, maquiagem e cuidados: só valem JUNTO de um "sinal" de fragrância
        # ("Dior Sauvage Eau de Toilette" passa; "Camiseta Dior" e "Batom Dior" não)
        "marcas": ["dior", "chanel", "natura", "boticario", "o boticario", "eudora", "jequiti", "avon", "versace",
                   "montblanc", "hugo boss", "calvin klein", "dolce gabbana", "giorgio armani", "yves saint laurent",
                   "ysl", "ralph lauren", "lacoste", "givenchy", "lancome", "burberry", "bvlgari", "kenzo",
                   "davidoff", "mugler", "thierry mugler", "antonio banderas", "ferrari", "polo", "nautica",
                   "adidas", "puma", "mahogany", "granado", "phebo", "quasar", "egeo", "kaiak",
                   "tom ford", "gucci", "prada", "hermes", "cartier", "valentino", "jimmy choo", "guerlain",
                   "jo malone", "diptyque", "maison margiela", "replica", "narciso rodriguez", "viktor rolf",
                   "paris hilton", "victoria s secret", "bath body works", "zara", "carolina herrera",
                   "in the box", "inthebox", "in box", "ariana grande", "britney spears", "jennifer lopez",
                   "playboy", "ferrari", "hollister", "abercrombie", "tommy hilfiger", "diesel", "moschino",
                   "cacharel", "chloe", "lanvin", "rochas", "salvatore ferragamo", "paul smith", "mont blanc"],
        "sinais": ["perfume", "perfumes", "parfum", "eau de parfum", "eau de toilette", "eau de cologne", "colonia",
                   "deo colonia", "desodorante colonia", "edp", "edt", "fragrancia", "body splash", "splash",
                   "sauvage", "one million", "invictus", "good girl", "la vie est belle", "black opium", "miss dior",
                   "coco mademoiselle", "bleu de chanel", "ck one", "eternity", "light blue", "le male", "212 vip",
                   "212 men", "malbec", "kaiak"],
        "excluir": ["porta perfume", "amostra", "decant", "atomizador vazio", "sabonete", "hidratante corporal",
                    "infantil", "capilar", "cabelo", "feromonio", "feromonios", "ambiente", "ambientes", "automotivo",
                    "carro", "carros", "roupa", "roupas", "tecido", "tecidos", "difusor", "vela", "pet", "cachorro",
                    "vazio", "frasco vazio", "essencia para", "cristais", "comfort",  # "Comfort Perfume em Cristais" é perfume de roupa
                    # produtos de limpeza/casa que só citam "fragrância" ou "perfumado" no título
                    "detergente", "limpador", "limpeza", "limpa", "extratora", "extratoras", "lava roupa", "lava roupas",
                    "amaciante", "desinfetante", "sabao", "multiuso", "odorizador", "aromatizador", "aromatizante",
                    "banheiro", "cozinha", "wap", "sachet", "home spray", "bruma para",
                    # perfume de criança / personagem
                    "turma da monica", "cebolinha", "magali", "disney", "frozen", "patrulha canina", "kids", "baby", "bebe",
                    # produtos das mesmas marcas que não são perfume
                    "camiseta", "camisa", "cueca", "jeans", "bermuda", "blusa", "tenis", "relogio", "oculos", "bolsa",
                    "carteira", "batom", "base", "po compacto", "rimel", "sombra", "esmalte", "shampoo",
                    "condicionador", "creme", "esfoliante", "protetor solar", "maquiagem", "desodorante antitranspirante",
                    "antitranspirante", "roll on",
                    # sinais clássicos de falsificação/imitação anunciada
                    "replica", "falsificado", "falsificada", "imitacao", "aaa", "primeira linha", "paralelo"],
        # falsificação é comum em perfume: só entra oferta de vendedor verificável (loja oficial)
        "exigir_loja_confiavel": True,
        # variedade: casa/linha diferente a cada post e alternando árabe, grife e nacional
        "diversidade": {"espaco": 5, "max_dia": 3, "familia_janela": 4, "familia_max": 2},
        "familia_padrao": "grife",
        "ruido_tipo": ["perfume", "parfum", "eau", "toilette", "colonia", "deo", "desodorante", "body", "splash", "edp", "edt",
                       "original", "importado", "tradicional", "beauty"],
        "tipos": [
            ("lattafa", "arabe", ["lattafa"]),
            ("armaf", "arabe", ["armaf", "club de nuit"]),
            ("afnan", "arabe", ["afnan"]),
            ("maison alhambra", "arabe", ["maison alhambra", "alhambra"]),
            ("al wataniah", "arabe", ["al wataniah", "wataniah"]),
            ("al haramain", "arabe", ["al haramain"]),
            ("orientica", "arabe", ["orientica"]),
            ("fragrance world", "arabe", ["fragrance world"]),
            ("arabe", "arabe", ["arabe", "rasasi", "swiss arabian", "ajmal", "al rehab", "khadlaj", "french avenue", "zimaya",
                                "pendora", "paris corner", "emper", "ard al zaafaran", "nabeel", "rave now", "oud", "oudh",
                                "attar", "rayhaan"]),
            ("armani", "grife", ["armani"]),
            ("ralph lauren", "grife", ["ralph lauren", "polo"]),
            ("carolina herrera", "grife", ["carolina herrera"]),
            ("paco rabanne", "grife", ["paco rabanne", "rabanne"]),
            ("jean paul gaultier", "grife", ["jean paul gaultier", "gaultier"]),
            ("lancome", "grife", ["lancome"]),
            ("calvin klein", "grife", ["calvin klein"]),
            ("hugo boss", "grife", ["hugo boss"]),
            ("montblanc", "grife", ["montblanc", "mont blanc"]),
            ("azzaro", "grife", ["azzaro"]),
            ("natura", "nacional", ["natura", "kaiak", "essencial"]),
            ("boticario", "nacional", ["boticario", "o boticario", "malbec"]),
            ("granado", "nacional", ["granado", "phebo"]),
            ("jequiti", "nacional", ["jequiti"]),
            ("eudora", "nacional", ["eudora", "avon", "hinode", "dumont"]),
            ("body splash", "nacional", ["body splash", "splash"]),
        ],
        "desconto_sugerido": 15,
    },
    "ferramentas": {
        "emoji": "🛠️", "nome": "Ferramentas",
        # categorias do ML (árvore pública): manuais, elétricas, acessórios, organização, medição e EPIs
        "ml": {"MLB2527": "Ferramentas Manuais", "MLB33376": "Alicates", "MLB439306": "Kits de Ferramentas Manuais",
               "MLB188547": "Martelos", "MLB33435": "Grampos Sargento", "MLB455249": "Corte e Desbaste (manual)",
               "MLB455252": "Fixação", "MLB455257": "Alvenaria", "MLB235594": "Morsas",
               "MLB2526": "Ferramentas Elétricas", "MLB189008": "Parafusadeiras", "MLB457298": "Chaves de Impacto",
               "MLB455276": "Perfuração", "MLB455277": "Corte (elétrico)", "MLB455275": "Lixado, Desbaste e Polimento",
               "MLB455278": "Soldagem", "MLB188783": "Sopradores Térmicos", "MLB455536": "Kits de Ferramentas Elétricas",
               "MLB269518": "Compressores de Ar", "MLB456073": "Multiferramentas Oscilantes", "MLB433706": "Equipamento de Pintura",
               "MLB2528": "Acessórios para Ferramentas", "MLB271220": "Pontas e Adaptadores", "MLB271774": "Lâminas para Serras",
               "MLB418395": "Baterias para Ferramentas", "MLB399135": "Tesouras",
               "MLB189210": "Caixas e Organizadores", "MLB189215": "Bolsas para Ferramentas", "MLB189217": "Caixas de Ferramentas",
               "MLB189212": "Maletas de Ferramentas", "MLB189214": "Gaveteiros", "MLB270539": "Painéis para Ferramentas",
               "MLB189213": "Carrinhos de Ferramentas", "MLB264711": "Bancadas de Trabalho",
               "MLB5550": "Medição e Instrumentação", "MLB455206": "Níveis", "MLB455212": "Medidores de Distância",
               "MLB455200": "Medidores de Eletricidade (multímetro)", "MLB455198": "Medidores de Comprimento (trenas)",
               "MLB260682": "Esquadros", "MLB454904": "Proteção Pessoal (EPIs)", "MLB270151": "Coletes Refletivos"},
        "ml_confiavel": True,  # tudo isso é ferramenta: a categoria prova o nicho (as exclusões continuam valendo)
        # busca por palavra-chave na API do ML (produtos de catálogo): a lista do dono + complementos
        "ml_buscas": ["jogo de chaves de fenda e philips", "jogo de chaves de precisão", "martelo de unha", "alicate universal",
                      "alicate de bico fino", "alicate de corte", "chave inglesa", "jogo de chaves combinadas", "jogo de chaves allen",
                      "jogo de soquetes com catraca", "estilete", "serrote", "arco de serra", "chave grifo", "trena",
                      "nível de bolha", "esquadro", "parafusadeira a bateria", "furadeira de impacto", "jogo de brocas", "jogo de bits",
                      "serra tico-tico", "esmerilhadeira", "multímetro", "ferro de solda", "pistola de cola quente", "fita isolante",
                      "fita silver tape", "fita veda rosca", "abraçadeira de nylon", "cola instantânea", "cola de madeira", "silicone",
                      "lixa", "wd-40", "óculos de proteção", "luvas de trabalho", "protetor auricular", "máscara contra pó",
                      "caneta teste", "lanterna de cabeça", "extensão elétrica", "escada dobrável", "grampo sargento", "ímã telescópico",
                      "detector de canos e fios", "maleta de ferramentas", "bolsa de ferramentas", "organizador de ferramentas",
                      "painel de ferramentas", "marreta", "formão", "paquímetro", "torquímetro", "serra circular", "soprador térmico",
                      "estação de solda", "compressor de ar", "pistola de pintura", "serra copo", "disco de corte", "alicate amperímetro",
                      "nível a laser", "trena a laser", "morsa de bancada", "rebitadeira", "grampeador", "refletor led",
                      "chave de impacto", "lixadeira", "micro retífica", "furadeira de bancada", "kit de ferramentas completo",
                      "chiaperini", "tafort", "ferramentas chiaperini", "ferramentas tafort"],
        "amazon_dep": {"tools": "Ferramentas"},
        "amazon_buscas": ["parafusadeira", "kit de ferramentas", "jogo de chaves", "furadeira", "alicate", "maleta de ferramentas",
                          "chiaperini", "tafort"],
        "shopee": ["kit de ferramentas", "jogo de chaves", "chave torx allen", "parafusadeira", "alicate", "maleta de ferramentas",
                   "trena", "multímetro", "ferro de solda", "bolsa de ferramentas", "chiaperini", "tafort"],
        # relevância (Amazon/Shopee e buscas): título com algum destes termos (frases específicas: "luva", "máscara" e
        # "lixa" sozinhas pegariam boxe, cosmético e lixa de unha)
        "termos": [
            "chiaperini", "tafort",  # fabricantes de ferramentas
            "ferramenta", "ferramentas", "kit de ferramentas", "jogo de ferramentas", "jogo chaves", "kit chaves", "caixa de ferramentas", "maleta de ferramentas",
            "bolsa de ferramentas", "organizador de ferramentas", "organizador com divisorias", "painel perfurado", "painel de ferramentas",
            "bancada de trabalho", "carrinho de ferramentas", "gaveteiro de ferramentas", "cartucheira",
            "chave de fenda", "chaves de fenda", "chave philips", "chave phillips", "jogo de chaves", "chave de precisao", "chaves de precisao",
            "chave inglesa", "chave combinada", "chaves combinadas", "chave allen", "chave torx", "chave de boca", "chave estrela",
            "chave fixa", "chave biela", "chave grifo", "grifo", "chave canhao", "chave de impacto", "torquimetro", "soquete", "soquetes", "catraca",
            "martelo", "marreta", "talhadeira", "formao", "alicate", "alicates", "alicate amperimetro", "alicate de pressao",
            "estilete", "serrote", "arco de serra", "serra manual", "trena", "fita metrica", "nivel de bolha", "nivel a laser", "esquadro",
            "paquimetro", "micrometro", "prumo", "morsa", "grampo sargento", "sargento", "pe de cabra", "colher de pedreiro",
            "desempenadeira", "espatula",
            "parafusadeira", "furadeira", "furadeira de impacto", "furadeira de bancada", "esmerilhadeira", "esmeril", "lixadeira",
            "serra tico-tico", "serra tico tico", "serra circular", "serra marmore", "serra sabre", "serra copo", "micro retifica",
            "retificadeira", "plaina eletrica", "tupia", "soprador termico", "pistola de ar quente", "pistola de cola quente",
            "cola quente", "ferro de solda", "estacao de solda", "maquina de solda", "inversora de solda", "pistola de pintura",
            "compressor de ar", "multimetro", "detector de metais", "detector de canos", "detector de fios", "rebitadeira",
            "grampeador", "pinador", "pistola de calafetar",
            "broca", "brocas", "jogo de brocas", "bits", "jogo de bits", "ponta de chave", "disco de corte", "disco de desbaste",
            "disco flap", "lixa de parede", "lixa dagua", "lixa para madeira", "folha de lixa", "lixas",
            "parafuso", "parafusos", "bucha", "buchas", "prego", "pregos", "porca", "arruela", "abracadeira", "abracadeiras",
            "fita isolante", "silver tape", "fita veda rosca", "veda rosca", "fita crepe", "fita adesiva", "cola instantanea",
            "cola de madeira", "cola epoxi", "silicone", "wd-40", "desengripante", "lubrificante",
            "oculos de protecao", "luva de trabalho", "luvas de trabalho", "luva de seguranca", "luvas de seguranca", "luva de raspa",
            "luva nitrilica", "protetor auricular", "abafador de ruido", "mascara contra po", "mascara de solda", "respirador",
            "capacete de seguranca", "bota de seguranca", "botina de seguranca", "colete refletivo", "cinto de seguranca",
            "lanterna de cabeca", "lanterna tatica", "refletor led", "extensao eletrica", "filtro de linha", "adaptador de tomada",
            "escada dobravel", "escada multifuncional", "ima telescopico", "caneta teste", "caneta de teste", "detector de tensao",
        ],
        # barra o que se parece com ferramenta mas não é (brinquedo, manicure, culinária...)
        "excluir": ["brinquedo", "brinquedos", "infantil", "boneca", "manicure", "pedicure", "cuticula", "esmalte", "cabelo", "barbear",
                    "arma", "armas", "airsoft", "municao",  # maleta de arma não é ferramenta
                    "composto polidor", "blindex", "piso tatil",  # cera de carro, ferragem de box e piso de acessibilidade
                    "cinto catraca", "gourmet", "fogareiro", "bicicleta", "ciclismo",  # cinto de roupa, maçarico de cozinha, camping e bike
                    "culinario", "churrasqueira", "acendedor", "acougueiro", "plantas", "do solo", "snow foam",  # cozinha, jardim e lavagem de carro
                    "cortador de unha", "alicate de unha", "alicate de cuticula", "lixa de unha", "kit unha", "sobrancelha", "depilador",
                    "pinca", "tesoura de cabelo", "salao",
                    "maquiagem", "livro", "apostila", "curso", "software", "capa de celular", "carro de controle", "pet", "cachorro",
                    "faca de cozinha", "utensilio", "culinaria", "cozinha", "churrasco", "alimento", "faxina", "limpeza", "galocha",
                    # carro, lavadora e peça de carro são do nicho "automotivo" (e o que é de carro não entra aqui)
                    "veicular", "veiculo", "veiculos", "carro", "carros", "pneu", "pneus", "lava jato", "lavadora", "lavadoras",
                    "hidrolavadora", "caminhonete", "auxiliar de partida", "peugeot", "renault", "fiat", "volkswagen",
                    "chevrolet", "eixo traseiro", "eixo dianteiro", "amortecedor", "oleo de motor", "polimento", "lustro"],
        "diversidade": {"espaco": 6, "max_dia": 4, "familia_janela": 4, "familia_max": 2},
        # (tipo, família, termos): o primeiro que casar vale; serve para não postar o mesmo TIPO de produto em sequência
        "tipos": [
            ("serra-manual", "manuais", ["serrote", "arco de serra", "serra manual"]),
            ("furadeira", "eletricas", ["parafusadeira", "furadeira", "chave de impacto"]),
            ("esmerilhadeira", "eletricas", ["esmerilhadeira", "esmeril", "retifica", "micro retifica"]),
            ("lixadeira", "eletricas", ["lixadeira", "lixa eletrica"]),
            ("serra", "eletricas", ["serra"]),
            ("plaina", "eletricas", ["plaina", "tupia"]),
            ("martelete", "eletricas", ["martelete", "rompedor"]),
            ("mascara-solda", "eletricas", ["mascara de solda", "mascara solda"]),
            ("respirador", "epi", ["mascara", "respirador", "pff2", "pff1", "filtro", "pre filtro"]),
            ("solda", "eletricas", ["solda", "soldagem", "eletrodo", "inversora"]),
            ("compressor-pintura", "eletricas", ["compressor", "pistola de pintura", "pulverizadora"]),
            ("soprador-macarico", "eletricas", ["soprador termico", "pistola de ar quente", "macarico"]),
            ("bits-brocas", "acessorios", ["broca", "bits", "ponta de chave", "disco de corte", "disco de desbaste",
                                           "disco flap", "jogo de pontas", "kit de pontas"]),
            ("lixa-disco", "acessorios", ["disco de lixa", "lixa", "folha de lixa", "interface", "disco"]),
            ("chaves", "manuais", ["jogo de chaves", "jogo chaves", "kit chaves", "chave allen", "chave torx", "chave combinada",
                                   "chave de boca", "chave estrela", "chave inglesa", "chave de fenda", "chave philips",
                                   "chave phillips", "chave grifo", "chave fixa", "chave de precisao", "chave canhao",
                                   "soquete", "catraca", "torquimetro"]),
            ("alicate", "manuais", ["alicate", "decapador", "crimpador", "desencapador"]),
            ("martelo", "manuais", ["martelo", "marreta", "talhadeira", "formao", "pe de cabra"]),
            ("kit-ferramentas", "manuais", ["jogo de ferramentas", "kit de ferramentas", "kit ferramentas", "ferramentas manuais",
                                            "kit eletricista", "kit eletrico"]),
            ("grampo-morsa", "manuais", ["grampo sargento", "sargento", "morsa", "grampo", "grampeador", "rebitadeira", "pinador",
                                         "estilete", "tesoura", "podador"]),
            ("organizacao", "organizacao", ["maleta", "bolsa", "mala", "caixa de ferramentas", "caixa para ferramentas", "painel",
                                            "organizador", "gaveteiro", "bancada", "carrinho", "cartucheira"]),
            ("nivel", "medicao", ["nivel", "esquadro", "prumo"]),
            ("medidor", "medicao", ["trena", "paquimetro", "medidor", "micrometro", "fita metrica", "termometro", "multimetro",
                                    "detector", "amperimetro", "caneta teste"]),
            ("bateria-ferramenta", "acessorios", ["bateria", "carregador"]),
            ("protecao-auditiva", "epi", ["abafador", "protetor auricular", "protecao auditiva"]),
            ("calcado-epi", "epi", ["bota", "botina", "coturno", "sapato de seguranca"]),
            ("luva", "epi", ["luva"]),
            ("oculos", "epi", ["oculos"]),
            ("colete-capacete", "epi", ["colete", "capacete", "cinto de seguranca"]),
            ("construcao", "construcao", ["colher de pedreiro", "desempenadeira", "riscador", "cortador de piso", "nivelador",
                                          "espacador", "porcelanato", "ventosa", "massa corrida", "escada"]),
            ("fita-cola", "acessorios", ["fita", "cola", "silicone", "veda rosca", "abracadeira", "parafuso", "bucha", "prego"]),
            ("iluminacao-extensao", "acessorios", ["lanterna", "refletor", "extensao", "filtro de linha", "adaptador de tomada"]),
        ],
    },
    "moto": {
        "emoji": "🏍️", "nome": "Moto",
        "ml": {"MLB1771": "Acessórios de Motos", "MLB243551": "Peças de Motos", "MLB458209": "Motos (acessórios)"},
        "ml_buscas": ["capacete", "baú moto", "capa de chuva motoqueiro", "intercomunicador capacete", "escapamento moto"],
        "amazon_buscas": ["capacete moto", "baú moto"],
        "shopee": ["capacete moto", "baú moto", "escapamento moto"],
        "termos": ["moto", "motos", "motocicleta", "capacete", "motoqueiro", "motoboy", "carenagem", "paralama", "cg", "titan",
                   "bros", "biz", "pcx", "xre", "crf", "cbx", "ybr", "xtz", "nxr", "yamaha", "suzuki", "kawasaki", "motocross",
                   "bau moto", "top case", "viseira", "intercomunicador"],
        "excluir": ["brinquedo", "livro", "carro de controle"],
    },
    "arcondicionado": {
        "emoji": "❄️", "nome": "Ar Condicionado",
        # catálogo pequeno (poucos termos = fica refém do rodízio genérico de categoria, que traz muita coisa fora do nicho):
        # cobre as potências e marcas mais comuns para achar oferta direto, sem depender só da categoria
        "ml_buscas": ["ar condicionado split 9000 btu", "ar condicionado split 12000 btu", "ar condicionado split 18000 btu",
                      "ar condicionado split 24000 btu", "ar condicionado inverter", "ar condicionado quente frio",
                      "ar condicionado lg", "ar condicionado samsung", "ar condicionado springer", "ar condicionado midea",
                      "ar condicionado electrolux", "ar condicionado philco", "ar condicionado consul", "ar condicionado elgin",
                      "climatizador de ar", "suporte ar condicionado"],
        "ml": {"MLB1646": "Ares Condicionados"},
        "ml_confiavel": True,
        "amazon_dep": {"appliances": "Eletrodomésticos"},
        "amazon_buscas": ["ar condicionado split", "ar condicionado inverter", "ar condicionado portátil",
                          "ar condicionado 9000 btu", "ar condicionado 12000 btu", "ar condicionado 18000 btu",
                          "climatizador de ar"],
        "shopee": ["ar condicionado", "ar condicionado split", "ar condicionado portátil", "climatizador de ar"],
        "termos": ["ar condicionado", "ar-condicionado", "split", "btu", "btus", "evaporadora", "condensadora",
                   "climatizador", "suporte para ar condicionado", "limpa ar condicionado"],
        "excluir": ["automotivo", "automotiva", "veicular", "veiculo", "carro", "carros", "caminhao", "onibus", "trator",
                    "caminhonete", "pickup", "moto", "12v", "24v", "capa protetora", "caixa evaporadora", "filtro de ar condicionado", "bosch",
                    # peças de ar condicionado de carro vêm com o modelo do carro no título (Gol G2 G3 G4...)
                    "gol", "palio", "uno", "corsa", "celta", "fiesta", "ka", "hb20", "onix", "prisma", "fusca", "kombi",
                    "strada", "saveiro", "siena", "fox", "polo", "golf", "civic", "corolla", "hilux", "ranger", "l200",
                    "fiat", "volkswagen", "vw", "chevrolet", "ford", "honda", "toyota", "hyundai", "renault", "nissan",
                    "peugeot", "citroen", "jeep", "mitsubishi", "kia", "mercedes", "scania", "volvo", "iveco"],
        "diversidade": False,  # tudo é "ar condicionado": diversificar por tipo travaria o canal
        # catálogo pequeno: com 7 dias sem repetir o canal zerou (15, 17 e 18/10). O mesmo aparelho volta após 3 dias
        "nao_repetir_dias": 3,
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


def exige_loja_confiavel(chaves: list[str]) -> bool:
    """Algum nicho do canal só aceita vendedor verificável (ex.: perfumes, onde há muita falsificação)?"""
    return any(NICHOS.get(c, {}).get("exigir_loja_confiavel") for c in chaves)


def prioritaria(titulo: str, chaves: list[str]) -> bool:
    """A oferta é do que o canal mais quer postar (nicho "prioridade": marca + produto, como jeans Ariat/Cinch)?"""
    t = _norm(titulo)
    for c in chaves:
        p = NICHOS.get(c, {}).get("prioridade")
        if p and any(_casa(m, t) for m in p["marcas"]) and any(_casa(x, t) for x in p["produtos"]):
            return True
    return False


def aceita_amazon_global(chaves: list[str]) -> bool:
    """Algum nicho do canal aceita produto "Enviado / Vendido Amazon Global" (importado pela própria Amazon,
    original)? Country: Wrangler, Ariat e Cinch só chegam assim."""
    return any(NICHOS.get(c, {}).get("amazon_global") for c in chaves)


def _norm(texto: str) -> str:
    """minúsculas, sem acento, só letras/números/hífen/espaço."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\- ]+", " ", t)


def _casa(termo: str, titulo_norm: str) -> bool:
    """O termo aparece no título como palavra(s) inteira(s)? Aceita plural em QUALQUER palavra do termo:
    "chave allen" casa "jogo de chaves allen"; "luva de trabalho" casa "luvas de trabalho"."""
    palavras = _norm(termo).split()
    if not palavras:
        return False
    corpo = r"\s+".join(re.escape(p) + r"(?:s|es)?" for p in palavras)
    return re.search(rf"(?<![a-z0-9]){corpo}(?![a-z0-9])", titulo_norm) is not None


def categorias_confiaveis(chaves: list[str]) -> set[str]:
    """Categorias do ML que, por si só, provam que a oferta é do nicho (só as exclusões continuam valendo)."""
    return {cid for c in chaves if NICHOS.get(c, {}).get("ml_confiavel") for cid in NICHOS[c].get("ml", {})}


def _aceita_nicho(n: dict, t: str, categoria: str | None) -> bool:
    """O título (já normalizado) serve a ESTE nicho? Categoria confiável do ML prova sozinha; senão precisa de um
    termo do nicho e, se o nicho define "produtos", também de um produto (estilo + produto: "Camisa Country")."""
    if categoria and n.get("ml_confiavel") and categoria in n.get("ml", {}):
        return True
    termos = n.get("termos")
    if not termos:
        return True
    produtos = n.get("produtos")
    if produtos and not any(_casa(x, t) for x in produtos):
        return False
    if any(_casa(x, t) for x in termos):
        return True
    # marca "ambígua" (Dior, Natura...) só vale acompanhada de um sinal de fragrância no título
    return any(_casa(m, t) for m in n.get("marcas", [])) and any(_casa(x, t) for x in n.get("sinais", []))


def relevante(titulo: str, chaves: list[str], palavras=(), excluir=(), categoria: str | None = None) -> bool:
    """O título faz sentido para o canal? `chaves` são nichos do catálogo; `palavras`/`excluir`
    são termos próprios do canal; `categoria` é a categoria do ML de onde a oferta veio.
    Sem nicho e sem palavras (ou nicho sem termos) = aceita."""
    if not chaves and not palavras:
        return True
    t = _norm(titulo)
    escolhidos = [NICHOS[c] for c in chaves if c in NICHOS]
    if any(_casa(x, t) for x in excluir):
        return False  # exclusão do canal vale para tudo
    if any(_casa(p, t) for p in palavras):
        return not any(_excluido(n, t) for n in escolhidos)
    if not escolhidos:
        return not palavras
    # cada nicho tem as SUAS exclusões: "camisa" barra no nicho perfumes mas não pode barrar "Camisa Country"
    return any(not _excluido(n, t) and _aceita_nicho(n, t, categoria) for n in escolhidos)


def _excluido(n: dict, t: str) -> bool:
    """O título (normalizado) cai numa exclusão do nicho (termo ou padrão, como a medida de pneu de moto)?"""
    return any(_casa(x, t) for x in n.get("excluir", [])) or any(re.search(r, t) for r in n.get("excluir_regex", []))


def dias_sem_repetir(chaves: list[str]) -> int | None:
    """Prazo próprio do nicho para não repetir o mesmo produto (None = o do config.yaml)."""
    return next((NICHOS[c]["nao_repetir_dias"] for c in chaves if NICHOS.get(c, {}).get("nao_repetir_dias")), None)


# ── Variedade: não postar o mesmo TIPO de produto em sequência ───────

DIVERSIDADE_PADRAO = {"espaco": 6, "horas": 3, "max_dia": 4, "familia_janela": 4, "familia_max": 2}
# palavras que não dizem o que o produto é (usadas só quando nenhum "tipo" do nicho casa)
_RUIDO_TIPO = set("""
kit jogo conjunto combo de da do das dos com sem para por em ao na no nas nos ou um uma peca pecas unidade unidades original
originais profissional completo completa premium novo nova promocao oferta frete gratis qualidade alta alto resistente
universal importado importada lancamento top super reforcado reforcada portatil recarregavel potente masculino masculina
feminino feminina unissex adulto cor cores sortido varios varias bivolt sem fio
""".split())


def parametros_diversidade(chaves: list[str]) -> dict | None:
    """Regras de variedade do canal (None = sem regra: nicho em que tudo é do mesmo tipo, como ar condicionado)."""
    escolhidos = [NICHOS[c] for c in chaves if c in NICHOS]
    if escolhidos and all(n.get("diversidade") is False for n in escolhidos):
        return None
    params = dict(DIVERSIDADE_PADRAO)
    for n in escolhidos:
        if isinstance(n.get("diversidade"), dict):
            params.update(n["diversidade"])
            break
    return params


def _tipo_generico(t: str, ruido_extra: set[str]) -> str:
    """Sem tipo cadastrado: as duas primeiras palavras que dizem o que é ("compressor ar", "nivel laser")."""
    palavras = []
    for p in t.split():
        if p.isdigit() or len(p) < 3 or re.fullmatch(r"\d+[a-z]{1,3}", p) or p in _RUIDO_TIPO or p in ruido_extra:
            continue
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        palavras.append(p)
        if len(palavras) == 2:
            break
    return " ".join(palavras) or "sem-tipo"


@lru_cache(maxsize=16384)
def _tipo_de(titulo: str, chaves: tuple[str, ...]) -> tuple[str, str]:
    t = _norm(titulo)
    escolhidos = [NICHOS[c] for c in chaves if c in NICHOS]
    for n in escolhidos:
        for tipo, familia, termos in n.get("tipos", []):
            if any(_casa(x, t) for x in termos):
                return tipo, familia
    ruido = {w for n in escolhidos for x in n.get("ruido_tipo", []) for w in _norm(x).split()}
    tipo = _tipo_generico(t, ruido)
    familia = next((n["familia_padrao"] for n in escolhidos if n.get("familia_padrao")), tipo)
    return tipo, familia


def tipo_de(titulo: str, chaves: list[str]) -> tuple[str, str]:
    """(tipo, família) do produto para o canal: "Chave De Impacto 4.0ah Dobevi" e "Parafusadeira 21v Philco" caem no
    mesmo tipo ("furadeira"); o pipeline usa isso para não repetir o tipo em sequência."""
    return _tipo_de(titulo, tuple(chaves))


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
    fixas = list(dict.fromkeys(kw for k in chaves for kw in NICHOS.get(k, {}).get("amazon_buscas_fixas", [])))
    return {"ml": ml, "amazon_dep": amazon_dep, "amazon_buscas": amazon_buscas, "shopee": shopee, "ml_buscas": ml_buscas,
            "amazon_fixas": fixas}

import os
import pathlib
import tempfile

# Os testes NUNCA tocam nos dados reais: apontam para uma pasta temporária antes de importar o bot.
os.environ["OFERTAS_DATA_DIR"] = tempfile.mkdtemp(prefix="ofertas-teste-")
os.environ["TELEGRAM_CHAT_ID"] = ""

import unittest
from datetime import datetime
from unittest import mock

from ofertas import pipeline
from ofertas.config import config, dentro_do_horario
from ofertas.models import Oferta
from ofertas.utils import parse_preco_br


def oferta(plat="amazon", id_="1", titulo="Produto teste", preco=50.0, original=100.0):
    return Oferta(plataforma=plat, id_produto=id_, titulo=titulo, url_afiliado="x",
                  preco=preco, preco_original=original)


class PrecoBR(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(parse_preco_br("R$ 1.234,56"), 1234.56)
        self.assertEqual(parse_preco_br("56,43"), 56.43)
        self.assertEqual(parse_preco_br("1.234"), 1234.0)
        self.assertIsNone(parse_preco_br("grátis"))


class Horario(unittest.TestCase):
    def test_janela(self):
        with mock.patch.object(config, "horario_ativo", "08:00-23:00"):
            self.assertTrue(dentro_do_horario(datetime(2026, 1, 1, 12, 0)))
            self.assertFalse(dentro_do_horario(datetime(2026, 1, 1, 3, 0)))

    def test_janela_virando_a_noite(self):
        with mock.patch.object(config, "horario_ativo", "22:00-06:00"):
            self.assertTrue(dentro_do_horario(datetime(2026, 1, 1, 23, 0)))
            self.assertFalse(dentro_do_horario(datetime(2026, 1, 1, 12, 0)))


class Desconto(unittest.TestCase):
    def test_calculado(self):
        self.assertEqual(oferta().desconto, 50)


class Filtro(unittest.TestCase):
    def test_desconto_minimo_e_palavras(self):
        ofs = [oferta(id_="a", preco=90, original=100),
               oferta(id_="b", titulo="Capinha bonita"),
               oferta(id_="c")]
        with mock.patch.object(config, "desconto_minimo", 25), \
             mock.patch.object(config, "palavras_bloqueadas", ["capinha"]), \
             mock.patch.object(config, "preco_minimo", 0), \
             mock.patch.object(config, "preco_maximo", 0), \
             mock.patch.object(pipeline.db, "ja_postada", return_value=False):
            self.assertEqual([o.id_produto for o in pipeline.filtrar(ofs)], ["c"])


class Escolha(unittest.TestCase):
    def test_alterna_plataformas_e_pula_variacoes(self):
        ofs = [oferta("amazon", "1", "Fone Bluetooth Pro Preto X", 40),
               oferta("amazon", "2", "Fone Bluetooth Pro Preto X", 45),
               oferta("mercadolivre", "3", "Cinta reboque 4x4", 60)]
        esc = pipeline.escolher(ofs, 2)
        self.assertEqual({o.plataforma for o in esc}, {"amazon", "mercadolivre"})
        self.assertEqual(len(esc), 2)


class Relevancia(unittest.TestCase):
    def test_automotivo(self):
        from ofertas.nichos import relevante
        ok = ["Central Multimídia MP5 Tela 7 Polegadas Roadstar", "TNT Pulverizador Snow Foam 2L Manual Detailing",
              "Kit Lavagem Completa Shampoo Cera Tok Final", "Carregador De Bateria Automotivo Bivolt",
              "Assento De Carro Infantil Elevação Fit Up", "Fone De Ouvido Para Capacete Bluetooth",
              "Rastreador GPS Veicular 4G", "Cinta Fita 70 Ton Reboque Guincho 4x4"]
        fora = ["Bíblia NVT Filament Letra Grande", "Cute & Comfy Coloring Book Livro de Colorir",
                "Hot Wheels City Pista de Brinquedo Reboque de Dragão", "Móbile Centopeia Espiral com Chocalho",
                "Meditações de Marco Aurélio", "Esponja Prateada Unitária Bettanin"]
        for t in ok:
            self.assertTrue(relevante(t, ["automotivo"]), t)
        for t in fora:
            self.assertFalse(relevante(t, ["automotivo"]), t)

    def test_sem_nicho_aceita_tudo(self):
        from ofertas.nichos import relevante
        self.assertTrue(relevante("Qualquer coisa", []))


class Canais(unittest.TestCase):
    def test_validar_ids_unicos_e_obrigatorios(self):
        from ofertas import canais
        lista = canais.validar([{"nome": "Perfumes", "chat_id": "-1"}, {"nome": "Perfumes", "chat_id": "-2"}])
        self.assertEqual([c.id for c in lista], ["perfumes", "perfumes-2"])
        with self.assertRaises(ValueError):
            canais.validar([{"nome": "", "chat_id": "-1"}])
        with self.assertRaises(ValueError):
            canais.validar([{"nome": "X", "chat_id": ""}])

    def test_palavras_aceitam_texto_com_virgula(self):
        from ofertas import canais
        c = canais.validar([{"nome": "Bikes", "chat_id": "-1", "palavras": "bicicleta, capacete ciclista\nbike"}])[0]
        self.assertEqual(c.palavras, ["bicicleta", "capacete ciclista", "bike"])

    def test_filtro_por_canal(self):
        from ofertas.canais import Canal
        perfumes = Canal(id="perfumes", nome="P", chat_id="-1", nichos=["perfumes"])
        country = Canal(id="country", nome="C", chat_id="-2", nichos=["country"])
        ofs = [oferta(id_="1", titulo="Perfume Asad Lattafa 100ml Eau de Parfum"),
               oferta(id_="2", titulo="Bota Country Masculina Couro Texana"),
               oferta(id_="3", titulo="Central Multimídia Universal")]
        with mock.patch.object(config, "desconto_minimo", 0), \
             mock.patch.object(pipeline.db, "ja_postada", return_value=False):
            self.assertEqual([o.id_produto for o in pipeline.filtrar(ofs, perfumes)], ["1"])
            self.assertEqual([o.id_produto for o in pipeline.filtrar(ofs, country)], ["2"])

    def test_palavras_proprias_e_excluir(self):
        from ofertas.nichos import relevante
        self.assertTrue(relevante("Bicicleta Aro 29 Mountain Bike", [], ["bicicleta"]))
        self.assertFalse(relevante("Brinquedo bicicleta infantil", [], ["bicicleta"], ["brinquedo"]))

    def test_historico_por_canal(self):
        from ofertas import db
        o = oferta(id_="h1")
        db.registrar(o, "a")
        self.assertTrue(db.ja_postada("a|" + o.uid, 7))
        self.assertFalse(db.ja_postada("b|" + o.uid, 7))


class Migracao(unittest.TestCase):
    def test_migra_canal_e_historico_em_processo_novo(self):
        import json, sqlite3, subprocess, sys
        pasta = tempfile.mkdtemp(prefix="ofertas-migra-")
        con = sqlite3.connect(os.path.join(pasta, "ofertas.db"))
        con.execute("CREATE TABLE postadas (uid TEXT PRIMARY KEY, plataforma TEXT, titulo TEXT, preco REAL, postada_em TEXT)")
        con.execute("INSERT INTO postadas VALUES ('amazon:X1','amazon','t',1.0,'2026-01-01T00:00:00')")
        con.commit(); con.close()
        with open(os.path.join(pasta, "nichos.json"), "w") as f:
            json.dump(["automotivo"], f)
        env = {**os.environ, "OFERTAS_DATA_DIR": pasta, "TELEGRAM_CHAT_ID": "-100123"}
        # importa db ANTES de config, como o bot faz de verdade (já quebrou por import circular)
        codigo = ("from ofertas import db; from ofertas.config import config; "
                  "print(len(config.canais), db.total_postadas('automotivo'))")
        r = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "1 1", r.stderr[-400:])


class FakeBot:
    def __init__(self):
        self.enviados = []  # (chat_id, texto)
        self.links = []     # (chat_id, url do botão)

    def _anota(self, chat_id, texto, kw):
        self.enviados.append((chat_id, texto))
        botoes = kw["reply_markup"].inline_keyboard[0] if kw.get("reply_markup") else []
        self.links.append((chat_id, botoes[0].url if botoes else None))

    async def send_message(self, chat_id, texto, **kw):
        self._anota(chat_id, texto, kw)

    async def send_photo(self, chat_id, foto, caption="", **kw):
        self._anota(chat_id, caption, kw)


class CicloMultiCanal(unittest.TestCase):
    def _rodar(self, ml_falha=False):
        import asyncio
        from ofertas.canais import Canal
        canais = [Canal(id="auto", nome="Auto", chat_id="-1", nichos=["automotivo"],
                        ml_etiqueta="etq-auto", amazon_tag="tag-auto-20"),
                  Canal(id="perf", nome="Perf", chat_id="-2", nichos=["perfumes"]),
                  Canal(id="country", nome="Country", chat_id="-3", nichos=["country"])]
        brutas = [
            Oferta("amazon", "a1", "Kit Lavagem Automotiva Shampoo Cera", "https://www.amazon.com.br/dp/a1?tag=geral-20", preco=50, preco_original=100),
            Oferta("mercadolivre", "m1", "Central Multimídia 7 polegadas carro", "", url_produto="https://ml/m1", preco=50, preco_original=100),
            Oferta("amazon", "a2", "Perfume Masculino Eau de Parfum 100ml", "https://x/a2", preco=50, preco_original=100),
            Oferta("mercadolivre", "m2", "Perfume Árabe Feminino 100ml", "", url_produto="https://ml/m2", preco=50, preco_original=100),
            Oferta("amazon", "a3", "Bota Country Texana Masculina", "https://x/a3", preco=50, preco_original=100),
            Oferta("amazon", "a4", "Bíblia Sagrada Letra Grande", "https://x/a4", preco=20, preco_original=100),
        ]

        self.etiquetas_usadas = []

        def gerar(grupos):
            if ml_falha:
                raise RuntimeError("Sessão do ML expirou")
            for etiqueta, ofs in grupos.items():
                self.etiquetas_usadas.append(etiqueta)
                for o in ofs:
                    o.url_afiliado = f"https://meli.la/{etiqueta}/{o.id_produto}"

        bot = FakeBot()
        with mock.patch.object(config, "canais", canais), mock.patch.object(config, "ml_etiqueta", "padrao"), mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "t.db"),             mock.patch.object(config, "horario_ativo", ""),              mock.patch.object(config, "desconto_minimo", 25),              mock.patch.object(config, "max_posts_por_ciclo", 3),              mock.patch.object(config, "espacamento_segundos", 0),              mock.patch.object(pipeline, "coletar", return_value=brutas),              mock.patch.object(pipeline.mercadolivre, "gerar_links_por_etiqueta", side_effect=gerar),              mock.patch.object(pipeline.asyncio, "sleep", new=mock.AsyncMock()),              mock.patch.object(pipeline, "avisar_dono", new=mock.AsyncMock()):
            n = asyncio.run(pipeline.executar_ciclo(bot))
        self.bot = bot
        return n, bot.enviados

    def test_cada_oferta_vai_para_o_canal_certo(self):
        n, env = self._rodar()
        por_canal = {}
        for chat, txt in env:
            por_canal.setdefault(chat, []).append(txt)
        self.assertEqual(n, 5)
        self.assertEqual(len(por_canal["-1"]), 2)   # lavagem + multimídia
        self.assertEqual(len(por_canal["-2"]), 2)   # 2 perfumes
        self.assertEqual(len(por_canal["-3"]), 1)   # bota country
        self.assertFalse(any("Bíblia" in t for _, t in env))
        self.assertEqual([c for c, _ in env[:3]], ["-1", "-2", "-3"])  # intercalado

    def test_link_por_canal_etiqueta_ml_e_tag_amazon(self):
        self._rodar()
        self.assertEqual(set(self.etiquetas_usadas), {"etq-auto", "padrao"})  # 1 grupo por etiqueta
        auto = [u for chat, u in self.bot.links if chat == "-1"]
        perf = [u for chat, u in self.bot.links if chat == "-2"]
        self.assertTrue(any("etq-auto" in u for u in auto))      # ML do canal Auto: etiqueta própria
        self.assertTrue(any("tag=tag-auto-20" in u for u in auto))  # Amazon do canal Auto: tag própria
        self.assertTrue(all("etq-auto" not in u and "tag-auto" not in u for u in perf))  # outros: padrão

    def test_tag_amazon_por_canal(self):
        from ofertas.pipeline import _tag_amazon
        self.assertEqual(_tag_amazon("https://www.amazon.com.br/dp/B0?tag=geral-20&x=1", "auto-20"),
                         "https://www.amazon.com.br/dp/B0?tag=auto-20&x=1")
        self.assertEqual(_tag_amazon("https://x/dp/B0?tag=geral-20", ""), "https://x/dp/B0?tag=geral-20")

    def test_ml_fora_do_ar_nao_desperdica_vagas(self):
        n, env = self._rodar(ml_falha=True)
        self.assertEqual(n, 3)  # sobra só o que veio da Amazon: 1 por canal
        self.assertTrue(all("meli.la" not in t for _, t in env))


class Qualidade(unittest.TestCase):
    def test_parse_vendas_e_nota(self):
        from ofertas.utils import parse_nota, parse_vendas
        self.assertEqual(parse_vendas("4.8 · +5mil vendidos"), 5000)
        self.assertEqual(parse_vendas("+10mil vendidos"), 10000)
        self.assertEqual(parse_vendas("+500 vendidos"), 500)
        self.assertEqual(parse_vendas("1,2 mil vendidos"), 1200)
        self.assertIsNone(parse_vendas("4.8"))
        self.assertEqual(parse_nota("4,7 (120)"), 4.7)
        self.assertIsNone(parse_nota("sem nota"))

    def test_filtros_de_qualidade(self):
        def of(i, nota=4.8, vendas=500, preco=50, original=100):
            o = oferta(id_=i, preco=preco, original=original)
            o.nota, o.vendas = nota, vendas
            return o
        ofs = [of("bom"), of("nota-baixa", nota=3.9), of("poucas-vendas", vendas=5),
               of("desconto-irreal", preco=5, original=100), of("sem-dados", nota=None, vendas=None)]
        with mock.patch.object(config, "desconto_minimo", 25),              mock.patch.object(config, "desconto_maximo", 85),              mock.patch.object(config, "nota_minima", 4.3),              mock.patch.object(config, "vendas_minimas", 30),              mock.patch.object(pipeline.db, "ja_postada", return_value=False):
            ids = [o.id_produto for o in pipeline.filtrar(ofs)]
        self.assertEqual(ids, ["bom", "sem-dados"])  # dado desconhecido não reprova

    def test_termos_automotivo_achados_nos_dados_reais(self):
        from ofertas.nichos import relevante
        for t in ["Alto Falante Jbl Triaxial 6trfx55 Flex4 110w", "Capa Chuva Motoqueiro Pvc Impermeável Motoboy",
                  "Bebê Conforto Para Bebê Comfort de 0 à 13kgs", "Escapamento F1 Mini Tri Fortuna Titan/fan/start"]:
            self.assertTrue(relevante(t, ["automotivo"]), t)
        for t in ["Aspirador De Pó Vertical e Sem Fio Redroad W15", "Kit 4 Rádios Comunicadores Walkie Talkie"]:
            self.assertFalse(relevante(t, ["automotivo"]), t)


class Legenda(unittest.TestCase):
    def test_legenda_completa(self):
        from ofertas.formatter import montar_caption
        o = Oferta("mercadolivre", "m", "Auxiliar de Partida", "u", preco=148.45, preco_original=300.0,
                   desconto_pct=50, extra="⭐ 4.8 · +5mil vendidos · 🚚 Frete grátis · 💠 preço no Pix", nota=4.8, vendas=5000)
        c = montar_caption(o)
        for trecho in ["SUPER OFERTA", "R$ 300,00", "R$ 148,45", "-50%", "Você economiza R$ 151,55",
                       "⭐ 4,8", "+5 mil vendidos", "Frete grátis", "preço no Pix", "Mercado Livre"]:
            self.assertIn(trecho, c)
        self.assertEqual(c.count("vendidos"), 1)  # não duplica o que veio no "extra"

    def test_sem_preco_nao_quebra_e_escapa_html(self):
        from ofertas.formatter import montar_caption
        c = montar_caption(Oferta("mercadolivre", "x", "Kit <b>& cia", "u"))
        self.assertIn("&lt;b&gt;&amp; cia", c)
        self.assertNotIn("De:", c)

    def test_titulo_curto_corta_em_palavra_inteira(self):
        from ofertas.formatter import titulo_curto
        t = titulo_curto("Auxiliar de Partida " + "palavra " * 30)
        self.assertLessEqual(len(t), 96)
        self.assertTrue(t.endswith("…") and not t.endswith("pala…"))
        self.assertEqual(titulo_curto("Curto"), "Curto")

    def test_botao_fixo_por_produto(self):
        from ofertas.formatter import texto_botao
        o = oferta(id_="z9")
        self.assertEqual(texto_botao(o), texto_botao(o))


class Servico(unittest.TestCase):
    def test_espera_cresce_e_tem_teto(self):
        from ofertas.servico import espera_apos_falha
        self.assertEqual([espera_apos_falha(n) for n in (1, 2, 3, 4)], [10, 20, 40, 80])
        self.assertEqual(espera_apos_falha(50), 300)

    def test_trava_de_instancia_unica(self):
        from ofertas import instancia
        arq = pathlib.Path(tempfile.mkdtemp()) / "bot.pid"
        with mock.patch.object(instancia, "ARQ", arq):
            self.assertIsNone(instancia.rodando())
            arq.write_text(str(os.getppid()))          # outro processo vivo (o pai deste teste)
            self.assertEqual(instancia.rodando(), os.getppid())
            self.assertFalse(instancia.adquirir())      # recusa: já tem dono
            arq.write_text("999999")                    # PID morto: trava velha não vale
            self.assertIsNone(instancia.rodando())
            self.assertTrue(instancia.adquirir())
            self.assertEqual(arq.read_text(), str(os.getpid()))
            instancia.liberar()
            self.assertFalse(arq.exists())

    def test_script_da_tarefa_do_windows(self):
        from ofertas import autostart
        s = autostart.script_instalar("X")
        for trecho in ["-m ofertas servico", "AtLogOn", "-RestartCount 999", "MultipleInstances IgnoreNew",
                       "TaskName 'X'", "ExecutionTimeLimit ([TimeSpan]::Zero)"]:
            self.assertIn(trecho, s)


class Relatorio(unittest.TestCase):
    def test_resumo_e_texto(self):
        import datetime as dt
        from ofertas import db, relatorio
        from ofertas.canais import Canal
        canais = [Canal(id="auto", nome="Auto", chat_id="-1", emoji="🚗"),
                  Canal(id="perf", nome="Perf", chat_id="-2", emoji="🧴", ml_etiqueta="perf")]
        with mock.patch.object(db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "r.db"),              mock.patch.object(config, "canais", canais):
            o1 = Oferta("mercadolivre", "1", "Auxiliar de Partida", "u", preco=50, preco_original=100, desconto_pct=58)
            o2 = Oferta("amazon", "2", "Kit Lavagem", "u", preco=50, preco_original=100)
            db.registrar(o1, "auto")
            db.registrar(o2, "auto")
            db.registrar_ciclo(40, 2, {"auto": {"boas": 12, "postadas": 2}, "perf": {"boas": 0, "postadas": 0}})
            db.registrar_evento("ml_sessao", "expirou")
            db.registrar_evento("fonte_vazia:amazon")
            db.registrar_evento("falha_post", "auto: chat not found")
            txt = relatorio.montar(dt.datetime.now() - dt.timedelta(hours=1), "TITULO")
        for trecho in ["TITULO", "2 posts", "🚗 Auto: 2", "ML 1", "Amazon 1", "🧴 Perf: 0 ⚠️", "Maior desconto: -58%",
                       "1 rodada · média de 40 ofertas coletadas por rodada", "sem sessão", "Amazon não trouxe ofertas", "Falha ao postar", "medidos em separado: 🧴 Perf"]:
            self.assertIn(trecho, txt)

    def test_banco_antigo_ganha_colunas_novas(self):
        import sqlite3
        from ofertas import db
        arq = pathlib.Path(tempfile.mkdtemp()) / "velho.db"
        c = sqlite3.connect(arq)
        c.execute("CREATE TABLE postadas (uid TEXT PRIMARY KEY, plataforma TEXT, titulo TEXT, preco REAL, postada_em TEXT)")
        c.execute("INSERT INTO postadas VALUES ('automotivo|amazon:X','amazon','t',1.0,'2026-01-01T00:00:00')")
        c.commit(); c.close()
        with mock.patch.object(db, "_DB", arq):
            self.assertEqual(db.total_postadas("automotivo"), 1)   # histórico preservado
            db.registrar(oferta(id_="novo"), "automotivo")          # coluna 'desconto' criada na hora
            self.assertEqual(db.total_postadas("automotivo"), 2)


class AuditoriaCorrecoes(unittest.TestCase):
    def test_falsos_positivos_achados_no_ensaio(self):
        from ofertas.nichos import relevante
        for t in ["Kit 6 Cuecas Lupo Boxer Box Sem Costura Basic Microfibra", "Smartphone Motorola Moto G54 128GB",
                  "Lavadora de Roupas 12kg Turbo", "Cera Depilatória Roll-on 100ml", "Óleo Capilar de Argan 60ml",
                  "Cinta Modeladora Feminina Pós Parto"]:
            self.assertFalse(relevante(t, ["automotivo"]), t)
        for t in ["Lavadora de Alta Pressão Karcher 1800 PSI", "Cera Automotiva Líquida Carnaúba 500ml",
                  "Óleo de Motor 5W30 Sintético 1L", "Pano de Microfibra Automotivo Kit 6", "Módulo Amplificador Som Automotivo"]:
            self.assertTrue(relevante(t, ["automotivo"]), t)

    def test_categoria_confiavel_dispensa_termos_mas_nao_as_exclusoes(self):
        from ofertas.nichos import relevante
        self.assertTrue(relevante("Carburador Fusca 1500 Kuerl Original", ["automotivo"], categoria="MLB22693"))
        self.assertFalse(relevante("Carburador Fusca 1500 Kuerl Original", ["automotivo"], categoria="MLB1430"))
        self.assertFalse(relevante("Smartphone Motorola Moto G54", ["automotivo"], categoria="MLB22693"))
        self.assertTrue(relevante("Lattafa Fakhar Platin 100ml", ["perfumes"], categoria="MLB6284"))

    def test_country_estrito(self):
        from ofertas.nichos import relevante
        self.assertTrue(relevante("Boné Country Trucker Masculino", ["country"]))
        self.assertTrue(relevante("Calça Country Feminina Rodeio Bordada", ["country"]))
        self.assertFalse(relevante("Chapéu Praia Dobrável Feminino Aba Larga", ["country"]))
        self.assertFalse(relevante("Bota Caterpillar Adventure Leve", ["country"]))

    def test_nao_reposta_variacao_do_mesmo_produto_entre_rodadas(self):
        from ofertas import db
        from ofertas.canais import Canal
        canal = Canal(id="auto", nome="A", chat_id="-1", nichos=[])
        with mock.patch.object(db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "s.db"),              mock.patch.object(config, "desconto_minimo", 0):
            db.registrar(oferta(id_="cor-azul", titulo="Cute Comfy Coloring Book Adults Bold Easy Azul"), "auto")
            variacao = oferta(id_="cor-rosa", titulo="Cute Comfy Coloring Book Adults Bold Easy Rosa")
            outro = oferta(id_="outro", titulo="Shampoo Automotivo Vonixx Concentrado")
            ids = [o.id_produto for o in pipeline.filtrar([variacao, outro], canal)]
        self.assertEqual(ids, ["outro"])

    def test_declaracao_da_amazon_so_nos_posts_da_amazon(self):
        from ofertas.formatter import montar_caption
        frase = "Como participante do Programa de Associados da Amazon, sou remunerado pelas compras qualificadas efetuadas."
        with mock.patch.object(config, "aviso_amazon", frase):
            self.assertIn(frase, montar_caption(oferta(plat="amazon")))
            self.assertNotIn(frase, montar_caption(oferta(plat="mercadolivre")))
        with mock.patch.object(config, "aviso_amazon", ""):
            self.assertNotIn("Programa de Associados", montar_caption(oferta(plat="amazon")))

    def test_historico_de_precos(self):
        from ofertas import db
        with mock.patch.object(db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "p.db"):
            o = oferta(id_="p1", preco=100.0)
            db.registrar_precos([o]); db.registrar_precos([o])           # mesma leitura em <3h: 1 linha só
            db.registrar_precos([oferta(id_="p1", preco=90.0)])          # preço mudou: nova linha
            self.assertEqual([p for _, p in db.historico_preco(o.uid)], [100.0, 90.0])


class PostaEnquantoHouverOferta(unittest.TestCase):
    def _rodar(self, ofertas, limite=0, prazo_estourado=False):
        import asyncio
        from ofertas.canais import Canal
        canal = Canal(id="c", nome="C", chat_id="-1")  # sem filtro de nicho
        bot = FakeBot()
        prazo = (lambda: pipeline.time.monotonic() - 1) if prazo_estourado else (lambda: float("inf"))
        with mock.patch.object(config, "canais", [canal]),              mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "l.db"),              mock.patch.object(config, "horario_ativo", ""), mock.patch.object(config, "desconto_minimo", 25),              mock.patch.object(config, "max_posts_por_ciclo", limite), mock.patch.object(config, "espacamento_segundos", 0),              mock.patch.object(pipeline, "coletar", return_value=ofertas),              mock.patch.object(pipeline, "_prazo_ciclo", side_effect=prazo),              mock.patch.object(pipeline.asyncio, "sleep", new=mock.AsyncMock()),              mock.patch.object(pipeline, "avisar_dono", new=mock.AsyncMock()):
            n = asyncio.run(pipeline.executar_ciclo(bot))
        return n, bot.enviados

    def _ofertas(self, n):
        nomes = ["Alfa", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima"]
        return [Oferta("amazon", f"id{i}", f"{nomes[i]} produto diferente numero {i} completo", "https://x/" + str(i),
                       preco=50, preco_original=100) for i in range(n)]

    def test_sem_limite_posta_tudo_que_for_valido(self):
        n, env = self._rodar(self._ofertas(11))
        self.assertEqual(n, 11)                        # 11 = mais que qualquer "lote": vários lotes seguidos
        self.assertEqual(len({t for _, t in env}), 11)  # nenhum repetido

    def test_teto_opcional_ainda_funciona(self):
        n, _ = self._rodar(self._ofertas(11), limite=4)
        self.assertEqual(n, 4)

    def test_rodada_sem_tempo_deixa_o_resto_para_a_proxima(self):
        n, _ = self._rodar(self._ofertas(5), prazo_estourado=True)
        self.assertEqual(n, 0)

    def test_variacoes_do_mesmo_produto_nao_saem_na_mesma_rodada(self):
        variacoes = [Oferta("amazon", f"v{i}", f"Mesmo Produto Kit Completo Especial Cor {cor}", "https://x/v", preco=50, preco_original=100)
                     for i, cor in enumerate(["Azul", "Rosa", "Verde"])]
        n, _ = self._rodar(variacoes + self._ofertas(2))
        self.assertEqual(n, 3)   # 1 das 3 cores + 2 produtos diferentes


class Concordancia(unittest.TestCase):
    def test_singular_e_plural_no_relatorio(self):
        from ofertas.relatorio import _pl
        self.assertEqual(_pl(1, "post", "posts"), "post")
        self.assertEqual(_pl(0, "post", "posts"), "posts")
        self.assertEqual(_pl(2, "rodada", "rodadas"), "rodadas")


class CupomLinkEArCondicionado(unittest.TestCase):
    def test_extrai_cupom_digitado(self):
        from ofertas.utils import extrair_cupom
        self.assertEqual(extrair_cupom("https://x.com/p cupom DIADACRIANCA"), "DIADACRIANCA")
        self.assertEqual(extrair_cupom("https://x.com/p cupom: dia10"), "DIA10")
        self.assertEqual(extrair_cupom("código BLACK50 https://x.com/p"), "BLACK50")
        self.assertIsNone(extrair_cupom("https://x.com/p cupom de 10% na página"))   # "de" não é código
        self.assertIsNone(extrair_cupom("https://x.com/cupom/ABC123"))               # 'cupom' dentro da URL não vale
        self.assertIsNone(extrair_cupom("só o link https://x.com/p"))

    def test_post_no_estilo_cupom_e_link(self):
        from ofertas.formatter import montar_caption
        o = Oferta("shopee", "s1", "Assento Redutor Infantil", "https://s.shopee.com.br/abc123", preco=55.16, cupom="DIADACRIANCA")
        with mock.patch.object(config, "link_visivel", True):
            c = montar_caption(o)
        self.assertIn("Use o cupom: <code>DIADACRIANCA</code>", c)
        self.assertIn("🛍 Compre aqui: https://s.shopee.com.br/abc123", c)
        self.assertLess(c.index("Use o cupom"), c.index("Compre aqui"))

    def test_link_longo_vira_texto_clicavel_e_da_para_desligar(self):
        from ofertas.formatter import montar_caption
        longo = "https://www.amazon.com.br/dp/B0ABCDEFGH?tag=arrudalucas-20&linkCode=ogi&th=1"
        o = Oferta("amazon", "B0", "Kit Lavagem", longo, preco=10)
        with mock.patch.object(config, "link_visivel", True):
            self.assertIn('<a href="' + longo.replace("&", "&amp;") + '">Compre aqui</a>', montar_caption(o))
        with mock.patch.object(config, "link_visivel", False):
            self.assertNotIn("Compre aqui", montar_caption(o))

    def test_ml_avisa_quando_o_preco_depende_de_cupom(self):
        from bs4 import BeautifulSoup
        from ofertas.sources.mercadolivre import _parse_card
        html = ('<div class="poly-card"><a class="poly-component__title" href="https://www.mercadolivre.com.br/p/MLB123">Ar Condicionado Split 12000 Btu</a>'
                '<div class="poly-component__price"><s class="andes-money-amount andes-money-amount--previous"><span class="andes-money-amount__fraction">4.300</span></s>'
                '<div class="poly-price__current"><span class="andes-money-amount__fraction">1.188</span></div>'
                '<span class="poly-price__discount-polylabel">72% OFF com Cupom</span> ou R$ 1.288 em 10x</div>'
                '<div class="poly-component__coupons"><div class="poly-coupons__wrapper">5% OFF com Cupom</div></div></div>')
        o = _parse_card(BeautifulSoup(html, "lxml").select_one("div.poly-card"))
        self.assertEqual((o.preco, o.preco_original, o.desconto), (1188.0, 4300.0, 72))
        self.assertIn("Preço com cupom do ML", o.extra)
        self.assertIn("Cupom extra: 5% OFF", o.extra)

    def test_nicho_ar_condicionado(self):
        from ofertas.nichos import catalogo, relevante
        for t in ["Ar Condicionado Split Elgin Eco Inverter 12000 Btu", "Ar-Condicionado Portátil Philco 10000 BTUs",
                  "Suporte para Ar Condicionado 400mm Reforçado"]:
            self.assertTrue(relevante(t, ["arcondicionado"]), t)
        for t in ["Geladeira Frost Free Inverter 400L", "Lavadora Inverter 12kg", "Ar Condicionado Automotivo 12V para Carro"]:
            self.assertFalse(relevante(t, ["arcondicionado"]), t)
        self.assertTrue(relevante("qualquer", ["arcondicionado"], categoria="MLB1646"))      # categoria do ML já prova
        self.assertEqual({n["chave"]: n["desconto_sugerido"] for n in catalogo()}["arcondicionado"], 10)


if __name__ == "__main__":
    unittest.main()

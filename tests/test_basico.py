import os
import pathlib
import tempfile

# Os testes NUNCA tocam nos dados reais: apontam para uma pasta temporária antes de importar o bot.
os.environ["OFERTAS_DATA_DIR"] = tempfile.mkdtemp(prefix="ofertas-teste-")
os.environ["TELEGRAM_CHAT_ID"] = ""

import unittest
from dataclasses import replace
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
              "Assento De Carro Infantil Elevação Fit Up",
              "Rastreador GPS Veicular 4G", "Cinta Fita 70 Ton Reboque Guincho 4x4"]
        fora = ["Bíblia NVT Filament Letra Grande", "Cute & Comfy Coloring Book Livro de Colorir",
                "Hot Wheels City Pista de Brinquedo Reboque de Dragão", "Móbile Centopeia Espiral com Chocalho", "Fone De Ouvido Para Capacete Bluetooth",
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
        ofs = [replace(oferta(id_="1", titulo="Perfume Asad Lattafa 100ml Eau de Parfum"), loja_confiavel=True),
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
            Oferta("mercadolivre", "m2", "Perfume Árabe Feminino 100ml", "", url_produto="https://ml/m2", preco=50, preco_original=100, loja_confiavel=True),
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
        with mock.patch.object(config, "canais", canais), mock.patch.object(config, "ml_etiqueta", "padrao"), mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "t.db"),             mock.patch.object(config, "horario_ativo", ""),              mock.patch.object(config, "desconto_minimo", 25),              mock.patch.object(config, "max_posts_por_ciclo", 3),              mock.patch.object(config, "espacamento_segundos", 0),              mock.patch.object(pipeline, "coletar", return_value=brutas),              mock.patch.object(pipeline.mercadolivre, "gerar_links_por_etiqueta", side_effect=gerar),              mock.patch.object(pipeline.asyncio, "sleep", new=mock.AsyncMock()),              mock.patch.object(pipeline.amazon, "vendedor_confiavel", return_value=True),              mock.patch.object(pipeline, "avisar_dono", new=mock.AsyncMock()):
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
        for t in ["Alto Falante Jbl Triaxial 6trfx55 Flex4 110w", "Bebê Conforto Para Bebê Comfort de 0 à 13kgs",
                  "Kit 2 Tweeter Jbl Auto St400 Preto Profissional", "Compressor de Ar Portátil Digital para Carro, Moto e Bike"]:
            self.assertTrue(relevante(t, ["automotivo"]), t)
        for t in ["Aspirador De Pó Vertical e Sem Fio Redroad W15 Seco Úmido", "Kit 4 Rádios Comunicadores Walkie Talkie"]:
            self.assertFalse(relevante(t, ["automotivo"]), t)                       # sem termo do nicho
        for t in ["Aspirador De Pó Vertical e Sem Fio Redroad W15 Seco Úmido", "Óculos De Sol Masculino Uv400 Polarizado vintage Preto"]:
            self.assertFalse(relevante(t, ["automotivo"], categoria="MLB1747"), t)  # palavra excluída vence a categoria confiável


class Legenda(unittest.TestCase):
    def test_legenda_completa(self):
        from ofertas.formatter import montar_caption
        o = Oferta("mercadolivre", "m", "Auxiliar de Partida", "u", preco=148.45, preco_original=300.0,
                   desconto_pct=50, extra="⭐ 4.8 · +5mil vendidos · 🚚 Frete grátis · 💠 preço no Pix", nota=4.8, vendas=5000)
        with mock.patch.object(config, "estilo_post", "completo"):
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
            self.assertIn("Compre aqui: " + longo.replace("&", "&amp;"), montar_caption(o))
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


class CoberturaEEnvio(unittest.TestCase):
    def test_rodizio_de_categorias_do_ml_cobre_todas_e_da_a_volta(self):
        from ofertas.sources import mercadolivre as ml
        cats = {f"MLB{i}": f"c{i}" for i in range(1, 6)}
        ml._rodizio = 0
        with mock.patch.object(config, "fonte_ml", {"ativa": True, "categorias": cats, "requisicoes_por_ciclo": 2}):
            rodadas = [list(ml._categorias_da_rodada()) for _ in range(3)]
        self.assertEqual(rodadas, [["MLB1", "MLB2"], ["MLB3", "MLB4"], ["MLB5", "MLB1"]])
        with mock.patch.object(config, "fonte_ml", {"ativa": True, "categorias": cats, "requisicoes_por_ciclo": 0}):
            self.assertEqual(len(ml._categorias_da_rodada()), 5)   # 0 = todas de uma vez

    def test_automotivo_cobre_iluminacao_escapamento_e_detailing(self):
        from ofertas.nichos import categorias_confiaveis
        conf = categorias_confiaveis(["automotivo"])
        for cid in ("MLB2228", "MLB63532", "MLB433258", "MLB263726", "MLB2227"):  # iluminação, escapamentos, boinas, ceras, ferramentas
            self.assertIn(cid, conf)

    def test_parcelas_sem_juros_do_card_do_ml(self):
        from bs4 import BeautifulSoup
        from ofertas.sources.mercadolivre import _parse_card
        base = ('<div class="poly-card"><a class="poly-component__title" href="https://www.mercadolivre.com.br/p/MLB9">Produto</a>'
                '<div class="poly-component__price"><div class="poly-price__current"><span class="andes-money-amount__fraction">1.188</span></div>{}</div></div>')
        com = _parse_card(BeautifulSoup(base.format("ou R$ 1.288 em 10x R$ 128 , 80 sem juros"), "lxml").select_one("div.poly-card"))
        self.assertIn("💳 10x de R$ 128,80 sem juros", com.extra)
        sem = _parse_card(BeautifulSoup(base.format("em 1x R$ 1.188 sem juros"), "lxml").select_one("div.poly-card"))
        self.assertFalse(sem.extra and "sem juros" in sem.extra)   # 1x não é parcelamento

    def _envio(self, falhas, erro):
        import asyncio
        from ofertas import telegram_poster as tp
        o = Oferta("mercadolivre", "e1", "Produto", "https://meli.la/x", preco=10, imagem="https://img/x.jpg")

        class Bot:
            def __init__(self):
                self.fotos, self.textos = 0, 0

            async def send_photo(self, *a, **k):
                self.fotos += 1
                if self.fotos <= falhas:
                    raise erro
                return "ok-foto"

            async def send_message(self, *a, **k):
                self.textos += 1
                return "ok-texto"

        bot = Bot()
        with mock.patch.object(tp.asyncio, "sleep", new=mock.AsyncMock()):
            try:
                r = asyncio.run(tp.postar_oferta(bot, o, "-1"))
            except Exception as e:
                r = e
        return r, bot

    def test_queda_de_rede_repete_e_depois_envia(self):
        from telegram.error import NetworkError
        r, bot = self._envio(2, NetworkError("httpx.ConnectError: "))
        self.assertEqual((r, bot.fotos, bot.textos), ("ok-foto", 3, 0))

    def test_rede_fora_do_ar_desiste_sem_cair_para_texto(self):
        from telegram.error import NetworkError
        r, bot = self._envio(99, NetworkError("httpx.ConnectError: "))
        self.assertIsInstance(r, NetworkError)
        self.assertEqual((bot.fotos, bot.textos), (3, 0))   # 3 tentativas; a oferta volta na próxima rodada

    def test_imagem_recusada_ainda_cai_para_texto(self):
        from telegram.error import BadRequest
        r, bot = self._envio(1, BadRequest("Wrong file identifier/HTTP URL specified"))
        self.assertEqual((r, bot.fotos, bot.textos), ("ok-texto", 1, 1))


class RitmoDosPosts(unittest.TestCase):
    def test_pausa_varia_dentro_da_faixa_e_nao_e_constante(self):
        with mock.patch.object(config, "variacao_espacamento", 25):
            valores = [pipeline._pausa(300) for _ in range(200)]
        self.assertTrue(all(225 <= v <= 375 for v in valores))
        self.assertGreater(len(set(round(v) for v in valores)), 50)   # irregular, como um humano
        with mock.patch.object(config, "variacao_espacamento", 0):
            self.assertEqual(pipeline._pausa(300), 300)                # 0 = exato

    def test_com_varios_canais_o_ritmo_de_cada_canal_se_mantem(self):
        import asyncio
        from ofertas.canais import Canal
        esperas = []

        async def dorme(t):
            esperas.append(t)

        canais = [Canal(id="a", nome="A", chat_id="-1"), Canal(id="b", nome="B", chat_id="-2"), Canal(id="c", nome="C", chat_id="-3")]
        ofs = [Oferta("amazon", f"x{i}", f"Produto numero {i} totalmente diferente {'abcdefgh'[i]}", "https://x/" + str(i), preco=50, preco_original=100) for i in range(6)]
        bot = FakeBot()
        with mock.patch.object(config, "canais", canais), mock.patch.object(config, "horario_ativo", ""),              mock.patch.object(config, "espacamento_segundos", 300), mock.patch.object(config, "variacao_espacamento", 0),              mock.patch.object(config, "max_posts_por_ciclo", 0), mock.patch.object(config, "desconto_minimo", 25),              mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "r.db"),              mock.patch.object(pipeline, "coletar", return_value=ofs), mock.patch.object(pipeline.asyncio, "sleep", new=dorme),              mock.patch.object(pipeline, "avisar_dono", new=mock.AsyncMock()):
            n = asyncio.run(pipeline.executar_ciclo(bot))
        self.assertEqual(n, 18)                                        # 3 canais sem filtro x 6 ofertas
        self.assertEqual(len(esperas), 17)                             # espera entre todos os posts, menos antes do 1º
        self.assertTrue(all(e == 100 for e in esperas))   # 300s / 3 canais: cada canal posta a cada 5 min


class ApiOficialDoML(unittest.TestCase):
    RESULTADO = {"id": "MLB4012345678", "title": "Lâmpada H4 Led Super Projetor Alto/baixo - Par", "price": 145.55,
                 "original_price": 279.9, "permalink": "https://produto.mercadolivre.com.br/MLB-4012345678-lampada-h4?x=1#frag",
                 "thumbnail": "http://http2.mlstatic.com/D_NQ_NP_123-I.jpg", "category_id": "MLB2228", "sold_quantity": 1200,
                 "shipping": {"free_shipping": True}, "installments": {"quantity": 4, "amount": 36.39, "rate": 0}}

    def test_resultado_de_busca_vira_oferta(self):
        from ofertas.sources.mercadolivre_api import oferta_de_item
        o = oferta_de_item(self.RESULTADO)
        self.assertEqual((o.id_produto, o.preco, o.preco_original, o.vendas, o.categoria), ("MLB4012345678", 145.55, 279.9, 1200, "MLB2228"))
        self.assertEqual(o.url_produto, "https://produto.mercadolivre.com.br/MLB-4012345678-lampada-h4")
        self.assertEqual(o.imagem, "https://http2.mlstatic.com/D_NQ_NP_123-O.jpg")   # miniatura -> imagem grande
        self.assertIn("🚚 Frete grátis", o.extra)
        self.assertIn("💳 4x de R$ 36,39 sem juros", o.extra)
        self.assertEqual(o.desconto, 48)

    def test_sem_preco_ou_com_juros_nao_quebra(self):
        from ofertas.sources.mercadolivre_api import oferta_de_item
        self.assertIsNone(oferta_de_item({"id": "MLB1", "title": "x"}))
        d = dict(self.RESULTADO, installments={"quantity": 12, "amount": 30.0, "rate": 1.99}, original_price=None)
        o = oferta_de_item(d)
        self.assertNotIn("sem juros", o.extra)
        self.assertIsNone(o.preco_original)

    def test_produto_de_catalogo_usa_a_oferta_de_menor_preco_entre_as_novas(self):
        from ofertas.sources import mercadolivre_api as api
        prod = {"id": "MLB75836344", "name": "Auxiliar de Partida 6 em 1", "status": "active", "pictures": [{"url": "https://img/a.jpg"}]}
        itens = {"results": [
            {"item_id": "A", "price": 161.36, "original_price": 300, "condition": "new", "tags": ["lightning_deal"],
             "shipping": {"free_shipping": True}, "category_id": "MLB63455"},
            {"item_id": "B", "price": 199.0, "condition": "new"},
            {"item_id": "C", "price": 90.0, "condition": "used"}]}       # usado não conta
        chamadas = []

        def falso(caminho, **k):
            chamadas.append(caminho)
            return prod if caminho.endswith("MLB75836344") else itens
        api._cache.clear()
        with mock.patch.object(api, "_get_ou_none", side_effect=falso), mock.patch.object(api.time, "sleep"):
            o = api.produto_para_oferta("MLB75836344")
            api.produto_para_oferta("MLB75836344")       # 2ª vez: vem do cache, sem chamar o ML de novo
        self.assertEqual((o.titulo, o.preco, o.preco_original, o.desconto, o.imagem),
                         ("Auxiliar de Partida 6 em 1", 161.36, 300.0, 46, "https://img/a.jpg"))
        self.assertEqual(o.url_produto, "https://www.mercadolivre.com.br/p/MLB75836344")
        self.assertIn("⚡ Oferta relâmpago", o.extra)
        self.assertIn("🚚 Frete grátis", o.extra)
        self.assertEqual(o.categoria, "MLB63455")
        self.assertEqual(len(chamadas), 2)

    def test_produto_sem_vendedor_vira_none_e_e_lembrado(self):
        from ofertas.sources import mercadolivre_api as api
        prod = {"id": "MLB44355993", "name": "Lâmpada LED 6w", "status": "active", "pictures": []}
        chamadas = []

        def falso(caminho, **k):
            chamadas.append(caminho)
            return prod if not caminho.endswith("/items") else None      # 404 "No winners found"
        api._cache.clear()
        with mock.patch.object(api, "_get_ou_none", side_effect=falso), mock.patch.object(api.time, "sleep"):
            self.assertIsNone(api.produto_para_oferta("MLB44355993"))
            self.assertIsNone(api.produto_para_oferta("MLB44355993"))
        self.assertEqual(len(chamadas), 2)   # não insiste no que já sabe que não tem vendedor

    def test_sem_credenciais_fica_desligada(self):
        from ofertas.sources import mercadolivre_api as api
        with mock.patch.object(config, "ml_app_id", ""), mock.patch.object(config, "ml_app_secret", ""):
            self.assertFalse(api.disponivel())
            self.assertIsNone(api.oferta_de_url("https://www.mercadolivre.com.br/p/MLB75836344"))
            self.assertIn("Preencha ML_APP_ID", api.diagnostico()[0])

    def test_rodada_junta_mais_vendidos_e_palavras_chave_e_para_no_403(self):
        from ofertas.models import Oferta as O
        from ofertas.sources import mercadolivre_api as api
        chamados = []

        def produto(pid, categoria=None, campeao=False):
            chamados.append((pid, categoria, campeao))
            return O("mercadolivre", pid, f"Produto {pid}", "", preco=10)
        api._rodizio = 0
        api._cache.clear()
        cfg = {"categorias": {"MLB188063": "Limpeza"}, "buscas_api": ["boina"], "buscas_api_por_ciclo": 5}
        with mock.patch.object(config, "fonte_ml", cfg), mock.patch.object(api, "destaques", return_value=["P1", "P2"]), \
             mock.patch.object(api, "buscar_produtos", side_effect=RuntimeError("API do ML /products/search respondeu HTTP 403")), \
             mock.patch.object(api, "produto_para_oferta", side_effect=produto), mock.patch.object(api.time, "sleep"):
            ofertas = api.buscar_rodada()
        self.assertEqual([o.id_produto for o in ofertas], ["P1", "P2"])
        self.assertEqual(chamados, [("P1", None, True), ("P2", None, True)])   # campeões da categoria; sem "categoria confiável"

    def test_conversor_usa_a_api_quando_a_pagina_pede_captcha(self):
        from ofertas.models import Oferta as O
        from ofertas.sources import mercadolivre as ml
        via_api = O("mercadolivre", "MLB75836344", "Auxiliar de Partida 6 em 1", "", preco=148.45, preco_original=300.0, imagem="https://img/a.jpg")

        def gerar(ofs):
            for o in ofs:
                o.url_afiliado = "https://meli.la/abc"
        with mock.patch.object(ml, "sessao", side_effect=RuntimeError("captcha")),              mock.patch("ofertas.sources.mercadolivre_api.oferta_de_url", return_value=via_api),              mock.patch.object(ml, "gerar_links_afiliado", side_effect=gerar):
            o = ml.converter("https://www.mercadolivre.com.br/p/MLB75836344")
        self.assertEqual((o.titulo, o.preco, o.preco_original, o.imagem), ("Auxiliar de Partida 6 em 1", 148.45, 300.0, "https://img/a.jpg"))
        self.assertEqual(o.url_afiliado, "https://meli.la/abc")

    def test_niches_trazem_buscas_para_a_api(self):
        from ofertas.nichos import expandir
        buscas = expandir(["automotivo", "perfumes"])["ml_buscas"]
        self.assertIn("boina de polimento", buscas)
        self.assertIn("perfume árabe", buscas)


class SemDescontoListado(unittest.TestCase):
    def test_so_entra_se_o_canal_aceita_e_o_produto_e_campeao(self):
        from ofertas.canais import Canal
        campeao = oferta(id_="campeao", preco=26, original=None)
        campeao.vendas, campeao.nota = 2000, 4.8
        fraco = oferta(id_="fraco", preco=26, original=None)
        fraco.vendas, fraco.nota = 20, 4.8
        com_desconto_baixo = oferta(id_="baixo", preco=90, original=100)   # 10%: tem desconto, mas baixo: não vale a regra
        com_desconto_baixo.vendas, com_desconto_baixo.nota = 2000, 4.8
        aceita = Canal(id="a", nome="A", chat_id="-1", aceitar_sem_desconto=True)
        padrao = Canal(id="p", nome="P", chat_id="-2")
        with mock.patch.object(config, "desconto_minimo", 25), mock.patch.object(config, "vendas_minimas", 30),              mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "sd.db"):
            ids = lambda canal: [o.id_produto for o in pipeline.filtrar([campeao, fraco, com_desconto_baixo], canal)]
            mais_vendido = oferta(id_="topo", preco=26, original=None)
            mais_vendido.mais_vendido = True                                  # sem dados de venda, mas é o nº 1 da categoria
            self.assertEqual([o.id_produto for o in pipeline.filtrar([mais_vendido], aceita)], ["topo"])
            self.assertEqual(ids(aceita), ["campeao"])
            self.assertEqual(ids(padrao), [])


class ApiNaoConfiaNaCategoriaDosMaisVendidos(unittest.TestCase):
    def test_produto_de_cabelo_entre_os_mais_vendidos_de_limpeza_automotiva_e_barrado(self):
        from ofertas.canais import Canal
        canal = Canal(id="auto-teste", nome="A", chat_id="-1", nichos=["automotivo"], aceitar_sem_desconto=True)
        fora = Oferta("mercadolivre", "MLB1", "Truss Uso Obrigatório Tratamento Reconstrutor 260ml", "", preco=61.9,
                      preco_original=98.0, categoria="MLB269712", mais_vendido=True)
        dentro = Oferta("mercadolivre", "MLB2", "Boina Lã Pirulito Corte Pesado Polimento Lincoln 5 Pol", "", preco=48.0,
                        preco_original=69.0, categoria="MLB433258", mais_vendido=True)
        with mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "c.db"), mock.patch.object(config, "desconto_minimo", 25):
            ids = [o.id_produto for o in pipeline.filtrar([fora, dentro], canal)]
        self.assertEqual(ids, ["MLB2"])


class ErrosDoTelegram(unittest.TestCase):
    def test_queda_de_rede_vira_uma_linha_e_erro_de_verdade_mantem_o_detalhe(self):
        import asyncio
        from telegram.error import NetworkError
        from ofertas import bot_interativo as bi

        class Ctx:
            def __init__(self, erro):
                self.error = erro
        with self.assertLogs("ofertas.bot", level="WARNING") as cap:
            asyncio.run(bi._erro(None, Ctx(NetworkError("httpx.ConnectError: "))))
        self.assertEqual(len(cap.records), 1)
        self.assertIsNone(cap.records[0].exc_info)              # sem tela de traceback
        with self.assertLogs("ofertas.bot", level="ERROR") as cap:
            asyncio.run(bi._erro(None, Ctx(ValueError("bug de verdade"))))
        self.assertIsNotNone(cap.records[0].exc_info)           # bug real continua com o detalhe


class PainelTelegram(unittest.TestCase):
    def test_queda_de_conexao_repete_e_depois_explica_em_portugues(self):
        import requests
        from ofertas import painel
        chamadas = []

        def cai(*a, **k):
            chamadas.append(1)
            raise requests.ConnectionError("('Connection aborted.', ConnectionResetError(10054))")
        with mock.patch.object(painel.requests, "get", side_effect=cai), mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                painel._telegram("getUpdates", "token")
        self.assertEqual(len(chamadas), 3)
        self.assertIn("conexão com o Telegram foi interrompida", str(ctx.exception))
        self.assertNotIn("10054", str(ctx.exception))          # sem o texto cru da biblioteca

    def test_recupera_se_a_segunda_tentativa_funciona(self):
        import requests
        from ofertas import painel
        respostas = [requests.ConnectionError("cai"), mock.Mock(json=lambda: {"ok": True, "result": []})]

        def get(*a, **k):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with mock.patch.object(painel.requests, "get", side_effect=get), mock.patch("time.sleep"):
            self.assertEqual(painel._telegram("getUpdates", "token"), {"ok": True, "result": []})

    def test_detectar_com_o_bot_ligado_explica_o_caminho_alternativo(self):
        from ofertas import painel
        with mock.patch.object(painel, "ler_env", return_value={"TELEGRAM_BOT_TOKEN": "x"}),              mock.patch.object(painel.instancia, "rodando", return_value=1234),              mock.patch.object(painel.bot, "rodando", return_value=False),              mock.patch.object(painel, "_telegram", side_effect=AssertionError("não devia chamar o Telegram")):
            r = painel.detectar_ids()
        self.assertIn("encaminhe um post do canal para o bot", r["erro"])
        self.assertIn("Telegram Web", r["erro"])


class RodizioJustoEntreCanais(unittest.TestCase):
    def test_repartir_da_o_que_sobra_do_pequeno_ao_grande(self):
        from ofertas.rodizio import repartir
        self.assertEqual(repartir([30, 1], 12), [11, 1])
        self.assertEqual(repartir([30, 30], 12), [6, 6])
        self.assertEqual(repartir([3, 2], 12), [3, 2])          # cabe tudo: cada um consulta tudo
        self.assertEqual(repartir([30, 1, 1], 12), [10, 1, 1])

    def test_canal_pequeno_e_consultado_toda_rodada_e_o_grande_da_a_volta(self):
        from ofertas import rodizio
        rodizio._indices.clear()
        grande = [f"A{i}" for i in range(30)]
        pequeno = ["AC1"]
        rodadas = [rodizio.escolher([grande, pequeno], 12, "t") for _ in range(3)]
        self.assertTrue(all("AC1" in r for r in rodadas))                    # ar condicionado: toda rodada
        self.assertTrue(all(len(r) == 12 for r in rodadas))
        cobertas = {x for r in rodadas for x in r if x != "AC1"}
        self.assertEqual(len(cobertas), 30)                                  # em 3 rodadas o grande cobriu todas as 30

    def test_ml_usa_a_cota_por_canal(self):
        from ofertas import rodizio
        from ofertas.sources import mercadolivre as ml
        rodizio._indices.clear()
        cats = {f"MLB{i}": f"c{i}" for i in range(1, 32)}     # 30 do automotivo + a 31ª, do ar condicionado
        grupos = [{"categorias": [f"MLB{i}" for i in range(1, 31)]}, {"categorias": ["MLB31"]}]
        with mock.patch.object(config, "fonte_ml", {"categorias": cats, "grupos": grupos, "requisicoes_por_ciclo": 12}):
            primeira = ml._categorias_da_rodada()
        self.assertIn("MLB31", primeira)      # antes só entrava na 3ª rodada
        self.assertEqual(len(primeira), 12)


class ArCondicionadoSoDeCasa(unittest.TestCase):
    def test_pecas_de_ar_condicionado_de_carro_ficam_de_fora(self):
        from ofertas.nichos import relevante
        for t in ["Caixa Evaporadora Universal 25.000btu 5 Difusores 12v Ou 24v",
                  "Capa Proteção Água Caixa Filtro Ar Condicionado Gol G2 G3 G4",
                  "Compressor Ar Condicionado Fiat Palio Uno Siena Strada",
                  "Filtro de Cabine Ar Condicionado Honda Civic 2012"]:
            self.assertFalse(relevante(t, ["arcondicionado"]), t)
        for t in ["Ar Condicionado Split Elgin Eco Inverter II Wi-fi 12000 Btu", "Ar-Condicionado Portátil Philco 10000 BTUs 220V",
                  "Ar Condicionado Haier Janela Eletrônico 8500 Btus Frio", "Suporte para Ar Condicionado Split 400mm Reforçado",
                  "Ar Condicionado Hw Electrolux Maxcomfort Inverter 9k F Branco"]:
            self.assertTrue(relevante(t, ["arcondicionado"]), t)


class AlertaDeRedeNaoMandaProAdmin(unittest.TestCase):
    def test_queda_de_rede_nao_diz_para_conferir_o_admin(self):
        import asyncio
        from telegram.error import NetworkError
        from ofertas.canais import Canal
        avisos = []

        async def avisar(bot, texto, **k):
            avisos.append(texto)

        class Bot:
            async def send_photo(self, *a, **k):
                raise NetworkError("httpx.ConnectError: ")
            send_message = send_photo

        canal = Canal(id="x", nome="X", chat_id="-1")
        o = Oferta("amazon", "r1", "Produto de teste completo", "https://x/1", preco=50, preco_original=100)
        with mock.patch.object(config, "canais", [canal]), mock.patch.object(config, "horario_ativo", ""),              mock.patch.object(config, "desconto_minimo", 25), mock.patch.object(config, "espacamento_segundos", 0),              mock.patch.object(pipeline.db, "_DB", pathlib.Path(tempfile.mkdtemp()) / "n.db"),              mock.patch.object(pipeline, "coletar", return_value=[o]), mock.patch.object(pipeline, "avisar_dono", side_effect=avisar),              mock.patch("ofertas.telegram_poster.asyncio.sleep", new=mock.AsyncMock()),              mock.patch.object(pipeline.asyncio, "sleep", new=mock.AsyncMock()):
            n = asyncio.run(pipeline.executar_ciclo(Bot()))
            self.assertEqual(n, 0)
            self.assertTrue(pipeline.db.ja_postada("x|amazon:r1", 7) is False)   # não ficou registrado: volta na próxima rodada
        self.assertEqual(len(avisos), 1)
        self.assertIn("conexão com o Telegram caiu", avisos[0])
        self.assertNotIn("administrador", avisos[0])


class MotoSaiDoAutomotivo(unittest.TestCase):
    MOTO = ["Frente Completa Cg 150 160 Titan Fan 2025 Paralama", "Kit Carenagem Moto Pro Tork Biz 125 Ks Es", "Capacete Moto Fechado Masculino Preto",
            "Capa Chuva Motoqueiro Pvc Impermeável Motoboy", "Baú Moto Traseiro 65 Litros Aluminio", "Escapamento F1 Mini Tri Fortuna Titan/fan/start",
            "Intercomunicador Bluetooth Para Capacete De Moto V6", "Bateria Moura MA5-D 5 Ah 12V Selada para Honda, Yamaha e Mais"]

    def test_peca_e_acessorio_de_moto_nao_entra_no_automotivo_nem_pela_categoria_confiavel(self):
        from ofertas.nichos import relevante
        for t in self.MOTO:
            self.assertFalse(relevante(t, ["automotivo"]), t)
            self.assertFalse(relevante(t, ["automotivo"], categoria="MLB22693"), t)

    def test_item_para_carro_e_moto_continua_valendo(self):
        from ofertas.nichos import relevante
        self.assertTrue(relevante("Mini Compressor de Ar Digital Portátil para Carro, Moto e Bicicleta", ["automotivo"]))
        self.assertTrue(relevante("Kit Ferramentas Parafusadeira 20v Carro Moto", ["automotivo"]))

    def test_moto_vira_nicho_proprio_para_quem_quiser_um_canal_de_moto(self):
        from ofertas.nichos import NICHOS, categorias_confiaveis, expandir, relevante
        self.assertIn("moto", NICHOS)
        for t in self.MOTO:
            self.assertTrue(relevante(t, ["moto"]), t)
        self.assertNotIn("MLB243551", expandir(["automotivo"])["ml"])      # peças de moto saíram da coleta do automotivo
        self.assertIn("MLB243551", expandir(["moto"])["ml"])

    def test_tweeter_e_busca_da_api_para_o_que_o_grupo_de_referencia_posta(self):
        from ofertas.nichos import expandir
        buscas = expandir(["automotivo"])["ml_buscas"]
        for termo in ("tweeter jbl selenium", "lavadora alta pressão wap", "adaptador engate rápido karcher", "pneu aro 14"):
            self.assertIn(termo, buscas)


class FerramentasEPlural(unittest.TestCase):
    def test_plural_em_qualquer_palavra_do_termo(self):
        from ofertas.nichos import _casa, _norm
        self.assertTrue(_casa("chave allen", _norm("Kit Jogo Chaves Allen 8 Peças Preto")))
        self.assertTrue(_casa("luva de trabalho", _norm("Par de Luvas de Trabalho Reforçadas")))
        self.assertTrue(_casa("fita isolante", _norm("3 Fitas Isolantes 19mm")))
        self.assertFalse(_casa("chave allen", _norm("Chavealleniforme")))      # continua exigindo palavra inteira
        self.assertFalse(_casa("luva de trabalho", _norm("Luva de Boxe Profissional")))

    def test_ferramentas_aceita_a_lista_do_dono_e_barra_o_que_nao_e(self):
        from ofertas.nichos import relevante
        bons = ["Jogo de Chaves de Fenda e Philips 6 Peças Isoladas", "Martelo de Unha 27mm Cabo Fibra", "Parafusadeira Furadeira de Impacto Vonder PFV120i",
                "Bolsa Maleta de Ferramentas 18 Polegadas Reforçada 16 Bolsos", "Jogo de Chave Torx + Jogo Allen Curta Kit com 18 Peças",
                "Kit Jogo Chaves Allen 8 Peças", "Multímetro Digital Profissional", "Ferro de Solda 60w 220v", "Óculos de Proteção Incolor Antiembaçante",
                "Protetor Auricular Tipo Concha", "Lanterna de Cabeça Recarregável", "Fita Veda Rosca 18mm x 50m", "Trena 5m Emborrachada",
                "Jogo de Soquetes com Catraca 40 Peças", "Serra Tico-Tico 650w", "Esmerilhadeira Angular 4 1/2 Bosch"]
        for t in bons:
            self.assertTrue(relevante(t, ["ferramentas"]), t)
        ruins = ["Kit Ferramentas de Brinquedo Infantil Bob Construtor", "Alicate de Cutícula Manicure Inox", "Luva de Boxe Profissional Couro",
                 "Máscara Facial de Argila Verde", "Lixa de Unha Profissional 100/180", "Extensão de Cabelo Humano Mega Hair",
                 "Ímã de Geladeira Decorativo", "Livro Ferramentas de Gestão"]
        for t in ruins:
            self.assertFalse(relevante(t, ["ferramentas"]), t)

    def test_categorias_de_ferramentas_sao_confiaveis_mas_as_exclusoes_valem(self):
        from ofertas.nichos import categorias_confiaveis, relevante
        conf = categorias_confiaveis(["ferramentas"])
        for cid in ("MLB2526", "MLB189008", "MLB454904", "MLB189215", "MLB455200"):
            self.assertIn(cid, conf)
        self.assertTrue(relevante("Item sem nome de ferramenta no título", ["ferramentas"], categoria="MLB189008"))
        self.assertFalse(relevante("Kit de Brinquedo Parafusadeira Infantil", ["ferramentas"], categoria="MLB189008"))

    def test_buscas_da_api_cobrem_a_lista_do_dono(self):
        from ofertas.nichos import expandir
        buscas = expandir(["ferramentas"])["ml_buscas"]
        for termo in ("martelo de unha", "jogo de bits", "ímã telescópico", "detector de canos e fios", "painel de ferramentas", "fita silver tape"):
            self.assertIn(termo, buscas)


class EstiloSimples(unittest.TestCase):
    def _cap(self, o, estilo="simples"):
        from ofertas.formatter import montar_caption
        with mock.patch.object(config, "estilo_post", estilo), mock.patch.object(config, "link_visivel", True),              mock.patch.object(config, "aviso_amazon", ""):
            return montar_caption(o)

    def test_exemplo_da_parafusadeira_com_cupom_e_pix(self):
        o = Oferta("mercadolivre", "1", "Parafusadeira Furadeira de Impacto Vonder PFV120i", "https://meli.la/2PUnVxM",
                   preco=115.0, preco_original=299.0, cupom="OFERTAS", extra="💠 preço no Pix")
        c = self._cap(o)
        self.assertEqual(c.splitlines(), [
            "<b>Parafusadeira Furadeira de Impacto Vonder PFV120i</b>", "",
            "De <s>R$ 299,00</s> por <b>R$ 115,00</b> no Pix",
            "🎟 Use o cupom: <code>OFERTAS</code>", "",
            "🛍 Compre aqui: https://meli.la/2PUnVxM"])

    def test_sem_preco_original_e_sem_cupom_fica_so_o_essencial(self):
        o = Oferta("shopee", "2", "Jogo de Chave Torx + Jogo Allen Curta Kit com 18 Peças", "https://s.shopee.com.br/8AVeJzfpzD", preco=29.0)
        c = self._cap(o)
        self.assertEqual(c.splitlines(), ["<b>Jogo de Chave Torx + Jogo Allen Curta Kit com 18 Peças</b>", "", "Por <b>R$ 29,00</b>",
                                          "", "🛍 Compre aqui: https://s.shopee.com.br/8AVeJzfpzD"])

    def test_nao_tem_selo_economia_nem_rodape_de_loja(self):
        o = Oferta("mercadolivre", "3", "Produto qualquer de teste", "https://meli.la/x", preco=50, preco_original=100)
        c = self._cap(o)
        for fora in ["OFERTA", "economiza", "Mercado Livre", "-50%"]:
            self.assertNotIn(fora, c)
        self.assertIn("De <s>R$ 100,00</s> por <b>R$ 50,00</b>", c)

    def test_mantem_o_que_importa_parcelas_cupom_do_ml_e_prova_social(self):
        o = Oferta("mercadolivre", "4", "Produto de teste", "https://meli.la/y", preco=1188.0, preco_original=4300.0, nota=4.8, vendas=5000,
                   extra="⭐ 4.8 · +5mil vendidos · 🚚 Frete grátis · 💳 10x de R$ 128,80 sem juros · 🎟 Preço com cupom do ML (ative o cupom na página do produto)")
        c = self._cap(o)
        self.assertIn("💳 10x de R$ 128,80 sem juros", c)
        self.assertIn("🎟 Preço com cupom do ML", c)             # honestidade sobre o cupom do ML continua
        self.assertIn("⭐ 4,8  ·  🔥 +5 mil vendidos  ·  🚚 Frete grátis", c)
        self.assertEqual(c.count("vendidos"), 1)

    def test_amazon_mantem_a_declaracao_exigida(self):
        from ofertas.formatter import montar_caption
        o = Oferta("amazon", "B0", "Kit de ferramentas", "https://www.amazon.com.br/dp/B0?tag=x-20", preco=100)
        frase = "Como participante do Programa de Associados da Amazon, sou remunerado pelas compras qualificadas efetuadas."
        with mock.patch.object(config, "estilo_post", "simples"), mock.patch.object(config, "aviso_amazon", frase):
            self.assertIn(frase, montar_caption(o))

    def test_estilo_completo_continua_disponivel(self):
        o = Oferta("mercadolivre", "5", "Produto de teste", "https://meli.la/z", preco=50, preco_original=100, desconto_pct=50)
        c = self._cap(o, "completo")
        self.assertIn("SUPER OFERTA", c)
        self.assertIn("Você economiza R$ 50,00", c)

class CupomFixoDoCanal(unittest.TestCase):
    def test_campo_do_canal_e_normalizado(self):
        from ofertas.canais import validar
        c = validar([{"nome": "A", "chat_id": "-1", "cupom": " ofertas "}])[0]
        self.assertEqual(c.cupom, "OFERTAS")
        self.assertEqual(validar([{"nome": "B", "chat_id": "-2"}])[0].cupom, "")



class NichosCountryEPerfumes(unittest.TestCase):
    def test_country_aceita_marcas_e_barra_falsos(self):
        from ofertas.nichos import relevante
        for t in ["Camisa Masculina Selff Western Manga Longa", "Calça Wrangler Cowboy Cut Masculina",
                  "Bota Texana Bico Fino Couro", "Chapéu Country Americano Rodeio Barretos"]:
            self.assertTrue(relevante(t, ["country"]), t)
        for t in ["Pneu Jeep Wrangler Aro 17", "Boneca Boiadeira Articulada", "Camiseta Preta Lisa Algodão",
                  "Bota de Segurança Trabalho Bico de Aço"]:
            self.assertFalse(relevante(t, ["country"]), t)

    def test_perfumes_aceita_marcas_e_barra_falsos(self):
        from ofertas.nichos import relevante
        for t in ["Perfume Lattafa His Confession Eau De Parfum 100ml", "Armaf Club De Nuit Intense Man 105ml",
                  "Body Splash Feminino 200ml", "Colônia Deo Masculina 100ml",
                  "Dior Sauvage Eau de Toilette 100ml", "Calvin Klein CK One Eau de Toilette 200ml",
                  "Natura Kaiak Desodorante Colônia Masculino", "Perfume Carolina Herrera Good Girl 80ml",
                  "Maison Alhambra Jean Lowe Immortel 100ml", "Creed Aventus Eau de Parfum 100ml",
                  "Fragrance World Hawas Elixir 100ml", "Tom Ford Oud Wood Eau de Parfum", "Contratipo 212 VIP Men 100ml",
                  "Gucci Guilty Pour Homme Eau de Toilette", "Perfume In The Box Masculino 100ml"]:
            self.assertTrue(relevante(t, ["perfumes"]), t)
        for t in ["Kit Colônia Infantil Cebolinha", "Perfume Capilar Anti Frizz", "Porta Perfume de Viagem",
                  "Perfume para Ambiente Difusor", "Hidratante Natura Ekos", "Camiseta Dior Preta",
                  "Batom Dior Rouge 999", "Camiseta Calvin Klein Slim", "Shampoo Natura Lumina", "Cueca Calvin Klein Kit 3",
                  "Óculos de Sol Tom Ford", "Bolsa Gucci Feminina Couro", "Tênis Prada Masculino", "Zara Camisa Linho"]:
            self.assertFalse(relevante(t, ["perfumes"]), t)

class AutomotivoGrupoDeReferencia(unittest.TestCase):
    def test_titulos_de_grupos_de_carro(self):
        from ofertas.nichos import relevante
        for t in ["Espuma Magica Limpador De Uso Geral 400ml Proauto", "Difusor de Escape Eletrônico Universal 2,5",
                  "Liqui Moly Super Diesel Additiv 250 ml", "Vintex Alumax 1,5L",
                  "Tacômetro Conta-giros Dragon 52mm", "Canhão de Espuma Snow Foam Gravity",
                  "Inversor de Energia Automotivo 400W 12V"]:
            self.assertTrue(relevante(t, ["automotivo"]), t)


class PerfumeSoDeLojaConfiavel(unittest.TestCase):
    def _canal(self):
        from ofertas.canais import Canal
        return Canal(id="perfumes", nome="P", chat_id="-1", nichos=["perfumes"])

    def _filtrar(self, ofs):
        with mock.patch.object(config, "desconto_minimo", 0), mock.patch.object(pipeline.db, "ja_postada", return_value=False):
            return [o.id_produto for o in pipeline.filtrar(ofs, self._canal())]

    def test_so_passa_vendedor_verificado(self):
        t = "Perfume Lattafa Asad Eau de Parfum 100ml"
        ofs = [Oferta("shopee", "ok", t + " a", "https://x", preco=90, preco_original=200, loja_confiavel=True),
               Oferta("shopee", "comum", t + " b", "https://x", preco=90, preco_original=200, loja_confiavel=False),
               Oferta("mercadolivre", "ml_ok", t + " c", "", preco=90, preco_original=200, loja_confiavel=True),
               Oferta("mercadolivre", "ml_sem_info", t + " d", "", preco=90, preco_original=200),
               Oferta("amazon", "amz", t + " e", "https://x", preco=90, preco_original=200)]
        self.assertEqual(self._filtrar(ofs), ["ok", "ml_ok", "amz"])  # Amazon é confirmada na página, antes de postar

    def test_outros_nichos_nao_exigem(self):
        from ofertas.canais import Canal
        o = Oferta("shopee", "x", "Bota Country Texana Couro", "https://x", preco=90, preco_original=200, loja_confiavel=False)
        with mock.patch.object(config, "desconto_minimo", 0), mock.patch.object(pipeline.db, "ja_postada", return_value=False):
            self.assertEqual(len(pipeline.filtrar([o], Canal(id="c", nome="C", chat_id="-2", nichos=["country"]))), 1)

    def test_shopee_so_loja_oficial_mall(self):
        from ofertas.sources import shopee
        base = {"itemId": 1, "productName": "Perfume X", "priceMin": "100", "ratingStar": "4.9", "sales": 500, "offerLink": "l"}
        self.assertTrue(shopee._node_para_oferta({**base, "shopType": [1]}).loja_confiavel)
        self.assertFalse(shopee._node_para_oferta({**base, "shopType": [2]}).loja_confiavel)
        self.assertFalse(shopee._node_para_oferta({**base, "shopType": []}).loja_confiavel)
        with mock.patch.object(config, "lojas_confiaveis", "oficial+lider"):
            self.assertTrue(shopee._node_para_oferta({**base, "shopType": [2]}).loja_confiavel)
            self.assertFalse(shopee._node_para_oferta({**base, "shopType": [2], "sales": 20}).loja_confiavel)

    def test_ml_escolhe_loja_oficial_em_perfume_mesmo_mais_cara(self):
        from ofertas.sources import mercadolivre_api as api
        itens = {"results": [
            {"price": 40, "condition": "new", "category_id": "MLB6284", "seller_id": 1},
            {"price": 120, "condition": "new", "category_id": "MLB6284", "seller_id": 2, "official_store_id": 99},
            {"price": 90, "condition": "new", "category_id": "MLB6284", "seller_id": 3}]}
        self.assertEqual(api._melhor_oferta(itens)["price"], 120)
        outra = {"results": [{**i, "category_id": "MLB1648"} for i in itens["results"]]}
        self.assertEqual(api._melhor_oferta(outra)["price"], 40)  # fora de perfumes continua o mais barato

    def test_sinais_de_falsificacao_no_titulo(self):
        from ofertas.nichos import relevante
        for t in ["Perfume Replica Importado Eau de Parfum 100ml", "Perfume Importado AAA Primeira Linha 100ml"]:
            self.assertFalse(relevante(t, ["perfumes"]), t)


class AutomotivoSemFerramentasGerais(unittest.TestCase):
    def test_ferramenta_geral_e_do_canal_de_ferramentas(self):
        from ofertas.nichos import relevante
        for t in ["40 Peças Jogo De Chave Catraca Caixa De Ferramentas", "Parafusadeira Furadeira a Bateria 12V",
                  "Kit de Ferramentas Elétricas 128V"]:
            self.assertFalse(relevante(t, ["automotivo"]), t)
            self.assertTrue(relevante(t, ["ferramentas"]), t)
        for t in ["Macaco Hidraulico Jacare 2 Toneladas", "Chave de Roda Cruz Automotivo", "Kit Ferramentas Automotivas Reparo"]:
            self.assertTrue(relevante(t, ["automotivo"]), t)

    def test_amazon_vendido_pela_propria_amazon(self):
        from ofertas.sources.amazon import _RE_VENDIDO_AMAZON as R
        for t in ["Enviado / Vendido Amazon.com.br Amazon.com.br", "Vendido por Amazon"]:
            self.assertTrue(R.search(t), t)
        for t in ["Enviado / Vendido WebContinental", "Enviado por Amazon Vendido por LojaX", "Vendido por Amazon Export"]:
            self.assertFalse(R.search(t), t)


class BloqueioDoML(unittest.TestCase):
    def test_pagina_de_verificacao_para_a_rodada(self):
        from ofertas.sources import mercadolivre
        resp = mock.Mock(url="https://www.mercadolivre.com.br/gz/account-verification?go=x", text="")
        sess = mock.Mock()
        sess.get.return_value = resp
        with mock.patch.object(mercadolivre, "sessao", return_value=sess),                 mock.patch.object(mercadolivre, "tem_sessao", return_value=False),                 mock.patch.object(mercadolivre, "_categorias_da_rodada", return_value={"A": "a", "B": "b"}):
            with self.assertRaises(mercadolivre.BloqueioML):
                mercadolivre.buscar_ofertas()
        self.assertEqual(sess.get.call_count, 1)  # não insiste nas outras categorias

    def test_bloqueio_cai_para_o_navegador_e_lembra_por_um_tempo(self):
        from ofertas.sources import mercadolivre
        resp = mock.Mock(url="https://www.mercadolivre.com.br/gz/account-verification?go=x", text="")
        sess = mock.Mock()
        sess.get.return_value = resp
        achada = Oferta("mercadolivre", "m1", "Perfume X", "", preco=10)
        with mock.patch.object(mercadolivre, "sessao", return_value=sess),                 mock.patch.object(mercadolivre, "tem_sessao", return_value=True),                 mock.patch.object(mercadolivre, "_bloqueio_ate", 0.0),                 mock.patch.object(mercadolivre, "_categorias_da_rodada", return_value={"A": "a"}),                 mock.patch.object(mercadolivre, "_buscar_pelo_navegador", return_value=[achada]) as nav:
            self.assertEqual(mercadolivre.buscar_ofertas(), [achada])   # 1ª rodada: tenta, é barrado, usa o navegador
            self.assertEqual(mercadolivre.buscar_ofertas(), [achada])   # 2ª: vai direto ao navegador
        self.assertEqual(sess.get.call_count, 1)
        self.assertEqual(nav.call_count, 2)


if __name__ == "__main__":
    unittest.main()

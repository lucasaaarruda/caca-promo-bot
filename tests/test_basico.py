import os
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


if __name__ == "__main__":
    unittest.main()

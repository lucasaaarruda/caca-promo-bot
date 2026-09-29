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
             mock.patch.object(config, "nichos", []), \
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


if __name__ == "__main__":
    unittest.main()

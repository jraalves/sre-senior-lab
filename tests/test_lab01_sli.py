"""Lab-01: calculo de SLI e orcamento de erro."""

import unittest

from _carga import caminho_lab, carregar_module

slo = carregar_module("lab01_slo", caminho_lab(
    "lab-01-slo-error-budget", "slo.py"))
CSV = caminho_lab("lab-01-slo-error-budget", "data", "slo-signals.csv")


def reg(ts, requests, failed, slow):
    return {"timestamp": ts, "requests": str(requests),
            "failed": str(failed), "slow": str(slow),
            "fast": str(requests - failed - slow)}


class TestSliTotal(unittest.TestCase):
    def test_aritmetica_exata(self):
        serie = [reg("2026-10-01T00:00:00Z", 1000, 5, 20),
                 reg("2026-10-01T01:00:00Z", 1000, 5, 30)]
        s = slo.sli_total(serie)
        self.assertEqual(s["requisicoes"], 2000)
        self.assertEqual(s["requisicoes_invalidas"], 10)
        self.assertEqual(s["requisicoes_lentas"], 50)
        self.assertAlmostEqual(s["sli_disponibilidade"], 1 - 10 / 2000.0, places=9)
        self.assertAlmostEqual(s["sli_latencia"], 1 - 50 / 2000.0, places=9)

    def test_zero_requisicoes_estoura(self):
        with self.assertRaises(ValueError):
            slo.sli_total([reg("2026-10-01T00:00:00Z", 0, 0, 0)])

    def test_sli_sobe_quando_nao_ha_falha(self):
        s = slo.sli_total([reg("2026-10-01T00:00:00Z", 500, 0, 0)])
        self.assertEqual(s["sli_disponibilidade"], 1.0)
        self.assertEqual(s["sli_latencia"], 1.0)


class TestPolitica(unittest.TestCase):
    def test_bloquear_com_orcamento_estourado(self):
        self.assertEqual(slo.decidir(120.0, 10.0)[0], "BLOQUEAR")

    def test_revisao_por_disponibilidade(self):
        self.assertEqual(slo.decidir(90.0, 10.0)[0], "LIBERAR_COM_REVISAO")

    def test_revisao_por_latencia(self):
        self.assertEqual(slo.decidir(20.0, 130.0)[0], "LIBERAR_COM_REVISAO")

    def test_liberar_dentro_do_orcamento(self):
        self.assertEqual(slo.decidir(20.0, 20.0)[0], "LIBERAR")


class TestProjecao(unittest.TestCase):
    def test_consumo_de_orcamento_na_aritmetica_manual(self):
        # 2 dias observados, 4000 requisicoes, 8 invalidas, alvo 99.9%.
        # budget projetado para a janela de 30 dias:
        #   4000 * 0,001 * (30/2) = 60 requisicoes invalidas.
        # consumo: 8/60 = 13,333...%.
        serie = [reg("2026-10-01T00:00:00Z", 2000, 4, 4),
                 reg("2026-10-02T00:00:00Z", 2000, 4, 4)]
        p = slo.projecao_e_decisao(serie, 0.999, 0.990, 30)
        self.assertEqual(p["dias_observados"], 2)
        self.assertEqual(p["invalidas_janela"], 8)
        self.assertEqual(p["orcamento_requisicoes_invalidas_janela"], 60)
        self.assertAlmostEqual(p["consumo_error_budget_pct"], 13.3, places=1)

    def test_serie_vazia_estoura(self):
        with self.assertRaises(ValueError):
            slo.projecao_e_decisao([], 0.999, 0.990, 30)


class TestDadosSinteticos(unittest.TestCase):
    def setUp(self):
        self.registros = slo.carregar(CSV)

    def test_consistencia_interna_do_csv(self):
        for r in self.registros:
            self.assertGreaterEqual(int(r["requests"]), int(r["failed"]))
            self.assertLessEqual(int(r["failed"]) + int(r["slow"]),
                                 int(r["requests"]))

    def test_compute_all_expoe_chaves_esperadas(self):
        saida = slo.compute_all(CSV)
        self.assertTrue(saida["sintetico"])
        for chave in ("sli", "projecao_e_decisao", "consumo_por_dia",
                     "consumo_por_semana"):
            self.assertIn(chave, saida)
        self.assertLess(saida["sli"]["sli_disponibilidade"], 1.0)
        self.assertIn(saida["projecao_e_decisao"]["decisao"],
                      ("LIBERAR", "LIBERAR_COM_REVISAO", "BLOQUEAR"))


if __name__ == "__main__":
    unittest.main()

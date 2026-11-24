"""Lab-06: projeção de capacidade por mínimos quadrados."""

import unittest

from _carga import caminho_lab, carregar_module

cap = carregar_module("lab06_capacity", caminho_lab(
    "lab-06-capacity-planning", "capacity.py"))
CSV = caminho_lab("lab-06-capacity-planning", "data", "capacity.csv")


class TestMinimosQuadrados(unittest.TestCase):
    def test_reta_exata(self):
        a, b = cap.minimos_quadrados([0, 1, 2, 3], [1, 3, 5, 7])
        self.assertAlmostEqual(a, 1.0, places=9)
        self.assertAlmostEqual(b, 2.0, places=9)

    def test_reta_com_intercepto_negativo(self):
        a, b = cap.minimos_quadrados([1, 2, 3], [1.5, 3.5, 5.5])
        self.assertAlmostEqual(a, -0.5, places=9)
        self.assertAlmostEqual(b, 2.0, places=9)

    def test_inclinacao_zero_para_serie_constante(self):
        a, b = cap.minimos_quadrados([0, 1, 2], [4.0, 4.0, 4.0])
        self.assertAlmostEqual(b, 0.0, places=9)
        self.assertAlmostEqual(a, 4.0, places=9)

    def test_um_ponto_so_nao_estoura(self):
        self.assertEqual(cap.minimos_quadrados([5], [10.0]), (10.0, 0.0))

    def test_xs_identicos_devolve_inclinacao_zero(self):
        _a, b = cap.minimos_quadrados([2, 2, 2], [1.0, 5.0, 9.0])
        self.assertEqual(b, 0.0)

    def test_serie_vazia_estoura(self):
        with self.assertRaises(ValueError):
            cap.minimos_quadrados([], [])

    def test_projecao_na_reta(self):
        a, b = cap.minimos_quadrados([0, 1, 2], [10.0, 20.0, 30.0])
        self.assertAlmostEqual(cap.projetar(a, b, 10), 110.0, places=6)

    def test_r_quadrado_perfeito(self):
        xs, ys = [0, 1, 2, 3], [2.0, 4.0, 6.0, 8.0]
        a, b = cap.minimos_quadrados(xs, ys)
        self.assertAlmostEqual(cap.r_quadrado(xs, ys, a, b), 1.0, places=9)


class TestDecisao(unittest.TestCase):
    def _ajuste(self, **kw):
        base = {"semanas_ate_o_alvo": 40.0, "inclinacao_rps_por_semana": 1.0,
                "alvo_operacional_rps": 1000.0, "cpu_p95_ultimo": 50.0}
        base.update(kw)
        return base

    def test_saturacao_dentro_do_lead_time_expande(self):
        acao, motivo = cap.decidir(self._ajuste(semanas_ate_o_alvo=3.0),
                                   lead_time=6)
        self.assertEqual(acao, "expandir")
        self.assertIn("lead time", motivo)

    def test_tendencia_de_queda_com_cpu_baixa_reduz(self):
        acao, _ = cap.decidir(self._ajuste(semanas_ate_o_alvo=None,
                                           inclinacao_rps_por_semana=-4.0,
                                           cpu_p95_ultimo=20.0))
        self.assertEqual(acao, "reduzir")

    def test_carga_ja_acima_do_alvo_expande(self):
        pontos = [{"semana": i, "inicio": "2026-10-%02d" % (i + 1), "rps": 900.0 + i,
                   "cpu_p95_pct": 80.0, "fila": 1.0, "saturacao_rps": 1000.0,
                   "rps_por_replica": 100.0} for i in range(4)]
        ajuste = cap.ajustar(pontos)
        self.assertEqual(ajuste["semanas_ate_o_alvo"], 0.0)
        self.assertEqual(cap.decidir(ajuste)[0], "expandir")

    def test_sem_inclinacao_positiva_observa(self):
        acao, _ = cap.decidir(self._ajuste(semanas_ate_o_alvo=None,
                                           inclinacao_rps_por_semana=0.0,
                                           cpu_p95_ultimo=50.0))
        self.assertEqual(acao, "observar")

    def test_folga_grande_so_observa(self):
        acao, _ = cap.decidir(self._ajuste(semanas_ate_o_alvo=52.0))
        self.assertEqual(acao, "observar")


class TestSerieSintetica(unittest.TestCase):
    def setUp(self):
        self.rel = cap.analisar(CSV)

    def test_seis_servicos_na_serie(self):
        self.assertEqual(len(self.rel["servicos"]), 6)
        self.assertEqual(self.rel["servicos"]["payments-api"]["pontos_na_serie"], 26)

    def test_toda_decisao_tem_motivo_medido(self):
        for nome, a in self.rel["servicos"].items():
            self.assertIn(a["decisao"], ("expandir", "observar", "reduzir"), nome)
            self.assertTrue(a["motivo"])
            self.assertGreater(a["saturacao_rps"], a["alvo_operacional_rps"])
            self.assertLessEqual(a["r_quadrado"], 1.0)

    def test_contagem_bate_com_as_decisoes(self):
        soma = sum(self.rel["contagem_por_decisao"].values())
        self.assertEqual(soma, len(self.rel["servicos"]))

    def test_replicas_necessarias_sao_coerentes(self):
        for a in self.rel["servicos"].values():
            esperado = -(-a["alvo_operacional_rps"] // a["rps_por_replica"])
            self.assertEqual(a["replicas_necessarias_no_alvo"], int(esperado))


if __name__ == "__main__":
    unittest.main()

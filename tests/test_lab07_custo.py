"""Lab-07: modelo de custo, alocacao por tag, desperdicio e projecao."""

import unittest

from _carga import caminho_lab, carregar_module

cm = carregar_module("lab07_cost_model", caminho_lab(
    "lab-07-finops", "cost_model.py"))
CSV = caminho_lab("lab-07-finops", "data", "cost-lines.csv")


def linha(period="2026-09", service="svc", env="prod", team="time", comp="compute",
          custo=100.0, util=50.0, rid="r"):
    return {"period": period, "service": service, "environment": env,
            "team": team, "component": comp, "resource_id": rid,
            "custo": custo, "usage_units": 1.0, "util": util}


class TestAgregacao(unittest.TestCase):
    def test_custo_por_componente_soma_e_participacao(self):
        l = [linha(comp="compute", custo=60.0), linha(comp="storage", custo=40.0)]
        r = cm.custo_por_componente(l)
        self.assertEqual(r["total_usd"], 100.0)
        self.assertEqual(r["itens"][0]["componente"], "compute")
        self.assertAlmostEqual(r["itens"][0]["participacao_pct"], 60.0, places=6)
        self.assertAlmostEqual(sum(i["participacao_pct"] for i in r["itens"]),
                               100.0, places=6)

    def test_alocacao_por_tag_nao_perde_custo(self):
        l = [linha(team="a", custo=10.0), linha(team="a", custo=15.0),
             linha(team="b", custo=25.0)]
        r = cm.alocacao_por_tag(l, "team")
        self.assertEqual(r["itens"][0]["valor"], "a")
        self.assertEqual(r["itens"][0]["custo_usd"], 25.0)
        self.assertAlmostEqual(sum(i["custo_usd"] for i in r["itens"]),
                               r["total_usd"], places=6)


class TestDesperdicio(unittest.TestCase):
    def test_recurso_zero_usoconta_como_ociosidade_total(self):
        r = cm.desperdicio([linha(custo=100.0, util=0.0)])
        self.assertEqual(r["ociosidade_usd"], 100.0)
        self.assertEqual(r["superdimensionamento_usd"], 0.0)

    def test_uso_abaixo_do_alvo_pela_fracao_excedente(self):
        # util 35 com alvo 70 -> excedente de 50% do custo
        r = cm.desperdicio([linha(custo=100.0, util=35.0)])
        self.assertAlmostEqual(r["superdimensionamento_usd"], 50.0, places=6)
        self.assertEqual(r["ociosidade_usd"], 0.0)

    def test_no_alvo_nao_conta_desperdicio(self):
        r = cm.desperdicio([linha(custo=100.0, util=85.0)])
        self.assertEqual(r["desperdicio_usd"], 0.0)
        self.assertEqual(r["top10_perdas"], [])

    def test_ordem_decrescente_de_perda(self):
        r = cm.desperdicio([linha(custo=10.0, util=0.0, rid="pequeno"),
                            linha(custo=900.0, util=1.0, rid="grande")])
        self.assertEqual(r["top10_perdas"][0]["resource_id"], "grande")


class TestProjecao(unittest.TestCase):
    def test_reta_perfeita_proximos_tres_meses(self):
        l = ([linha(period="2026-07", custo=100.0)]
             + [linha(period="2026-08", custo=200.0)]
             + [linha(period="2026-09", custo=300.0)])
        r = cm.projecao_tres_meses(l)
        self.assertAlmostEqual(r["inclinacao_usd_por_mes"], 100.0, places=6)
        self.assertEqual([m["custo_usd"] for m in r["meses"]],
                         [400.0, 500.0, 600.0])
        self.assertEqual(r["proximo_trimestre_usd"], 1500.0)

    def test_historico_preserva_periodos(self):
        r = cm.projecao_tres_meses([linha(period="2026-07", custo=10.0)])
        self.assertEqual([h["period"] for h in r["historico"]], ["2026-07"])


class TestCenarios(unittest.TestCase):
    def test_tres_cenarios_e_conomia_limitada_ao_custo(self):
        l = [linha(comp="compute", custo=100.0, util=10.0, env="dev"),
             linha(comp="storage", custo=100.0, util=90.0),
             linha(comp="network", custo=100.0, util=90.0)]
        r = cm.cenarios_otimizacao(l)
        self.assertEqual(len(r["cenarios"]), 3)
        self.assertEqual(r["custo_base_usd"], 300.0)
        for c in r["cenarios"]:
            self.assertGreaterEqual(c["economia_usd"], 0.0)
            self.assertLessEqual(c["economia_pct"], 100.0)

    def test_prod_ocioso_fora_do_c1(self):
        l = [linha(comp="compute", custo=100.0, util=5.0, env="prod")]
        r = cm.cenarios_otimizacao(l)
        c1 = [c for c in r["cenarios"] if c["cenario"].startswith("C1")][0]
        self.assertEqual(c1["economia_usd"], 0.0)


class TestSerieSintetica(unittest.TestCase):
    def setUp(self):
        self.rel = cm.analisar(CSV)

    def test_periodo_e_o_ultimo_do_csv(self):
        self.assertEqual(self.rel["periodo_analisado"], "2026-09")
        self.assertEqual(self.rel["linhas_totais"], 441)

    def test_componentes_batem_com_o_total(self):
        cc = self.rel["custo_por_componente"]
        soma = round(sum(i["custo_usd"] for i in cc["itens"]), 2)
        self.assertAlmostEqual(soma, cc["total_usd"], places=2)

    def test_tres_tags_de_aallocacao_existem(self):
        for chave in ("alocacao_por_team", "alocacao_por_environment",
                     "alocacao_por_service"):
            self.assertIn(chave, self.rel)
            self.assertGreater(len(self.rel[chave]["itens"]), 0)

    def test_desperdicio_e_um_terco_do_mes_no_maximo(self):
        d = self.rel["desperdicio"]
        self.assertGreater(d["desperdicio_usd"], 0.0)
        self.assertLess(d["desperdicio_pct"], 40.0)

    def test_cenarios_tem_descricao_e_base(self):
        self.assertEqual(len(self.rel["cenarios"]["cenarios"]), 3)
        for c in self.rel["cenarios"]["cenarios"]:
            self.assertTrue(c["descricao"])


if __name__ == "__main__":
    unittest.main()

"""Avaliador do agente: contrato das metricas, vocabulario e determinismo."""

import json
import unittest

from _carga import RAIZ, carregar_module

triage = carregar_module("triage", RAIZ / "agent" / "triage.py")
avaliador = carregar_module("evaluate", RAIZ / "agent" / "evaluate.py")
CASOS = RAIZ / "agent" / "data" / "eval_cases.jsonl"


class TestBanco(unittest.TestCase):
    def test_banco_tem_setenta_e_nove_casos(self):
        casos = avaliador.carregar_casos(CASOS)
        self.assertEqual(len(casos), 79)

    def test_todos_os_casos_tem_campos_de_entrada_e_rotulo(self):
        casos = avaliador.carregar_casos(CASOS)
        obrigatorios = {"id", "text", "alertname", "metadata", "severity",
                        "label_category", "label_runbook", "label_symptom"}
        for c in casos:
            self.assertTrue(obrigatorios.issubset(c.keys()), c.get("id"))

    def test_ids_unicos(self):
        casos = avaliador.carregar_casos(CASOS)
        ids = [c["id"] for c in casos]
        self.assertEqual(len(ids), len(set(ids)))


class TestTriage(unittest.TestCase):
    def test_devolve_apenas_vocabulario_do_banco(self):
        casos = avaliador.carregar_casos(CASOS)[:8]
        for c in casos:
            r = triage.classificar_caso(c)
            self.assertIn(r["categoria"], triage.CATEGORIAS)
            self.assertIn(r["runbook"], triage.RUNBOOKS)
            self.assertEqual(r["runbook"], triage.RUNBOOK_POR_SINTOMA[r["sintoma"]])

    def test_nao_le_os_rotulos_do_caso(self):
        # se o classificador lesse label_*, a saida mudaria ao remove-los
        casos = avaliador.carregar_casos(CASOS)[:12]
        for c in casos:
            limpo = {k: v for k, v in c.items() if not k.startswith("label_")}
            self.assertEqual(triage.classificar_caso(c)["runbook"],
                             triage.classificar_caso(limpo)["runbook"])
            self.assertEqual(triage.classificar_caso(c)["categoria"],
                             triage.classificar_caso(limpo)["categoria"])

    def test_latencia_clara_vira_rb01(self):
        r = triage.classificar("P95LatencyHigh",
                               "p95 da rota em 1,4 s contra alvo de 350 ms")
        self.assertEqual(r["categoria"], "latencia")
        self.assertEqual(r["runbook"], "rb-01-latencia-alta")

    def test_seguranca_sem_sinal_dourado_escala(self):
        r = triage.classificar("NewClusterRoleBinding",
                               "Novo RoleBinding concedendo cluster-admin")
        self.assertEqual(r["categoria"], "seguranca")
        self.assertEqual(r["runbook"], "rb-00-escalada-humana")

    def test_duas_chamadas_iguais_dao_a_mesma_saida(self):
        args = ("ConntrackFull",
                "Tabela conntrack do node com 96% de ocupacao",
                {"cluster": "gke-br-sa2b", "namespace": "finance-core",
                 "service": "ledger-api", "channel": "chat-plantao"})
        self.assertEqual(json.dumps(triage.classificar(*args), sort_keys=True),
                         json.dumps(triage.classificar(*args), sort_keys=True))

    def test_explicabilidade_da_decisao(self):
        r = triage.classificar("ErrorRateHigh",
                               "Taxa de erro HTTP 5xx em 4,2% contra SLO de 1%")
        self.assertTrue(r["motivos"])
        self.assertTrue(any("alertname" in m for m in r["motivos"]))

    def test_vazio_nao_estoura(self):
        r = triage.classificar("", "", None)
        self.assertIn(r["categoria"], triage.CATEGORIAS)


class TestMetricas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.casos = avaliador.carregar_casos(CASOS)
        cls.m = avaliador.avaliar(cls.casos)

    def test_subsete_oito_casos_funciona(self):
        parcial = avaliador.avaliar(self.casos[:8])
        self.assertEqual(parcial["total_de_casos"], 8)
        self.assertEqual(parcial["acertos_categoria"]
                         + parcial["erros_de_categoria"], 8)

    def test_campos_obrigatorios_das_metricas(self):
        for chave in ("total_de_casos", "acuracia_categoria_pct",
                      "correspondencia_runbook_pct", "por_categoria",
                      "confusoes_top3", "erros", "macro_media", "analises"):
            self.assertIn(chave, self.m)

    def test_precisao_recall_f1_por_categoria(self):
        self.assertEqual(sorted(self.m["por_categoria"]),
                         sorted(triage.CATEGORIAS))
        for c, p in self.m["por_categoria"].items():
            for chave in ("precision_pct", "recall_pct", "f1_pct", "support"):
                self.assertIn(chave, p)
            self.assertLessEqual(p["f1_pct"], 100.0)
            self.assertGreaterEqual(p["f1_pct"], 0.0)

    def test_support_soma_setenta_e_nove(self):
        self.assertEqual(sum(p["support"] for p in self.m["por_categoria"].values()),
                         79)

    def test_acuracia_medida_acima_do_piso_de_regressao(self):
        self.assertGreaterEqual(self.m["acuracia_categoria_pct"], 90.0)
        self.assertGreaterEqual(self.m["correspondencia_runbook_pct"], 90.0)

    def test_erros_tem_id_esperado_e_obtido(self):
        for e in self.m["erros"]:
            self.assertTrue({"id", "esperado", "obtido"}.issubset(e.keys()))

    def test_confusoes_no_maximo_tres(self):
        self.assertLessEqual(len(self.m["confusoes_top3"]), 3)
        for c in self.m["confusoes_top3"]:
            self.assertGreaterEqual(c["ocorrencias"], 1)

    def test_analises_tem_ablacao_e_robustez(self):
        ab = self.m["analises"]["ablacao_de_camadas"]
        rb = self.m["analises"]["robustez_a_perturbacao"]
        self.assertIn("completo", ab)
        self.assertIn("so_lexico", ab)
        self.assertIn("ordem_das_palavras_invertida", rb)
        # o completo nunca e pior que uma ablacao em acuracia de categoria
        self.assertGreaterEqual(ab["completo"]["acuracia_categoria_pct"],
                                ab["so_lexico"]["acuracia_categoria_pct"])

    def test_render_do_json_e_estavel(self):
        det = {"execucoes": 2, "identico": True, "sha256_16": "x"}
        a = avaliador.render_metrics(self.m, det)
        b = avaliador.render_metrics(self.m, det)
        self.assertEqual(a, b)
        json.loads(a)  # precisa continuar sendo JSON valido

    def test_render_do_report_traz_as_tabelas(self):
        texto = avaliador.render_report(self.m)
        for trecho in ("acuracia de categoria", "correspondencia de runbook",
                       "Tres confusoes mais frequentes", "Ablacao de camadas",
                       "Robustez a perturbacao"):
            self.assertIn(trecho, texto)


class TestDeterminismo(unittest.TestCase):
    def test_duas_execucoes_identicas(self):
        casos = avaliador.carregar_casos(CASOS)
        d = avaliador.verificar_determinismo(casos)
        self.assertTrue(d["identico"])
        self.assertEqual(len(d["sha256_16"]), 16)


if __name__ == "__main__":
    unittest.main()

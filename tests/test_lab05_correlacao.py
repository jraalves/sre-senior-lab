"""Lab-05: correlacao por identificador (request_id, trace_id, span_id)."""

import json
import tempfile
import unittest
from pathlib import Path

from _carga import caminho_lab, carregar_module

cor = carregar_module("lab05_correlate", caminho_lab(
    "lab-05-golden-signals", "correlate.py"))
DATA_REAL = caminho_lab("lab-05-golden-signals", "data")

RID_A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RID_B = "11111111-2222-3333-4444-555555555555"
TRAACO_A = "ab" * 16
SPAN_A = "cd" * 8


def _request(rid, trace, span, status=500, dur=1200.0):
    return {"request_id": rid, "trace_id": trace, "span_id": span,
            "service": "payments-api", "route": "POST /v1/charge",
            "status": status, "duration_ms": dur, "self_ms": dur * 0.3,
            "dependency_ms": dur * 0.7, "cache_hit": False,
            "concurrency": 4, "concurrency_limit": 10,
            "ts": "2026-10-01T00:00:00Z", "t": 0.0, "log_level": "ERROR",
            "log_message": "falha no upstream", "span_events": ["connection refused"]}


def _span(trace, span, pai=""):
    return {"traceID": trace, "spanID": span, "parentSpanID": pai,
            "service": "payments-api", "operation": "POST /v1/charge",
            "startTimeUnixNano": 1759277000000000000,
            "durationUnixNano": 1200000000, "status": 2, "tags": {},
            "events": []}


class TestComFixutura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        logs = [
            "2026-10-01 00:00:00.000 INFO [%s] request iniciado rota=POST" % RID_A,
            "2026-10-01 00:00:01.200 ERROR [%s] upstream connection refused" % RID_A,
            "2026-10-01 00:00:02.000 INFO [%s] request concluido status=200" % RID_B,
        ]
        (d / "requests.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in
                    [_request(RID_A, TRAACO_A, SPAN_A),
                     _request(RID_B, "ff" * 16, "99" * 8, 200, 80.0)]),
            encoding="utf-8")
        (d / "spans.jsonl").write_text(
            "".join(json.dumps(s) + "\n" for s in
                    [_span(TRAACO_A, SPAN_A),
                     _span(TRAACO_A, "ee" * 8, SPAN_A)]),
            encoding="utf-8")
        (d / "logs.txt").write_text("\n".join(logs) + "\n", encoding="utf-8")
        cls.dados = cor.carregar_tudo(d)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_resolve_por_request_id(self):
        self.assertEqual(cor.resolver(self.dados, RID_A), [RID_A])

    def test_resolve_por_trace_id_volta_o_request(self):
        self.assertEqual(cor.resolver(self.dados, TRAACO_A), [RID_A])

    def test_resolve_por_texto_do_log(self):
        self.assertEqual(cor.resolver(self.dados, "connection refused"), [RID_A])

    def test_resolve_por_texto_de_span_event(self):
        self.assertIn(RID_A, cor.resolver(self.dados, "refused"))

    def test_termo_desconhecido_devolve_lista_vazia(self):
        self.assertEqual(cor.resolver(self.dados, "zzz-que-nao-existe"), [])

    def test_visao_amarra_metrica_log_e_traco(self):
        v = cor.visao(self.dados, RID_A)
        self.assertEqual(v["trace_id"], TRAACO_A)
        self.assertEqual(v["metrica"]["status"], 500)
        self.assertEqual(len(v["logs"]), 2)
        self.assertEqual(len(v["spans"]), 2)
        self.assertIsInstance(v["veredito"]["classe"], str)
        self.assertTrue(v["veredito"]["classe"])
        self.assertTrue(v["veredito"]["explicacao"])
        self.assertTrue(v["como_continuar"])

    def test_visao_de_request_inexistente_e_none(self):
        self.assertIsNone(cor.visao(self.dados, "0" * 8 + "-0000-0000-0000-000000000000"))


class TestComDadoGerado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados = cor.carregar_tudo(DATA_REAL)

    def test_todo_request_tem_log_correlato(self):
        amostra = self.dados["registros"][:50]
        for r in amostra:
            self.assertIn(r["request_id"], self.dados["logs_por_rid"],
                          "request_id sem linha de log: %s" % r["request_id"])

    def test_trace_de_cada_request_existe_no_arquivo_de_spans(self):
        for r in self.dados["registros"][:50]:
            self.assertIn(r["trace_id"], self.dados["spans_por_trace"])

    def test_summary_bate_com_a_lista_de_registros(self):
        s = cor.summary(self.dados)
        self.assertEqual(s["requisicoes"], len(self.dados["registros"]))
        self.assertEqual(s["tracos"], len(self.dados["spans_por_trace"]))
        self.assertEqual(s["spans"], self.dados["spans_totais"])
        self.assertGreater(s["logs_correlacionaveis_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()

"""Lab-02: burn rate multi-janela contra orcamento de erro."""

import unittest
from datetime import datetime, timedelta, timezone

from _carga import caminho_lab, carregar_module

br = carregar_module("lab02_burnrate", caminho_lab(
    "lab-02-burn-rate-alerting", "burnrate.py"))
CSV = caminho_lab("lab-02-burn-rate-alerting", "data", "burn-rate.csv")


def serie(n, requests, failed, passo=5, inicio=None):
    inicio = inicio or datetime(2026, 10, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        ts = inicio + timedelta(minutes=passo * i)
        out.append({"bucket_start": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "requests": requests, "failed": failed, "_ts": ts})
    return out


class TestJanela(unittest.TestCase):
    def test_notacoes_conhecidas(self):
        self.assertEqual(br.janela_min("5m"), 5)
        self.assertEqual(br.janela_min("1h"), 60)
        self.assertEqual(br.janela_min("24h"), 1440)
        self.assertEqual(br.janela_min("14d"), 20160)


class TestBurnRate(unittest.TestCase):
    def test_queima_exatamente_no_orcamento(self):
        # alvo 99.9% -> tolerancia 0,1%. serie com 0,1% de erro -> burn 1.0
        s = serie(20, 1000, 1)
        self.assertAlmostEqual(br.burn_rate(s, 60, 19, 5, 0.999), 1.0, places=6)

    def test_dez_vezes_o_orcamento(self):
        s = serie(20, 1000, 10)
        self.assertAlmostEqual(br.burn_rate(s, 60, 19, 5, 0.999), 10.0, places=6)

    def test_janela_incompleta_devolve_none(self):
        # 60 min de janela = 12 buckets; indice 5 nao tem serie suficiente.
        s = serie(20, 1000, 10)
        self.assertIsNone(br.burn_rate(s, 60, 5, 5, 0.999))

    def test_janela_menor_que_o_bucket_estoura(self):
        s = serie(10, 1000, 1)
        with self.assertRaises(ValueError):
            br.burn_rate(s, 1, 9, 5, 0.999)

    def test_minutos_em_violacao_conta_buckets(self):
        s = serie(40, 1000, 10)
        m = br.minutos_em_violacao(s, 60, 39, 5, 0.999, 2.0)
        self.assertGreaterEqual(m, 5)


class TestAvaliar(unittest.TestCase):
    def test_matriz_de_regras_aplicada_na_serie_real(self):
        registros = br.carregar(CSV)
        self.assertEqual(len(registros), 4032)
        self.assertEqual(br.intervalo_min(registros), 5)
        r = br.avaliar(registros, alvo=0.999)
        # a matriz de 99.9% tem seis regras (fast/warn/slow em duas variantes);
        # o teste trava o contrato, nao o tamanho exato da matriz
        self.assertGreaterEqual(len(r["regras"]), 4)
        # o ultimo bucket da serie sintetica esta dentro de incidente plantado,
        # entao pelo menos a regra lenta precisa enxergar queima acima de 1x.
        queimas = [x["burn_longo"] for x in r["regras"] if x["burn_longo"]]
        self.assertTrue(any(b >= 1.0 for b in queimas))
        for regra in r["regras"]:
            self.assertIn(regra["tier"], ("fast", "warn", "slow"))
            self.assertIsInstance(regra["dispara"], bool)

    def test_alvo_sem_matriz_estoura(self):
        registros = br.carregar(CSV)
        with self.assertRaises(ValueError):
            br.avaliar(registros, alvo=0.5)

    def test_resumo_texto_menciona_pagamento_ou_silencio(self):
        r = br.avaliar(br.carregar(CSV), alvo=0.999)
        texto = br.resumo_texto(r)
        self.assertTrue(("PAGARIA" in texto) or ("NENHUMA REGRA ATIVA" in texto))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Lab 05 - gerador de carga sintetica que mede os quatro golden signals.

Gera N requisicoes contra um servico **sintetico** (nao abre socket, nao toca
rede: o "cliente" e uma funcao que amostra latencia, erro e saturacao de um
modelo deterministico), propaga `X-Request-Id` e `traceparent` em cada request e
escreve tres artefatos correlacionaveis:

  data/requests.jsonl  metrica por request (inclui request_id e trace_id)
  data/logs.txt        linhas de log com o request_id entre colchetes
  data/spans.jsonl     spans em formato simplificado, com request_id nos tags

Uso:
  python3 labs/lab-05-golden-signals/loadgen.py --report
  python3 labs/lab-05-golden-signals/loadgen.py --requests 5000 --rps 12 --seed 9 --out /tmp/carga
  python3 labs/lab-05-golden-signals/loadgen.py --format csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))
sys.path.insert(0, str(LAB_DIR.parent.parent / "tools"))

import metrics  # noqa: E402
from synth import golden_log_lines, golden_requests, golden_span_lines  # noqa: E402

CAMPOS_CSV = ["t", "ts", "request_id", "trace_id", "span_id", "service", "route",
              "status", "duration_ms", "self_ms", "dependency_ms", "cache_hit",
              "concurrency", "concurrency_limit", "log_level", "log_message"]


def traceparent(trace_id, span_id):
    """Header W3C traceparent: versao-traco-span-flags."""
    return "00-%s-%s-01" % (trace_id, span_id)


def escrever_jsonl(caminho, registros):
    with caminho.open("w", encoding="utf-8") as fh:
        for r in registros:
            linha = {k: v for k, v in r.items() if k != "spans"}
            fh.write(json.dumps(linha, sort_keys=True, ensure_ascii=False) + "\n")
    return caminho


def escrever_csv(caminho, registros):
    with caminho.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        writer.writeheader()
        for r in registros:
            writer.writerow({k: r[k] for k in CAMPOS_CSV})
    return caminho


def escrever_spans(caminho, registros):
    with caminho.open("w", encoding="utf-8") as fh:
        for linha in golden_span_lines(registros):
            fh.write(linha + "\n")
    return caminho


def escrever_logs(caminho, registros):
    with caminho.open("w", encoding="utf-8") as fh:
        fh.write("".join(golden_log_lines(registros)))
    return caminho


def exemplos_interestantes(registros, n=3):
    """Um request de cada tipo util para o proximo passo (correlate.py)."""
    saida = []
    erros = [r for r in registros if r["status"] >= 500]
    lentos = sorted(registros, key=lambda r: -r["duration_ms"])[:1]
    if erros:
        saida.append(("primeiro erro 5xx", erros[0]))
    if lentos:
        saida.append(("request mais lento", lentos[0]))
    cache_miss = next((r for r in registros if not r["cache_hit"]), None)
    if cache_miss:
        saida.append(("cache miss", cache_miss))
    return [(rotulo, r["request_id"], r["trace_id"], r["duration_ms"], r["status"])
            for rotulo, r in saida[:n]]


def main(argv=None):
    parser = argparse.ArgumentParser(description="gerador de carga sintetica (lab-05)")
    parser.add_argument("--requests", type=int, default=2400)
    parser.add_argument("--rps", type=float, default=8.0,
                        help="apenas informativo: o modelo amostra t = i/rps")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(LAB_DIR / "data"))
    parser.add_argument("--format", choices=["jsonl", "csv", "both"], default="both")
    parser.add_argument("--window", type=int, default=30,
                        help="segundos por janela de agregacao no relatorio")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    registros = golden_requests(args.seed, args.requests)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    arquivos = []
    if args.format in ("jsonl", "both"):
        arquivos.append(escrever_jsonl(out / "requests.jsonl", registros))
    if args.format == "csv":
        arquivos.append(escrever_csv(out / "requests.csv", registros))
    arquivos.append(escrever_spans(out / "spans.jsonl", registros))
    arquivos.append(escrever_logs(out / "logs.txt", registros))

    gs = metrics.golden_signals(registros)
    series = metrics.dividir_por_janela(registros, args.window)
    pico = metrics.pico_e_queda(series)
    cabecalho = {"X-Request-Id": registros[0]["request_id"],
                 "traceparent": traceparent(registros[0]["trace_id"], registros[0]["span_id"])}

    if args.json:
        print(json.dumps({"sintetico": True, "seed": args.seed,
                          "arquivos": [str(a) for a in arquivos],
                          "golden_signals": gs, "pico": pico,
                          "cabecalho_propagado_exemplo": cabecalho},
                         indent=2, sort_keys=True))
        return 0

    print("lab-05 | carga sintetica e golden signals | dados sintetico")
    print("=" * 66)
    print("arquivos gerados:")
    for a in arquivos:
        print("  %s (%d bytes)" % (a, a.stat().st_size))
    print("")
    print(metrics.formatar(gs))
    print("")
    print("evolucao em janelas de %d s (latencia p95 | erro%% | saturacao max):" % args.window)
    for s in series:
        barra = "#" * max(1, int(s["latencia_ms"]["p95"] / 40))
        print("  t=%4ds  %8.1f  %-28s erro %.2f%%  sat %3.0f%%" % (
            s["janela"]["t_inicio"], s["latencia_ms"]["p95"], barra,
            s["erro"]["taxa_pct"], (s["saturacao"]["max"] or 0) * 100))
    print("")
    if pico:
        print("pico detectado: t=%ds p95=%.1f ms (mediana %.1f ms), erro na janela %.2f%%, "
              "normalizacao em %s s" % (
                  pico["pior_janela_t"], pico["pior_p95"], pico["mediana_p95"],
                  pico["taxa_de_erro_na_pior_janela_pct"],
                  pico["segundos_ate_registrar_normalizacao"]))
    print("")
    print("headers propagados no primeiro request (o mesmo par vale para todos):")
    print("  X-Request-Id: %s" % cabecalho["X-Request-Id"])
    print("  traceparent : %s" % cabecalho["traceparent"])
    print("")
    print("para investigar agora mesmo:")
    for rotulo, rid, tid, dur, status in exemplos_interestantes(registros):
        print("  %-22s request_id=%s trace_id=%s %.1f ms status=%d" % (
            rotulo, rid, tid, dur, status))
        print("    python3 labs/lab-05-golden-signals/correlate.py --request-id %s" % rid)
    print("")
    print("Nada neste lab abre socket nem fala com servico real de terceiros.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

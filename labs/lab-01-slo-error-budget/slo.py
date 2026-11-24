#!/usr/bin/env python3
"""Lab 01 - SLI de disponibilidade e latencia, error budget e decisao de release.

Le um CSV de sinais agregado por bucket (requests, failed, fast, slow) e
calcula, sem nenhuma biblioteca externa:

  - SLI de disponibilidade = requisicoes validas / requisicoes totais
  - SLI de latencia        = requisicoes dentro do alvo / requisicoes totais
  - error budget consumido por dia e por semana, em % do orcamento da janela
  - projecao do ritmo observado para a janela inteira e decisao de release

Uso:
  python3 labs/lab-01-slo-error-budget/slo.py --report
  python3 labs/lab-01-slo-error-budget/slo.py --json
  python3 labs/lab-01-slo-error-budget/slo.py --target-availability 0.995
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR.parent.parent / "tools"))

import data_defs  # noqa: E402

ALVO_DISPONIBILIDADE = data_defs.SLO_TARGET_DISPONIBILIDADE
ALVO_LATENCIA = data_defs.SLO_TARGET_LATENCIA
DIAS_JANELA = 30  # janela classica de 30 dias para orcamento de erro


def carregar(csv_path):
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _parse_ts(valor):
    return datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def sli_total(registros):
    """SLI agregado da serie inteira."""
    total = sum(int(r["requests"]) for r in registros)
    invalidas = sum(int(r["failed"]) for r in registros)
    lentas = sum(int(r["slow"]) for r in registros)
    if total == 0:
        raise ValueError("serie sem requisicoes")
    return {
        "requisicoes": total,
        "requisicoes_invalidas": invalidas,
        "requisicoes_lentas": lentas,
        "sli_disponibilidade": (total - invalidas) / total,
        "sli_latencia": (total - lentas) / total,
    }


def _agrupar(registros, chave):
    grupos = defaultdict(lambda: {"requests": 0, "failed": 0, "slow": 0})
    for r in registros:
        k = chave(r)
        grupos[k]["requests"] += int(r["requests"])
        grupos[k]["failed"] += int(r["failed"])
        grupos[k]["slow"] += int(r["slow"])
    return grupos


def _iso_semana(timestamp):
    ano, semana, _ = _parse_ts(timestamp).isocalendar()
    return "%d-W%02d" % (ano, semana)


def consumo_por_dia(registros, alvo_disp=ALVO_DISPONIBILIDADE, alvo_lat=ALVO_LATENCIA):
    """Consumo em % do orcamento diario (janela/30) por dia de calendario."""
    grupos = _agrupar(registros, lambda r: r["timestamp"][:10])
    saida = []
    for dia in sorted(grupos):
        g = grupos[dia]
        orcamento_disp = g["requests"] * (1.0 - alvo_disp)
        orcamento_lat = g["requests"] * (1.0 - alvo_lat)
        saida.append({
            "dia": dia,
            "requisicoes": g["requests"],
            "sli_disponibilidade": (g["requests"] - g["failed"]) / g["requests"],
            "sli_latencia": (g["requests"] - g["slow"]) / g["requests"],
            "consumo_error_budget_pct": round(
                g["failed"] / orcamento_disp * 100.0 if orcamento_disp else 0.0, 1),
            "consumo_orcamento_latencia_pct": round(
                g["slow"] / orcamento_lat * 100.0 if orcamento_lat else 0.0, 1),
        })
    return saida


def consumo_por_semana(registros, alvo_disp=ALVO_DISPONIBILIDADE, alvo_lat=ALVO_LATENCIA):
    grupos = _agrupar(registros, lambda r: _iso_semana(r["timestamp"]))
    saida = []
    for semana in sorted(grupos):
        g = grupos[semana]
        orcamento_disp = g["requests"] * (1.0 - alvo_disp)
        orcamento_lat = g["requests"] * (1.0 - alvo_lat)
        saida.append({
            "semana": semana,
            "requisicoes": g["requests"],
            "sli_disponibilidade": round((g["requests"] - g["failed"]) / g["requests"], 7),
            "consumo_error_budget_pct": round(
                g["failed"] / orcamento_disp * 100.0 if orcamento_disp else 0.0, 1),
            "consumo_orcamento_latencia_pct": round(
                g["slow"] / orcamento_lat * 100.0 if orcamento_lat else 0.0, 1),
        })
    return saida


def decidir(consumo_disp_pct, consumo_lat_pct):
    """Politica explicita de release gate baseada em consumo de orcamento.

    100% = a janela inteira seria consumida no ritmo observado.
    """
    if consumo_disp_pct > 100.0:
        return "BLOQUEAR", (
            "orcamento de disponibilidade projetado em %.1f%% da janela: nada quebra-ciclo "
            "entra sem revisao de SLO e congelamento de mudancas arriscadas" % consumo_disp_pct)
    if consumo_disp_pct > 80.0:
        return "LIBERAR_COM_REVISAO", (
            "sobrou menos de 20%% do orcamento de disponibilidade (%.1f%% consumido): "
            "liberar apenas com revisao de risco" % consumo_disp_pct)
    if consumo_lat_pct > 100.0:
        return "LIBERAR_COM_REVISAO", (
            "disponibilidade saudavel (%.1f%% consumido), mas o orcamento de latencia "
            "estourou (%.1f%%): revisar antes de mexer no caminho de resposta"
            % (consumo_disp_pct, consumo_lat_pct))
    return "LIBERAR", (
        "consumo dentro do esperado (disp %.1f%%, latencia %.1f%% da janela)"
        % (consumo_disp_pct, consumo_lat_pct))


def projecao_e_decisao(registros, alvo_disp=ALVO_DISPONIBILIDADE, alvo_lat=ALVO_LATENCIA,
                       dias_janela=DIAS_JANELA):
    """Extrapola o ritmo observado para a janela inteira e decide o release."""
    total = sum(int(r["requests"]) for r in registros)
    invalidas = sum(int(r["failed"]) for r in registros)
    lentas = sum(int(r["slow"]) for r in registros)
    dias_obs = len({r["timestamp"][:10] for r in registros})
    if dias_obs == 0 or total == 0:
        raise ValueError("serie vazia")
    # orcamento da janela projetado: taxa de tolerancia * trafego esperado na janela
    orcamento_disp = total * (1.0 - alvo_disp) * dias_janela / dias_obs
    orcamento_lat = total * (1.0 - alvo_lat) * dias_janela / dias_obs
    consumo_disp = invalidas / orcamento_disp * 100.0
    consumo_lat = lentas / orcamento_lat * 100.0
    decisao, motivo = decidir(consumo_disp, consumo_lat)
    return {
        "dias_observados": dias_obs,
        "dias_janela": dias_janela,
        "dias_restantes_na_janela": max(dias_janela - dias_obs, 0),
        "requisicoes_janela": total,
        "invalidas_janela": invalidas,
        "lentas_janela": lentas,
        "orcamento_requisicoes_invalidas_janela": int(round(orcamento_disp)),
        "consumo_error_budget_pct": round(consumo_disp, 1),
        "consumo_orcamento_latencia_pct": round(consumo_lat, 1),
        "consumo_diario_medio_pct": round(consumo_disp * dias_obs / dias_janela, 2),
        "caberiam_mais_invalidas": int(round(max(orcamento_disp - invalidas, 0))),
        "taxa_invalidas_por_milhao": round(invalidas / total * 1e6, 1),
        "decisao": decisao,
        "motivo": motivo,
    }


def compute_all(csv_path, alvo_disp=ALVO_DISPONIBILIDADE, alvo_lat=ALVO_LATENCIA,
               dias_janela=DIAS_JANELA):
    registros = carregar(csv_path)
    return {
        "sintetico": True,
        "arquivo": str(csv_path),
        "alvos": {"disponibilidade": alvo_disp, "latencia": alvo_lat,
                  "janela_dias": dias_janela},
        "sli": sli_total(registros),
        "projecao_e_decisao": projecao_e_decisao(registros, alvo_disp, alvo_lat, dias_janela),
        "consumo_por_dia": consumo_por_dia(registros, alvo_disp, alvo_lat),
        "consumo_por_semana": consumo_por_semana(registros, alvo_disp, alvo_lat),
    }


def formatar_piores_dias(dias, topo=8):
    piores = sorted(dias, key=lambda d: d["consumo_error_budget_pct"], reverse=True)[:topo]
    linhas = ["%-11s %11s %11s %11s %13s" % ("dia", "requisicoes", "SLI disp",
                                             "SLI lat", "% orcamento"),
              "-" * 62]
    for d in piores:
        linhas.append("%-11s %11d %10.5f%% %10.5f%% %12.1f%%" % (
            d["dia"], d["requisicoes"], d["sli_disponibilidade"] * 100.0,
            d["sli_latencia"] * 100.0, d["consumo_error_budget_pct"]))
    return "\n".join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SLI e error budget (lab-01)")
    parser.add_argument("--data", default=str(LAB_DIR / "data/slo-signals.csv"))
    parser.add_argument("--target-availability", type=float, default=ALVO_DISPONIBILIDADE)
    parser.add_argument("--target-latency", type=float, default=ALVO_LATENCIA)
    parser.add_argument("--window-days", type=int, default=DIAS_JANELA)
    parser.add_argument("--top", type=int, default=8, help="quantos piores dias exibir")
    parser.add_argument("--json", action="store_true", help="saida em JSON")
    parser.add_argument("--report", action="store_true", help="saida legivel (padrao)")
    args = parser.parse_args(argv)

    r = compute_all(args.data, args.target_availability, args.target_latency, args.window_days)
    if args.json:
        print(json.dumps(r, indent=2, sort_keys=True))
        return 0

    sli, proj = r["sli"], r["projecao_e_decisao"]
    print("lab-01 | SLI, error budget e decisao de release | dados sinteticos")
    print("-" * 62)
    print("arquivo             : %s" % r["arquivo"])
    print("dias observados     : %d (janela de %d dias)" % (proj["dias_observados"], args.window_days))
    print("requisicoes totais  : %d" % sli["requisicoes"])
    print("invalidas           : %d (%.1f por milhao)" % (
        sli["requisicoes_invalidas"], proj["taxa_invalidas_por_milhao"]))
    print("acima do alvo       : %d" % sli["requisicoes_lentas"])
    print("SLI disponibilidade : %.5f%% (alvo %.3f%%)" % (
        sli["sli_disponibilidade"] * 100.0, args.target_availability * 100.0))
    print("SLI latencia        : %.5f%% (alvo %.3f%%)" % (
        sli["sli_latencia"] * 100.0, args.target_latency * 100.0))
    print("")
    print("orcamento da janela : %d requisicoes invalidas" % proj["orcamento_requisicoes_invalidas_janela"])
    print("consumo projetado   : disponibilidade %.1f%% | latencia %.1f%%" % (
        proj["consumo_error_budget_pct"], proj["consumo_orcamento_latencia_pct"]))
    print("ritmo diario medio  : %.2f%% do orcamento da janela" % proj["consumo_diario_medio_pct"])
    print("ainda caberiam      : %d requisicoes invalidas" % proj["caberiam_mais_invalidas"])
    print("")
    print("DECISAO DE RELEASE  : %s" % proj["decisao"])
    print("motivo              : %s" % proj["motivo"])
    print("")
    print("piores dias:")
    print(formatar_piores_dias(r["consumo_por_dia"], args.top))
    print("")
    print("por semana:")
    for s in r["consumo_por_semana"]:
        print("  %s  disp=%.5f%%  orcamento=%.1f%%  latencia=%.1f%%" % (
            s["semana"], s["sli_disponibilidade"] * 100.0,
            s["consumo_error_budget_pct"], s["consumo_orcamento_latencia_pct"]))
    print("")
    print("Nada aqui veio de producao. Regras PromQL equivalentes em prometheus/slo_rules.yml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

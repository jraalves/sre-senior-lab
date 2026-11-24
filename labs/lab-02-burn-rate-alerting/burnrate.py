#!/usr/bin/env python3
"""Lab 02 - burn rate multi-janela e multi-burn-rate (Google SRE capitulo 5).

Dado um CSV de buckets igualmente espacados com colunas
bucket_start, service, requests, failed, este script calcula o burn rate
(short window e long window) de cada regra da matriz e diz quais alertas
disparariam naquele ponto da serie.

O burn rate e adimensional: quantas vezes mais rapido que o normal o
error budget esta sendo consumido.

  burn = (fracao_invalida_janela) / (1 - alvo)

Sem dependencias de terceiros. Uso:
  python3 labs/lab-02-burn-rate-alerting/burnrate.py --report
  python3 labs/lab-02-burn-rate-alerting/burnrate.py --json --at 2026-10-02T12:00:00Z
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
MINUTOS = {"5m": 5, "10m": 10, "15m": 15, "30m": 30, "1h": 60, "2h": 120,
           "6h": 360, "24h": 1440, "30d": 43200}
DIAS_14_MIN = 14 * 24 * 60  # 20160 minutos; 14d so existe como notacao PromQL


def janela_min(notacao):
    return DIAS_14_MIN if notacao == "14d" else MINUTOS[notacao]


# Matriz de alertas. Cada regra: tier (fast/warn/slow), severidade esperada,
# limite do long window, janela curta, janela longa, minimo instantaneo e
# comentario do porque existe. Alvo em notacao curta (99.9 = 0.999).
RULES = {
    "99.9": [
        {"tier": "fast", "severity": "page", "short": "5m", "long": "1h",
         "limite": 14.4, "minimo": 14.4,
         "nota": "consome 2 dias de orcamento em 1 hora"},
        {"tier": "warn", "severity": "page", "short": "30m", "long": "6h",
         "limite": 6.0, "minimo": 6.0,
         "nota": "consome 1 dia e meio de orcamento em 6 horas"},
        {"tier": "slow", "severity": "ticket", "short": "2h", "long": "24h",
         "limite": 6.0, "minimo": 3.0,
         "nota": "queima lenta relevante, abre ticket e nao acorda ninguem"},
        {"tier": "slow", "severity": "page", "short": "2h", "long": "14d",
         "limite": 1.0, "minimo": 2.0,
         "nota": "orcamento do periodo inteiro esta se esgotando"},
        {"tier": "slow", "severity": "page", "short": "30m", "long": "14d",
         "limite": 1.0, "minimo": 1.0,
         "nota": "variacao de 14d com confirmacao rapida"},
        {"tier": "slow", "severity": "ticket", "short": "30m", "long": "14d",
         "limite": 6.0, "minimo": 3.0,
         "nota": "queima moderada sustentada ao longo do periodo"},
    ],
    "99.95": [
        {"tier": "fast", "severity": "page", "short": "5m", "long": "1h",
         "limite": 11.1, "minimo": 11.1, "nota": "queima rapida de 99.95"},
        {"tier": "warn", "severity": "page", "short": "30m", "long": "6h",
         "limite": 5.0, "minimo": 5.0, "nota": "queima intermediaria de 99.95"},
        {"tier": "slow", "severity": "ticket", "short": "2h", "long": "24h",
         "limite": 5.0, "minimo": 2.5, "nota": "queima lenta de 99.95"},
        {"tier": "slow", "severity": "page", "short": "2h", "long": "14d",
         "limite": 1.0, "minimo": 1.5, "nota": "orcamento do periodo acabando"},
    ],
    "99.99": [
        {"tier": "fast", "severity": "page", "short": "5m", "long": "1h",
         "limite": 11.1, "minimo": 11.1, "nota": "queima rapida de 99.99"},
        {"tier": "warn", "severity": "page", "short": "30m", "long": "6h",
         "limite": 3.0, "minimo": 3.0, "nota": "queima intermediaria de 99.99"},
        {"tier": "slow", "severity": "ticket", "short": "2h", "long": "24h",
         "limite": 3.0, "minimo": 1.5, "nota": "queima lenta de 99.99"},
        {"tier": "slow", "severity": "page", "short": "2h", "long": "14d",
         "limite": 1.0, "minimo": 1.5, "nota": "orcamento do periodo acabando"},
    ],
}


def carregar(csv_path):
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        linhas = list(csv.DictReader(fh))
    for linha in linhas:
        linha["requests"] = int(linha["requests"])
        linha["failed"] = int(linha["failed"])
        linha["_ts"] = datetime.strptime(linha["bucket_start"],
                                         "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    linhas.sort(key=lambda r: r["_ts"])
    return linhas


def intervalo_min(registros):
    """Espacamento entre buckets, medido na propria serie."""
    if len(registros) < 2:
        return 1
    delta = (registros[1]["_ts"] - registros[0]["_ts"]).total_seconds() / 60.0
    return int(round(delta))


def burn_rate(registros, minutos, indice, passo_min, alvo):
    """Burn rate da janela que termina em `indice` (inclusivo).

    Retorna None quando a janela ainda nao tem dados suficientes: sem isso o
    alerta dispararia no comeco da serie por artefato de janela incompleta.
    """
    buckets = int(round(minutos / passo_min))
    if buckets < 1:
        raise ValueError("janela %s menor que o intervalo dos buckets" % minutos)
    inicio = indice - buckets + 1
    if inicio < 0:
        return None
    janela = registros[inicio:indice + 1]
    total = sum(r["requests"] for r in janela)
    if total == 0:
        return None
    invalidas = sum(r["failed"] for r in janela)
    tolerancia = 1.0 - alvo
    return (invalidas / total) / tolerancia


def minutos_em_violacao(registros, minutos, indice, passo_min, alvo, limite):
    """Quantos buckets consecutivos a janela longa ja esta acima do limite."""
    cont = 0
    i = indice
    while i >= 0:
        b = burn_rate(registros, minutos, i, passo_min, alvo)
        if b is None or b < limite:
            break
        cont += 1
        i -= 1
    return cont * passo_min


def avaliar(registros, alvo=0.999, indice=None, passo_min=None):
    """Aplica todas as regras da matriz no ponto indicado da serie."""
    passo = passo_min or intervalo_min(registros)
    idx = len(registros) - 1 if indice is None else indice
    chave = "%.5f" % alvo
    nome_alvo = chave.rstrip("0").rstrip(".") if "." in chave else chave
    regras = RULES.get(chave) or RULES.get(_notacao_alvo(alvo))
    if regras is None:
        raise ValueError("sem regras para o alvo %s (use 99.9, 99.95 ou 99.99)" % alvo)
    saida = []
    for regra in regras:
        b_curto = burn_rate(registros, janela_min(regra["short"]), idx, passo, alvo)
        b_longo = burn_rate(registros, janela_min(regra["long"]), idx, passo, alvo)
        dispara = (b_longo is not None and b_curto is not None
                   and b_longo >= regra["limite"] and b_curto >= regra["minimo"])
        saida.append({
            "tier": regra["tier"],
            "severity": regra["severity"],
            "janela_curta": regra["short"],
            "janela_longa": regra["long"],
            "limite": regra["limite"],
            "minimo_instantaneo": regra["minimo"],
            "burn_curto": None if b_curto is None else round(b_curto, 3),
            "burn_longo": None if b_longo is None else round(b_longo, 3),
            "dispara": bool(dispara),
            "minutos_em_violacao": minutos_em_violacao(
                registros, janela_min(regra["long"]), idx, passo, alvo, regra["limite"]),
            "nota": regra["nota"],
        })
    return {"indice": idx, "instante": registros[idx]["bucket_start"],
            "alvo": alvo, "passo_min": passo, "regras": saida}


def _notacao_alvo(alvo):
    return {0.999: "99.9", 0.9995: "99.95", 0.9999: "99.99"}.get(round(alvo, 5), None)


def varredura(registros, alvo=0.999, passo_saida=12):
    """Percorre a serie e mostra em que ponto cada alerta fica ativo.

    passo_saida em buckets: com granulos de 5 minutos, 12 = a cada hora.
    """
    passo = intervalo_min(registros)
    linhas = []
    for idx in range(0, len(registros), passo_saida):
        resultado = avaliar(registros, alvo, idx, passo)
        ativos = [r for r in resultado["regras"] if r["dispara"]]
        linhas.append({
            "instante": registros[idx]["bucket_start"],
            "bucket": idx,
            "ativos": ["%s/%s %s %.2fx" % (r["janela_curta"], r["janela_longa"],
                                           r["tier"], r["burn_longo"]) for r in ativos],
            "max_burn_longo": max([r["burn_longo"] for r in resultado["regras"]
                                   if r["burn_longo"] is not None] or [0.0]),
        })
    return linhas


def formatar(resultado):
    linhas = [
        "burn rate no instante %s (alvo %.3f%%, buckets de %d min)" % (
            resultado["instante"], resultado["alvo"] * 100.0, resultado["passo_min"]),
        "%-6s %-8s %-6s %-7s %8s %8s %8s %9s  %s" % (
            "tier", "sev", "curta", "longa", "limite", "burn L", "burn S", "ativa", "obs"),
        "-" * 100,
    ]
    for r in resultado["regras"]:
        linhas.append("%-6s %-8s %-6s %-7s %8.2f %8s %8s %9s  %s" % (
            r["tier"], r["severity"], r["janela_curta"], r["janela_longa"], r["limite"],
            "-" if r["burn_longo"] is None else "%.3f" % r["burn_longo"],
            "-" if r["burn_curto"] is None else "%.3f" % r["burn_curto"],
            "SIM" if r["dispara"] else "nao",
            "%d min em violacao" % r["minutos_em_violacao"] if r["minutos_em_violacao"] else r["nota"],
        ))
    return "\n".join(linhas)


def resumo_texto(resultado):
    """Conclusao legivel: o que pagaria, o que viraria ticket, o que fica quieto."""
    paginas = [r for r in resultado["regras"] if r["dispara"] and r["severity"] == "page"]
    tickets = [r for r in resultado["regras"] if r["dispara"] and r["severity"] == "ticket"]
    silenciosos = [r for r in resultado["regras"] if not r["dispara"]]
    partes = []
    if paginas:
        partes.append("PAGARIA: " + ", ".join(
            "%s/%s (%.2fx >= %.2f)" % (r["janela_curta"], r["janela_longa"],
                                       r["burn_longo"], r["limite"]) for r in paginas))
    if tickets:
        partes.append("TICKET: " + ", ".join(
            "%s/%s (%.2fx >= %.2f)" % (r["janela_curta"], r["janela_longa"],
                                       r["burn_longo"], r["limite"]) for r in tickets))
    if silenciosos:
        partes.append("NAO DISPARARIA (%d de %d regras): %s" % (
            len(silenciosos), len(resultado["regras"]),
            ", ".join("%s/%s %.2fx" % (r["janela_curta"], r["janela_longa"],
                                       r["burn_longo"] if r["burn_longo"] is not None else 0.0)
                      for r in silenciosos)))
    if not paginas and not tickets:
        partes.append("NENHUMA REGRA ATIVA - queima dentro do orcamento")
    return "\n".join(partes)


def main(argv=None):
    parser = argparse.ArgumentParser(description="burn rate multi-janela (lab-02)")
    parser.add_argument("--data", default=str(LAB_DIR / "data/burn-rate.csv"))
    parser.add_argument("--slo", type=float, default=0.999,
                        help="alvo de disponibilidade (0.999, 0.9995, 0.9999)")
    parser.add_argument("--at", default=None,
                        help="timestamp ISO do bucket ate o qual avaliar")
    parser.add_argument("--bucket", type=int, default=None, help="indice do bucket")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--sweep", action="store_true",
                        help="varre a serie mostrando quando cada alerta fica ativo")
    args = parser.parse_args(argv)

    registros = carregar(args.data)
    indice = args.bucket
    if args.at and indice is None:
        alvo_ts = datetime.strptime(args.at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        candidatos = [i for i, r in enumerate(registros) if r["_ts"] <= alvo_ts]
        indice = candidatos[-1] if candidatos else 0

    resultado = avaliar(registros, args.slo, indice)
    if args.json:
        print(json.dumps(resultado, indent=2, sort_keys=True))
        return 0

    print(formatar(resultado))
    print("")
    print(resumo_texto(resultado))
    if args.sweep or args.report:
        print("")
        print("varredura da serie (a cada %d buckets):" % 12)
        print("%-22s %9s %8s  %s" % ("instante", "bucket", "max burn", "alertas ativos"))
        print("-" * 96)
        for linha in varredura(registros, args.slo):
            print("%-22s %9d %8.2f  %s" % (
                linha["instante"], linha["bucket"], linha["max_burn_longo"],
                ", ".join(linha["ativos"]) or "-"))
    if not args.report:
        print("")
        print("(use --report para a varredura temporal, --json para saida em maquina)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

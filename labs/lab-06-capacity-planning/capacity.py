#!/usr/bin/env python3
"""Lab-06: planejamento de capacidade por extrapolacao de tendencia.

Le `data/capacity.csv` (100% sintetico, gerado por `tools/synth.py`) e devolve,
para cada servico:
  - reta de tendencia semanal por minimos quadrados escritos a mao (stdlib
    puro: a formula e o ponto do exercicio, entao ela aparece no codigo)
  - R^2, para dizer se a reta explica alguma coisa
  - semana projetada de saturacao (quando a carga estimada toca o alvo
    operacional = saturation_rps * ALVO_UTILIZACAO)
  - replicas necessarias no ponto de saturacao
  - decisao: expandir | observar | reduzir

Politica de decisao (documentada, ajustavel por CLI):
  LEAD_TIME_SEMANAS (6) e o intervalo entre pedir capacidade e ela estar no ar.
  MARGEM_OBSERVACAO (8) e a folga alem do lead time em que ainda so monitorar.
  Se a saturacao chega antes do lead time, nao ha o que observar: expandir.
  Se a tendencia e de queda e o CPU p95 esta baixo, a decisao correta e
  reduzir: ai o problema que sobra e custo.

Uso:
  python3 labs/lab-06-capacity-planning/capacity.py --report
  python3 labs/lab-06-capacity-planning/capacity.py --json
  python3 labs/lab-06-capacity-planning/capacity.py --service payments-api
"""

import argparse
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
CSV_PADRAO = LAB_DIR / "data" / "capacity.csv"

LEAD_TIME_SEMANAS = 6      # semanas entre solicitar e receber capacidade
MARGEM_OBSERVACAO = 8      # folga alem do lead time para apenas monitorar
ALVO_UTILIZACAO = 0.75     # nao se projeta ate 100% da saturacao
CORTE_QUEDA = -0.5         # rps/semana abaixo disso e tendencia de queda
UTIL_BAIXA = 35.0          # CPU p95 (%) que caracteriza recurso ocioso


def minimos_quadrados(xs, ys):
    """Retorna (intercepto, inclinacao) da reta y = a + b*x.

    Deducao explicita, minimizando a soma dos quadrados dos residuos:
        b = Sxy / Sxx   com Sxy = sum((xi-xb)(yi-yb)) e Sxx = sum((xi-xb)^2)
        a = yb - b*xb
    Sxx == 0 (serie de um ponto ou xs identicos) devolve inclinacao zero:
    sem variacao em x nao ha tendencia a projetar.
    """
    n = len(xs)
    if n == 0:
        raise ValueError("serie vazia")
    if n == 1:
        return float(ys[0]), 0.0
    xb = sum(xs) / n
    yb = sum(ys) / n
    sxy = sum((x - xb) * (y - yb) for x, y in zip(xs, ys))
    sxx = sum((x - xb) ** 2 for x in xs)
    if sxx == 0:
        return yb, 0.0
    b = sxy / sxx
    return yb - b * xb, b


def r_quadrado(xs, ys, a, b):
    """R^2 = 1 - SSres/SSTot. Defensivo para serie perfeitamente constante."""
    media = sum(ys) / len(ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - media) ** 2 for y in ys)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return 1.0 - ss_res / ss_tot


def projetar(a, b, semana):
    """Valor da reta em `semana`."""
    return a + b * semana


def carregar(caminho):
    """Le o CSV e agrupa por servico, ordenado por semana."""
    with Path(caminho).open(newline="", encoding="utf-8") as fh:
        linhas = list(csv.DictReader(fh))
    por_servico = {}
    for r in linhas:
        por_servico.setdefault(r["service"], []).append({
            "semana": int(r["week_index"]),
            "inicio": r["week_start"],
            "rps": float(r["rps"]),
            "cpu_p95_pct": float(r["cpu_p95_pct"]),
            "fila": float(r["queue_depth"]),
            "saturacao_rps": float(r["saturation_rps"]),
            "rps_por_replica": float(r["rps_per_replica"]),
        })
    for pontos in por_servico.values():
        pontos.sort(key=lambda p: p["semana"])
    return por_servico


def data_da_semana(pontos, semana):
    """Converte indice de semana em data (a serie avanca de 7 em 7 dias)."""
    if not pontos:
        return None
    primeira = datetime.strptime(pontos[0]["inicio"], "%Y-%m-%d").date()
    return (primeira + timedelta(days=7 * int(round(semana - pontos[0]["semana"])))) \
        .isoformat()


def ajustar(pontos):
    """Ajuste de tendencia + derivacoes de capacidade para um servico."""
    xs = [p["semana"] for p in pontos]
    ys = [p["rps"] for p in pontos]
    a, b = minimos_quadrados(xs, ys)
    ultimo = pontos[-1]
    carga = ys[-1]
    duro = ultimo["saturacao_rps"]
    alvo = duro * ALVO_UTILIZACAO
    por_replica = ultimo["rps_por_replica"]

    def semanas_ate(nivel):
        if b <= 0:
            return None
        d = (nivel - carga) / b
        # Carga ja passou do nivel: distancia zero. Devolver None aqui era o
        # bug que transformava "estou acima do alvo operacional" em "observar".
        return 0.0 if d < 0 else round(d, 1)

    s_alvo = semanas_ate(alvo)
    s_duro = semanas_ate(duro)
    replicas_alvo = int(-(-alvo / por_replica // 1))
    return {
        "intercepto": round(a, 3),
        "inclinacao_rps_por_semana": round(b, 3),
        "r_quadrado": round(r_quadrado(xs, ys, a, b), 4),
        "semana_final": ultimo["semana"],
        "rps_ultimo": round(carga, 1),
        "saturacao_rps": duro,
        "alvo_operacional_rps": round(alvo, 1),
        "rps_por_replica": por_replica,
        "semanas_ate_o_alvo": s_alvo,
        "semana_projetada_de_saturacao": (None if s_duro is None
                                         else round(ultimo["semana"] + s_duro, 1)),
        "data_de_saturacao": (None if s_duro is None
                              else data_da_semana(pontos, ultimo["semana"] + s_duro)),
        "prazo_para_pedir": (None if s_duro is None
                             else data_da_semana(pontos,
                                                 ultimo["semana"] + s_duro
                                                 - LEAD_TIME_SEMANAS)),
        "folga_rps": round(duro - carga, 1),
        "replicas_equiv_agora": round(carga / por_replica, 2),
        "replicas_necessarias_no_alvo": replicas_alvo,
        "cpu_p95_ultimo": ultimo["cpu_p95_pct"],
        "fila_ultima": ultimo["fila"],
        "pontos_na_serie": len(pontos),
    }


def decidir(ajuste, lead_time=LEAD_TIME_SEMANAS, margem=MARGEM_OBSERVACAO):
    """expandir | observar | reduzir, com o motivo medido na serie."""
    s_alvo = ajuste["semanas_ate_o_alvo"]
    incl = ajuste["inclinacao_rps_por_semana"]
    if s_alvo is not None and s_alvo <= lead_time:
        return "expandir", (
            "a reta toca o alvo operacional de %.0f rps em %.1f semana(s), dentro "
            "do lead time de %d semanas para provisionar"
            % (ajuste["alvo_operacional_rps"], s_alvo, lead_time))
    if incl <= CORTE_QUEDA and ajuste["cpu_p95_ultimo"] < UTIL_BAIXA:
        return "reduzir", (
            "tendencia de %.2f rps/semana com CPU p95 em %.1f%%: capacidade "
            "sobrando e alguem pagando por ela"
            % (incl, ajuste["cpu_p95_ultimo"]))
    if s_alvo is None:
        return "observar", (
            "inclinacao %.2f rps/semana nao projeta saturacao" % incl)
    if s_alvo <= lead_time + margem:
        return "observar", (
            "alvo operacional em %.1f semanas: passou do lead time (%d) mas esta "
            "dentro da margem de observacao (%d); revisar no proximo ciclo"
            % (s_alvo, lead_time, margem))
    return "observar", (
        "folga de %.1f semanas ate o alvo operacional: nenhuma acao agora" % s_alvo)


def analisar(caminho, lead_time=LEAD_TIME_SEMANAS):
    por_servico = carregar(caminho)
    resultado = {}
    for servico in sorted(por_servico):
        ajuste = ajustar(por_servico[servico])
        acao, motivo = decidir(ajuste, lead_time=lead_time)
        ajuste["decisao"] = acao
        ajuste["motivo"] = motivo
        resultado[servico] = ajuste
    contagem = {}
    for item in resultado.values():
        contagem[item["decisao"]] = contagem.get(item["decisao"], 0) + 1
    return {"servicos": resultado, "contagem_por_decisao": contagem,
            "parametros": {"lead_time_semanas": lead_time,
                           "margem_observacao": MARGEM_OBSERVACAO,
                           "alvo_utilizacao": ALVO_UTILIZACAO,
                           "corte_queda_rps_por_semana": CORTE_QUEDA,
                           "cpu_p95_baixo_pct": UTIL_BAIXA},
            "dados": "sinteticos (tools/synth.py, artefato capacity)"}


def formatar(rel):
    L = ["# Lab-06 - planejamento de capacidade", "",
         "Series sinteticas: 26 semanas por servico (`data/capacity.csv`).", ""]
    L.append("| servico | rps atual | rps/sem | R^2 | sem. ate alvo | sem. saturacao |"
             " data saturacao | prazo p/ pedir | replicas no alvo | decisao |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s, a in rel["servicos"].items():
        L.append("| %s | %.1f | %+.2f | %.3f | %s | %s | %s | %s | %d | **%s** |" % (
            s, a["rps_ultimo"], a["inclinacao_rps_por_semana"], a["r_quadrado"],
            "-" if a["semanas_ate_o_alvo"] is None else "%.1f" % a["semanas_ate_o_alvo"],
            "-" if a["semana_projetada_de_saturacao"] is None
            else "%.1f" % a["semana_projetada_de_saturacao"],
            a["data_de_saturacao"] or "-", a["prazo_para_pedir"] or "-",
            a["replicas_necessarias_no_alvo"], a["decisao"]))
    L.append("")
    for s, a in rel["servicos"].items():
        L.append("- **%s** -> %s: %s" % (s, a["decisao"], a["motivo"]))
    L.append("")
    L.append("Contagem por decisao: %s"
             % json.dumps(rel["contagem_por_decisao"], sort_keys=True))
    L.append("Parametros: %s" % json.dumps(rel["parametros"], sort_keys=True))
    L.append("")
    L.append("Tudo aqui e sintético e nao mede producao alguma: os numeros vem da"
             " execucao deste script sobre dados gerados por `tools/synth.py`.")
    return "\n".join(L)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="projecao de capacidade por minimos quadrados (lab-06)")
    parser.add_argument("--data", default=str(CSV_PADRAO))
    parser.add_argument("--lead-time", type=int, default=LEAD_TIME_SEMANAS,
                        help="semanas para provisionar capacidade")
    parser.add_argument("--service", default=None, help="filtra um servico")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true",
                        help="saida legivel (tambem o padrao)")
    args = parser.parse_args(argv)

    rel = analisar(args.data, lead_time=args.lead_time)
    if args.service:
        if args.service not in rel["servicos"]:
            raise SystemExit("servico desconhecido: %s" % args.service)
        rel = {"servicos": {args.service: rel["servicos"][args.service]},
               "parametros": rel["parametros"], "dados": rel["dados"]}
    if args.json:
        print(json.dumps(rel, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(formatar(rel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

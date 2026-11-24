#!/usr/bin/env python3
"""Lab-07: modelo de custo a partir de linhas de cobranca sinteticas.

Le `data/cost-lines.csv` (441 linhas, 3 periodos, 4 componentes, 12 servicos;
tudo gerado por `tools/synth.py`) e calcula, sem nenhuma dependencia externa:

  1. custo por componente e por periodo
  2. alocacao por tag (team, environment, service) e o que ficou sem dono
  3. desperdicio, separado em duas causas que pedem acoes diferentes:
       - ociosidade: recurso pago e quase nao usado (util < OCIOSIDADE_PCT)
       - superdimensionamento: recurso usado, mas abaixo do alvo operacional
  4. projecao de tres meses por minimos quadrados sobre os totais do periodo
  5. tres cenarios de otimizacao, com economia medida sobre o proprio CSV

Definicoes aritmeticas (o ponto do exercicio e elas serem explicitas):
  fracao_ociosa(linha)   = 1 - utilization_pct/100                  [0..1]
  ociosidade             = sum(custo * fracao_ociosa) p/ util < 25
  excedente(linha)       = max(0, 1 - utilization_pct/70)           [0..1]
  superdimensionamento   = sum(custo * excedente) p/ 25 <= util < 70
  Todos os valores em USD/mes, soma simples das linhas do ultimo periodo, a
  menos que dito o contrario. Nenhum numero aqui vem de fatura real.

Uso:
  python3 labs/lab-07-finops/cost_model.py --report
  python3 labs/lab-07-finops/cost_model.py --json
  python3 labs/lab-07-finops/cost_model.py --tag team
"""

import argparse
import csv
import json
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
CSV_PADRAO = LAB_DIR / "data" / "cost-lines.csv"

OCIOSIDADE_PCT = 25.0   # abaixo disso o recurso esta ocioso
ALVO_UTILIZACAO = 70.0  # alvo operacional de uso de compute
FATOR_SNAPSHOT = 0.30   # cena C3: ciclo de vida reduz 30% do storage
FATOR_EGRESS = 0.15     # cena C3: cache/menor egress reduz 15% da rede


def minimos_quadrados(xs, ys):
    """(intercepto, inclinacao) da reta y = a + b*x, na mao (stdlib)."""
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


def carregar(caminho):
    """Le o CSV convertendo os numericos; mantem a ordem original."""
    with Path(caminho).open(newline="", encoding="utf-8") as fh:
        linhas = []
        for r in csv.DictReader(fh):
            linhas.append({
                "period": r["period"],
                "service": r["service"],
                "environment": r["environment"],
                "team": r["team"],
                "component": r["component"],
                "resource_id": r["resource_id"],
                "custo": float(r["monthly_cost_usd"]),
                "usage_units": float(r["usage_units"]),
                "util": float(r["utilization_pct"]),
            })
    return linhas


def periodo_atual(linhas):
    """Ultimo periodo do CSV: e sobre ele que as acoes sao decididas."""
    return max(l["period"] for l in linhas)


def no_periodo(linhas, periodo):
    return [l for l in linhas if l["period"] == periodo]


def custo_por_componente(linhas, periodo=None):
    """Soma de custo e participacao, ordenada por custo decrescente (estavel)."""
    base = no_periodo(linhas, periodo) if periodo else linhas
    total = sum(l["custo"] for l in base) or 1.0
    acum = {}
    for l in base:
        acum[l["component"]] = acum.get(l["component"], 0.0) + l["custo"]
    return {
        "total_usd": round(total, 2),
        "itens": [
            {"componente": c, "custo_usd": round(v, 2),
             "participacao_pct": round(100.0 * v / total, 2)}
            for c, v in sorted(acum.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def alocacao_por_tag(linhas, tag, periodo=None):
    """Aloca custo por valor de tag. `tag` em {team, environment, service}."""
    campo = {"team": "team", "environment": "environment",
             "service": "service"}[tag]
    base = no_periodo(linhas, periodo) if periodo else linhas
    acum = {}
    for l in base:
        chave = l[campo] or "SEM_TAG"
        acum[chave] = acum.get(chave, 0.0) + l["custo"]
    total = sum(acum.values()) or 1.0
    return {
        "tag": tag,
        "total_usd": round(total, 2),
        "itens": [
            {"valor": k, "custo_usd": round(v, 2),
             "participacao_pct": round(100.0 * v / total, 2)}
            for k, v in sorted(acum.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def desperdicio(linhas, periodo=None):
    """Separa ociosidade de superdimensionamento, com contagem de linhas."""
    base = no_periodo(linhas, periodo) if periodo else linhas
    total = sum(l["custo"] for l in base) or 1.0
    ocio = super_ = 0.0
    n_ocio = n_super = 0
    pior = []
    for l in base:
        if l["util"] < OCIOSIDADE_PCT:
            frac = 1.0 - l["util"] / 100.0
            perda = l["custo"] * frac
            ocio += perda
            n_ocio += 1
            pior.append({"resource_id": l["resource_id"], "team": l["team"],
                         "component": l["component"], "util_pct": l["util"],
                         "custo_usd": round(l["custo"], 2),
                         "causa": "ociosidade", "perda_usd": round(perda, 2)})
        elif l["util"] < ALVO_UTILIZACAO:
            frac = 1.0 - l["util"] / ALVO_UTILIZACAO
            perda = l["custo"] * frac
            super_ += perda
            n_super += 1
            pior.append({"resource_id": l["resource_id"], "team": l["team"],
                         "component": l["component"], "util_pct": l["util"],
                         "custo_usd": round(l["custo"], 2),
                         "causa": "superdimensionamento",
                         "perda_usd": round(perda, 2)})
    pior.sort(key=lambda d: (-d["perda_usd"], d["resource_id"]))
    return {
        "total_custo_usd": round(total, 2),
        "ociosidade_usd": round(ocio, 2),
        "superdimensionamento_usd": round(super_, 2),
        "desperdicio_usd": round(ocio + super_, 2),
        "desperdicio_pct": round(100.0 * (ocio + super_) / total, 2),
        "linhas_ociosas": n_ocio,
        "linhas_superdimensionadas": n_super,
        "top10_perdas": pior[:10],
    }


def projecao_tres_meses(linhas, meses=3):
    """Minimos quadrados sobre o total de cada periodo, extrapola `meses`."""
    tot = {}
    for l in linhas:
        tot[l["period"]] = tot.get(l["period"], 0.0) + l["custo"]
    periodos = sorted(tot)
    xs = list(range(len(periodos)))
    ys = [round(tot[p], 2) for p in periodos]
    a, b = minimos_quadrados(xs, ys)
    projetado = []
    for i in range(1, meses + 1):
        valor = a + b * (len(periodos) - 1 + i)
        projetado.append({"passo": i, "custo_usd": round(valor, 2)})
    return {
        "historico": [{"period": p, "custo_usd": round(tot[p], 2)}
                      for p in periodos],
        "inclinacao_usd_por_mes": round(b, 2),
        "intercepto": round(a, 2),
        "proximo_trimestre_usd": round(sum(x["custo_usd"] for x in projetado), 2),
        "meses": projetado,
        "ultimo_conhecido_usd": ys[-1],
        "variacao_pct_vs_ultimo": round(100.0 * (projetado[0]["custo_usd"] - ys[-1])
                                        / ys[-1], 2) if ys else 0.0,
    }


def cenarios_otimizacao(linhas, periodo=None):
    """Tres cenarios independentes, cada um com conta explicita."""
    base = no_periodo(linhas, periodo) if periodo else linhas
    total = sum(l["custo"] for l in base) or 1.0
    d = desperdicio(base)

    # C1: desligar o que esta ocioso fora de producao (dev/staging). Em prod a
    # ociosidade pode ser folga de resiliencia, entao nao entra aqui.
    ocio_nao_prod = [l for l in base if l["util"] < OCIOSIDADE_PCT
                     and l["environment"] != "prod"]
    c1 = sum(l["custo"] for l in ocio_nao_prod)

    # C2: right-size de compute: leva cada linha abaixo do alvo para o alvo,
    # cortando a parte do preco proporcional ao excedente.
    c2 = sum(l["custo"] * max(0.0, 1.0 - l["util"] / ALVO_UTILIZACAO)
             for l in base if l["component"] == "compute")

    # C3: higiene de plataforma: ciclo de vida de snapshot no storage e menos
    # egress com cache mais bem usado na camada de rede.
    storage = sum(l["custo"] for l in base if l["component"] == "storage")
    rede = sum(l["custo"] for l in base if l["component"] == "network")
    c3 = storage * FATOR_SNAPSHOT + rede * FATOR_EGRESS

    saida = []
    for nome, econ, descricao in [
        ("C1_desligar_ocioso_nao_prod", c1,
         "desligar recursos com uso < %.0f%% em dev/staging; prod fica de fora "
         "porque folga ali pode ser resiliencia" % OCIOSIDADE_PCT),
        ("C2_right_size_compute", c2,
         "redimensionar compute para %.0f%% de uso alvo, cortando o excedente "
         "proporcional (%d linhas ociosas e %d superdimensionadas no mes)"
         % (ALVO_UTILIZACAO, d["linhas_ociosas"],
            d["linhas_superdimensionadas"])),
        ("C3_ciclo_de_vida_e_cache", c3,
         "reter snapshots por menos tempo (-%.0f%% de storage) e servir mais do "
         "cache (-%.0f%% de rede)" % (FATOR_SNAPSHOT * 100, FATOR_EGRESS * 100)),
    ]:
        saida.append({"cenario": nome, "economia_usd": round(econ, 2),
                      "economia_pct": round(100.0 * econ / total, 2),
                      "custo_restante_usd": round(total - econ, 2),
                      "descricao": descricao})
    return {"custo_base_usd": round(total, 2), "cenarios": saida,
            "empilhamento_usd": round(sum(x["economia_usd"] for x in saida), 2),
            "aviso": "os tres cenarios se sobrepoem parcialmente (uma linha "
                     "ociosa aparece em C1 e C2); soma deles e teto, nao objetivo"}


def analisar(caminho, tag="team"):
    linhas = carregar(caminho)
    periodo = periodo_atual(linhas)
    base = no_periodo(linhas, periodo)
    return {
        "periodo_analisado": periodo,
        "linhas_no_periodo": len(base),
        "linhas_totais": len(linhas),
        "custo_por_componente": custo_por_componente(base),
        "alocacao_por_team": alocacao_por_tag(base, "team"),
        "alocacao_por_environment": alocacao_por_tag(base, "environment"),
        "alocacao_por_service": alocacao_por_tag(base, "service"),
        "tag_pedido_para_report": alocacao_por_tag(base, tag),
        "desperdicio": desperdicio(base),
        "projecao_tres_meses": projecao_tres_meses(linhas),
        "cenarios": cenarios_otimizacao(base),
        "dados": "sinteticos (tools/synth.py, artefato cost); precos ficticios",
    }


def formatar(rel):
    L = ["# Lab-07 - modelo de custo (dados sinteticos)", "",
         "Periodo analisado: **%s** (%d linhas de %d no CSV)."
         % (rel["periodo_analisado"], rel["linhas_no_periodo"],
            rel["linhas_totais"]), ""]
    cc = rel["custo_por_componente"]
    L.append("## Custo por componente (USD/mes)")
    L.append("")
    L.append("| componente | custo | participacao |")
    L.append("| --- | --- | --- |")
    for it in cc["itens"]:
        L.append("| %s | %.2f | %.2f%% |"
                 % (it["componente"], it["custo_usd"], it["participacao_pct"]))
    L.append("| **total** | **%.2f** | 100.00%% |" % cc["total_usd"])
    L.append("")
    for chave, titulo in [("alocacao_por_team", "team"),
                          ("alocacao_por_environment", "environment"),
                          ("alocacao_por_service", "service")]:
        a = rel[chave]
        L.append("## Alocacao por tag `%s`" % titulo)
        L.append("")
        L.append("| %s | custo | participacao |" % titulo)
        L.append("| --- | --- | --- |")
        for it in a["itens"]:
            L.append("| %s | %.2f | %.2f%% |"
                     % (it["valor"], it["custo_usd"], it["participacao_pct"]))
        L.append("")
    d = rel["desperdicio"]
    L.append("## Desperdicio")
    L.append("")
    L.append("- ociosidade (util < %.0f%%): %.2f USD em %d linhas"
             % (OCIOSIDADE_PCT, d["ociosidade_usd"], d["linhas_ociosas"]))
    L.append("- superdimensionamento (%.0f%% <= util < %.0f%%): %.2f USD em "
             "%d linhas" % (OCIOSIDADE_PCT, ALVO_UTILIZACAO,
                            d["superdimensionamento_usd"],
                            d["linhas_superdimensionadas"]))
    L.append("- **total: %.2f USD (%.2f%% do custo do mes)**"
             % (d["desperdicio_usd"], d["desperdicio_pct"]))
    L.append("")
    p = rel["projecao_tres_meses"]
    L.append("## Projecao de tres meses")
    L.append("")
    L.append("- historico: %s"
             % ", ".join("%s=%.2f" % (h["period"], h["custo_usd"])
                         for h in p["historico"]))
    L.append("- inclinacao ajustada: %+.2f USD/mes" % p["inclinacao_usd_por_mes"])
    L.append("- proximo trimestre: %.2f USD (%+.2f%% vs ultimo mes conhecido)"
             % (p["proximo_trimestre_usd"], p["variacao_pct_vs_ultimo"]))
    L.append("- meses projetados: %s"
             % ", ".join("%.2f" % m["custo_usd"] for m in p["meses"]))
    L.append("")
    c = rel["cenarios"]
    L.append("## Cenarios de otimizacao (base %.2f USD/mes)" % c["custo_base_usd"])
    L.append("")
    L.append("| cenario | economia | economia % | custo restante |")
    L.append("| --- | --- | --- | --- |")
    for x in c["cenarios"]:
        L.append("| %s | %.2f | %.2f%% | %.2f |"
                 % (x["cenario"], x["economia_usd"], x["economia_pct"],
                    x["custo_restante_usd"]))
    L.append("")
    L.append("Empilhamento bruto: %.2f USD. %s." % (c["empilhamento_usd"],
                                                    c["aviso"]))
    L.append("")
    L.append("Todos os numeros sao sinteticos e foram produzidos por este script"
             " sobre `data/cost-lines.csv`; nenhum valor vem de fatura real.")
    return "\n".join(L)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="modelo de custo finops (lab-07)")
    parser.add_argument("--data", default=str(CSV_PADRAO))
    parser.add_argument("--tag", default="team",
                        choices=["team", "environment", "service"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true",
                        help="saida legivel (tambem o padrao)")
    args = parser.parse_args(argv)

    rel = analisar(args.data, tag=args.tag)
    if args.json:
        print(json.dumps(rel, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(formatar(rel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

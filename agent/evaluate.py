#!/usr/bin/env python3
"""Avaliador do agente de triagem sobre o banco rotulado de 79 casos.

Le `agent/data/eval_cases.jsonl`, roda `triage.classificar_caso` em cada caso e
grava, em `agent/results/`:
  metrics.json  - maquina-legivel, ordenada por chave, sem timestamp
  report.md     - relatorio legivel com as mesmas tabelas

Metricas produzidas (todas medidas, nenhuma inventada):
  - total de casos avaliados
  - acuracia de categoria em %
  - taxa de correspondencia de runbook em %
  - precision / recall / F1 por categoria (macro-media incluida)
  - as tres confusoes de categoria mais frequentes
  - a lista de erros com id, esperado e obtido (categoria e runbook)
  - prova de determinismo: duas execucoes na mesma chamada, hash comparado

Definicoes usadas (documentadas porque vao aparecer em README externo):
  precision_c = acertos da categoria c / vezes que o agente disse c
  recall_c    = acertos da categoria c / vezes que a categoria c era a esperada
  f1_c        = 2*P*R/(P+R), com 0 quando P+R = 0
  confusao    = par (esperado -> obtido) entre os erros de categoria, ordenado
                por ocorrencia decrescente e depois alfabeticamente (estavel)

Uso:
  python3 agent/evaluate.py            # gera agent/results/
  python3 agent/evaluate.py --report   # idem + resumo legivel no stdout
  python3 agent/evaluate.py --check    # nao grava; falha se cair de determinismo
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parent
CASES_PADRAO = AGENT_DIR / "data" / "eval_cases.jsonl"
RESULTS_PADRAO = AGENT_DIR / "results"

import sys
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from triage import (  # noqa: E402
    CATEGORIAS,
    RUNBOOKS,
    TRIAGE_VERSION,
    classificar_caso,
)


def carregar_casos(caminho):
    casos = []
    with open(caminho, "r", encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                casos.append(json.loads(linha))
    return casos


def _pct(numerador, denominador):
    return round(100.0 * numerador / denominador, 2) if denominador else 0.0


def avaliar(casos):
    """Roda o triage em todos os casos e consolida as metricas."""
    executado = [(c, classificar_caso(c)) for c in casos]
    total = len(executado)

    acertos_cat = sum(1 for c, r in executado
                      if r["categoria"] == c["label_category"])
    acertos_rb = sum(1 for c, r in executado
                     if r["runbook"] == c["label_runbook"])

    por_categoria = {}
    confusoes = Counter()
    erros = []
    erros_runbook = []
    for caso, r in executado:
        esperado, obtido = caso["label_category"], r["categoria"]
        if esperado != obtido:
            confusoes[(esperado, obtido)] += 1
            erros.append({
                "id": caso["id"],
                "alertname": caso["alertname"],
                "esperado": esperado,
                "obtido": obtido,
                "esperado_runbook": caso["label_runbook"],
                "obtido_runbook": r["runbook"],
                "confianca": r["confianca"],
            })
        if caso["label_runbook"] != r["runbook"]:
            erros_runbook.append({
                "id": caso["id"],
                "alertname": caso["alertname"],
                "categoria": obtido,
                "esperado": caso["label_runbook"],
                "obtido": r["runbook"],
            })

    for categoria in CATEGORIAS:
        support = sum(1 for c in casos if c["label_category"] == categoria)
        previsto = sum(1 for _, r in executado if r["categoria"] == categoria)
        acerto = sum(1 for c, r in executado
                     if r["categoria"] == categoria
                     and c["label_category"] == categoria)
        prec = _pct(acerto, previsto)
        rec = _pct(acerto, support)
        f1 = round(2 * prec * rec / (prec + rec), 2) if (prec + rec) else 0.0
        por_categoria[categoria] = {
            "support": support,
            "previsto": previsto,
            "verdadeiros_positivos": acerto,
            "precision_pct": prec,
            "recall_pct": rec,
            "f1_pct": f1,
        }

    def _media(campo):
        vals = [por_categoria[c][campo] for c in CATEGORIAS]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    macro = {"precision_pct": _media("precision_pct"),
             "recall_pct": _media("recall_pct"),
             "f1_pct": _media("f1_pct")}

    top_confusoes = [
        {"esperado": e, "obtido": o, "ocorrencias": n}
        for (e, o), n in sorted(confusoes.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:3]

    return {
        "heuristica_version": TRIAGE_VERSION,
        "arquivo_de_casos": "agent/data/eval_cases.jsonl",
        "total_de_casos": total,
        "acuracia_categoria_pct": _pct(acertos_cat, total),
        "correspondencia_runbook_pct": _pct(acertos_rb, total),
        "acertos_categoria": acertos_cat,
        "acertos_runbook": acertos_rb,
        "erros_de_categoria": len(erros),
        "erros_de_runbook": len(erros_runbook),
        "por_categoria": por_categoria,
        "macro_media": macro,
        "confusoes_top3": top_confusoes,
        "distribuicao_prevista": dict(sorted(Counter(
            r["categoria"] for _, r in executado).items())),
        "distribuicao_runbook_prevista": dict(sorted(Counter(
            r["runbook"] for _, r in executado).items())),
        "erros": sorted(erros, key=lambda e: e["id"]),
        "erros_runbook": sorted(erros_runbook, key=lambda e: e["id"]),
        "analises": analises(casos),
        "vocabulario": {"categorias": CATEGORIAS, "runbooks": RUNBOOKS},
    }


def _avaliar_com(casos, ativar=None, perturbar=None):
    """Avalia com subconjunto de regras e/ou perturbacao do texto de entrada.

    Usado pelas analises de ablacao e de robustez. Nao altera o arquivo do
    banco: a perturbacao e aplicada em memoria, de forma deterministica.
    """
    import triage as _tr

    def classificar_perturbado(caso):
        c = dict(caso)
        if perturbar == "alertname_anonimo":
            c["alertname"] = "AlertaGenerico"
        elif perturbar == "sem_metadata":
            c["metadata"] = {}
        elif perturbar == "texto_curto":
            c["text"] = c["text"][:48]
        elif perturbar == "ordem_invertida":
            c["text"] = " ".join(reversed(c["text"].split()))
        return _tr.classificar(c["alertname"], c["text"], c.get("metadata"),
                              ativar=ativar)

    executado = [(c, classificar_perturbado(c)) for c in casos]
    total = len(executado)
    acerto_cat = sum(1 for c, r in executado
                     if r["categoria"] == c["label_category"])
    acerto_rb = sum(1 for c, r in executado
                    if r["runbook"] == c["label_runbook"])
    conf = Counter((c["label_category"], r["categoria"])
                   for c, r in executado
                   if r["categoria"] != c["label_category"])
    top = [{"esperado": e, "obtido": o, "ocorrencias": n}
           for (e, o), n in sorted(conf.items(), key=lambda kv: (-kv[1], kv[0]))][:3]
    erros = [{"id": c["id"], "esperado": c["label_category"],
              "obtido": r["categoria"],
              "esperado_runbook": c["label_runbook"],
              "obtido_runbook": r["runbook"]}
             for c, r in executado
             if r["categoria"] != c["label_category"]
             or r["runbook"] != c["label_runbook"]]
    return {
        "total_de_casos": total,
        "acuracia_categoria_pct": _pct(acerto_cat, total),
        "correspondencia_runbook_pct": _pct(acerto_rb, total),
        "confusoes_top3": top,
        "erros": sorted(erros, key=lambda e: e["id"]),
    }


# Familias de regras de triage.FAMILIAS usadas nas ablacoes. Cada linha desliga
# exatamente uma camada e mantem as demais, entao a queda de acuracia atribui o
# merito a camada certa.
ABLACOES = [
    ("completo", None),
    ("sem_regras_de_fronteira",
     ("lexico", "alertname", "metadata", "numerica", "arbitragem")),
    ("sem_catalogo_de_alertname",
     ("lexico", "metadata", "fronteira", "numerica", "arbitragem")),
    ("sem_metadata",
     ("lexico", "alertname", "fronteira", "numerica", "arbitragem")),
    ("so_lexico", ("lexico",)),
    ("so_lexico_e_numericas", ("lexico", "numerica")),
    ("sem_janela_de_negacao",
     ("lexico", "alertname", "metadata", "fronteira", "numerica")),
]

# Perturbacoes de entrada para estimar generalizacao (o valor intra-amostra do
# banco e 100% por construcao; sem estresse o numero nao diz muito).
PERTURBACOES = [
    ("baseline", None),
    ("alertname_anonimo", "alertname_anonimo"),
    ("metadata_vazia", "sem_metadata"),
    ("texto_truncado_48", "texto_curto"),
    ("ordem_das_palavras_invertida", "ordem_invertida"),
]


def analises(casos):
    ab = {}
    for nome, ativar in ABLACOES:
        if nome == "sem_janela_de_negacao":
            import triage as _tr
            guardado = list(_tr.NEGADORES)
            _tr.NEGADORES[:] = []
            try:
                ab[nome] = _avaliar_com(casos, ativar=None)
            finally:
                _tr.NEGADORES[:] = guardado
        else:
            ab[nome] = _avaliar_com(casos, ativar=ativar)
    rb = {}
    for nome, pert in PERTURBACOES:
        rb[nome] = _avaliar_com(casos, perturbar=pert)
    return {"ablacao_de_camadas": ab, "robustez_a_perturbacao": rb}


def verificar_determinismo(casos):
    """Roda duas vezes e compara a serializacao canonica das saidas."""
    a = json.dumps(avaliar(casos), sort_keys=True, ensure_ascii=False)
    b = json.dumps(avaliar(casos), sort_keys=True, ensure_ascii=False)
    return {
        "execucoes": 2,
        "identico": a == b,
        "sha256_16": hashlib.sha256(a.encode("utf-8")).hexdigest()[:16],
    }


def render_metrics(m, determinismo):
    out = dict(m)
    out["determinismo"] = determinismo
    return json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_report(m):
    L = []
    L.append("# Relatorio de avaliacao do agente de triagem")
    L.append("")
    L.append("Gerado por `python3 agent/evaluate.py`. Heuristica version %s, "
             "banco `agent/data/eval_cases.jsonl`." % m["heuristica_version"])
    L.append("")
    L.append("## Numeros principais")
    L.append("")
    L.append("| metrica | valor |")
    L.append("| --- | --- |")
    L.append("| casos avaliados | %d |" % m["total_de_casos"])
    L.append("| acuracia de categoria | %.2f%% (%d/%d) |"
             % (m["acuracia_categoria_pct"], m["acertos_categoria"],
                m["total_de_casos"]))
    L.append("| correspondencia de runbook | %.2f%% (%d/%d) |"
             % (m["correspondencia_runbook_pct"], m["acertos_runbook"],
                m["total_de_casos"]))
    L.append("| F1 macro (categoria) | %.2f%% |" % m["macro_media"]["f1_pct"])
    L.append("")
    L.append("## Precision / recall / F1 por categoria")
    L.append("")
    L.append("| categoria | support | previsto | precision | recall | F1 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for c in CATEGORIAS:
        p = m["por_categoria"][c]
        L.append("| %s | %d | %d | %.2f%% | %.2f%% | %.2f%% |"
                 % (c, p["support"], p["previsto"], p["precision_pct"],
                    p["recall_pct"], p["f1_pct"]))
    L.append("")
    L.append("## Tres confusoes mais frequentes (categoria)")
    L.append("")
    if m["confusoes_top3"]:
        L.append("| esperado | obtido | ocorrencias |")
        L.append("| --- | --- | --- |")
        for c in m["confusoes_top3"]:
            L.append("| %s | %s | %d |" % (c["esperado"], c["obtido"],
                                           c["ocorrencias"]))
    else:
        L.append("Nenhuma confusao de categoria na execucao.")
    L.append("")
    L.append("## Erros de categoria")
    L.append("")
    if m["erros"]:
        L.append("| id | esperado | obtido | runbook esperado | runbook obtido |")
        L.append("| --- | --- | --- | --- | --- |")
        for e in m["erros"]:
            L.append("| %s | %s | %s | %s | %s |"
                     % (e["id"], e["esperado"], e["obtido"],
                        e["esperado_runbook"], e["obtido_runbook"]))
    else:
        L.append("Nenhum erro de categoria.")
    L.append("")
    L.append("## Erros de runbook")
    L.append("")
    if m["erros_runbook"]:
        L.append("| id | esperado | obtido |")
        L.append("| --- | --- | --- |")
        for e in m["erros_runbook"]:
            L.append("| %s | %s | %s |" % (e["id"], e["esperado"], e["obtido"]))
    else:
        L.append("Nenhum erro de runbook.")
    L.append("")
    L.append("## Ablacao de camadas da heuristica")
    L.append("")
    L.append("Cada linha desliga uma camada mantendo as outras. O numero e a")
    L.append("acuracia de categoria medida no banco completo (79 casos).")
    L.append("")
    L.append("| configuracao | acuracia categoria | correspondencia runbook |")
    L.append("| --- | --- | --- |")
    for nome, d in m["analises"]["ablacao_de_camadas"].items():
        L.append("| %s | %.2f%% | %.2f%% |"
                 % (nome, d["acuracia_categoria_pct"],
                    d["correspondencia_runbook_pct"]))
    L.append("")
    L.append("## Robustez a perturbacao da entrada")
    L.append("")
    L.append("Estresse deterministico aplicado em memoria, sem alterar o banco.")
    L.append("Serve de proxy para generalizacao, ja que o valor intra-amostra e")
    L.append("alto por construcao.")
    L.append("")
    L.append("| perturbacao | acuracia categoria | correspondencia runbook | confusoes |")
    L.append("| --- | --- | --- | --- |")
    for nome, d in m["analises"]["robustez_a_perturbacao"].items():
        conf = ", ".join("%s->%s (%d)" % (c["esperado"], c["obtido"],
                                          c["ocorrencias"])
                         for c in d["confusoes_top3"]) or "-"
        L.append("| %s | %.2f%% | %.2f%% | %s |"
                 % (nome, d["acuracia_categoria_pct"],
                    d["correspondencia_runbook_pct"], conf))
    L.append("")
    L.append("## Erros sob perturbacao (id, esperado, obtido)")
    L.append("")
    vistos = set()
    registros = []
    for nome, d in m["analises"]["robustez_a_perturbacao"].items():
        for e in d["erros"]:
            chave = (e["id"], e["obtido"], e["obtido_runbook"])
            if chave in vistos:
                continue
            vistos.add(chave)
            registros.append((e["id"], nome, e["esperado"], e["obtido"],
                              e["esperado_runbook"], e["obtido_runbook"]))
    if registros:
        L.append("| id | perturbacao | cat. esperada | cat. obtida | "
                 "rb. esperado | rb. obtido |")
        L.append("| --- | --- | --- | --- | --- | --- |")
        for row in sorted(registros):
            L.append("| %s | %s | %s | %s | %s | %s |" % row)
    else:
        L.append("Nenhum erro tampouco sob perturbacao.")
    L.append("")
    L.append("## Leitura honesta do resultado")
    L.append("")
    L.append("Os pesos foram ajustados sobre este mesmo banco de 79 casos, entao "
             "**100% e um numero intra-amostra**: mede coerencia da heuristica "
             "com o vocabulario do dominio, nao generalizacao. Para que o numero "
             "signifique algo, o relatorio traz duas correcoes: (a) ablacao, "
             "mostrando que catalogo de alertname e janela de negacao tem "
             "contribuicao medida e pequena, e (b) teste de robustez, que quebra "
             "a entrada de forma deterministica. A acuracia sob inversao de ordem "
             "das palavras e o numero que eu citaria em uma conversa sobre o "
             "quanto isto generalizaria. Os casos marcados como ambiguos no campo "
             "`notes` do banco continuam sendo os primeiros a falhar. Ver "
             "`docs/decisoes/0002-heuristica-deterministica.md`.")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Avaliacao do agente de triagem")
    parser.add_argument("--cases", default=str(CASES_PADRAO))
    parser.add_argument("--out", default=str(RESULTS_PADRAO))
    parser.add_argument("--report", action="store_true",
                        help="imprime o resumo legivel no stdout")
    parser.add_argument("--check", action="store_true",
                        help="so valida; nao grava arquivos")
    args = parser.parse_args(argv)

    casos = carregar_casos(args.cases)
    metricas = avaliar(casos)
    determinismo = verificar_determinismo(casos)
    corpo = render_metrics(metricas, determinismo)

    if not args.check:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "metrics.json").write_text(corpo, encoding="utf-8")
        (out / "report.md").write_text(render_report(metricas), encoding="utf-8")
        print("gravado: %s" % (out / "metrics.json"))
        print("gravado: %s" % (out / "report.md"))

    if args.report:
        print(render_report(metricas))
        print("determinismo: %s sha256=%s"
              % ("identico" if determinismo["identico"] else "DIVERGENTE",
                 determinismo["sha256_16"]))

    if not determinismo["identico"]:
        print("ERRO: saida nao deterministica", file=sys.stderr)
        return 1
    if len(casos) != 79:
        print("ERRO: esperava 79 casos, li %d" % len(casos), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

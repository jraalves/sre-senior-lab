#!/usr/bin/env python3
"""Lab 05 - correlacao de metrica, log e traco pelo mesmo request_id.

Entrada: os tres arquivos gerados por loadgen.py (ou tools/synth.py):
  data/requests.jsonl  -> metrica por requisicao
  data/logs.txt        -> linhas de log com [request_id]
  data/spans.jsonl     -> spans com tags.request_id e traceID

Saida: uma unica visao de diagnostico por requisicao, com arvore de spans,
onde o tempo foi gasto e um veredito de onde investigar. O ponto do exercicio
e mostrar que a correlacao funciona sem nenhuma biblioteca de APM: basta
propagar `X-Request-Id` e `traceparent` e escrever os tres sinais com a mesma
chave.

Uso:
  python3 labs/lab-05-golden-signals/correlate.py --list-errors --limit 5
  python3 labs/lab-05-golden-signals/correlate.py --request-id <uuid>
  python3 labs/lab-05-golden-signals/correlate.py --trace-id <hex32>
  python3 labs/lab-05-golden-signals/correlate.py --find 429          # texto/ID
  python3 labs/lab-05-golden-signals/correlate.py --summary
"""

import argparse
import json
import re
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB_DIR))
sys.path.insert(0, str(LAB_DIR.parent.parent / "tools"))

import metrics  # noqa: E402

# data hora level [request_id] mensagem chave=valor ...
LOG_RE_ALT = re.compile(
    r"^(?P<data>\d{4}-\d{2}-\d{2}) (?P<hora>\d{2}:\d{2}:\d{2}\.\d{3}) "
    r"(?P<level>[A-Z]+) \[(?P<rid>[0-9a-f-]{36})\] (?P<msg>.*)$")

ROTULOS = {
    "metrica": "METRICA (requests.jsonl)",
    "log": "LOG (logs.txt)",
    "traco": "TRACO (spans.jsonl)",
}


def carregar_tudo(data_dir):
    data_dir = Path(data_dir)
    registros = metrics.carregar_jsonl(data_dir / "requests.jsonl")
    spans = metrics.carregar_jsonl(data_dir / "spans.jsonl")
    logs = parsear_logs((data_dir / "logs.txt").read_text(encoding="utf-8").splitlines())
    by_rid = {r["request_id"]: r for r in registros}
    by_trace = {r["trace_id"]: r for r in registros}
    spans_por_trace = {}
    for sp in spans:
        spans_por_trace.setdefault(sp["traceID"], []).append(sp)
    # profundidades calculadas ANTES de ordenar: chamar _profundidade dentro do
    # key de list.sort() leria a lista enquanto ela e reorganizada, e a ordem
    # final sairia errada (comportamento observatorio, nao teoria).
    for tracos in spans_por_trace.values():
        profundidade = {sp["spanID"]: _profundidade(sp, tracos) for sp in tracos}
        tracos.sort(key=lambda sp: (profundidade[sp["spanID"]],
                                    -_nanos(sp["durationUnixNano"])))
    return {"registros": registros, "spans_por_trace": spans_por_trace,
            "logs_por_rid": logs, "by_rid": by_rid, "by_trace": by_trace,
            "spans_totais": len(spans)}


def _profundidade(span, tracos):
    """Distancia ate a raiz, usada para desenhar a arvore na ordem certa."""
    por_id = {sp["spanID"]: sp for sp in tracos}
    nivel, pai = 0, span.get("parentSpanID")
    while pai and pai in por_id and nivel < 8:
        nivel += 1
        pai = por_id[pai].get("parentSpanID")
    return nivel


def _nanos(valor):
    return float(valor or 0)


def parsear_logs(linhas):
    """Indexa linhas de log por request_id sem depender de parser de Loki."""
    saida = {}
    for linha in linhas:
        match = LOG_RE_ALT.match(linha)
        if not match:
            continue
        rid = match.group("rid")
        saida.setdefault(rid, []).append({
            "ts": "%s %s" % (match.group("data"), match.group("hora")),
            "level": match.group("level"),
            "mensagem": match.group("msg"),
            "linha": linha,
        })
    return saida


def resolver(dados, termo):
    """Aceita request_id, trace_id, span_id ou texto parcial; devolve request_ids."""
    termo = termo.strip()
    if termo in dados["by_rid"]:
        return [termo]
    if termo in dados["by_trace"]:
        return [dados["by_trace"][termo]["request_id"]]
    baixos = termo.lower()
    achados = []
    for rid, linhas in dados["logs_por_rid"].items():
        if baixos in " ".join(l["mensagem"].lower() for l in linhas):
            achados.append(rid)
    if achados:
        return achados
    # o texto pode estar so no evento do span (ex.: connection refused)
    for reg in dados["registros"]:
        if any(baixos in ev.lower() for ev in reg.get("span_events", [])):
            achados.append(reg["request_id"])
    if achados:
        return achados
    for sp_id in (r["span_id"] for r in dados["registros"]):
        if termo == sp_id:
            return [r["request_id"] for r in dados["registros"] if r["span_id"] == sp_id]
    return []


def arvore_traco(spans, largura=48):
    """Renderiza a hierarquia de spans com participacao no tempo total."""
    if not spans:
        return ["  (sem spans para este traco)"]
    total = _nanos(spans[0]["durationUnixNano"]) or 1.0
    linhas = []
    por_id = {s["spanID"]: s for s in spans}
    for sp in spans:
        nivel = 0
        pai = sp.get("parentSpanID")
        while pai and pai in por_id and nivel < 6:
            nivel += 1
            pai = por_id[pai].get("parentSpanID")
        dur = _nanos(sp["durationUnixNano"])
        parte = dur / total
        barra = "#" * max(1, int(parte * largura))
        estado = sp.get("status", "OK")
        linhas.append("  %s%-22s %-26s %8.1f ms %4.0f%% %-6s %s" % (
            "   " * nivel, sp["service"], sp["operation"], dur / 1e6,
            parte * 100, "[ERRO]" if estado == "ERROR" else "",
            sp["spanID"][:8]))
        for ev in sp.get("events", []):
            linhas.append("  %s   ! %s" % ("   " * nivel, ev["name"]))
    return linhas


def veredito(reg, spans):
    """Heuristica explicita de onde apontar, derivada dos tres sinais."""
    dur = float(reg["duration_ms"])
    alvo = metrics.ALVO_LATENCIA_MS
    dep = float(reg.get("dependency_ms", 0.0))
    share = dep / dur if dur else 0.0
    status = int(reg["status"])
    if status >= 500:
        culpados = [s for s in spans if s.get("status") == "ERROR"]
        if culpados:
            pior = culpados[0]
            return ("dependencia", "span em erro em %s (%.1f ms de %.1f ms; %.0f%% do tempo)" % (
                pior["service"], _nanos(pior["durationUnixNano"]) / 1e6, dur, share * 100))
        return ("servico", "status %d sem span em erro: falha gerada no proprio servico" % status)
    if dur > alvo and share >= 0.5:
        return ("dependencia", "%.0f%% do tempo gasto em chamada de saida: "
                "olhar o downstream antes do codigo" % (share * 100))
    if dur > alvo:
        return ("servico", "requisicao acima do alvo (%.1f ms > %.0f ms) com pouco tempo "
                "de saida (%.0f%%): investigar codigo, GC, lock ou fila interna" % (
                    dur, alvo, share * 100))
    if not reg.get("cache_hit", True):
        return ("cache", "dentro do alvo, mas cache miss: %.1f ms sem cache" % dur)
    return ("saudavel", "dentro do alvo (%.1f ms <= %.0f ms) e sem erro" % (dur, alvo))


def visao(dados, request_id):
    reg = dados["by_rid"].get(request_id)
    if reg is None:
        return None
    spans = dados["spans_por_trace"].get(reg["trace_id"], [])
    logs = dados["logs_por_rid"].get(request_id, [])
    classe, explicacao = veredito(reg, spans)
    return {
        "request_id": request_id,
        "trace_id": reg["trace_id"],
        "span_raiz": reg["span_id"],
        "metrica": {
            "service": reg["service"], "route": reg["route"], "status": reg["status"],
            "duration_ms": reg["duration_ms"], "self_ms": reg["self_ms"],
            "dependency_ms": reg["dependency_ms"], "cache_hit": reg["cache_hit"],
            "concorrencia": "%s/%s" % (reg["concurrency"], reg["concurrency_limit"]),
            "ts": reg["ts"],
        },
        "logs": logs,
        "spans": spans,
        "veredito": {"classe": classe, "explicacao": explicacao},
        "como_continuar": _proximos_passos(reg, classe),
    }


def _proximos_passos(reg, classe):
    """Aponta o proximo passo, incluindo o runbook do lab-04 correto."""
    status = int(reg["status"])
    dur = float(reg["duration_ms"])
    ocupacao = float(reg["concurrency"]) / float(reg["concurrency_limit"])
    if status >= 500:
        runbook = "labs/lab-04-runbooks/rb-02-taxa-de-erro.md"
    elif dur > metrics.ALVO_LATENCIA_MS and ocupacao > 0.8:
        runbook = "labs/lab-04-runbooks/rb-03-saturacao-cpu-memoria.md"
    elif dur > metrics.ALVO_LATENCIA_MS:
        runbook = "labs/lab-04-runbooks/rb-01-latencia-alta.md"
    else:
        runbook = "nenhum (request dentro do normal)"
    return {
        "contexto": "python3 labs/lab-05-golden-signals/loadgen.py --report",
        "alerta que deveria ter pego": "python3 labs/lab-02-burn-rate-alerting/burnrate.py",
        "runbook": runbook,
    }


def imprimir_visao(v):
    m, l = v["metrica"], v["logs"]
    print("=" * 78)
    print("diagnostico do request %s" % v["request_id"])
    print("trace %s | span raiz %s" % (v["trace_id"], v["span_raiz"]))
    print("-" * 78)
    print(ROTULOS["metrica"])
    print("  %s %s" % (m["ts"], m["route"]))
    print("  service=%s status=%d duration=%.1f ms (self %.1f / saida %.1f) cache_hit=%s concorrencia=%s" % (
        m["service"], m["status"], m["duration_ms"], m["self_ms"],
        m["dependency_ms"], m["cache_hit"], m["concorrencia"]))
    print("")
    print(ROTULOS["log"])
    if l:
        for linha in l:
            print("  %s %-5s %s" % (linha["ts"], linha["level"], linha["mensagem"]))
    else:
        print("  (nenhuma linha de log com este request_id - o que ja e um achado)")
    print("")
    print(ROTULOS["traco"])
    for linha in arvore_traco(v["spans"]):
        print(linha)
    print("")
    print("veredito: %s - %s" % (v["veredito"]["classe"], v["veredito"]["explicacao"]))
    print("para continuar:")
    for chave, cmd in v["como_continuar"].items():
        print("  %-28s %s" % (chave + ":", cmd))


def listar(dados, filtro, limite):
    saida = []
    for reg in dados["registros"]:
        if filtro == "error" and int(reg["status"]) < 500:
            continue
        if filtro == "slow" and float(reg["duration_ms"]) <= metrics.ALVO_LATENCIA_MS:
            continue
        saida.append(reg)
        if len(saida) >= limite:
            break
    return saida


def summary(dados):
    gs = metrics.golden_signals(dados["registros"])
    logs_com_rid = sum(len(v) for v in dados["logs_por_rid"].values())
    return {
        "requisicoes": gs["requisicoes"],
        "request_ids_unicos": len(dados["by_rid"]),
        "tracos": len(dados["spans_por_trace"]),
        "spans": dados["spans_totais"],
        "linhas_de_log": logs_com_rid,
        "logs_correlacionaveis_pct": round(
            sum(1 for r in dados["registros"] if r["request_id"] in dados["logs_por_rid"])
            / gs["requisicoes"] * 100.0, 2),
        "golden": gs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="correlacao por request_id (lab-05)")
    parser.add_argument("--data", default=str(LAB_DIR / "data"))
    parser.add_argument("--request-id")
    parser.add_argument("--trace-id")
    parser.add_argument("--find", help="texto, request_id, trace_id ou span_id")
    parser.add_argument("--list-errors", action="store_true")
    parser.add_argument("--list-slow", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dados = carregar_tudo(args.data)

    if args.summary:
        s = summary(dados)
        if args.json:
            print(json.dumps(s, indent=2, sort_keys=True))
            return 0
        print("lab-05 | visao consolidada de correlacao (dados sinteticos)")
        print("-" * 66)
        for chave in ("requisicoes", "request_ids_unicos", "tracos", "spans",
                      "linhas_de_log", "logs_correlacionaveis_pct"):
            print("  %-26s %s" % (chave, s[chave]))
        print("")
        print(metrics.formatar(s["golden"]))
        return 0

    alvo = None
    if args.request_id:
        alvo = [args.request_id]
    elif args.trace_id:
        alvo = resolver(dados, args.trace_id)
    elif args.find:
        alvo = resolver(dados, args.find)
    elif args.list_errors or args.list_slow:
        filtro = "error" if args.list_errors else "slow"
        alvo = [r["request_id"] for r in listar(dados, filtro, args.limit)]
        if args.json:
            print(json.dumps(alvo, indent=2))
            return 0
        print("request_ids (%s):" % filtro)
        for rid in alvo:
            reg = dados["by_rid"][rid]
            print("  %s  %-20s %6.1f ms  %d  %s" % (
                rid, reg["service"], reg["duration_ms"], reg["status"], reg["route"]))
        print("")
        print("detalhe de um deles: --request-id <id>")
        return 0
    else:
        parser.error("informe --request-id, --trace-id, --find, --list-errors, --list-slow ou --summary")

    if not alvo:
        print("nada encontrado. rode antes: python3 labs/lab-05-golden-signals/loadgen.py",
              file=sys.stderr)
        return 1

    vistos = 0
    for rid in alvo[:args.limit if (args.find or args.trace_id) else len(alvo)]:
        v = visao(dados, rid)
        if v is None:
            print("request_id %s nao esta em requests.jsonl" % rid, file=sys.stderr)
            continue
        if args.json:
            print(json.dumps(v, indent=2, sort_keys=True))
        else:
            imprimir_visao(v)
        vistos += 1
    return 0 if vistos else 1


if __name__ == "__main__":
    raise SystemExit(main())

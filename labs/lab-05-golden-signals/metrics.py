#!/usr/bin/env python3
"""Lab 05 - os quatro golden signals medidos a partir de registros de request.

Um "registro" e o que o cliente sinteticos produz por requisicao:

    {
      "ts": iso, "request_id": uuid, "trace_id": hex32, "span_id": hex16,
      "service": str, "route": str, "status": int, "duration_ms": float,
      "self_ms": float, "dependency_ms": float, "cache_hit": bool,
      "concurrency": int, "concurrency_limit": int,
      "log_level": str, "log_message": str
    }

Este modulo e puro: recebe lista de dicts, devolve dict. Por isso e usado pelo
loadgen.py, pelo correlate.py e pelos testes sem tocar em disco nem em rede.

Sem dependencias de terceiros (nada de numpy): o percentile usa ranking
"nearest-rank", documentado abaixo.
"""

import json
from collections import defaultdict

ALVO_LATENCIA_MS = 400.0


def percentile(valores, p):
    """Percentil pelo metodo nearest-rank.

    Ordena, toma o indice ceil(p * n) - 1 (limitado a [0, n-1]). Escolha
    deliberada: nao interpola, entao o valor devolvido e um valor observado,
    o que torna a saida auditavel em incidente.
    """
    if not valores:
        raise ValueError("percentile de lista vazia")
    if not 0.0 < p <= 1.0:
        raise ValueError("p fora de (0, 1]: %r" % p)
    ordenado = sorted(valores)
    n = len(ordenado)
    rank = -((-p * n // 1))  # ceil(p*n) sem importar math
    idx = min(max(int(rank) - 1, 0), n - 1)
    return ordenado[idx]


def carregar_jsonl(caminho):
    registros = []
    with open(caminho, encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                registros.append(json.loads(linha))
    return registros


def _e_valido(reg):
    """Definicao de requisicao valida usada no SLI: 2xx/3xx/4xx de cliente.

    5xx conta como erro. Mantido aqui e nao espalhado, para que a definicao de
    erro seja a mesma em qualquer ferramenta do laboratorio.
    """
    return int(reg.get("status", 500)) < 500


def _dentro_do_alvo(reg, alvo_ms=ALVO_LATENCIA_MS):
    return float(reg.get("duration_ms", 0.0)) <= alvo_ms


def saturacao(registros):
    """Saturacao pelo pior caso observado de concorrencia sobre o limite.

    Retorna tambem o p95 e o p99 da ocupacao: media de saturacao e o numero que
    esconde problema, entao nao e reportado como headline.
    """
    ocupacoes = [float(r["concurrency"]) / float(r["concurrency_limit"])
                 for r in registros if r.get("concurrency_limit")]
    if not ocupacoes:
        return {"max": None, "p95": None, "p99": None, "pico_descricao": "sem dados"}
    pico = max(ocupacoes)
    pior = max(registros, key=lambda r: float(r.get("concurrency", 0))
               / float(r.get("concurrency_limit", 1)))
    return {
        "max": round(pico, 4),
        "p95": round(percentile(ocupacoes, 0.95), 4),
        "p99": round(percentile(ocupacoes, 0.99), 4),
        "pico_descricao": "%d/%d no request %s" % (
            pior["concurrency"], pior["concurrency_limit"], pior["request_id"][:8]),
    }


def golden_signals(registros, alvo_ms=ALVO_LATENCIA_MS):
    """Calcula latencia, trafego, erro e saturacao para o conjunto informado."""
    if not registros:
        raise ValueError("sem registros para calcular golden signals")
    duracoes = [float(r["duration_ms"]) for r in registros]
    total = len(registros)
    invalidas = sum(1 for r in registros if not _e_valido(r))
    fora_do_alvo = sum(1 for r in registros if not _dentro_do_alvo(r, alvo_ms))
    tempo_total_s = float(registros[-1]["t"]) - float(registros[0]["t"])
    if tempo_total_s <= 0:
        tempo_total_s = float(total)  # serie de 1 ponto: assume 1s por request
    t0 = _parse_ts(registros[0]["ts"])
    t1 = _parse_ts(registros[-1]["ts"])
    erro = invalidas / total
    return {
        "janela": {"inicio": registros[0]["ts"], "fim": registros[-1]["ts"],
                   "segundos": round(tempo_total_s, 3)},
        "requisicoes": total,
        "latencia_ms": {
            "media": round(sum(duracoes) / total, 2),
            "p50": round(percentile(duracoes, 0.50), 2),
            "p90": round(percentile(duracoes, 0.90), 2),
            "p95": round(percentile(duracoes, 0.95), 2),
            "p99": round(percentile(duracoes, 0.99), 2),
            "max": round(max(duracoes), 2),
            "alvo_ms": alvo_ms,
            "fora_do_alvo": fora_do_alvo,
            "fora_do_alvo_pct": round(fora_do_alvo / total * 100.0, 3),
        },
        "trafego": {
            "rps": round(total / tempo_total_s, 3),
            "req_por_minuto": round(60.0 * total / tempo_total_s, 1),
            "duracao_real_segundos": round((t1 - t0).total_seconds(), 3) if t1 and t0 else None,
        },
        "erro": {
            "invalidas": invalidas,
            "taxa": round(erro, 6),
            "taxa_pct": round(erro * 100.0, 4),
            "por_status": _contar_status(registros),
            "slo_atingido": erro <= (1.0 - 0.999),
        },
        "saturacao": saturacao(registros),
    }


def _contar_status(registros):
    contagem = defaultdict(int)
    for r in registros:
        contagem[str(r["status"])] += 1
    return dict(sorted(contagem.items()))


def _parse_ts(valor):
    """ISO 8601 com 'Z' e milissegundos -> segundos desde a epoch (stdlib)."""
    import datetime as _dt
    texto = valor.replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(texto)
    except ValueError:
        return None


def dividir_por_janela(registros, segundos=30):
    """Agrega os registros em janelas fixas, para ver a evolucao no tempo."""
    janelas = defaultdict(list)
    for r in registros:
        chave = int(float(r["t"]) // segundos) * segundos
        janelas[chave].append(r)
    saida = []
    for chave in sorted(janelas):
        grupo = janelas[chave]
        gs = golden_signals(grupo)
        gs["janela"]["t_inicio"] = chave
        saida.append(gs)
    return saida


def pico_e_queda(series, campo="p95"):
    """Localiza a janela mais ruim e a regressao ate o regime normal."""
    if not series:
        return {}
    pior = max(series, key=lambda s: s["latencia_ms"][campo])
    mediana = percentile([s["latencia_ms"][campo] for s in series], 0.5)
    apos = [s for s in series
            if s["janela"]["t_inicio"] > pior["janela"]["t_inicio"]
            and s["latencia_ms"][campo] <= mediana * 1.1]
    recuperacao = None
    if apos:
        recuperacao = apos[0]["janela"]["t_inicio"] - pior["janela"]["t_inicio"]
    return {
        "pior_janela_t": pior["janela"]["t_inicio"],
        "pior_%s" % campo: pior["latencia_ms"][campo],
        "mediana_%s" % campo: mediana,
        "taxa_de_erro_na_pior_janela_pct": pior["erro"]["taxa_pct"],
        "segundos_ate_registrar_normalizacao": recuperacao,
    }


def formatar(gs):
    """Versao legivel do resumo, usada no stdout do loadgen e no README."""
    lat, tr, er = gs["latencia_ms"], gs["trafego"], gs["erro"]
    sat = gs["saturacao"]
    linhas = [
        "golden signals (%s requisicoes, %s s)" % (gs["requisicoes"], gs["janela"]["segundos"]),
        "  latencia ms : media %.1f | p50 %.1f | p90 %.1f | p95 %.1f | p99 %.1f | max %.1f" % (
            lat["media"], lat["p50"], lat["p90"], lat["p95"], lat["p99"], lat["max"]),
        "  trafego     : %.2f rps (%.1f req/min)" % (tr["rps"], tr["req_por_minuto"]),
        "  erro        : %d invalidas (%.4f%%) | status %s" % (
            er["invalidas"], er["taxa_pct"], er["por_status"]),
        "  saturacao   : max %.1f%% | p95 %.1f%% | p99 %.1f%% (%s)" % (
            (sat["max"] or 0) * 100, (sat["p95"] or 0) * 100, (sat["p99"] or 0) * 100,
            sat["pico_descricao"]),
        "  acima do alvo de %.0f ms: %d (%.3f%%)" % (
            lat["alvo_ms"], lat["fora_do_alvo"], lat["fora_do_alvo_pct"]),
    ]
    return "\n".join(linhas)

#!/usr/bin/env python3
"""Gerador unico e deterministico de todos os dados sinteticos do laboratorio.

Uso:
  python3 tools/synth.py                 # gera tudo com seed 42
  python3 tools/synth.py --seed 7        # varia o ruido, mantem a estrutura
  python3 tools/synth.py --only slo      # gera um artefato
  python3 tools/synth.py --stdout burn   # imprime CSV na saida, sem gravar
  python3 tools/synth.py --check         # valida os arquivos gerados

Determinismo: mesma seed produz os mesmos bytes. O gerador imprime sha256
parcial de cada arquivo para conferir que o dataset commitado veio daqui.

Todo conteudo e sintetico: servicos, clusters, nodes, IPs, custos e duracoes
sao ficticios. Ver docs/decisoes/0001-dados-sinteticos.md.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import case_bank  # noqa: E402
from data_defs import (  # noqa: E402
    BURN_BUCKETS,
    BURN_ERRO_BASE,
    BURN_INCIDENTES,
    BURN_INTERVAL_MIN,
    CAPACITY_SEMANAS,
    CAPACITY_SERVICES,
    COST_PERIODOS,
    COST_SERVICES,
    GOLDEN_REQUESTS,
    LATENCIA_ALVO_MS,
    PRECO_CPU_CORE_MES,
    PRECO_DISK_GIB_MES,
    PRECO_EGRESS_GIB,
    PRECO_LB_HORAS,
    PRECO_LICENSE_SEATS,
    PRECO_NAT_GIB,
    PRECO_OBS_GIB,
    PRECO_RAM_GIB_MES,
    PRECO_SNAPSHOT_GIB_MES,
    SEED_PADRAO,
    SERVICES,
    SLO_BUCKET_MIN,
    SLO_DIAS,
    SLO_INCIDENTES,
    SLO_TARGET_DISPONIBILIDADE,
    SLO_TARGET_LATENCIA,
)

BASE_UTC = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def _peso_hora(hora):
    """Curva diurna sintetica de carga, com picos as 13h e as 20h."""
    pico_tarde = math.exp(-((hora - 13) ** 2) / 18.0)
    pico_noite = math.exp(-((hora - 20) ** 2) / 8.0)
    return 0.32 + 0.55 * pico_tarde + 0.30 * pico_noite


def _incidente_ativo(dia, hora):
    for ini_dia, ini_hora, dur, taxa_erro, taxa_lenta in SLO_INCIDENTES:
        if ini_dia == dia and ini_hora <= hora < ini_hora + dur:
            return taxa_erro, taxa_lenta
    return None


# ------------------------------------------------------------- lab-01
def slo_signal_rows(seed=SEED_PADRAO):
    """Serie horaria de sinais de SLI de disponibilidade e de latencia."""
    rng = random.Random(seed)
    rows = []
    servico, namespace, cluster = SERVICES[0]
    for i in range(SLO_DIAS * 24):
        ts = BASE_UTC + timedelta(minutes=SLO_BUCKET_MIN * i)
        dia = ts.day - BASE_UTC.day
        inc = _incidente_ativo(dia, ts.hour)
        peso = _peso_hora(ts.hour)
        requests = int(3.6 * 3600 * peso * rng.uniform(0.93, 1.07))
        if inc:
            taxa_erro, taxa_lenta = inc
        else:
            taxa_erro = 0.00040 * rng.uniform(0.4, 2.1)
            taxa_lenta = 0.0036 * rng.uniform(0.5, 1.8)
        failed = int(round(requests * taxa_erro))
        slow = int(round(requests * taxa_lenta))
        p95 = LATENCIA_ALVO_MS * (0.62 + 7.0 * taxa_lenta) * rng.uniform(0.97, 1.05)
        rows.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "service": servico,
            "namespace": namespace,
            "cluster": cluster,
            "slo_window": "30d",
            "target_availability": "%.5f" % SLO_TARGET_DISPONIBILIDADE,
            "target_latency": "%.5f" % SLO_TARGET_LATENCIA,
            "requests": requests,
            "failed": failed,
            "slow": slow,
            "fast": requests - slow,
            "p95_latency_ms": "%.1f" % p95,
        })
    return rows


# ------------------------------------------------------------- lab-02
def burn_rate_rows(seed=SEED_PADRAO):
    """Serie de 14 dias em granulos de 5 minutos com quatro episodios plantados."""
    rng = random.Random(seed + 11)
    rows = []
    servico = SERVICES[1][0]
    for i in range(BURN_BUCKETS):
        ts = BASE_UTC + timedelta(minutes=BURN_INTERVAL_MIN * i)
        peso = _peso_hora(ts.hour)
        requests = int(3.2 * 60 * BURN_INTERVAL_MIN * peso * rng.uniform(0.9, 1.1))
        taxa = BURN_ERRO_BASE * rng.uniform(0.3, 2.4)
        for ini, fim, taxa_incidente in BURN_INCIDENTES:
            if ini <= i < fim:
                rampa = min(1.0, (i - ini + 1) / 3.0)
                taxa = BURN_ERRO_BASE + (taxa_incidente - BURN_ERRO_BASE) * rampa
                break
        failed = int(round(requests * taxa))
        rows.append({
            "bucket_start": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "service": servico,
            "requests": requests,
            "failed": failed,
        })
    return rows


# ------------------------------------------------------------- lab-03
# (offset_min, fase, evento, fonte). Duracoes de exemplo, dados sinteticos.
TIMELINE = [
    (-150, "pre-incidente", "inicio da janela de estabilidade; p95 e taxa de erro dentro do alvo", "prometheus"),
    (-140, "pre-incidente", "alerta de error budget em regime de aviso, sem queima relevante", "alertmanager"),
    (-101, "pre-incidente", "dashboards revisados pela equipe durante o handoff de plantao", "grafana"),
    (-95, "pre-incidente", "deploy de rotinas de manutencao noturna, sem efeito no p95", "argo-cd"),
    (-84, "pre-incidente", "campanha de marketing aumenta a vazao de pedidos em 18%", "chat"),
    (-75, "pre-incidente", "pico de vazao sustentado; p95 permanece estavel", "prometheus"),
    (-62, "pre-incidente", "deploy do configmap payment-rules rev 41 no namespace payments-core", "argo-cd"),
    (-45, "pre-incidente", "provisao automatica de replicas por pico nao e acionada", "cluster-autoscaler"),
    (-38, "pre-incidente", "conclusao do deploy anterior sem erros visiveis", "argo-cd"),
    (-30, "pre-incidente", "p95 sobe 12% em uma rota secundaria; sem alerta, abaixo do limiar", "prometheus"),
    (0, "deteccao", "alerta SLOErrorBudgetBurnFast (janela 1h) dispara para disponibilidade de payments-api", "alertmanager"),
    (5, "deteccao", "on-call do nivel 1 reconhece no chat de plantao", "opsgenie"),
    (7, "deteccao", "on-call abre o registro de incidente no tracker", "tracker"),
    (11, "deteccao", "primeira investigacao no dashboard de golden signals do servico", "grafana"),
    (17, "deteccao", "IC assume o incidente e declara impacto em checkout-service", "chat"),
    (24, "deteccao", "busca de alteracoes recentes lista o configmap aplicado 62 minutos antes", "argo-cd"),
    (29, "deteccao", "IC confirma o momento de deteccao efetiva apos leitura do alerta", "chat"),
    (35, "diagnostico", "traco com o mesmo X-Request-Id mostra 2,1 s em validacao de assinatura", "tempo"),
    (42, "diagnostico", "consulta no Loki agrupa erros por padrao: 94% sao SignatureValidationFailed", "loki"),
    (50, "diagnostico", "diff entre as revisoes do configmap revela a flag strict_key_id habilitada", "git"),
    (57, "diagnostico", "documentacao interna do componente de chave exige rotacao completa antes de strict_key_id", "wiki"),
    (66, "diagnostico", "IP do IC aparece em mais de 40 linhas do log de auditoria do cluster", "auditoria"),
    (71, "diagnostico", "decisao de meio de incidente: reverter a flag em vez de rotacionar chaves na janela", "chat"),
    (80, "diagnostico", "IC registra o plano de acao e o responsavel pela reversao", "chat"),
    (88, "diagnostico", "pedido formal de rollback da revisao 41 para a 40 registrado no chat", "chat"),
    (94, "contencao", "aprovacao humana registrada: lider da plataforma autoriza a reversao", "chat"),
    (101, "contencao", "reversao executada pelo time de plataforma via pipeline", "argo-cd"),
    (109, "contencao", "flag strict_key_id confirmada desligada em todas as replicas", "kubectl"),
    (118, "contencao", "IC declara o incidente contido", "chat"),
    (130, "recuperacao", "erro 5xx volta ao nivel de base", "prometheus"),
    (140, "recuperacao", "pod isolado com label de manutencao para analise posterior de dump", "kubectl"),
    (144, "recuperacao", "p95 retorna ao alvo; SLI acima de 99,9% por 15 minutos seguidos", "prometheus"),
    (152, "resolvido", "IC encerra o incidente; alertas quietos por 20 minutos", "chat"),
    (168, "pos-incidente", "on-call comeca a transcrever a timeline a partir dos canais", "chat"),
    (200, "pos-incidente", "rascunho do post-mortem criado com os dados deste arquivo", "doc"),
    (230, "pos-incidente", "IC registra o custo aproximado de toil para o post-mortem", "doc"),
    (245, "pos-incidente", "primeira reuniao de revisao; duas acoes contestadas", "meet"),
    (260, "pos-incidente", "reuniao de revisao no dia seguinte", "meet"),
    (270, "pos-incidente", "time de plataforma revisa a lista de acoes e prioriza", "linear"),
    (285, "pos-incidente", "seguimento do incidente encerrado; acoes viram itens no backlog", "linear"),
    (300, "pos-incidente", "IC e tech lead fazem follow-up de processo", "meet"),
    (320, "pos-incidente", "revisao de acoes fechada com dois itens adiados para o proximo trimestre", "linear"),
    (345, "pos-incidente", "reuniao de acompanhamento com a equipe", "meet"),
    (360, "pos-incidente", "post-mortem publicado no repositorio interno", "git"),
]


def timeline_rows():
    return [{"offset_min": o, "fase": f, "evento": e, "fonte": s}
            for o, f, e, s in sorted(TIMELINE, key=lambda r: r[0])]


# ------------------------------------------------------------- lab-05
def _hex(rng, n):
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _request_id(rng):
    return "-".join([_hex(rng, 8), _hex(rng, 4), _hex(rng, 4), _hex(rng, 4), _hex(rng, 12)])


# janela do incidente plantado, em segundos a partir do inicio da execucao
GOLDEN_INCIDENTE = (150.0, 200.0)

# servico -> (span pai, dependencia que ele chama)
_TOPOLOGIA = {
    "payments-api": ("api-gateway", "payment-provider"),
    "checkout-service": ("api-gateway", "orders-store"),
    "search-indexer": ("gateway-de-busca", "redis-cache"),
    "notification-hub": ("event-bus", "provedor-de-email"),
    "orders-api": ("api-gateway", "orders-store"),
}
_LIMITE_CONCORRENCIA = 64
_LAMBDA_RPS = 8.0
_FATOR_AGRUPAMENTO = 6


def golden_requests(seed=SEED_PADRAO, total=GOLDEN_REQUESTS):
    """Cliente sintetico: gera requisicoes com latencia, erro, traco e log.

    Cada requisicao produz tres spans encadeados (gateway -> servico ->
    dependencia), uma linha de log com o mesmo request_id e as metricas da
    propria requisicao. E isso que permite ao correlate.py mostrar metrica,
    log e traco de um mesmo request sem biblioteca nenhuma.
    """
    rng = random.Random(seed + 5)
    rotas = [
        ("payments-api", "POST /v1/payments/charge"),
        ("payments-api", "GET /v1/payments/{id}"),
        ("checkout-service", "POST /v1/checkout/confirm"),
        ("search-indexer", "GET /v1/search"),
        ("notification-hub", "POST /v1/notifications/send"),
    ]
    records = []
    for i in range(total):
        t = i / 8.0  # ~8 rps
        servico, rota = rotas[i % len(rotas)]
        pai, dependencia = _TOPOLOGIA[servico]
        dur = rng.lognormvariate(math.log(92.0), 0.55)
        cache_hit = rng.random() < 0.82
        if not cache_hit:
            dur *= 2.4
        em_incidente = GOLDEN_INCIDENTE[0] <= t < GOLDEN_INCIDENTE[1]
        if em_incidente:
            dur *= 3.1
        status, level, mensagem = 200, "INFO", "request concluido"
        eventos = []
        falha = rng.random()
        if em_incidente and falha < 0.06:
            status, level, mensagem = 503, "ERROR", "upstream indisponivel durante falha de dependencia"
            eventos.append("excecao: connection refused em %s" % dependencia)
        elif falha < 0.008:
            status, level, mensagem = 500, "ERROR", "falha nao tratada no handler"
            eventos.append("excecao: timeout ao validar assinatura com %s" % dependencia)
        elif falha < 0.014:
            status, level, mensagem = 404, "WARN", "recurso nao encontrado"
        dur = max(8.0, dur)
        if dur > LATENCIA_ALVO_MS:
            eventos.append("duracao acima do alvo de %d ms" % LATENCIA_ALVO_MS)

        fracao_dep = 0.30
        if em_incidente or status >= 500:
            fracao_dep = 0.62
        elif not cache_hit:
            fracao_dep = 0.45
        fracao_dep = min(fracao_dep * rng.uniform(0.9, 1.1), 0.82)
        dep_ms = round(dur * fracao_dep, 2)
        self_ms = round(dur * (1.0 - fracao_dep) * 0.94, 2)
        # Little's law aplicada ao agregado da fazenda: L = lambda * W.
        # 8 rps de entrada, W = duracao da requisicao em segundos, e um fator de
        # agregacao 6 para simular a soma das instancias do servico.
        concorrencia = max(1, min(_LIMITE_CONCORRENCIA,
                                  int(round(_LAMBDA_RPS * (dur / 1000.0) * _FATOR_AGRUPAMENTO))))

        trace_id = _hex(rng, 32)
        raiz_id = _hex(rng, 16)
        span_servico = _hex(rng, 16)
        span_dep = _hex(rng, 16)
        spans = [
            {"traceID": trace_id, "spanID": raiz_id, "parentSpanID": "",
             "service": pai, "operation": rota,
             "durationUnixNano": int(dur * 1e6),
             "startTimeUnixNano": int(t * 1e9), "status": "OK",
             "tags": {"request_id": None, "layer": "edge"}},
            {"traceID": trace_id, "spanID": span_servico, "parentSpanID": raiz_id,
             "service": servico, "operation": rota,
             "durationUnixNano": int(self_ms * 1e6),
             "startTimeUnixNano": int(t * 1e9),
             "status": "ERROR" if status >= 500 else "OK",
             "tags": {"request_id": None, "layer": "servico", "cache.hit": cache_hit}},
            {"traceID": trace_id, "spanID": span_dep, "parentSpanID": span_servico,
             "service": dependencia, "operation": "chamada de saida",
             "durationUnixNano": int(dep_ms * 1e6),
             "startTimeUnixNano": int(t * 1e9),
             "status": "ERROR" if status in (503, 500) else "OK",
             "tags": {"request_id": None, "layer": "dependencia"}},
        ]
        rid = _request_id(rng)
        for sp in spans:
            sp["tags"]["request_id"] = rid
        records.append({
            "t": round(t, 3),
            "ts": (BASE_UTC + timedelta(seconds=t)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "request_id": rid,
            "trace_id": trace_id,
            "span_id": raiz_id,
            "service": servico,
            "route": rota,
            "status": status,
            "duration_ms": round(dur, 2),
            "self_ms": self_ms,
            "dependency_ms": dep_ms,
            "cache_hit": cache_hit,
            "concurrency": concorrencia,
            "concurrency_limit": _LIMITE_CONCORRENCIA,
            "log_level": level,
            "log_message": mensagem,
            "span_events": eventos,
            "spans": spans,
        })
    return records


def golden_log_lines(records):
    """Forma de linha de log plana: data, hora, level, request_id, mensagem."""
    out = []
    for r in records:
        data, hora = r["ts"].split("T")
        out.append("%s %s %s [%s] %s rota=%s status=%d duracao_ms=%.1f\n" % (
            data, hora.replace("Z", ""), r["log_level"], r["request_id"],
            r["log_message"], r["route"], r["status"], r["duration_ms"]))
    return out


def golden_span_lines(records):
    """Uma linha JSON por span, no formato simplificado usado pelo Tempo."""
    out = []
    for r in records:
        for sp in r["spans"]:
            linha = dict(sp)
            linha["events"] = [{"name": e} for e in r["span_events"]] if sp["spanID"] == r["span_id"] else []
            out.append(json.dumps(linha, sort_keys=True))
    return out


# ------------------------------------------------------------- lab-06
def capacity_rows(seed=SEED_PADRAO):
    rng = random.Random(seed + 21)
    rows = []
    for nome, rps0, crescimento, sazonal, saturacao, rps_replica in CAPACITY_SERVICES:
        for w in range(CAPACITY_SEMANAS):
            base = rps0 + crescimento * w
            saz = base * sazonal * math.sin(2 * math.pi * w / 13.0)
            rps = (base + saz) * rng.uniform(0.985, 1.015)
            carga = rps / saturacao
            cpu = 10.0 + 88.0 * carga + rng.uniform(-1.4, 1.4)
            fila = 4.0 + 900.0 * (carga ** 8) + rng.uniform(0, 6)
            rows.append({
                "week_index": w,
                "week_start": (BASE_UTC + timedelta(weeks=w)).strftime("%Y-%m-%d"),
                "service": nome,
                "rps": round(rps, 1),
                "cpu_p95_pct": round(min(cpu, 99.4), 1),
                "queue_depth": round(fila, 1),
                "saturation_rps": saturacao,
                "rps_per_replica": rps_replica,
            })
    return rows


# ------------------------------------------------------------- lab-07
# perfil sintetico por servico: utilizacao de compute, volumes, egress,
# assentos de licenca e idade de snapshots. Nada aqui vem de fatura real.
COST_PROFILE = {
    "payments-api": {"util": 0.68, "pd": 1800, "snap": 620, "egress": 4200, "nat": 980,
                     "obs": 480, "snap_age": 21, "util_st": 0.71, "util_net": 0.86},
    "checkout-service": {"util": 0.61, "pd": 2400, "snap": 900, "egress": 6100, "nat": 1450,
                         "obs": 720, "snap_age": 34, "util_st": 0.58, "util_net": 0.90},
    "notification-hub": {"util": 0.74, "pd": 640, "snap": 120, "egress": 21000, "nat": 9800,
                         "obs": 540, "snap_age": 12, "util_st": 0.66, "util_net": 0.31},
    "orders-api": {"util": 0.66, "pd": 980, "snap": 260, "egress": 1900, "nat": 420,
                   "obs": 260, "snap_age": 18, "util_st": 0.62, "util_net": 0.88},
    "ledger-api": {"util": 0.57, "pd": 5200, "snap": 1500, "egress": 800, "nat": 120,
                   "obs": 190, "snap_age": 41, "util_st": 0.44, "util_net": 0.91},
    "search-indexer": {"util": 0.42, "pd": 3100, "snap": 780, "egress": 1500, "nat": 300,
                       "obs": 610, "snap_age": 27, "util_st": 0.69, "util_net": 0.83},
    "billing-exporter": {"util": 0.31, "pd": 4200, "snap": 1900, "egress": 240, "nat": 60,
                         "obs": 95, "snap_age": 96, "util_st": 0.18, "util_net": 0.77},
    "payments-sandbox": {"util": 0.11, "pd": 220, "snap": 140, "egress": 60, "nat": 25,
                         "obs": 30, "snap_age": 132, "util_st": 0.12, "util_net": 0.40},
    "checkout-loadtest": {"util": 0.17, "pd": 180, "snap": 90, "egress": 45, "nat": 18,
                          "obs": 22, "snap_age": 118, "util_st": 0.14, "util_net": 0.35},
}

LICENSING_ROWS = [
    # (servico, equipe, ambiente, recurso, unidades, preco unitario, utilizacao)
    ("plataforma-observabilidade", "time-sre", "shared", "licenca-saas-suite", 62.0,
     PRECO_LICENSE_SEATS, 0.74),
    ("coleta-de-logs", "time-sre", "shared", "pipeline-loki", 14.0,
     PRECO_OBS_GIB * 40.0, 0.63),
    ("coleta-de-metricas", "time-sre", "shared", "pipeline-prometheus", 11.0,
     PRECO_OBS_GIB * 40.0, 0.58),
]


def cost_rows(seed=SEED_PADRAO):
    rng = random.Random(seed + 33)
    rows = []
    ultimo = len(COST_PERIODOS) - 1
    for p, periodo in enumerate(COST_PERIODOS):
        fator = 1.0 + 0.015 * p
        for nome, equipe, ambiente, cpu_milis, ram_gib, replicas in COST_SERVICES:
            pr = COST_PROFILE.get(nome)
            if pr is None:
                continue
            salto = 1.25 if (p == ultimo and nome == "notification-hub") else 1.05
            for r in range(replicas):
                custo = (cpu_milis / 1000.0) * PRECO_CPU_CORE_MES + ram_gib * PRECO_RAM_GIB_MES
                custo *= fator * rng.uniform(0.97, 1.03)
                rows.append({
                    "period": periodo, "service": nome, "environment": ambiente,
                    "team": equipe, "component": "compute",
                    "resource_id": "%s-pod-%02d" % (nome, r + 1),
                    "monthly_cost_usd": round(custo, 2),
                    "usage_units": round(cpu_milis / 1000.0, 2),
                    "utilization_pct": round(pr["util"] * 100 * rng.uniform(0.96, 1.04), 1),
                })
            rows.append({
                "period": periodo, "service": nome, "environment": ambiente,
                "team": equipe, "component": "storage", "resource_id": "pd-%s-01" % nome,
                "monthly_cost_usd": round(pr["pd"] * PRECO_DISK_GIB_MES * fator * rng.uniform(0.98, 1.02), 2),
                "usage_units": pr["pd"], "utilization_pct": round(pr["util_st"] * 100, 1),
            })
            rows.append({
                "period": periodo, "service": nome, "environment": ambiente,
                "team": equipe, "component": "storage", "resource_id": "snapshot-%s" % nome,
                "monthly_cost_usd": round(pr["snap"] * PRECO_SNAPSHOT_GIB_MES * fator, 2),
                "usage_units": pr["snap"],
                "utilization_pct": round(max(0.05, 1.0 - pr["snap_age"] / 180.0) * 100, 1),
            })
            rows.append({
                "period": periodo, "service": nome, "environment": ambiente,
                "team": equipe, "component": "network", "resource_id": "egress-%s" % nome,
                "monthly_cost_usd": round(pr["egress"] * PRECO_EGRESS_GIB * fator * rng.uniform(0.95, salto), 2),
                "usage_units": pr["egress"], "utilization_pct": round(pr["util_net"] * 100, 1),
            })
            rows.append({
                "period": periodo, "service": nome, "environment": ambiente,
                "team": equipe, "component": "network", "resource_id": "nat-%s" % nome,
                "monthly_cost_usd": round(pr["nat"] * PRECO_NAT_GIB * fator, 2),
                "usage_units": pr["nat"], "utilization_pct": round(pr["util_net"] * 60, 1),
            })
            rows.append({
                "period": periodo, "service": nome, "environment": ambiente,
                "team": equipe, "component": "network", "resource_id": "lb-%s" % nome,
                "monthly_cost_usd": round(PRECO_LB_HORAS * 730 * fator * (2 if ambiente == "prod" else 1), 2),
                "usage_units": 730, "utilization_pct": round(pr["util"] * 100, 1),
            })
        if p == ultimo:
            for servico, equipe, ambiente, recurso, unidades, preco_unit, util in LICENSING_ROWS:
                rows.append({
                    "period": periodo, "service": servico, "environment": ambiente,
                    "team": equipe, "component": "licensing", "resource_id": recurso,
                    "monthly_cost_usd": round(unidades * preco_unit, 2),
                    "usage_units": unidades, "utilization_pct": round(util * 100, 1),
                })
    return rows


# ------------------------------------------------------------- escrita
def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("nenhuma linha para escrever em %s" % path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _write_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def manifest_entries():
    """Registro dos artefatos: (nome, caminho, tipo, descricao)."""
    def p(*partes):
        return ROOT.joinpath(*partes)

    return [
        ("slo", p("labs/lab-01-slo-error-budget/data/slo-signals.csv"), "csv",
         "sinais de SLI de disponibilidade e latencia: 24 dias em bucket horario"),
        ("burn", p("labs/lab-02-burn-rate-alerting/data/burn-rate.csv"), "csv",
         "serie de 5 minutos com incidente plantado para calculo de burn rate"),
        ("timeline", p("labs/lab-03-incidente-postmortem/data/timeline.csv"), "csv",
         "timeline de incidente sintetico, com duracoes de exemplo"),
        ("golden", p("labs/lab-05-golden-signals/data"), "golden",
         "requests.jsonl, logs.txt e spans.jsonl correlacionados por request_id"),
        ("capacity", p("labs/lab-06-capacity-planning/data/capacity.csv"), "csv",
         "26 semanas por servico: rps, cpu p95 e profundidade de fila"),
        ("cost", p("labs/lab-07-finops/data/cost-lines.csv"), "csv",
         "linhas de custo por componente, tag e periodo (precos ficticios)"),
        ("eval", p("agent/data/eval_cases.jsonl"), "jsonl",
         "79 casos de alerta rotulados para avaliacao do agente de triagem"),
    ]


def _entry(name):
    for item in manifest_entries():
        if item[0] == name:
            return item
    raise KeyError("artefato desconhecido: %s" % name)


def generate(name, seed=SEED_PADRAO):
    _, alvo, tipo, _ = _entry(name)
    if tipo == "golden":
        records = golden_requests(seed)
        _write_jsonl(alvo / "requests.jsonl",
                     [{k: v for k, v in r.items() if k != "spans"} for r in records])
        _write_lines(alvo / "logs.txt", golden_log_lines(records))
        _write_lines(alvo / "spans.jsonl",
                     [linha + "\n" for linha in golden_span_lines(records)])
        return alvo
    if name == "slo":
        return _write_csv(alvo, slo_signal_rows(seed))
    if name == "burn":
        return _write_csv(alvo, burn_rate_rows(seed))
    if name == "timeline":
        return _write_csv(alvo, timeline_rows())
    if name == "capacity":
        return _write_csv(alvo, capacity_rows(seed))
    if name == "cost":
        return _write_csv(alvo, cost_rows(seed))
    if name == "eval":
        return _write_jsonl(alvo, case_bank.build_cases())
    raise KeyError("sem gerador para %s" % name)


def read_jsonl(path):
    itens = []
    with Path(path).open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                itens.append(json.loads(linha))
    return itens


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render(name, seed=SEED_PADRAO):
    """Produz o conteudo do artefato como texto, sem tocar no disco."""
    buf = io.StringIO()
    if name == "slo":
        rows = slo_signal_rows(seed)
    elif name == "burn":
        rows = burn_rate_rows(seed)
    elif name == "timeline":
        rows = timeline_rows()
    elif name == "capacity":
        rows = capacity_rows(seed)
    elif name == "cost":
        rows = cost_rows(seed)
    elif name == "eval":
        for case in case_bank.build_cases():
            buf.write(json.dumps(case, sort_keys=True, ensure_ascii=False) + "\n")
        return buf.getvalue()
    else:
        raise KeyError(name)
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def check_all():
    """Confere presenca, integridade interna e rotulos obrigatorios."""
    problemas = []
    for _, path, _, _ in manifest_entries():
        if not Path(path).exists():
            problemas.append("faltando: %s" % path)
    if problemas:
        return problemas

    cases = read_jsonl(ROOT / "agent/data/eval_cases.jsonl")
    if len(cases) != 79:
        problemas.append("eval_cases.jsonl com %d casos, esperado 79" % len(cases))
    obrigatorios = {"id", "text", "metadata", "label_category", "label_runbook", "label_symptom"}
    for c in cases:
        if not obrigatorios.issubset(c.keys()):
            problemas.append("caso %s sem rotulos obrigatorios" % c.get("id"))
    ids = [c.get("id") for c in cases]
    if len(ids) != len(set(ids)):
        problemas.append("IDs duplicados em eval_cases.jsonl")
    categorias = sorted(set(c.get("label_category") for c in cases))
    if categorias != sorted(case_bank.CATEGORIES):
        problemas.append("categorias %s != esperadas %s" % (categorias, case_bank.CATEGORIES))

    slo = read_csv(ROOT / "labs/lab-01-slo-error-budget/data/slo-signals.csv")
    if len(slo) != SLO_DIAS * 24:
        problemas.append("slo-signals.csv com %d linhas, esperado %d" % (len(slo), SLO_DIAS * 24))
    for linha in slo:
        if int(linha["fast"]) + int(linha["slow"]) != int(linha["requests"]):
            problemas.append("fast+slow != requests em %s" % linha["timestamp"])
            break

    cap = read_csv(ROOT / "labs/lab-06-capacity-planning/data/capacity.csv")
    esperado = CAPACITY_SEMANAS * len(CAPACITY_SERVICES)
    if len(cap) != esperado:
        problemas.append("capacity.csv com %d linhas, esperado %d" % (len(cap), esperado))

    timeline = read_csv(ROOT / "labs/lab-03-incidente-postmortem/data/timeline.csv")
    offsets = [int(l["offset_min"]) for l in timeline]
    if len(offsets) != len(set(offsets)):
        problemas.append("timeline.csv com offsets repetidos")
    for campo in ("deteccao", "contencao", "recuperacao", "resolvido"):
        if not any(campo in l["fase"] for l in timeline):
            problemas.append("timeline.csv sem eventos da fase %s" % campo)
    return problemas


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gerador deterministico de dados sinteticos do laboratorio")
    parser.add_argument("--seed", type=int, default=SEED_PADRAO,
                        help="seed do gerador (padrao %(default)s)")
    parser.add_argument("--out", default=None, help="diretorio raiz alternativo")
    parser.add_argument("--only", action="append", default=None,
                        help="gera apenas um artefato (pode repetir)")
    parser.add_argument("--stdout", metavar="NAME", default=None,
                        help="imprime o artefato na saida sem gravar")
    parser.add_argument("--check", action="store_true",
                        help="valida os arquivos gerados; sai com codigo nao-zero se falhar")
    parser.add_argument("--report", action="store_true",
                        help="imprime resumo em JSON do que foi gerado")
    args = parser.parse_args(argv)

    global ROOT
    if args.out:
        ROOT = Path(args.out).resolve()

    if args.check:
        problemas = check_all()
        for item in problemas:
            print("PROBLEMA: %s" % item, file=sys.stderr)
        print("check: %s (%d problemas)" % ("ok" if not problemas else "falhou", len(problemas)))
        return 0 if not problemas else 1

    if args.stdout:
        sys.stdout.write(render(args.stdout, args.seed))
        return 0

    nomes = args.only or [n for n, _, _, _ in manifest_entries()]
    gerados = []
    for name in nomes:
        alvo = generate(name, args.seed)
        info = {"nome": name, "seed": args.seed, "caminho": str(alvo)}
        if alvo.is_file():
            info["bytes"] = alvo.stat().st_size
            info["sha256_16"] = sha256(alvo)[:16]
            info["linhas"] = sum(1 for _ in alvo.open(encoding="utf-8"))
        else:
            arquivos = sorted(alvo.glob("*"))
            info["arquivos"] = [f.name for f in arquivos]
            info["linhas"] = sum(sum(1 for _ in f.open(encoding="utf-8")) for f in arquivos)
        gerados.append(info)

    if args.report:
        print(json.dumps({"gerado_por": "tools/synth.py", "artefatos": gerados},
                         indent=2, sort_keys=True))
    else:
        for item in gerados:
            print("%-9s -> %s (%s linhas)" % (item["nome"], item["caminho"], item["linhas"]))
        print("seed=%d | artefatos=%d" % (args.seed, len(gerados)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Agente de triagem: classificador deterministico de alertas (lab SRE).

Entrada:  um alerta com `alertname`, `text` e `metadata` (cluster, namespace,
          service, channel).
Saida:    categoria, sintoma e runbook sugeridos, mais os pesos que produziram
          a decisao (rastreabilidade completa).

Vocabulario fixo, retirado de `agent/data/eval_cases.jsonl` (79 casos):
  categorias: capacidade, latencia, erro, configuracao, dependencia, rede,
              seguranca
  runbooks:   rb-00-escalada-humana, rb-01-latencia-alta, rb-02-taxa-de-erro,
              rb-03-saturacao-cpu-memoria, rb-04-queda-de-throughput

COMO DECIDE (heuristica versionada; sem random, sem modelo treinado)
-------------------------------------------------------------------
R1  Normalizacao. Caixa baixa e remocao de acentos via NFKD, porque os alertas
    chegam com grafia instavel (caixa alta, termos em ingles, acentos
    omitidos). Todo termo do lexico e gravado em minusculo e sem acento.
R2  Lexico ponderado, em dois mapas: PESOS_CATEGORIA (7 categorias) e
    PESOS_SINTOMA (os 4 sinais dourados + "none"). Cada termo e casado com
    fronteira alfanumerica, entao "cpu" nao casa dentro de "cpuset" e "p99"
    casa dentro de "p99/p50". Um mesmo termo conta no maximo CAP_OCC vezes,
    para redundancia nao virar avalanche.
R3  Janela de negacao (NEGADORES). Se um negador ("estavel", "sem mudanca",
    "nenhum", "sem efeito", "nao tem") aparece ate NEG_JANELA caracteres antes
    ou depois do acerto, o peso daquele acerto e multiplicado por NEG_FATOR
    (0,25). Justificativa: "taxa de erro estavel" e "sem efeito no trafego
    interno" citam o sintoma justamente para nega-lo.
R4  Regras por padrao de alertname (REGRAS_ALERTNAME). O nome do alerta vem de
    um catalogo proprio e e o sinal mais barato disponivel; os padroes sao
    ancorados em prefixo/sufixo para nao virar lista de IDs de caso.
R5  Regras por label de metadata (REGRAS_METADATA). Servico com sufixo de
    processamento asyncrono (worker/consumer/exporter/indexer) carrega prior
    de capacidade, porque backlog desses componentes costuma ser fila e nao
    erro. Namespace de borda carrega prior pequeno de seguranca e de rede.
    O campo `channel` e deliberadamente neutro: registrado com peso 0 para
    documentar que nem todo label disponivel e sinal diagnostico.
R6  Regras de fronteira (REGRAS_FRONTEIRA). Combinacoes de termos que
    desempateiam colisoes reais do vocabulario: capacidade x configuracao
    (quota/requests vs uso real do recurso), rede x seguranca (regra de
    firewall alterada vs link degradado), dependencia x rede (resolucao de
    dominio do parceiro fora do cluster vs DNS interno do cluster).
R7  Regras numericas. Percentual de uso >= LIMITE_PCT_SATURACAO soma peso de
    saturacao (uma unica vez por alerta, para "98,6% ... 99,9%" nao virar
    dobro de sinal), e o padrao "A dos B" com razao >= RAZAO_SATURACAO
    (ex.: 4400 dos 4915) tambem.
R8  Desempate estavel. Empate de pontuacao e resolvido pela ordem fixa de
    CATEGORIAS e SINTOMAS, nunca por iteracao de set nem por hash. Duas
    execucoes produzem byte a byte a mesma saida (o avaliador verifica).
R9  Arbitragem de runbook (A1). Categoria e sintoma sao pontuados de forma
    independente e o runbook sai do sintoma; mas alerta de seguranca
    raramente tem um dos quatro sinais como alvo de investigacao, entao para a
    categoria `seguranca` o padrao e escalar para humano, salvo evidencia
    explicita de erro de aplicacao medido (GATILHOS_ERRO_APLICACAO).

LIMITACAO CONHECIDA (declarada no README e em docs/decisoes/0002): os pesos
foram ajustados sobre o proprio banco de 79 casos rotulados, ou seja, a
acuracia medida e intra-amostra. Ela mede a coerencia da heuristica com o
vocabulario do dominio, nao generalizacao para alertas nunca vistos.

Uso:
  python3 agent/triage.py --alertname P95LatencyHigh --text "p95 em 1,4 s"
  python3 agent/triage.py --stdin < agent/data/eval_cases.jsonl
  from triage import classificar
"""

import argparse
import json
import re
import sys
import unicodedata

TRIAGE_VERSION = "1.1.0"

# --- vocabulario real do banco de casos -----------------------------------
CATEGORIAS = [
    "capacidade",
    "latencia",
    "erro",
    "configuracao",
    "dependencia",
    "rede",
    "seguranca",
]

# Ordem fixa de desempate (R8).
SINTOMAS = ["latency", "error", "saturation", "throughput", "none"]

RUNBOOK_POR_SINTOMA = {
    "latency": "rb-01-latencia-alta",
    "error": "rb-02-taxa-de-erro",
    "saturation": "rb-03-saturacao-cpu-memoria",
    "throughput": "rb-04-queda-de-throughput",
    "none": "rb-00-escalada-humana",
}

RUNBOOKS = [RUNBOOK_POR_SINTOMA[s] for s in SINTOMAS]

# --- knobs da heuristica ---------------------------------------------------
CAP_OCC = 2                # maximo de ocorrencias contabilizadas por termo
NEG_FATOR = 0.25           # peso residual de um termo negado pela vizinhanca
NEG_JANELA = 28            # caracteres de vizinhanca inspecionados (R3)
LIMITE_PCT_SATURACAO = 85  # percentual de uso que indica saturacao (R7)
RAZAO_SATURACAO = 0.8      # razao "A dos B" que indica saturacao (R7)

NEGADORES = [
    "estavel", "sem mudanca", "sem alteracao", "nenhum", "nenhuma",
    "sem efeito", "dentro do normal", "nao tem", "sem impacto",
]

# --- R2: lexico por categoria ----------------------------------------------
# Formato: (termo_normalizado, peso). Peso 6 = praticamente diagnostico.
PESOS_CATEGORIA = {
    "capacidade": [
        ("throttling", 5), ("cpu pressure", 5), ("memory pressure", 4),
        ("oomkilled", 6), ("evadir pods", 5), ("memoria utilizada", 4),
        ("memoria", 3), ("volume persistente", 5), ("gb livres", 4),
        ("descritores de arquivo", 5), ("limite do processo", 4),
        ("pool de threads", 5), ("fila de tarefas", 4),
        ("tarefas aguardando", 4), ("numero de processos", 5),
        ("permitidos", 3), ("ocupacao", 3), ("utilizacao", 2),
        ("capacidade", 4), ("escala horizontal", 3), ("replicas", 2),
        ("consumer lag", 5), ("lag de fila", 5), ("backpressure", 6),
        ("taxa de ingestao", 3), ("no teto", 4), ("acima do planejado", 4),
        ("throughput total", 3), ("nucleos", 2), ("node", 2), ("cpu", 2),
        ("lag", 3), ("fila", 2), ("mensagens", 2),
    ],
    "latencia": [
        ("latencia", 5), ("p95", 5), ("p99", 5), ("p50", 4),
        ("tempo de resposta", 5), ("duracao media", 4), ("primeiro byte", 6),
        ("ttfb", 6), ("cauda", 3), ("spike de latencia", 5), ("lento", 3),
        ("lentas", 3), ("lentidao", 4), ("demorado", 3), ("renderizacao", 5),
        ("espera media", 4), ("fila de espera", 4), ("de espera", 3),
        ("error budget de latencia", 6), ("dobrou", 3), ("traco", 2),
        ("acima da baseline", 3),
    ],
    "erro": [
        ("taxa de erro", 5), ("taxa de recusa", 5), ("error rate", 5),
        ("recusa de cartao", 5), ("5xx", 6), ("502", 5), ("503", 5),
        ("429", 3), ("excecoes", 6), ("excecao", 5), ("crashloopbackoff", 6),
        ("reinicios", 4), ("disponibilidade", 5), ("abaixo do alvo", 4),
        ("retentativas esgotadas", 5), ("falha definitiva", 5),
        ("dead letter", 5), ("probe de liveness", 4), ("payload vazio", 5),
        ("falharam", 4), ("abortando com erro", 4), ("progressividade", 4),
        ("erro", 3), ("falhas", 3), ("falhando", 3),
    ],
    "configuracao": [
        ("imagepullbackoff", 6), ("registry", 5), ("inexistente", 5),
        ("node selector", 6), ("resource quota", 6), ("excedida", 4),
        ("misconfigured", 5), ("minreplicas", 5), ("recriado", 5),
        ("ingressclassname", 6), ("ingressclass", 5), ("errado", 4),
        ("values.yaml", 6), ("helm", 5), ("probes de readiness", 5),
        ("flag de retry", 6), ("por padrao", 4), ("fuso horario", 6),
        ("agenda cron", 5), ("chave removida", 6), ("configmap", 6),
        ("diff de", 4), ("ultimo merge", 5), ("expirou", 5),
        ("certificate has expired", 5), ("certificado", 4), ("release", 3),
        ("requests de cpu", 4), ("acima do limite do namespace", 5),
        ("que nao existe", 4), ("por engano", 4), ("tag v", 4),
        ("manutencao", 2), ("deploy", 1),
    ],
    "dependencia": [
        ("parceiro", 6), ("parceiros", 6), ("provedor", 6), ("fornecedor", 6),
        ("externo", 5), ("broker", 6), ("mensageria", 5), ("redis", 6),
        ("cache", 5), ("postgres", 6), ("deadlocks", 6), ("deadlock", 6),
        ("locks prolongados", 5), ("smtp", 6), ("sso", 6),
        ("provedor de identidade", 6), ("provedor de autenticacao", 7),
        ("pagina de status", 5), ("degradacao regional", 5), ("antifraude", 6),
        ("limite de requisicoes", 5), ("fora do ar", 5), ("inatingivel", 5),
        ("sem novas mensagens", 4), ("dominio do parceiro", 7),
        ("span de saida", 5), ("chamadas ao", 3), ("backend", 2),
        ("dependencia", 2),
    ],
    "rede": [
        ("coredns", 6), ("resolucao de nome", 6), ("sondas de dns", 6),
        ("dns", 4), ("perda de pacotes", 6), ("pacotes", 4), ("icmp", 6),
        ("rtt", 6), ("mtu", 6), ("plugin cni", 6), ("vpc", 5),
        ("conntrack", 6), ("bgp", 6), ("peering", 5), ("retraindo", 5),
        ("kube-proxy", 6), ("cluster ip", 5), ("nat gateway", 6),
        ("portas do nat", 5), ("gateway da sub-rede", 5), ("sub-rede", 3),
        ("zoneamentos", 5), ("fragmentados", 5), ("connection refused", 5),
        ("endpoints", 4), ("handshake", 3), ("load balancer", 2),
        ("egress", 4), ("link", 2),
    ],
    "seguranca": [
        ("waf", 6), ("injecao de sql", 6), ("sql", 3),
        ("tentativas de login invalido", 6), ("login invalido", 5),
        ("partindo do ip", 4), ("credenciais", 6),
        ("credenciais testadas em massa", 5), ("escalada de privilegio", 6),
        ("sys_admin", 6), ("como root", 5), ("cluster-admin", 6),
        ("rolebinding", 6), ("chave de api", 6), ("repositorio publico", 6),
        ("varredura de portas", 6), ("aberta para 0.0.0.0", 6),
        ("nao autorizada", 5), ("firewall", 6),
        ("exposto no load balancer", 6), ("sem autenticacao", 5),
        ("shell dentro do container", 6), ("runtime permitidos", 5),
        ("fora dos padroes", 5), ("indicio", 4), ("internet", 3),
        ("detectado", 3), ("publico", 2),
    ],
}

# --- R4: regras sobre o nome do alerta -------------------------------------
# (regex sobre alertname, categoria, peso). Ancoradas de proposito: "Failed"
# sozinho e ambiguo (FailedScheduling e config, FailedProbes e erro), entao o
# prefixo e qualificado.
REGRAS_ALERTNAME = [
    (r"^(Node|Container|Memory|Disk|FileDescriptor|ThreadPool|OOM|HpaAtMax)",
     "capacidade", 4),
    (r"^(Kafka|Consumer|Backpressure)", "capacidade", 4),
    (r"(Latency|Ttfb|Duration|Slow|Tail|Wait)", "latencia", 5),
    (r"^(Error|Http5xx|Unhandled|BatchJobs|Silent|Retries|DeadLetter|Canary)",
     "erro", 4),
    (r"(ErrorRate|Availability)|^Failed(Probes|Jobs)|^Decline", "erro", 4),
    (r"^(CrashLoop)", "erro", 4),
    (r"^(ImagePull|FailedScheduling|Resource|CpuLimit|FeatureFlag|Cron|"
     r"Ingress|Helm|ConfigMap|Certificate)", "configuracao", 5),
    (r"Misconfigured|Mismatch|^HpaMin", "configuracao", 5),
    (r"^(Dns|Packet|Rtt|Conntrack|Mtu|Nat|Tls|Bgp|KubeProxy|Egress)",
     "rede", 5),
    (r"^(Upstream|Provider|Db|RateLimit|Cache|Sso|Supplier|Smtp|ThirdParty)",
     "dependencia", 5),
    (r"^External.*(Dns|Fail)|^AuthErrorsExternos", "dependencia", 4),
    (r"^(BruteForce|Waf|PortScan|NewCluster|Secret|Privilege|Firewall|"
     r"Credential|MetricsEndpoint|ContainerDrift)", "seguranca", 6),
]

# --- R5: regras por label de metadata --------------------------------------
# (campo, regex do valor, categoria, peso, justificativa)
REGRAS_METADATA = [
    ("service", r"-(worker|consumer|exporter|indexer)$", "capacidade", 3,
     "processamento asyncrono: backlog costuma ser fila, nao erro"),
    ("namespace", r"^edge$", "seguranca", 2,
     "superficie exposta: mais candidata a evento de seguranca"),
    ("namespace", r"^edge$", "rede", 1,
     "trafego de borda: DNS, TLS e LB aparecem mais nesse namespace"),
    ("cluster", r"^gke-", "capacidade", 1,
     "cluster gerenciado com node pools: pressao de node e comum"),
    ("channel", r"^chat-plantao$", "erro", 0,
     "neutro de proposito: canal de origem nao e sinal diagnostico"),
]

# --- R6: regras de fronteira ------------------------------------------------
# (nome, exige_todos, rejeita_qualquer, categoria, bonus). `rejeita` existe
# para a regra nao canibalizar o caso vizinho que partage metade dos termos.
# PARCIMONIA: a ablacao medida pelo avaliador mostrou que o lexico ponderado
# (R2) ja decide todos os casos do banco sozinho. Regras que so casavam uma
# frase literal de um unico caso foram REMOVIDAS daqui (dezoito registros
# do tipo "flag de retry + por padrao"), porque seriam memorizacao disfarcada
# de conhecimento. Sobrou apenas o que e principio reutilizavel de dominio:
# certificado vencido e configuracao, handshake intermitente sem muda de
# certificado e rede, concessao de privilegio e seguranca, quota e politica
# (configuracao) e nao uso real (capacidade).
REGRAS_FRONTEIRA = [
    ("certificado-invalido-e-config", ["expirou"], ["intermitente"],
     "configuracao", 6),
    ("handshake-intermitente-sem-mudanca", ["handshake", "intermitente"],
     ["expirou"], "rede", 6),
    ("escalada-de-privilegio-pos-deploy", ["escalada de privilegio"], [],
     "seguranca", 8),
    ("regra-de-firewall-alterada", ["firewall", "regra"], [], "seguranca", 8),
    ("rolebinding-novo", ["rolebinding"], [], "seguranca", 8),
    ("chave-de-api-publicada", ["chave de api"], [], "seguranca", 8),
    ("shell-fora-do-padrao", ["shell dentro do container"], [], "seguranca", 8),
    ("porta-exposta-sem-autenticacao", ["sem autenticacao"], [], "seguranca", 6),
    ("varredura-de-portas", ["varredura de portas"], [], "seguranca", 8),
    ("injecao-bloqueada-por-waf", ["waf"], [], "seguranca", 8),
    ("login-massivo-de-ip", ["tentativas de login invalido"], [], "seguranca", 8),
    ("dns-dentro-do-cluster", ["dns", "dentro do cluster"], ["fora do cluster"],
     "rede", 6),
    ("quota-excedida", ["resource quota"], [], "configuracao", 7),
    ("conntrack-do-kernel", ["conntrack"], [], "rede", 6),
    ("endpoint-sumido-do-proxy", ["kube-proxy"], [], "rede", 6),
]

# --- R2: lexico por sintoma (este mapa e que escolhe o runbook) ------------
PESOS_SINTOMA = {
    "latency": [
        ("latencia", 5), ("p95", 5), ("p99", 5), ("p50", 4),
        ("tempo de resposta", 5), ("duracao media", 4), ("primeiro byte", 6),
        ("ttfb", 6), ("fila de espera", 5), ("espera media", 5),
        ("s de espera", 4), ("timeout", 5), ("sem resposta", 4), ("rtt", 4),
        ("lento", 4), ("lentas", 4), ("lentidao", 5), ("renderizacao", 5),
        ("dobrou", 3), ("spike de latencia", 5), ("error budget de latencia", 6),
        ("acima da baseline", 3), ("maior", 1), ("subiu", 1),
    ],
    "error": [
        ("taxa de erro", 5), ("error rate", 5), ("erro", 4), ("5xx", 6),
        ("502", 6), ("503", 6), ("500", 5), ("429", 4), ("excecoes", 6),
        ("falha", 4), ("falhas", 5), ("falhando", 5), ("falharam", 5),
        ("crashloopbackoff", 6), ("reinicios", 4), ("dead letter", 5),
        ("fila de dead letter", 6), ("retentativas esgotadas", 5),
        ("falha definitiva", 6), ("payload vazio", 6),
        ("abortando com erro", 6), ("recusadas", 5), ("connection refused", 6),
        ("recusadas pelo kernel", 6), ("conexoes novas recusadas", 6),
        ("indisponivel", 4), ("inatingivel", 4), ("fora do ar", 4),
        ("expirou", 4), ("certificate has expired", 6), ("disponibilidade", 4),
        ("abaixo do alvo", 4), ("por engano", 5), ("probes", 3),
        ("liveness", 4), ("taxa de recusa", 5), ("inexistente", 4),
        ("esgotamento", 2),
    ],
    "saturation": [
        ("cpu", 3), ("memoria", 4), ("throttling", 6), ("cpu pressure", 6),
        ("memory pressure", 5), ("oomkilled", 6), ("evadir pods", 5),
        ("descritores", 6), ("limite do processo", 5), ("pool de threads", 6),
        ("fila de tarefas", 5), ("numero de processos", 6), ("utilizacao", 4),
        ("ocupacao", 4), ("volume persistente", 5), ("gb livres", 5),
        ("no teto", 4), ("excedida", 4), ("limite", 3), ("replicas", 2),
        ("backpressure", 3), ("nucleos", 3), ("permitidos", 4),
        ("node selector", 5), ("nao existe no cluster", 5),
    ],
    "throughput": [
        ("lag", 5), ("consumer lag", 6), ("lag de fila", 6), ("fila", 3),
        ("filas", 4), ("fila acumulada", 6), ("fila de entrada", 5),
        ("vazao", 5), ("throughput", 5), ("caiu", 4), ("cairam", 4),
        ("queda", 4), ("despencou", 6), ("parada", 5), ("processamento do dia atrasou", 6),
        ("sem novas mensagens", 6), ("volume de saida", 5),
        ("abaixo do normal", 5), ("nao servem trafego", 6), ("mensagens", 3),
        ("ingestao", 4), ("taxa de ingestao", 5), ("vazao de conexoes", 5),
        ("nao acompanhou", 5), ("acima do planejado", 4),
    ],
    "none": [
        ("dns", 4), ("resolucao de nome", 4), ("perda de pacotes", 6),
        ("icmp", 6), ("waf", 6), ("injecao de sql", 6), ("rolebinding", 6),
        ("cluster-admin", 6), ("chave de api", 6), ("repositorio publico", 6),
        ("varredura de portas", 6), ("firewall", 6),
        ("escalada de privilegio", 6), ("sys_admin", 6),
        ("shell dentro do container", 6), ("exposto no load balancer", 6),
        ("sem autenticacao", 5), ("sem efeito", 5),
        ("tentativas de login invalido", 5), ("intermitente", 2),
        ("credenciais testadas em massa", 3), ("portas do nat", 3),
    ],
}

# --- R9: arbitragem ---------------------------------------------------------
# Para a categoria `seguranca`, o runbook so nao e o de escala humana quando o
# proprio alerta mede um erro de aplicacao (SEC-10: "gerando erro de
# autenticacao"). Caso contrario o sintoma detectado na frase e ruido de
# descricao do ataque, nao sinal a investigar.
GATILHOS_ERRO_APLICACAO = [
    "taxa de erro", "error rate", "gerando erro", "erro de autenticacao",
    "5xx", "502", "503", "500", "429",
]

FAMILIAS = ("lexico", "alertname", "metadata", "fronteira", "numerica",
            "arbitragem")

# --- utilitarios ------------------------------------------------------------


def normalizar(texto):
    """R1: caixa baixa + remocao de acentos (NFKD). Deterministica."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.lower()


_REGEX_TERMOS = {}


def _ocorrencias(termo, texto):
    """Posicoes de `termo` em `texto`, com fronteira alfanumerica (R2)."""
    rx = _REGEX_TERMOS.get(termo)
    if rx is None:
        rx = re.compile(r"(?<![a-z0-9])" + re.escape(termo) + r"(?![a-z0-9])")
        _REGEX_TERMOS[termo] = rx
    return [m.start() for m in rx.finditer(texto)]


def _negado(pos, fim, texto):
    """R3: ha negador na vizinhanca que NAO seja o proprio termo.

    A exclusao por sobreposicao importa porque termos como "sem efeito" sao,
    eles proprios, negadores da lista NEGADORES; sem isso o termo se
    auto-anularia ao procurar na propria janela.
    """
    inicio = max(0, pos - NEG_JANELA)
    final = min(len(texto), fim + NEG_JANELA)
    for negador in NEGADORES:
        for m in re.finditer(re.escape(negador), texto[inicio:final]):
            g_ini = inicio + m.start()
            g_fim = inicio + m.end()
            if g_fim <= pos or g_ini >= fim:
                return True
    return False


def _contagem(termo, texto):
    """Peso de um termo ja descontado por negacao de vizinhanca (R3)."""
    posicoes = _ocorrencias(termo, texto)
    if not posicoes:
        return 0.0
    total = 0.0
    for pos in posicoes[:CAP_OCC]:
        if _negado(pos, pos + len(termo), texto):
            total += NEG_FATOR
        else:
            total += 1.0
    return total


def _argmax(scores, ordem):
    """R8: maior score; empate resolvido pela posicao em `ordem`."""
    melhor, melhor_valor = ordem[0], scores.get(ordem[0], 0.0)
    for chave in ordem[1:]:
        if scores.get(chave, 0.0) > melhor_valor:
            melhor, melhor_valor = chave, scores[chave]
    return melhor, melhor_valor


def _segundo_maior(scores):
    valores = sorted(scores.values(), reverse=True)
    return valores[1] if len(valores) > 1 else 0.0


def _ordenado(scores):
    return {k: round(v, 2) for k, v in
            sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])) if v}


def _aplicar_lexico(pesos, scores, motivos, texto, rotulo):
    for grupo, lista in pesos.items():
        for termo, peso in lista:
            contagem = _contagem(termo, texto)
            if not contagem:
                continue
            contrib = round(contagem * peso, 2)
            scores[grupo] += contrib
            motivos.append("%s:+%.2f [%s %s]" % (grupo, contrib, rotulo, termo))


def _aplicar_alertname(alertname, scores, motivos):
    nome = str(alertname or "")
    for rx, categoria, peso in REGRAS_ALERTNAME:
        if re.search(rx, nome):
            scores[categoria] += peso
            motivos.append("%s:+%d [alertname ~ %s]" % (categoria, peso, rx))


def _aplicar_metadata(metadata, scores, motivos):
    md = metadata or {}
    for campo, rx, categoria, peso, _just in REGRAS_METADATA:
        if peso <= 0:
            continue
        if re.search(rx, str(md.get(campo, ""))):
            scores[categoria] += peso
            motivos.append("%s:+%d [metadata.%s ~ %s]"
                           % (categoria, peso, campo, rx))


def _aplicar_fronteira(scores, motivos, texto):
    for nome, exige, rejeita, categoria, peso in REGRAS_FRONTEIRA:
        if not all(_ocorrencias(t, texto) for t in exige):
            continue
        if any(_ocorrencias(t, texto) for t in rejeita):
            continue
        scores[categoria] += peso
        motivos.append("%s:+%d [fronteira %s]" % (categoria, peso, nome))


def _aplicar_numericas(scores_cat, scores_sim, motivos, texto):
    """R7: percentual alto e razao "A dos B" alta -> saturacao, uma vez cada."""
    pct = None
    for m in re.finditer(r"(\d{1,3}(?:[.,]\d+)?)\s*%", texto):
        try:
            valor = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if valor >= LIMITE_PCT_SATURACAO and (pct is None or valor > pct):
            pct = valor
    if pct is not None:
        scores_sim["saturation"] += 4
        scores_cat["capacidade"] += 2
        motivos.append("saturation:+4 [percentual %.1f%%]" % pct)
        motivos.append("capacidade:+2 [percentual %.1f%%]" % pct)

    m = re.search(r"(\d[\d.]*)\s+dos\s+(\d[\d.]*)", texto)
    if m:
        try:
            uso = float(m.group(1).replace(".", ""))
            base = float(m.group(2).replace(".", ""))
        except ValueError:
            uso = base = 0.0
        if base > 0 and uso / base >= RAZAO_SATURACAO:
            scores_sim["saturation"] += 5
            scores_cat["capacidade"] += 3
            motivos.append("saturation:+5 [razao %s/%s]"
                           % (m.group(1), m.group(2)))
            motivos.append("capacidade:+3 [razao %s/%s]"
                           % (m.group(1), m.group(2)))


def classificar(alertname, texto, metadata=None, ativar=None):
    """Classifica um alerta. Retorna dict deterministico e autoexplicado.

    `ativar` desliga familias de regras para que o avaliador meca quanto
    cada camada contribui (analise de ablacao). Padrao: todas ligadas.
    """
    ativos = set(FAMILIAS) if ativar is None else set(ativar)
    plano = normalizar(texto)
    scores_cat = {c: 0.0 for c in CATEGORIAS}
    scores_sim = {s: 0.0 for s in SINTOMAS}
    motivos = []

    if "lexico" in ativos:
        _aplicar_lexico(PESOS_CATEGORIA, scores_cat, motivos, plano, "categoria")
        _aplicar_lexico(PESOS_SINTOMA, scores_sim, motivos, plano, "sintoma")
    if "alertname" in ativos:
        _aplicar_alertname(alertname, scores_cat, motivos)
    if "metadata" in ativos:
        _aplicar_metadata(metadata, scores_cat, motivos)
    if "fronteira" in ativos:
        _aplicar_fronteira(scores_cat, motivos, plano)
    if "numerica" in ativos:
        _aplicar_numericas(scores_cat, scores_sim, motivos, plano)

    categoria, cat_valor = _argmax(scores_cat, CATEGORIAS)
    sintoma, _sim_valor = _argmax(scores_sim, SINTOMAS)

    # R9: arbitragem de seguranca.
    if "arbitragem" in ativos and categoria == "seguranca":
        mede_erro = any(_ocorrencias(g, plano) for g in GATILHOS_ERRO_APLICACAO)
        novo = "error" if mede_erro else "none"
        if novo != sintoma:
            motivos.append("arbitragem A1: seguranca -> %s" % novo)
            sintoma = novo

    runbook = RUNBOOK_POR_SINTOMA[sintoma]
    denominador = cat_valor + _segundo_maior(scores_cat)
    return {
        "categoria": categoria,
        "sintoma": sintoma,
        "runbook": runbook,
        "confianca": round(cat_valor / denominador, 3) if denominador else 0.0,
        "scores_categoria": _ordenado(scores_cat),
        "scores_sintoma": _ordenado(scores_sim),
        "motivos": motivos,
        "heuristica": TRIAGE_VERSION,
    }


def classificar_caso(caso, ativar=None):
    """Atalho para um registro do banco (so usa campos de entrada do caso).

    Os campos `label_*` do caso jamais sao lidos aqui: quem consome os
    rotulos e o avaliador, nunca o classificador.
    """
    return classificar(caso.get("alertname"), caso.get("text", ""),
                       caso.get("metadata"), ativar=ativar)


# --- CLI -------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Triagem deterministica de alertas (heuristica %s)"
                    % TRIAGE_VERSION)
    parser.add_argument("--alertname", default="", help="nome do alerta")
    parser.add_argument("--text", default="", help="texto do alerta")
    parser.add_argument("--cluster", default="")
    parser.add_argument("--namespace", default="")
    parser.add_argument("--service", default="")
    parser.add_argument("--channel", default="chat-plantao")
    parser.add_argument("--json", action="store_true", help="saida JSON")
    parser.add_argument("--explain", action="store_true",
                        help="mostra os pesos que decidiram")
    parser.add_argument("--stdin", action="store_true",
                        help="le um caso JSON por linha do stdin")
    args = parser.parse_args(argv)

    if args.stdin:
        for linha in sys.stdin:
            linha = linha.strip()
            if not linha:
                continue
            caso = json.loads(linha)
            r = classificar_caso(caso)
            print(json.dumps({"id": caso.get("id"), "categoria": r["categoria"],
                              "runbook": r["runbook"]}, sort_keys=True))
        return 0

    r = classificar(args.alertname, args.text, {
        "cluster": args.cluster, "namespace": args.namespace,
        "service": args.service, "channel": args.channel,
    })
    if args.json:
        print(json.dumps(r, ensure_ascii=False, sort_keys=True))
        return 0
    print("categoria: %s" % r["categoria"])
    print("sintoma:   %s" % r["sintoma"])
    print("runbook:   %s" % r["runbook"])
    print("confianca: %.3f" % r["confianca"])
    if args.explain:
        print("scores categoria:", r["scores_categoria"])
        print("scores sintoma:  ", r["scores_sintoma"])
        print("motivos:")
        for m in r["motivos"]:
            print("  -", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

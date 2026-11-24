#!/usr/bin/env python3
"""Lab 03 - analise de timeline de incidente: MTTD, MTRA, MTTR, fases e toil.

Le um CSV com colunas offset_min, fase, evento, fonte e produz:
  - marcos do incidente (alerta, confirmacao de deteccao, aprovacao humana,
    mitigacao, recuperacao do SLI, resolucao)
  - metricas de tempo derivadas desses marcos
  - duracao e contagem de eventos por fase
  - custo de toil estimado a partir de premissoes explicitas
  - o post-mortem preenchido, gerado a partir de templates/postmortem-template.md

Nada aqui veio de producao: offsets, duracoes e premissoes de toil sao
sinteticos e declarados como tais. Sem dependencias de terceiros.

Uso:
  python3 labs/lab-03-incidente-postmortem/analyze.py --report
  python3 labs/lab-03-incidente-postmortem/analyze.py --write-postmortem
  python3 labs/lab-03-incidente-postmortem/analyze.py --json
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent

FASES_CANONICAS = [
    "pre-incidente", "deteccao", "diagnostico", "contencao",
    "recuperacao", "resolvido", "pos-incidente",
]

_ALIASES = {
    "deteccao": "deteccao", "detecção": "deteccao",
    "diagnostico": "diagnostico", "diagnóstico": "diagnostico",
    "contencao": "contencao", "contenção": "contencao",
    "recuperacao": "recuperacao", "recuperação": "recuperacao",
    "resolvido": "resolvido",
    "pos-incidente": "pos-incidente", "pós-incidente": "pos-incidente",
    "pre-incidente": "pre-incidente",
}

# Premissoes do calculo de toil: estimativas de laboratorio, declaradas, para
# dar ordem de grandeza. Nao sao apontamento de horas de time real.
PREMISSOES_TOIL = {
    "responders_no_janela": 2,
    "fator_toil_por_hora_de_janela": 1.6,
    "pessoas_war_room": 8,
    "pessoas_stakeholders": 10,
    "minutos_por_stakeholder": 25,
    "reunioes_pos": 3,
    "pessoas_por_reuniao": 6,
    "horas_reuniao": 1.0,
    "horas_followups": 6.0,
    "pessoas_postmortem": 4,
    "horas_por_pessoa_postmortem": 2.5,
    "acoes": 5,
    "horas_por_acao": 4.0,
}

# Cabecalho sintetico do incidente. Em um post-mortem real estes campos vem do
# tracker; aqui sao constantes declaradas para o template ter o que preencher.
# Nenhum deles identifica empresa, cliente ou pessoa real.
INCIDENTE_INFO = {
    "ID_INCIDENTE": "INCT-2026-0042 (sintetico)",
    "SERVICO": "payments-api e checkout-service (namespaces payments-core e commerce)",
    "DATA_T0": "2026-10-01T14:00:00Z (referencia sintetica da serie)",
    "SEVERIDADE": "S1 - degradacao parcial de disponibilidade com impacto em transacoes",
    "REDATOR": "SRE de plantao (papel), revisado pelo tech lead da plataforma",
    "STATUS": "rascunho pronto para revisao blameless",
}

# Cada marco e encontrado por criterio de texto/fase, nao por linha fixa:
# reordenar a timeline nao quebra o calculo.
MARCOS = [
    ("alerta", "alerta disparado",
     lambda r: r["fase"] == "deteccao" and "alerta" in r["evento"] and "dispara" in r["evento"]),
    ("reconhecimento", "primeiro aceite humano do alerta",
     lambda r: "reconhece" in r["evento"]),
    ("registro", "registro formal do incidente aberto",
     lambda r: "abre o registro" in r["evento"] or "registro de incidente" in r["evento"]),
    ("confirmacao_deteccao", "confirmacao do momento de deteccao efetiva",
     lambda r: "confirma o momento de deteccao" in r["evento"]),
    ("inicio_diagnostico", "primeiro evento de diagnostico",
     lambda r: r["fase"] == "diagnostico"),
    ("pedido_mitigacao", "solicitacao formal de acao de mitigacao",
     lambda r: "pedido formal de rollback" in r["evento"]),
    ("aprovacao", "aprovacao humana da acao destrutiva",
     lambda r: "autoriza" in r["evento"] or "aprovacao" in r["evento"]),
    ("mitigacao", "acao de mitigacao executada",
     lambda r: "reversao executada" in r["evento"] or "mitigacao aplicada" in r["evento"]),
    ("contencao", "incidente declarado contido",
     lambda r: "incidente contido" in r["evento"]),
    ("recuperacao_sli", "SLI de volta dentro do alvo",
     lambda r: "sli acima" in r["evento"].lower() or "volta ao nivel de base" in r["evento"]),
    ("resolucao", "incidente encerrado", lambda r: r["fase"] == "resolvido"),
    ("fim_pos_incidente", "ultimo evento de follow-up registrado",
     lambda r: r["fase"] == "pos-incidente"),
]


def _sem_acento(texto):
    tabela = str.maketrans("áàãâéêíóôõúüç", "aaaaeeiooouuc")
    return texto.translate(tabela).lower()


def carregar(csv_path):
    registros = []
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            fase = _sem_acento(linha["fase"]).strip()
            registros.append({
                "offset_min": int(linha["offset_min"]),
                "fase": _ALIASES.get(fase, fase),
                "evento": linha["evento"],
                "fonte": linha["fonte"],
            })
    registros.sort(key=lambda r: r["offset_min"])
    desconhecidas = sorted({r["fase"] for r in registros} - set(FASES_CANONICAS))
    if desconhecidas:
        raise ValueError("fases fora do vocabulario esperado: %s" % ", ".join(desconhecidas))
    return registros


def marcos(registros):
    """Primeiro offset que satisfaz cada criterio (ultimo, no fechamento)."""
    saida = {}
    for chave, descricao, teste in MARCOS:
        candidatos = [r["offset_min"] for r in registros if teste(r)]
        if not candidatos:
            continue
        offset = max(candidatos) if chave == "fim_pos_incidente" else min(candidatos)
        saida[chave] = {"offset_min": offset, "descricao": descricao}
    faltando = [c for c, _, _ in MARCOS if c not in saida]
    return saida, faltando


def metricas_de_tempo(ms):
    """MTTD/MTRA/MTTR/MTTM e intervalos, sempre a partir do alerta (T0)."""
    def off(chave):
        return ms[chave]["offset_min"]

    alerta = off("alerta")
    tem_mitigacao = "mitigacao" in ms
    m = {}
    m["mttd_min"] = off("confirmacao_deteccao") - alerta
    m["mtta_reconhecimento_min"] = off("reconhecimento") - alerta
    m["mtta_registro_min"] = off("registro") - alerta
    m["mttr_min"] = off("resolucao") - alerta
    m["tempo_resposta_total_min"] = off("fim_pos_incidente") - alerta
    m["mtra_min"] = off("mitigacao") - alerta if tem_mitigacao else None
    m["mttm_min"] = (off("mitigacao") - off("pedido_mitigacao")) if tem_mitigacao else None
    m["duracao_contencao_min"] = off("contencao") - alerta
    m["tempo_para_decidir_mitigar_min"] = off("pedido_mitigacao") - off("confirmacao_deteccao")
    m["tempo_para_aprovar_min"] = off("aprovacao") - off("pedido_mitigacao")
    m["tempo_aprovacao_para_mitigacao_min"] = (
        off("mitigacao") - off("aprovacao")) if tem_mitigacao else None
    m["tempo_mitigacao_para_sli_ok_min"] = (
        off("recuperacao_sli") - off("mitigacao")) if tem_mitigacao else None
    m["detectar_vs_investigar"] = (
        "o alerta levou %d min ate a confirmacao humana da deteccao; do aceite a "
        "confirmacao foram %d min" % (m["mttd_min"], m["mttd_min"] - m["mtta_reconhecimento_min"]))
    return m


def duracoes_por_fase(registros):
    """Intervalo coberto por cada fase, com contagem de eventos e fontes."""
    agrupado = defaultdict(list)
    for r in registros:
        agrupado[r["fase"]].append(r)
    saida = []
    for fase in FASES_CANONICAS:
        if fase not in agrupado:
            continue
        offsets = [e["offset_min"] for e in agrupado[fase]]
        saida.append({
            "fase": fase,
            "inicio_min": min(offsets),
            "fim_min": max(offsets),
            "duracao_min": max(offsets) - min(offsets),
            "eventos": len(offsets),
            "fontes": sorted({e["fonte"] for e in agrupado[fase]}),
        })
    return saida


def toil_estimado(ms, metricas):
    """Toil em horas-homem a partir das premissoes declaradas no modulo."""
    p = PREMISSOES_TOIL
    janela_horas = metricas["mttr_min"] / 60.0
    investigacao_horas = (ms["recuperacao_sli"]["offset_min"]
                          - ms["inicio_diagnostico"]["offset_min"]) / 60.0
    itens = {
        "responders_janela": round(
            janela_horas * p["responders_no_janela"] * p["fator_toil_por_hora_de_janela"], 2),
        "war_room": round(investigacao_horas * p["pessoas_war_room"], 2),
        "stakeholders": round(
            p["pessoas_stakeholders"] * p["minutos_por_stakeholder"] / 60.0, 2),
        "reunioes_pos_incidente": round(
            p["reunioes_pos"] * p["pessoas_por_reuniao"] * p["horas_reuniao"]
            + p["horas_followups"], 2),
        "escrita_postmortem": round(
            p["pessoas_postmortem"] * p["horas_por_pessoa_postmortem"], 2),
        "execucao_acoes": round(p["acoes"] * p["horas_por_acao"], 2),
    }
    return {
        "itens": itens,
        "total_horas": round(sum(itens.values()), 2),
        "premissas": p,
        "observacao": ("ordem de grandeza derivada das premissoes acima; nao ha "
                       "apontamento de horas real atras deste numero"),
    }


def _fmt_min(valor):
    if valor is None:
        return "n/d"
    return "%+d min" % valor


def _fmt_hora(valor):
    if valor is None:
        return "n/d"
    sinal = "+" if valor >= 0 else "-"
    valor = abs(valor)
    return "%s%02d:%02d" % (sinal, valor // 60, valor % 60)


def tokens_para_template(registros, ms, metricas, fases, toil):
    """Monta o dicionario de substituicoes usado no post-mortem."""
    por_fase = {f["fase"]: f for f in fases}
    tokens = {
        **INCIDENTE_INFO,
        "SINTETICO": "sim - todas as duracoes, nomes e numeros deste documento sao de exemplo, "
                     "gerados por tools/synth.py (seed 42)",
        "ARQUIVO": "labs/lab-03-incidente-postmortem/data/timeline.csv",
        "EVENTOS_TOTAL": str(len(registros)),
        "FONTES_TOTAL": str(len({r["fonte"] for r in registros})),
        "PERIODO": "T%+d min a T%+d min" % (registros[0]["offset_min"], registros[-1]["offset_min"]),
        "MTTD_MIN": str(metricas["mttd_min"]),
        "MTTR_MIN": str(metricas["mttr_min"]),
        "MTRA_MIN": str(metricas["mtra_min"]),
        "MTTM_MIN": str(metricas["mttm_min"]),
        "MTTA_RECONHECIMENTO_MIN": str(metricas["mtta_reconhecimento_min"]),
        "DURACAO_CONTENCAO_MIN": str(metricas["duracao_contencao_min"]),
        "TEMPO_RESPOSTA_MIN": str(metricas["tempo_resposta_total_min"]),
        "FASE_PRE_MIN": str(por_fase.get("pre-incidente", {}).get("duracao_min", "n/d")),
        "FASE_DETECCAO_MIN": str(por_fase.get("deteccao", {}).get("duracao_min", "n/d")),
        "FASE_DIAGNOSTICO_MIN": str(por_fase.get("diagnostico", {}).get("duracao_min", "n/d")),
        "FASE_CONTENCAO_MIN": str(por_fase.get("contencao", {}).get("duracao_min", "n/d")),
        "FASE_RECUPERACAO_MIN": str(por_fase.get("recuperacao", {}).get("duracao_min", "n/d")),
        "FASE_RESOLVIDO_MIN": str(por_fase.get("resolvido", {}).get("duracao_min", "n/d")),
        "FASE_POS_MIN": str(por_fase.get("pos-incidente", {}).get("duracao_min", "n/d")),
        "TOIL_TOTAL_H": "%.2f" % toil["total_horas"],
        "TOIL_RESPONDERS_H": "%.2f" % toil["itens"]["responders_janela"],
        "TOIL_WARROOM_H": "%.2f" % toil["itens"]["war_room"],
        "TOIL_STAKEHOLDERS_H": "%.2f" % toil["itens"]["stakeholders"],
        "TOIL_REUNIOES_H": "%.2f" % toil["itens"]["reunioes_pos_incidente"],
        "TOIL_POSTMORTEM_H": "%.2f" % toil["itens"]["escrita_postmortem"],
        "TOIL_ACOES_H": "%.2f" % toil["itens"]["execucao_acoes"],
    }
    tokens["RESUMO"] = (
        "Na referencia sintetica adotada, uma mudanca de configuracao no componente de "
        "validacao de assinatura passou a rejeitar parte das requisicoes de pagamento. O "
        "alerta de queima acelerada de error budget abriu o incidente: foram %d minutos para "
        "confirmar a deteccao, %d minutos ate a mitigacao aplicada (reversao de configuracao, "
        "com aprovacao humana obrigatoria) e %d minutos ate a resolucao. Nao houve perda de "
        "dados nem corrupcao de estado." % (
            metricas["mttd_min"], metricas["mtra_min"], metricas["mttr_min"]))
    linhas = []
    for chave, info in ms.items():
        linhas.append("| %s | %s | %s |" % (chave.replace("_", " "),
                                            _fmt_min(info["offset_min"]),
                                            info["descricao"]))
    tokens["TABELA_MARCOS"] = "\n".join(sorted(
        linhas, key=lambda l: int(l.split("|")[2].strip().replace("+", "").split(" ")[0])))
    tokens["TABELA_FASES"] = "\n".join(
        "| %s | %s | %s | %d | %d |" % (
            f["fase"], _fmt_hora(f["inicio_min"]), _fmt_hora(f["fim_min"]),
            f["duracao_min"], f["eventos"]) for f in fases)
    tokens["TABELA_TOIL"] = "\n".join(
        "| %s | %.2f h |" % (k.replace("_", " "), v) for k, v in toil["itens"].items())
    return tokens


def preencher(template_texto, tokens):
    """Substitui {{CHAVE}} pelo valor; falha se sobrar token sem valor."""
    desconhecidas = set()

    def troca(match):
        chave = match.group(1)
        if chave not in tokens:
            desconhecidas.add(chave)
            return match.group(0)
        return tokens[chave]

    saida = re.sub(r"\{\{([A-Z0-9_]+)\}\}", troca, template_texto)
    return saida, sorted(desconhecidas)


def linha_do_tempo(registros, largura=60):
    """Timeline compacta em ASCII, uma linha por fase, com offsets."""
    partes = []
    for fase in FASES_CANONICAS:
        offsets = [r["offset_min"] for r in registros if r["fase"] == fase]
        if not offsets:
            continue
        barra = "#" * max(1, min(largura // 7, round((max(offsets) - min(offsets)) / 12)))
        partes.append("%-14s %s [%+d..%+d]" % (fase, barra, min(offsets), max(offsets)))
    return "\n".join(partes)


def analisar(csv_path):
    registros = carregar(csv_path)
    ms, faltando = marcos(registros)
    if faltando:
        raise ValueError("timeline sem marcos obrigatorios: %s" % ", ".join(faltando))
    metricas = metricas_de_tempo(ms)
    fases = duracoes_por_fase(registros)
    toil = toil_estimado(ms, metricas)
    por_fonte = Counter(r["fonte"] for r in registros)
    return {
        "sintetico": True,
        "aviso": "duracoes de exemplo, dados sinteticos",
        "arquivo": str(csv_path),
        "eventos": len(registros),
        "marcos": ms,
        "metricas": metricas,
        "fases": fases,
        "toil": toil,
        "fontes": dict(por_fonte),
        "linha_do_tempo": linha_do_tempo(registros),
    }


def report_texto(resultado, tokens):
    m = resultado["metricas"]
    linhas = [
        "lab-03 | analise de timeline de incidente sintetico",
        "=" * 72,
        "aviso: %s | eventos: %d | arquivo: %s" % (
            resultado["aviso"], resultado["eventos"], resultado["arquivo"]),
        "",
        "metricas (minutos a partir do alerta, T0):",
        "  MTTD  deteccao efetiva .......... %s min" % m["mttd_min"],
        "  MTTA  reconhecimento ............ %s min" % m["mtta_reconhecimento_min"],
        "  MTRA mitigacao aplicada ......... %s min" % m["mtra_min"],
        "  MTTR incidente resolvido ........ %s min" % m["mttr_min"],
        "  MTTM pedido->mitigacao .......... %s min" % m["mttm_min"],
        "  contencao declarada ............. %s min" % m["duracao_contencao_min"],
        "  tempo de resposta total ......... %s min" % m["tempo_resposta_total_min"],
        "",
        "intervalos que interessam para a retro:",
        "  confirmar deteccao apos aceite ... %s" % m["detectar_vs_investigar"],
        "  deteccao ate pedir mitigacao ..... %s min" % m["tempo_para_decidir_mitigar_min"],
        "  pedir ate aprovar ................ %s min" % m["tempo_para_aprovar_min"],
        "  aprovar ate executar ............. %s min" % m["tempo_aprovacao_para_mitigacao_min"],
        "  executar ate SLI voltar .......... %s min" % m["tempo_mitigacao_para_sli_ok_min"],
        "",
        "duracao por fase:",
        "%-16s %10s %10s %8s %8s" % ("fase", "inicio", "fim", "min", "eventos"),
        "\n".join("%-16s %10s %10s %8d %8d" % (
            f["fase"], _fmt_hora(f["inicio_min"]), _fmt_hora(f["fim_min"]),
            f["duracao_min"], f["eventos"]) for f in resultado["fases"]),
        "",
        "linha do tempo:",
        resultado["linha_do_tempo"],
        "",
        "toil estimado (%s h-h no total, ordem de grandeza):" % tokens["TOIL_TOTAL_H"],
        "%-34s %10s" % ("item", "horas"),
        "\n".join("%-34s %10.2f" % (k.replace("_", " "), v)
                  for k, v in resultado["toil"]["itens"].items()),
        "",
        "premissoes do calculo de toil:",
    ]
    for chave, valor in resultado["toil"]["premissas"].items():
        linhas.append("  %-38s %s" % (chave, valor))
    linhas += ["", "fontes citadas na timeline:"]
    for fonte, qtd in sorted(resultado["fontes"].items(), key=lambda kv: (-kv[1], kv[0])):
        linhas.append("  %-16s %d %s" % (fonte, qtd, "evento" if qtd == 1 else "eventos"))
    return "\n".join(linhas)


def main(argv=None):
    parser = argparse.ArgumentParser(description="analise de timeline (lab-03)")
    parser.add_argument("--timeline", default=str(LAB_DIR / "data/timeline.csv"))
    parser.add_argument("--template", default=str(LAB_DIR / "templates/postmortem-template.md"))
    parser.add_argument("--out", default=str(LAB_DIR / "postmortem.md"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--write-postmortem", action="store_true",
                        help="preenche o template e escreve o post-mortem")
    parser.add_argument("--check-postmortem", action="store_true",
                        help="confere se o post-mortem commitado bate com o calculado")
    args = parser.parse_args(argv)

    resultado = analisar(args.timeline)
    registros = carregar(args.timeline)
    tokens = tokens_para_template(registros, resultado["marcos"], resultado["metricas"],
                                  resultado["fases"], resultado["toil"])

    if args.json:
        saida = dict(resultado)
        saida.pop("linha_do_tempo", None)
        print(json.dumps(saida, indent=2, sort_keys=True, default=str))
        return 0

    if args.write_postmortem:
        template = Path(args.template).read_text(encoding="utf-8")
        preenchido, sobrando = preencher(template, tokens)
        if sobrando:
            print("TOKENS SEM VALOR: %s" % ", ".join(sobrando), file=sys.stderr)
            return 1
        cabecalho = ("<!-- gerado por labs/lab-03-incidente-postmortem/analyze.py "
                     "--write-postmortem; nao editar a mao -->\n\n")
        Path(args.out).write_text(cabecalho + preenchido, encoding="utf-8")
        print("\npost-mortem escrito em %s (%d substituicoes, 0 tokens sobrando)" % (
            args.out, len(tokens)))
        return 0

    if args.check_postmortem:
        atual = Path(args.out).read_text(encoding="utf-8")
        template = Path(args.template).read_text(encoding="utf-8")
        esperado, sobrando = preencher(template, tokens)
        if sobrando:
            print("TOKENS SEM VALOR: %s" % ", ".join(sobrando), file=sys.stderr)
            return 1
        corpo = atual.split("-->\n\n", 1)[-1]
        mesmo = corpo == esperado
        print("postmortem.md %s com os valores calculados agora" %
              ("bate" if mesmo else "NAO bate"))
        if not mesmo:
            print("rode: python3 labs/lab-03-incidente-postmortem/analyze.py --write-postmortem",
                  file=sys.stderr)
        return 0 if mesmo else 1

    print(report_texto(resultado, tokens))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

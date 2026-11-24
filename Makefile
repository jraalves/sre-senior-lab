# SRE senior lab - tudo roda com a biblioteca padrao do Python 3.
# Nao ha dependencias a instalar (ver requirements.txt).
PY := python3
LABS := labs

.PHONY: help run test eval labs lab01 lab02 lab03 lab04 lab05 lab06 lab07 clean

help: ## lista os alvos
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-7s %s\n", $$1, $$2}'

run: ## gera os dados sinteticos (tools/synth.py) e confere com --check
	$(PY) tools/synth.py --report
	$(PY) tools/synth.py --check

test: ## roda a suite unittest
	$(PY) -m unittest discover -s tests

eval: ## avalia o agente de triagem e imprime o resumo medido
	$(PY) agent/evaluate.py --report

labs: lab01 lab02 lab03 lab04 lab05 lab06 lab07 ## roda os sete labs em sequencia

lab01: ## lab-01 SLI e orcamento de erro
	$(PY) $(LABS)/lab-01-slo-error-budget/slo.py --report

lab02: ## lab-02 burn rate multi-janela
	$(PY) $(LABS)/lab-02-burn-rate-alerting/burnrate.py --report

lab03: ## lab-03 timeline de incidente e postmortem
	$(PY) $(LABS)/lab-03-incidente-postmortem/analyze.py --report

lab04: ## lab-04 runbooks (documentacao estatica, sem script proprio)
	@echo "runbooks em labs/lab-04-runbooks:"
	@ls -1 $(LABS)/lab-04-runbooks | sed 's/^/  - /'
	@echo "nota: rb-00-escalada-humana e um rotulo valido no banco de casos -"
	@echo "significa que nenhum runbook se aplica e atriagem escala para humano."

lab05: ## lab-05 sinais dourados e correlacao por request_id
	$(PY) $(LABS)/lab-05-golden-signals/metrics.py --report
	$(PY) $(LABS)/lab-05-golden-signals/correlate.py --summary

lab06: ## lab-06 planejamento de capacidade
	$(PY) $(LABS)/lab-06-capacity-planning/capacity.py --report

lab07: ## lab-07 modelo de custo
	$(PY) $(LABS)/lab-07-finops/cost_model.py --report

clean: ## remove __pycache__, *.pyc e resultados gerados
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -type f -delete
	rm -rf agent/results
	@echo "limpo: __pycache__, *.pyc e agent/results"

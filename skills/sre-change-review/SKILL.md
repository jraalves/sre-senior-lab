---
name: sre-change-review
description: Use this skill before a change goes to production - reviewing a deployment, a config or alert-rule edit, a Terraform/GitOps diff, a database migration or a feature flag rollout - when the user asks "revisar essa mudanca", "posso subir isso?", "code review de deploy", "review o PR de infra" ou apresenta um plano de release. Also use it to define or check the rollback and the error-budget consequence of a change.
license: Apache-2.0
---
# Revisao de mudanca orientada a orcamento de erro

O que se pergunta aqui, nesta ordem: **qual e o criterio de sucesso, o que quebra, como
volta atras e quantos pontos do orcamento de erro isso consome.**

## Checklist executavel
1. **Escopo e gatilho.** Qual SLI a mudanca toca? Confirmar a definicao em
   `labs/lab-01-slo-error-budget/slo.py` e o burn rate esperado em
   `labs/lab-02-burn-rate-alerting/burnrate.py` (`make lab01 && make lab02`).
2. **Orçamento.** Rodar o lab-01 e responder com numero: quanto do orcamento existe hoje
   e quanto a mudanca pode consumir se der errado. Sem saldo, a resposta e "adiar ou
   reduzir escopo", nao "dar mais cuidado".
3. **Reversibilidade.** Passo a passo de rollback testado em ambiente sintetico, com
   tempo estimado. Migracao que nao tem dump de volta nao e rollout: e aposta.
4. **Observabilidade da mudanca.** A mudanca precisa de um sinal proprio (metrica de
   negocio ou de erro nova, log estruturado, correlacao por `request_id`)? Se nao houver
   como saber em 5 minutos que ela piorou algo, ela nao sobe.
5. **Superficies expostas.** Config, segredo, permissao de IAM/K8s, dependencia externa.
   Segredo em arquivo ou em YAML de aplicacao e bloqueante (ver `git-secret-guard` do
   perfil e `tests/test_anonimato.py`).
6. **Decisao registrada.** Se a revisao muda uma regra de alerta ou a heuristica do
   agente, exigir ADR novo em `docs/decisoes/` com `make eval` antes/depois.

## Saidas possiveis (uma delas, explicita)
- **Aprovar** — com o criterio de sucesso e o dono do monitoramento nomeados.
- **Aprovar com condiçao** — a condicao e mensuravel e tem prazo.
- **Adiar** — orcamento insuficiente, rollback inexistente ou sinal ausente.
- **Recusar** — risco estrutural (sem volta atras, segredo exposto, sem SLI).

Diga a saida em uma linha no topo, depois a evidencia. Revisao que termina em "acho que
pode subir" nao e revisao.

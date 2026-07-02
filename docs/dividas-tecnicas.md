# Dívidas Técnicas Registradas

Registro de dívidas conhecidas, com origem e condição de resgate. Referências F#
apontam para `docs/revisao-critica-2026-06-09.md`.

## F15 — Denominador de `compute_readiness` (registrada em 2026-07-02, Fase 0.6)

**Onde:** `src/pipeline.py` (`compute_readiness`, ~linha 545).

**O quê:** `total_checks = self._ids_rules_count + self.report.total_issues` mistura
"regras IDS aplicadas" com "issues encontradas" — o denominador não representa o
número de checks efetivamente avaliados. O score de readiness resultante é uma
aproximação, não uma fração exata de conformidade.

**Decisão (plano de orquestração 2026-06-25, §3 item 0.6):** o readiness score
**não é métrica do artigo** (as métricas do experimento são top-k, conformidade IDS
pós-correção, estabilidade de saída, eficiência e proxy de revisão — ver
`docs/metricas-avaliacao.md`). Correção adiada.

**Condição de resgate:** se o readiness score vier a ser citado no artigo ou usado
em decisão de engenharia, corrigir o denominador para `total_checks = checks
avaliados de fato` (regras IDS aplicáveis avaliadas + verificações determinísticas
executadas), com teste de regressão.

## F8 — Dualidade de nomes em `src/models.py`

**Decisão:** PR mecânico após as fases experimentais estabilizarem (Fase D, item 3
do plano de orquestração). Não bloqueia o experimento.

# Backlog — Laboratorio de Derivativos

> Itens nomeados fora do PR corrente. Regra da sessao: mudanca fora do PR e
> nomeada aqui, nunca implementada "ja que estou aqui".

## Nao-objetivos da Fase 1 (escopo fechado)

- Chamadas reais a OpLab, token real, smoke test autenticado, homologacao.
- Qualquer rota do dominio de ordens; ordens; roteamento; portfolio da
  corretora.
- Modelos americanos (CRR, Bjerksund-Stensland), saltos, vol estocastica,
  superficies/SVI, Monte Carlo, Kronos, Qlib.
- `quimera estrutura`, `quimera holding`, mapeador de eventos, Copom,
  consenso, Kelly, CVaR, Markowitz.
- Redis (servico ou conector), Telegram, LangGraph, PydanticAI,
  NumPy/SciPy/pandas, Ruff/Black, qualquer dependencia nova.
- Persistencia em PostgreSQL (snapshots duraveis entram na Fase 2 com
  migracao propria).
- CLI alem de um wrapper fino opcional (DL-PR07).
- Alterar `CLAUDE.md`, `AGENTS.md`, `.claude/`.

## Itens nomeados (fora do Lab ou de fase futura)

- Suite regenera artefatos rastreados: `docs/rag/rag_01b_pr08_integration_report.md`,
  `evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json`,
  `rag_01b_pr08_integration_health.json`, `rag_01b_pr08_latency_summary.json`,
  `rag_01b_pr09_health_report.json`, `rag_01b_pr09_smoke_summary.json` —
  migrar para `tmp_path`; fora do Lab.
- `test_wm_docs.py` referencia `docs/adr/` minusculo; canonico e `docs/ADR/`.
- Bundle OKF para `knowledge/` (`okf_init`) — fora do Lab.
- Python 3.14 no shell vs 3.12 do projeto — verificar interpretador fora do
  `uv`.
- `.gitignore` pode ter entrada duplicada de `.obsidian` — conferir.
- Superficie de vol / SVI-SSVI — pesquisa posterior.
- Andersen/Andreasen (americanas rapidas) — so apos CRR de referencia
  (Fase 2).
- Verificar hashes canonicos internos dos bundles de calendario
  (`integrity.*_sha256`) conforme `integrity.canonicalization` — so se a
  especificacao no arquivo for inequivoca.
- Persistir calendario em PostgreSQL quando houver 2o consumidor.
- Calendarios EUA (NYSE/SIFMA/Fedwire) → eventos do Mapeador (Fase 2), nao
  calendario do pricer.
- Jäckel *Let's Be Rational* como metodo rapido de IV, apos oraculo
  (PR04+); a bissecao protegida do DL-PR04 vem primeiro.
- CRR/BS-1993 (Bjerksund-Stensland) para americanas — Fase 2, com
  referencia numerica propria.
- `/market/options/bs` da OpLab: so reconciliacao na homologacao (estado
  B); nunca fonte de preco do Lab.
- Oraculo mpmath: estender `bsm_reference_cases.json` com casos de IV
  (alvo do DL-PR04) e theta da put; hoje `theta_option_type = call`.
- Renumeracao 2026-11-06: DL-PR02 = tempo (calendario + convencoes),
  DL-PR03 = BSM + gregas, DL-PR04 = IV, DL-PR05 = cliente OpLab,
  DL-PR06 = ChainService + latencia, DL-PR07 = servidor MCP,
  DL-PR08 = CLI (opcional).

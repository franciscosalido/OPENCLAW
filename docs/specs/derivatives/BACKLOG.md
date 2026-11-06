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

- Bundle OKF para `knowledge/` (`okf_init`) — fora do Lab.
- Python 3.14 no shell vs 3.12 do projeto — verificar interpretador fora do
  `uv`.
- `.gitignore` pode ter entrada duplicada de `.obsidian` — conferir.
- Superficie de vol / SVI-SSVI — pesquisa posterior.
- Andersen/Andreasen (americanas rapidas) — so apos CRR de referencia
  (Fase 2).

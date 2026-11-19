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
- CLI alem de um wrapper fino opcional (DL-PR08).
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
- Jäckel *Let's Be Rational* e/ou Brent como aceleracao de IV, validados
  contra a bissecao protegida do DL-PR04 (que passa a ser o oraculo de
  referencia da inversao); mesma bateria round-trip + oraculo mpmath.
- Reformatar `pricing/calendar.py` (15 linhas) e `pricing/conventions.py`
  (1 linha) para <= 100 colunas — pre-existente do DL-PR02, detectado no
  gate V-B do DL-PR04; so formatacao, sem mudanca semantica.
- CRR/BS-1993 (Bjerksund-Stensland) para americanas — Fase 2, com
  referencia numerica propria.
- `/market/options/bs` da OpLab: so reconciliacao na homologacao (estado
  B); nunca fonte de preco do Lab.
- Oraculo mpmath: estender `bsm_reference_cases.json` com casos de IV
  (Codex; o DL-PR04 inverteu os 92 casos existentes — casos dedicados de IV
  com sigma-alvo publicado seguem pendentes) e theta da put; hoje
  `theta_option_type = call`.
- Renumeracao 2026-11-06: DL-PR02 = tempo (calendario + convencoes),
  DL-PR03 = BSM + gregas, DL-PR04 = IV, DL-PR05 = cliente OpLab,
  DL-PR06 = ChainService + latencia, DL-PR07 = servidor MCP,
  DL-PR08 = CLI (opcional).
- Cache de capturas com TTL (Redis/Postgres) so se medicao exigir (PR06+).
- Homologacao (estado B): checklist de campos, unidades, limites reais e
  formato real de `Retry-After` e dos corpos de erro da OpLab.
- Registro global de `RequestBudget` por credencial (hoje: uma instancia
  criada pela raiz de composicao) — so se houver mais de um transporte HTTP
  no mesmo processo.
- `vendor_models.py` tem 1 linha > 100 colunas pre-existente do DL-PR01
  (detectada no DL-PR05); so formatacao.
- Medir o protocolo de latencia nativamente em macOS (DL-PR06 mediu em VM
  Linux aarch64 no mesmo hardware).
- `day_count: calendar_365` esta no contrato YAML sem contagem
  implementada; o `ChainService` recusa. Implementar ou remover do contrato.
- Politica para ativo ausente (404 em `/market/stocks`): hoje a captura
  falha inteira; avaliar chain com spot da propria opcao e flag.
- `sigma_source` configuravel por chamada (hoje: mid) e leitura paralela das
  quatro rotas — so com medicao que justifique.
- DL-PR08 (CLI fino) implementado em 2026-11-19; falta conferir no Mac o
  script `quimera` instalado e eventual colisao de nome no PATH.
- Fase 1 fechada em estado A. Proximos passos fora da fase: assinatura
  OpLab e homologacao (estado B); promocao (estado C); registrar o servidor
  nos clientes MCP dos agentes consultores.
- Resposta da demonstracao tem ~67 KB para 100 linhas: avaliar filtro por
  faixa de strike ou paginacao antes de expor chains reais maiores.
- Guarda MCP depende de `FastMCP._mcp_server.request_handlers` (privado,
  FastMCP 3.4.0): revalidar a cada atualizacao do SDK; avaliar trocar por
  `TransportSecuritySettings` nativo quando o FastMCP o expuser.
- Fase B: `HttpTransport` so aceita `MockTransport` no estado A; reabilitar
  rede real exige ADR proprio. Remover entao os parametros sem efeito
  (`live_service`, `production_view`, `root`, `fixture_dir`).
- Homologacao: confirmar `parent_symbol` das opcoes e definir teto para
  `Retry-After` (hoje bloqueia ate o limite de `datetime`).
- `demo_fixture.py` usa APIs POSIX e mora em `oplab/`; mover para um pacote
  de demonstracao quando houver segunda fixture.
- Homologacao: `OBSERVED` deve nascer apenas no caminho de aquisicao real;
  alterar de proposito `test_phase_a_production_code_never_assigns_observed`
  junto com o ADR-0023. Definir tambem limite de plausibilidade para a taxa
  (hoje so o dominio matematico e validado) e fazer o carimbo da captura
  herdar a procedencia worst-of das quatro leituras, nao so a de opcoes.

# ADR-0024 - Reversao condicionada da proibicao de corretora

## Status

PROPOSED — aguardando assinatura explicita de Francisco. Este ADR nao altera
`CLAUDE.md` e nao produz nenhum efeito enquanto nao for assinado.

## Proibicao vigente (citada literalmente de CLAUDE.md)

> **Never** connect to brokerage APIs or execute trades automatically.

> Do NOT integrate brokerage APIs (ADR-007 — non-revisable).

Enquanto este ADR permanecer PROPOSED, a proibicao acima permanece em pleno
efeito, sem excecoes.

## Nova regra proposta

- Conexao a corretora **somente via OpLab**, nunca diretamente.
- Execucao **somente apos aprovacao humana fora de banda, por ordem** —
  nenhuma aprovacao em lote, nenhuma aprovacao implicita.
- O agente **nunca executa**: prepara, descreve e aguarda; a acao final e
  sempre de Francisco, fora do processo do agente.

## Invariantes de seguranca da Fase 3 (vinculantes se assinado)

1. Aprovacao nunca e parametro de tool: nenhum campo `approve`, `confirm` ou
   equivalente em schema MCP; a aprovacao acontece fora de banda.
2. Credenciais fora do processo MCP: o processo que serve tools de consulta
   nunca carrega credencial com poder de ordem.
3. Tres superficies MCP separadas: consulta de mercado, simulacao/preparacao
   e execucao — processos distintos, portas distintas, credenciais distintas.
4. Allowlist de rotas em codigo desde a Fase 1; a superficie de consulta
   jamais ganha rotas do dominio de ordens.

## Condicao de mudanca de estado

Este ADR so muda de PROPOSED para aceito com commit assinado por Francisco
alterando `CLAUDE.md`. Nenhum agente esta autorizado a fazer essa alteracao.

## Escopo negativo

Este ADR nao autoriza nenhuma implementacao de Fase 3, nenhuma rota de
ordens, nenhum armazenamento de credencial e nenhuma mudanca em
`CLAUDE.md`/`AGENTS.md`/`.claude/`.

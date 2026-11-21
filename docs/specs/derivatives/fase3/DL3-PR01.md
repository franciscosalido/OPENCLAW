## DL3-PR01 — Modelo da boleta, versão e resumo criptográfico

**Branch:** `feat/dl3-pr01-ticket-models`
**Arquivos novos:** `ticket/__init__.py`, `ticket/models.py`, `ticket/digest.py`,
`tests/architecture/test_ticket_boundaries.py`, testes unitários, o SDD e este cartão.

**Modelos (pydantic, `frozen=True`, `extra="forbid"`)**
- `Side` (`BUY`, `SELL`), `Environment` (somente `SIMULATED`).
- `Leg`: `symbol`, `side`, `quantity: int > 0`, `limit_price: Decimal > 0`, `lot_size: int`.
- `EditableField`: enum dos campos operacionais (símbolo, lado, quantidade, limite por
  perna, limite do conjunto, prazo de envio, validade).
- `TicketDraft`: 1 a 4 pernas, `net_limit` (débito máximo ou crédito mínimo), `gross_cap`,
  `send_deadline`, `order_validity`, `quote_snapshot_id`, `locked: frozenset[...]`.
- `Preview`: tudo o que será assinado, mais `partial_exposure` (perda se só a primeira
  perna executar) e `version: int`, `digest: str`.

**Funções**
- `canonical_bytes(preview)`: JSON com chaves ordenadas, `Decimal` como texto normalizado,
  sem espaços. `digest(preview)`: SHA-256 em hexadecimal.
- `apply_human_edit(draft, field, value) -> TicketDraft`: versão +1, campo travado.
- `apply_market_refresh(draft, suggestion) -> TicketDraft`: escreve só em campo não travado;
  se nada autorizável mudou, mesma versão e mesmo resumo.
- `unlock(draft, field)`.

**Validações:** preço fora do passo de 0,01 rejeitado; `float` rejeitado em campo de
dinheiro; pernas duplicadas rejeitadas; quantidade não múltipla do lote rejeitada.

**Testes exigidos**
- Mesma entrada ⇒ mesmo resumo; ordem de chaves e de construção não altera o resumo.
- Cada campo autorizável alterado ⇒ resumo diferente (um teste por campo).
- Refresh não escreve em campo travado (cenário S17, parte de modelo).
- Arquitetura (SDD §5): `ticket` não importa rede, LLM, `oplab.client`, `oplab.transport`,
  `mcp`, `gateway`; `mcp` não importa `ticket`; `Environment` não tem `REAL`;
  `routes.ALLOWED_METHOD == "GET"`. Use o padrão de `tests/architecture/derivatives_imports.py`.
- Mutantes: omitir um campo do resumo; refresh ignorar a trava; aceitar `float`.


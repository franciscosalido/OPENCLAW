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


### Convenções de representação do PR01

- O limite líquido positivo representa débito máximo, e o negativo, crédito mínimo.
  A prévia recebe a exposição parcial em reais. O cálculo de exposição pertence ao PR03.
- O lote valida a quantidade. Em D0 a projeção da perna no hash contém símbolo, lado,
  quantidade e preço-limite, conforme SDD §4.2.
- A trava identifica o campo e, nas pernas, o índice. Um refresh aplica suas sugestões
  em conjunto. Só adota a foto do mercado se algum valor autorizável sugerido mudou.
  Destravar um campo conserva a versão e o resumo.
- O JSON preserva a ordem das pernas, usa prazos com fuso convertidos a UTC e dinheiro
  em texto decimal, com zero único e sem zeros fracionários redundantes. Para valores de
  magnitude igual ou superior a 10²¹,
  usa notação científica compacta. O hash exclui o próprio digest, a versão e as travas.
- Se a proposta passar de A para B e voltar a A, o conteúdo recupera o mesmo hash.
  Ao implementar o PR05, a decisão humana deve conferir também a versão ou invalidar
  decisões anteriores. Este modelo apenas fornece a versão e o resumo.

## Revisão e integração — 21/11/2026 (Claude)

Cabeça `55b1746`: **GO** na primeira rodada, formado antes de ler os relatórios da skill.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração | 10.844 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas de produção | 239, teto de 350 |
| SDD no PR | idêntico byte a byte ao publicado |
| 14 sondas de entrada inválida (float, subcentavo, não finito, data sem fuso, lote, série duplicada, ambiente `REAL`, índice de perna) | todas rejeitadas |
| 20 mutantes do revisor | 19 mortos; 1 equivalente |

O mutante equivalente remove a checagem de valor não finito: a rejeição continua, pela
asserção sobre o expoente logo abaixo. Sob `python -O` essa asserção some e a checagem
explícita passa a ser a única guarda; por isso ela fica.

Relatórios da skill lidos depois, com SHA-256 conferidos: parecer GO e simplificação v0.2
sem bloqueante. As três notas para os próximos cartões estão em `current_state.md`.

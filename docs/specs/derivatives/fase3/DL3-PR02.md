## DL3-PR02 — Estados, transições e recibo

**Branch:** `feat/dl3-pr02-ticket-state`
**Arquivos:** `ticket/state.py`, `ticket/receipt.py`.

- `TicketState` e `OrderState` conforme SDD §4.9. Tabela de transições **explícita**
  (dicionário imutável). Transição fora da tabela levanta erro tipado.
- Estados terminais não saem. `UNCERTAIN` só sai por `reconcile(...)` explícito.
- `Receipt`: lista só de acréscimo de `ReceiptEvent(seq, ts, kind, payload, prev_hash,
  hash)`. Não há método de edição nem de remoção. `verify()` revalida a cadeia.
- Rótulos em português da ADR em `LABELS_PT`, fora da lógica.

**Testes:** propriedade percorrendo todos os pares (estado, evento): só os da tabela passam;
terminal é terminal; adulterar um evento quebra `verify()`; dois eventos conflitantes
(execução depois de pedido de cancelamento) ficam ambos no recibo (base do S08).
Mutantes: permitir `CANCEL_REQUESTED → CANCELLED` sem evento da venue; permitir saída de
`UNCERTAIN` por evento comum.


### Contrato de implementação

- Reconciliação tem uma API separada, exige referência de evidência e só resolve
  estado incerto para um estado verificável; estados terminais nunca reabrem.
  Pedido local de cancelamento não é confirmação da venue; execução durante
  cancelamento preserva ambas as ocorrências no recibo.
- Recibo em memória, eventos imutáveis com payload JSON canônico UTF-8, sem números
  não finitos ou chaves duplicadas. Timestamps explícitos com fuso viram UTC.
  Um evento de prévia guarda o conteúdo integral, inclusive lote e versão, em
  envelope separado do digest; leitura valida novamente o modelo e o digest.
- SHA-256 detecta adulteração em relação a uma ponta conhecida. Sem ponta
  externa confiável, não autentica origem nem comprova ausência de truncamento.
- Referências: [Python JSON](https://docs.python.org/3.12/library/json.html),
  [MappingProxyType](https://docs.python.org/3.12/library/types.html#types.MappingProxyType)
  e [Pydantic Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/).
  Trata-se de perfil JSON local, não uma implementação de RFC 8785.

## Revisão e integração — 22/11/2026 (Claude)

Cabeça `638fc31`: **GO**, formado antes de ler os relatórios da skill. A produção não mudou
na revisão; os testes ganharam 13 casos do revisor.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração, com os testes do revisor | 10.873 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas de produção | 291, teto de 300 |
| Sondas de adulteração do recibo (truncar, remover, trocar ordem, payload, instante, tipo, prévia forjada com cadeia refeita) | todas detectadas; truncamento só com âncora, como documentado |
| 20 mutantes do revisor na primeira passada | 12 mortos, 8 sobreviventes |

Os 8 sobreviventes eram lacunas de teste, não de código. A matriz de transições calculava
o esperado a partir da própria tabela, então um destino trocado passava. Os testes do
revisor fixam à mão a tabela, os destinos de reconciliação, os rótulos e cada campo do
evento. Depois deles sobra 1 mutante, equivalente: a checagem de chave duplicada é
redundante com a comparação de bytes canônicos.

Relatórios da skill lidos depois, com SHA-256 conferidos (`4eec4087…98b0` e
`e71d8334…4b8d`): GO sem bloqueante. As lacunas L1 (tabela), L2 (rótulos) e a de gravação
em UTC que eles apontam estão cobertas pelos testes do revisor.

## DL3-PR03 — Sequenciamento de pernas, cobertura e reservas

**Branch:** `feat/dl3-pr03-ticket-sequencing`
**Arquivo:** `ticket/sequencing.py`. Função pura, sem estado global.

- `plan_legs(draft, position) -> LegPlan`: ordena as pernas pela regra "primeiro o que
  aumenta comprado ou reduz vendido". Estrutura que não admite sequência segura é recusada
  com motivo tipado.
- `releasable_quantity(leg, fills, reservations) -> int`: quantidade da perna seguinte =
  executado da perna protetora − já vendido − reservado em ordens vivas, arredondado para
  baixo ao lote.
- `ReservationBook`: reservas exclusivas por (conta simulada, série); duas boletas nunca
  somam mais que a cobertura.
- `partial_exposure(draft) -> Decimal`: perda máxima se só a primeira perna executar.
- `within_signed_limits(draft, fills, next_leg) -> bool`: verifica débito máximo ou crédito
  mínimo e teto bruto com o que já executou; o limite da perna seguinte não se move.

**Testes:** S03, S04, S09, S21, S22 no nível de função; propriedade: para qualquer sequência
de execuções parciais, `vendido + reservado ≤ comprado` em todo instante. Mutantes: liberar
por enviado em vez de executado; esquecer o arredondamento ao lote; ignorar reserva de
outra boleta.

Valores sintéticos, custos conhecidos zero, quantidades em unidades. A reserva pertence
à mesma conta simulada e à série protetora compatível em todas as linhas S04 e S09.

| Cenário | Entrada | Resultado manual |
|---|---|---|
| S03 | Compra protetora executada: 10 × R$ 1,00. A venda não cruza. | 10 compradas, 0 vendidas, prêmio pago R$ 10,00. |
| S04 | 10 enviadas para compra, só 3 executadas e conciliadas. Lote da venda 1. | 3 liberáveis. Com zero execuções, 0. |
| S04 | 7 compradas e conciliadas, 2 vendidas e 1 reservada. Lote da venda 3. | Saldo livre 4; liberáveis 3. |
| S09 | 3 compradas, 1 vendida, 2 reservadas para a primeira boleta. | A segunda boleta pode reservar 0. |
| S09 | Pedido de cancelamento local da primeira boleta. | 0 liberáveis pela segunda. |
| S09 | Execução de mais 1 durante o pedido: 2 vendidas e 1 reservada. | 0 liberáveis. |
| S09 | Conciliação confirma cancelamento da unidade que restava. | 2 vendidas + 0 reservadas; 1 liberável. |
| S21 | Posição de 10 compradas na proteção A e 10 vendidas em B. Desmontagem propõe vender A e comprar B. | Recomprar B antes de vender A. |
| S22 | Limite de venda R$ 1,50; única compra disponível para essa venda a R$ 1,49. | Recusar a perna; manter R$ 1,50. |

### G3 — tabela de aceitação calculada antes de implementar

As pernas de referência são compra de 10 unidades a R$ 1,00 e venda de 10 a R$ 1,50.
Os limites são totais em reais. O pior preço líquido permitido nas unidades restantes
é o limite assinado de cada perna. Substituem-se apenas as unidades efetivamente
executadas por seu preço real. O custo conhecido total entra uma vez no líquido e no bruto.

| Variação | Líquido projetado | Bruto projetado | Limites líquido / bruto | Admite |
|---|---:|---:|---:|---|
| Sem execução, custo zero | −5,00 | 25,00 | −5,00 / 25,00 | sim |
| Crédito mínimo um centavo maior | −5,00 | 25,00 | −5,01 / 25,00 | não |
| Teto bruto um centavo menor | −5,00 | 25,00 | −5,00 / 24,99 | não |
| Custo total de 0,01 | −4,99 | 25,01 | −4,99 / 25,01 | sim |
| Compra de 3 a 0,90 já executada; 7 a 1,00 restantes | −5,30 | 24,70 | −5,30 / 24,70 | sim |
| Compra proposta a 1,01 ou venda proposta a 1,49 | — | — | limites por perna violados | não |
| Compra 10 a 2,00; venda 10 a 1,50 | +5,00 | 35,00 | +5,00 / 35,00 | sim |
| Mesma estrutura a débito | +5,00 | 35,00 | +4,99 / 35,00 | não |

A projeção serve à admissão; o crédito continua não realizado. Se só a compra protetora
executar integralmente a 1,00, o prêmio pago é 10,00. Um preço de venda melhor pode elevar
o bruto: o teste de admissão também considera o preço proposto para a quantidade seguinte.
O teto não é garantia de preço da execução futura. A trava não desloca limites assinados.

G2 usa evidência sintética explícita de pareamento, posições conciliadas, ativo-objeto,
tipo, vencimento e multiplicador. Preços e quantidades do rascunho são por unidade;
lote é passo de quantidade. A reserva pertence à conta e à série cuja compra confirmada
libera a próxima perna. Na desmontagem essa compra é a recompra da série vendida.
Reservas em aberto continuam ocupadas até execução ou liberação conciliada.
Aritmética de dinheiro usa contexto decimal próprio para que a precisão do chamador não
arredonde uma comparação de fronteira. [Python 3.12, decimal](https://docs.python.org/3.12/library/decimal.html#context-objects).

Permanecem para o PR04 a relação entre prazos, para o PR05 a vinculação de versão e o
dinheiro como texto decimal no recibo, e para o PR06 a separação dos rótulos se divergirem.

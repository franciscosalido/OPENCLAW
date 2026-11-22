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

### Adendo R1 e Adendo 1 autorizados por Francisco em 22/11/2026

O plano envia todas as compras antes das vendas. A prévia deve mostrar o desembolso máximo
se nenhuma venda executar. A regra R1 substitui a referência original à primeira perna.
Somam-se a quantidade vezes o preço limite de cada compra e, uma única vez, o custo conhecido.

| Boleta | Custo conhecido | Desembolso máximo |
|---|---:|---:|
| Trava com compra de 10 a 1,00 e venda de 10 a 1,50 | 0,00 | 10,00 |
| Condor com compras de 10 A a 3,00 e de 10 D a 0,50, vendas de 10 B a 2,00 e de 10 C a 1,00 | 0,00 | 35,00 |
| Mesmo condor | 0,07 | 35,07 |

O livro valida primeiro a identidade não vazia e a integridade do plano recebido. Em seguida
compara a foto conciliada da conta e, por último, o plano já registrado para a boleta.
Uma foto divergente de um plano íntegro exige conciliação inclusive para a boleta original.
Um plano adulterado ou uma troca de plano sob a mesma foto gera a recusa de identidade ou
plano divergente. O motor do PR05 jamais deve decidir pelo texto da mensagem. Se precisar
distinguir os motivos, esse cartão deverá introduzir um motivo tipado.

### Limitações conhecidas

- **N1.** A venda para zerar uma posição comprada própria, sem série vendida pareada, é
  recusada. Essa operação encerraria a posição sem abrir venda descoberta. Suporte fica
  para cartão próprio.
- **N2.** A atribuição exige uma única compra protetora por venda. Borboletas e demais
  estruturas com duas compras protegendo a mesma venda são recusadas. Travas e condores
  com pares identificáveis são suportados. Atribuição múltipla fica para cartão próprio.
- **O1.** `gross_cap` limita o volume bruto da boleta, somando compras e vendas ao pior
  preço assinado e o custo conhecido. O desembolso máximo se nenhuma venda executar é
  `partial_exposure`. Francisco pode alterar a definição de volume bruto por adendo.

## Revisão e integração — 22/11/2026 (Claude)

Duas rodadas. Cabeça `e69f6b4`: **NO-GO**. A exposição parcial somava só a primeira compra
(defeito do cartão) e nove guardas não tinham teste. Correção pelo supercartão
`DL3-PR03-R1` e pelo Adendo 1, que autorizou reordenar as verificações do livro. Cabeça
`30f9e66`: **GO**.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração, com os testes do revisor | 10.924 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| Linhas de produção | 299, teto de 300 |
| Sorteio do revisor: 3.000 sequências, duas boletas no mesmo par, lotes de 1 a 5 | `vendido + reservado <= comprado` nunca violado |
| 29 mutantes do revisor | 28 mortos; 1 equivalente (teto redundante na desmontagem) |

O revisor acrescentou dois testes para lacunas apontadas pelo parecer da skill: boleta sem
identidade e custo inválido na exposição. Relatórios lidos depois do parecer formado, com
SHA-256 conferidos (`16b9cc9a…8dcc` e `8a5a3ee0…2c5c`): GO, sem bloqueante.

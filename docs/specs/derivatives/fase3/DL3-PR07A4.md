# DL3-PR07A4 — Supercartão: relato contraditório vira divergência registrada (DP-13, 1ª parte)

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `a520c11` (DL3-PR07A3D integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** DP-13 de Francisco (Revisão 2, 22/11/2026), na parte
do relato contraditório: «Duplicata idêntica é reconhecida uma vez. Correção oficial
referencia o fato original. Uma ordem de 10 com execução acumulada de 12 gera divergência:
preservamos a mensagem, o último saldo conciliado e o bloqueio de novos envios da conta
afetada. […] Durante o bloqueio, o sistema continua recebendo fatos. Quero incluir no teste
uma execução válida que chega enquanto o cancelamento está pendente.»

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- Um relato impossível para o estado da ordem (execução depois de a ordem estar executada,
  por exemplo) **levanta exceção** dentro do motor. O resto do lote de relatos não é
  processado.
- Uma execução que ultrapassa a quantidade da ordem **é gravada como execução** no recibo e
  soma ao bruto executado. Só depois o livro recusa e a divergência é registrada.
- O relato da venue não tem identidade. O motor não distingue duplicata nem correção.

**O que este cartão entrega.** Antes de aplicar um relato, o motor o confere. O relato
contraditório **não é aplicado**: vira um registro de divergência com a mensagem inteira, o
motivo e o último executado conciliado da ordem, e bloqueia novos envios da conta. Os
relatos seguintes continuam entrando.

**O que este cartão não faz.**

- **Evento externo legítimo** (exercício, enquadramento) fica para o DL3-PR07A5. É a outra
  metade da DP-13 e pede desenho próprio (§8).
- Não aplica correção a saldos. No simulador, a correção oficial é registrada com a
  referência ao fato original e bloqueia a conta para conciliação.
- Não cria caminho para desfazer o bloqueio por divergência. Continua como hoje.
- Não muda a venue de papel (ela não emite identidade de fato), o livro, a prévia, o resumo
  criptográfico nem a conciliação de ordem incerta.
- O formato real das mensagens da corretora é assunto do D1.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/venue.py` | dois campos opcionais em `VenueReport` | 58 (55) |
| `backend/derivatives/ticket/engine.py` | conferência do relato e registro da divergência | 483 (447) |
| `tests/unit/derivatives/ticket/test_engine.py` | Y1 a Y9 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A4.md` | cópia deste cartão | — |

**Não muda:** os demais módulos da boleta, `scripts/derivatives_ticket_replay.py`,
`current_state.md`, arquivos protegidos. **Nenhum teste existente muda de resultado.** As
âncoras e os recibos das três sessões oficiais não mudam.

## 2. Regra

### 2.1 Identidade do relato (`venue.py`)

`VenueReport` ganha dois campos opcionais, no fim, ambos `None` por padrão:

| Campo | Significado |
|---|---|
| `fact` | identificador do fato na venue |
| `corrects` | identificador do fato original que esta mensagem corrige |

A venue de papel não os preenche. Relato sem `fact` não tem como ser reconhecido como
duplicata: dois relatos idênticos sem identidade são dois fatos (Y8).

### 2.2 Conferência (`on_reports`)

Ordem incerta continua como hoje: o relato vai para a fila da conciliação. Para as demais,
cada relato do lote recebe um de três destinos, **conferidos nesta ordem**:

| Condição | Destino |
|---|---|
| tem `corrects` e o fato original é conhecido | divergência, motivo «correção oficial» |
| tem `corrects` e o fato original não é conhecido | divergência, «correção sem fato original» |
| tem `fact` já aplicado e é idêntico ao relato aplicado | **ignorado**: nada é gravado |
| tem `fact` já aplicado e difere do relato aplicado | divergência, «fato repetido com conteúdo diferente» |
| a máquina de estados não admite o evento naquele estado | divergência, «relato impossível para o estado da ordem» |
| execução com quantidade que não é inteiro positivo, ou sem preço | divergência, «execução malformada» |
| execução que leva o acumulado acima da quantidade da ordem | divergência, «execução acima da quantidade da ordem» |
| nenhuma das anteriores | **aplicado**, como hoje; se tem `fact`, o motor o memoriza |

«Fato conhecido» é o `fact` de um relato já aplicado por este motor. `True` não é
quantidade inteira.

### 2.3 Divergência

O relato contraditório **não altera** a ordem, as execuções, o bruto nem o livro. O motor:

1. grava no recibo um registro `divergence` com `order_id`, `reason` (o motivo literal do
   §2.2), `filled` (o executado conciliado da ordem até ali) e `report`: a mensagem recebida,
   com `event` e, quando presentes, `quantity`, `price` (texto), `fact` e `corrects`;
2. bloqueia a conta com a mesma chave de divergência de hoje;
3. **segue para o próximo relato do lote.**

O estado da boleta não muda por causa da divergência. A divergência que vem da recusa do
livro continua como está, com o registro de hoje.

## 3. Cenários

Auxiliares de `test_engine.py`. `A` é `T1:A:1` (compra de 10 a 1,00) e `B` é `T1:B:1` (venda
a 1,50). Os relatos são entregues direto ao motor com `on_reports`. «T1 confirmada» é
`s.confirmed()`: confirmação em `at(2)`, com `A` viva.

**Y1 — execução acima da ordem.** T1 confirmada.

1. Relato de execução parcial de 6 em `A`, a 1,00, em `at(3)`: `A` em `PARTIAL`; bruto
   executado 6,00; entra a venda `B` (2 pedidos à venue).
2. Relato de execução total de **6** em `A`, em `at(4)` (acumulado 12): **um** registro novo
   no recibo, `divergence`, com exatamente:
   `order_id` `T1:A:1`; `reason` «execução acima da quantidade da ordem»; `filled` 6;
   `report` `{"event": "venue_fill", "quantity": 6, "price": "1"}`.
3. `A` segue `PARTIAL`; bruto executado 6,00; boleta em `WORKING`; conta `sim` bloqueada por
   divergência; continuam 2 pedidos à venue.
4. Relato de execução total de **4** em `A`, em `at(5)`: aplicado. `A` em `FILLED`; bruto
   executado 10,00; nenhum pedido novo. O recibo verifica.

**Y2 — relato impossível.** T1 confirmada; A com oferta a 1,00 em 3 (`A` em `FILLED`).

1. Relato de execução parcial de 1 em `A`, em `at(4)`: `divergence`, «relato impossível para
   o estado da ordem», `filled` 10, `report` com `venue_partial`, 1 e `"1"`. `A` segue
   `FILLED`; bruto executado 10,00; conta bloqueada. **Hoje:** exceção.
2. Relato de cancelamento de `B` em `at(4)`, sem pedido de cancelamento: `divergence`, o
   mesmo motivo, `filled` 0, `report` `{"event": "venue_cancelled"}`. `B` segue viva.

**Y3 — duplicata.** T1 confirmada. Relato de execução parcial de 3 em `A`, a 1,00, com
`fact` `x1`, em `at(3)`: aplicado. O **mesmo** relato entregue mais três vezes (uma sozinho,
duas no mesmo lote): o recibo não cresce; bruto executado 3,00; conta livre.

Depois, relato com `fact` `x1` e quantidade **4**: `divergence`, «fato repetido com conteúdo
diferente», `filled` 3, `report` `{"event": "venue_partial", "quantity": 4, "price": "1",
"fact": "x1"}`. Bruto executado 3,00; conta bloqueada.

**Y4 — correção oficial.** T1 confirmada; execução parcial de 3 em `A` com `fact` `x1`.

1. Relato com `fact` `x2`, `corrects` `x1`, parcial de 2 a 1,00, em `at(4)`: `divergence`,
   «correção oficial», `filled` 3, `report` `{"event": "venue_partial", "quantity": 2,
   "price": "1", "fact": "x2", "corrects": "x1"}`. Bruto executado 3,00; conta bloqueada.
2. Relato com `fact` `x3`, `corrects` `zz`, em `at(5)`: «correção sem fato original».

**Y5 — execução válida com cancelamento pendente, durante o bloqueio.** T1 confirmada; A
com oferta a 1,00 em 3 (`A` executada, `B` viva com 10).

1. Relato de execução parcial de 1 em `A`, em `at(3)`: divergência; conta bloqueada.
2. Cancela `B` em 4. B com demanda a 1,50, tamanho 4, em 5.
3. Últimos quatro registros do recibo: `request_cancel venue_partial venue_cancelled stop`.
   A execução é de `B`, quantidade 4, bruto executado `16.00`.
4. T1 em `STOPPED`; `B` em `CANCELLED`; conta ainda bloqueada; sobra da T1 vista por
   terceiro: 0 (conta com divergência não marca a boleta); 2 pedidos à venue.

**Y6 — o lote continua depois da contradição.** T1 confirmada; A com oferta a 1,00 em 3. Um
só lote, em `at(4)`: execução parcial de 1 em `A` (impossível) e execução parcial de 4 em
`B`, a 1,50 (válida). Dois registros novos, nesta ordem: `divergence` e `venue_partial`. `B`
em `PARTIAL`; bruto executado 16,00.

**Y7 — execução malformada.** T1 confirmada. Execução parcial em `A` com cada um destes
pares (quantidade, preço): (0, 1,00), (−1, 1,00), (sem quantidade, 1,00), (3, sem preço),
(`True`, 1,00). Em todos: `divergence`, «execução malformada», `filled` 0; `A` segue `LIVE`.

**Y8 — sem identidade não há duplicata.** T1 confirmada. Um lote com o mesmo relato duas
vezes, parcial de 3 em `A`, sem `fact`: os dois são aplicados; bruto executado 6,00; conta
livre. **Já passa no `main`**; entra para fixar a regra do §2.1.

**Y9 — outra boleta da conta não confirma.** T1 confirmada; A com oferta a 1,00 em 3;
relato impossível em `A` em `at(4)`. Uma T2 de referência tenta confirmar em `at(5)`: recusa
«conta em estado incerto».

## 4. Evidência do planejador

- **Fatos de hoje.** Os três comportamentos do §0 foram reproduzidos no `main` `a520c11`.
- **Protótipo descartável:** `engine.py` com 479 linhas (32 a mais) e `venue.py` com 57.
  Tipagem estrita limpa.
- **Portão completo no protótipo** (sem `tests/integration`): 11.459 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras seguem passando.
- **Cenários do §3:** os nove passam no protótipo. No `main` de hoje, só Y8 passa.
- **Mutantes:** 16 defeitos plantados, um por vez, todos detectados (§5).

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. A execução acima da ordem é aplicada (Y1).
2. A execução que completa exatamente a ordem vira divergência (Y1).
3. O relato impossível volta a levantar exceção (Y2, Y5, Y6, Y9).
4. A duplicata idêntica é aplicada de novo (Y3).
5. O fato repetido com conteúdo diferente é ignorado (Y3).
6. A correção oficial é aplicada como fato novo (Y4).
7. A correção sem fato original é tratada como oficial (Y4).
8. A divergência não bloqueia a conta (Y1 a Y5, Y9).
9. O registro sai sem o último executado conciliado (Y1 a Y4).
10. O lote para na primeira contradição (Y6).
11. A execução malformada não é conferida (Y7).
12. O fato aplicado não é memorizado (Y3, Y4).
13. O relato contraditório também é aplicado (Y1 a Y7, Y9).
14. A mensagem preservada sai sem a referência da correção (Y4).
15. A mensagem preservada sai sem a quantidade (Y1 a Y4).
16. `True` é aceito como quantidade (Y7).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado, ou alguma âncora de sessão mudar;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- Y8 falhar no `main` (seria defeito já integrado).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. Y8 nasce verde: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos dois arquivos, os 16 mutantes, as âncoras
   e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

**DL3-PR07A5 — evento externo legítimo (DP-13, 2ª parte).** Exercício ou enquadramento
confirmado pela corretora compõe a posição conciliada mesmo sem boleta de origem. O
planejador ainda precisa resolver, antes de escrever o cartão:

- onde o fato fica registrado, já que hoje só existe recibo por boleta;
- por onde ele entra no simulador (evento da fita ou ação do roteiro);
- o que acontece com as boletas em execução daquela conta quando a posição muda. A regra
  conservadora que já existe é parar novos envios até haver prévia nova sobre a posição
  atualizada.

Depois: DL3-PR07B (DP-02 e DP-03: zeragem e borboleta no motor).

# DL3-PR07B2 — Supercartão: montagem da borboleta, com strike na foto (DP-03)

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `5a08d8b` (DL3-PR07B1 e acompanhamento do DL3-PR07A4 integrados)
**PR novo**, em rascunho
**Decisão que este cartão implementa:** DP-03 de Francisco (Revisão 2, 22/11/2026): «Na
borboleta de calls `+1 K1, −2 K2, +1 K3`, com strikes crescentes, a compra em K1 e a compra
em K3 têm efeitos econômicos diferentes. […] Quero testes para a estrutura completa, cada
asa isolada e execuções parciais. O motor deve conferir ativo-objeto, call ou put, strikes,
vencimento, multiplicador e quantidades executadas antes de reconhecer a proteção. A mesma
unidade comprada só pode proteger uma unidade vendida por vez.»

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- A borboleta é recusada no plano: uma série vendida só pode ter uma proteção declarada
  («atribuição de proteção ambígua»).
- A foto de posição não tem strike. O par é conferido em ativo-objeto, tipo, vencimento e
  multiplicador.

**O que este cartão entrega: a montagem.**

1. A foto passa a ter o strike de cada série, e o par só vale com strikes diferentes.
2. Uma série vendida pode ter mais de uma proteção. A venda é liberada por cada compra
   executada, na quantidade dela: cada unidade comprada protege uma só unidade vendida.
3. O motor envia uma ordem de venda por proteção e o recibo diz qual série protegeu cada
   ordem. É assim que a asa de baixo e a asa de cima ficam distintas.
4. Os testes pedidos: estrutura completa, cada asa isolada, execuções parciais; e as duas
   contas da DP-03 pela análise de vencimento já entregue.
5. Dois testes pendentes das revisões dos PRs #176 e #177 (§3.4).

**O que este cartão não faz.**

- **Desmontagem e zeragem de borboleta.** A foto ainda não diz quanto cada proteção cobre de
  uma vendida já aberta. Foto com vendida aberta e mais de uma proteção é recusada.
- Não usa o strike para escolher a ordem das proteções nem para calcular risco no motor. A
  ordem vem da boleta assinada; o risco de cada par é da análise (DL3-PR08).
- Não muda a prévia, o resumo criptográfico nem os recibos das sessões oficiais.
- Trava, condor, autorização de sobra e zeragem de comprada ficam como estão.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | strike na foto; plano e livro com várias proteções | 448 (426) |
| `backend/derivatives/ticket/engine.py` | envio e recibo por proteção | 494 (485) |
| `tests/fixtures/derivatives/synthetic/ticket/sessions/*.roteiro.json` | strike nas duas séries dos três roteiros | — |
| `tests/unit/derivatives/ticket/test_sequencing.py` | auxiliar `holding` com strike; B1, B2 e G1 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | B3 a B6 e G2 | — |
| `tests/unit/derivatives/test_expiry_payoff.py` | B7 | — |
| `docs/specs/derivatives/fase3/DL3-PR07B2.md` | cópia deste cartão | — |

**Não muda:** `models.py`, `digest.py`, `receipt.py`, `report_check.py`, os demais módulos
da boleta, `scripts/derivatives_ticket_replay.py`, `current_state.md`, arquivos protegidos.
Linhas novas com até 100 colunas.

**Nenhum teste existente muda de resultado**, depois de o auxiliar `holding` e os três
roteiros ganharem strike. As quatro âncoras e os recibos das sessões oficiais não mudam: a
foto não entra no recibo.

## 2. Regra

### 2.1 Strike na foto

`Holding` ganha o campo obrigatório `strike`, dinheiro maior que zero. No par declarado, a
proteção e a vendida precisam ter **strikes diferentes**; iguais é «séries incompatíveis»,
junto das conferências de hoje (ativo-objeto, tipo, vencimento, multiplicador).

Nos três roteiros oficiais: strike `"10"` para A e `"11"` para B. No auxiliar `holding` dos
testes: um padrão por série, com A em 10, B em 11, C em 12, e a opção de informar outro.

### 2.2 Vendida com mais de uma proteção

- Uma série vendida pode aparecer em vários pares. Continuam recusados com «atribuição de
  proteção ambígua»: o mesmo par declarado duas vezes; uma série que é proteção em um par e
  vendida em outro.
- Foto com a vendida **já aberta** (saldo negativo) e mais de uma proteção: «vendida aberta
  com mais de uma proteção».

### 2.3 Plano

Para uma venda de montagem, todas as proteções declaradas que a boleta compra (ou que têm
autorização de sobra) são candidatas. O plano reparte a quantidade vendida entre elas, **na
ordem das pernas de compra da boleta**; proteção que só vem de autorização entra depois,
por nome. Cada proteção entra com no máximo o que ainda não foi usado por outra venda da
mesma boleta. Faltando proteção: «quantidade de proteção insuficiente».

As dependências passam a ter **uma linha por proteção usada**, na ordem de uso. Proteção
que não foi necessária não entra. `LegPlan` ganha `protections_for(perna)`, que devolve as
séries nessa ordem; `protection_for` continua existindo e devolve a primeira.

Desmontagem e zeragem seguem com uma só origem por venda, como hoje. Uma venda com
candidatas de montagem e de desmontagem ao mesmo tempo continua em «pareamento ausente ou
ambíguo».

### 2.4 Livro de reservas

`available` e `reserve` ganham o parâmetro nomeado `source`, opcional. Sem ele, vale a
primeira proteção da perna, como hoje. Com ele, o cálculo usa aquela proteção; série que
não é proteção daquela perna no plano dá 0. O resto do cálculo não muda: cada ordem consome
as compras executadas da **sua** proteção, e o teto da perna vale para a soma das ordens.

### 2.5 Motor

Para cada perna de venda, o motor percorre as proteções na ordem do plano. Em cada uma:
primeiro as compras próprias, depois as autorizações de sobra daquela série. Envia uma
ordem por fonte com disponível maior que zero, reservada com a proteção e a origem
correspondentes. No recibo, `protection` de cada ordem de venda é a série que a protegeu.

## 3. Cenários

**Foto F:** conta `sim`; A (strike 10), B (strike 11) e C (strike 12), todas zeradas; pares
(A, B) e (C, B). **Borboleta de referência:** compra A 5 a 2,00; vende B 10 a 1,20; compra
C 5 a 0,60; nessa ordem; líquido 1, bruto 25; prazo `END` e validade `CLOSE`.

Nos cenários de motor, cotações sintéticas antes da proposta: A 1,95 × 2,05; B 1,15 × 1,25;
C 0,55 × 0,65. «A executa `n`» é cotação de A com oferta a 2,00 e tamanho `n` (demanda
1,95); «C executa `n`», oferta a 0,60 (demanda 0,55); «B executa `n`», demanda a 1,20
(oferta 1,25).

### 3.1 Plano e livro (`test_sequencing.py`)

**B1 — plano.**

| Boleta e foto | Esperado |
|---|---|
| referência, foto F | pernas na ordem A, C, B; dependências `(("B", "A", False), ("B", "C", False))`; `protections_for` da venda: `("A", "C")`; `protection_for`: `A` |
| as mesmas pernas na ordem C, B, A | dependências `(("B", "C", False), ("B", "A", False))` |
| referência com venda de 6 (líquido 5,80, bruto 20,20) | as duas dependências, A e depois C |
| referência com venda de 5 (líquido 7, bruto 19) | só `(("B", "A", False),)` |
| referência com venda de 11 (líquido −0,20, bruto 26,20) | «quantidade de proteção insuficiente» |
| referência, foto F com C no strike 11 | «séries incompatíveis» |
| referência, pares (A, B) e (A, B) | «atribuição de proteção ambígua» |
| referência, pares (A, B) e (B, C) | «atribuição de proteção ambígua» |
| referência, foto com A +1, B −2, C +1 | «vendida aberta com mais de uma proteção» |
| foto com A, B e D, pares (A, B) e (A, D): compra A 5, vende B 3 e D 2 a 1,20 (líquido 4, bruto 16) | dependências `(("B", "A", False), ("D", "A", False))` |
| a mesma, vendendo D 3 (líquido 2,80, bruto 17,20) | «quantidade de proteção insuficiente» |
| trava de referência (`BUY`, `SELL`), foto padrão | `(("B", "A", False),)`, como hoje |

Exposição parcial da borboleta de referência: `13.00`.

**B2 — cada unidade comprada protege uma só vendida.** Foto F, T1 com a referência,
admitida. Disponível da venda por proteção:

| Passo | Proteção A | Proteção C |
|---|---|---|
| início | 0 | 0 |
| compra 5 A | 5 | 0 |
| reserva 5 com proteção A | 0 | 0 |
| compra 3 C | 0 | 3 |
| reserva 3 com proteção A | recusa «reserva indisponível» | — |
| reserva 3 com proteção C | 0 | 0 |
| compra mais 2 C | 0 | 2 |
| da primeira ordem, 2 executam e 3 são liberadas | 3 | 2 |

Sem `source`, o disponível é o da proteção A (0 no início, 5 depois da compra de A). Com
`source` `Z`: 0.

### 3.2 Motor (`test_engine.py`)

**B3 — estrutura completa.** T1 com a referência; exposição parcial 13,00; confirmada em
`at(2)`: ordens `T1:A:1` e `T1:C:1` vivas.

1. A executa 5, em 3: pedido `T1:B:1`, 5 a 1,20, `protection` `A`.
2. C executa 5, em 4: pedido `T1:B:2`, 5 a 1,20, `protection` `C`.
3. B executa 10, em 5: T1 em `COMPLETED`; bruto executado 25,00; 4 pedidos à venue.

**B4 — cada asa isolada.**

- **Só a de cima.** T1 confirmada em `at(2)`. C executa 5, em 3: pedido `T1:B:1`, 5 a 1,20,
  `protection` `C`. B executa 10, em 4: `T1:B:1` em `FILLED`; T1 segue `WORKING`; 3 pedidos.
  Cancela `T1:A:1` em 4; cotação de A em 5: T1 em `STOPPED`; bruto executado 9,00.
- **Só a de baixo.** T2 com a referência, confirmada em `at(6)`. A executa 5, em 7: pedido
  `T2:B:1`, 5 a 1,20, `protection` `A`.

**B5 — execuções parciais.** T1 confirmada em `at(2)`. A executa 2, em 3; C executa 3, em
4; A executa 3, em 5; C executa 2, em 6. Pedidos de venda, nesta ordem, com quantidade e
`protection`: `T1:B:1` 2 `A`; `T1:B:2` 3 `C`; `T1:B:3` 3 `A`; `T1:B:4` 2 `C`.

**B6 — na mesma passada, vale a ordem das compras na boleta.** T1 com a referência e T2
com as mesmas pernas na ordem C, B, A; cada uma confirmada e pausada em `at(2)`. A e C
executam 10 em 3. Cada boleta é retomada em `at(4)`: T1 envia `T1:B:1` (`A`) e `T1:B:2`
(`C`); T2 envia `T2:B:1` (`C`) e `T2:B:2` (`A`). Todas de 5.

### 3.3 As duas contas da DP-03 (análise de vencimento)

**B7.** Com `expiry_profile`, calls, por unidade, sem custos. **Já passa no `main`**; entra
para fixar os números de Francisco.

| Estrutura | Entrada líquida | Perda máxima |
|---|---|---|
| compra 1 no strike 10 a 2,00; vende 2 no 11 a 1,20; compra 1 no 12 a 0,60 | `0.20` (débito) | `-0.20`: o débito pago |
| vende 1 no 11 a 1,20; compra 1 no 12 a 0,60 (asa de cima) | `-0.60` (crédito) | `-0.40`: largura 1,00 menos crédito 0,60 |
| compra 1 no 10 a 2,00; vende 1 no 11 a 1,20 (asa de baixo) | `0.80` (débito) | `-0.80`: o débito pago |

Ganho máximo da borboleta inteira: `0.80`.

### 3.4 Dois testes pendentes das revisões anteriores

Os dois **já passam no `main`**.

**G1 — par com a «vendida» em saldo positivo não aumenta o saldo livre**
(`test_sequencing.py`; revisão do PR #177). Foto com A +7, B +2, A protege B. Zeragem de 7
de A: aceita, dependências `(("A", "A", True),)`. Zeragem de 8: «saldo livre insuficiente».

**G2 — correção sem original seguida do original, na mesma fila da ordem incerta**
(`test_engine.py`; revisão do PR #176). Leve para a suíte a contraprova arquivada em
`reports/fase03/dl3-pr07a4-conciliacao/evidencias/b11d492/test_contraprova.py`. Esperado,
conforme o repasse daquele PR: a divergência é registrada e as 2 unidades confirmadas pela
consulta são contabilizadas uma só vez.

## 4. Evidência do planejador

- **Fatos de hoje.** A recusa da borboleta foi reproduzida no `main` `5a08d8b`.
- **Protótipo descartável:** `sequencing.py` com 444 linhas (18 a mais) e `engine.py` com
  491 (6 a mais), mais o strike no auxiliar `holding` e nos três roteiros. Tipagem estrita
  limpa.
- **Portão completo no protótipo** (sem `tests/integration`): 11.497 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras seguem passando.
- **Cenários:** B1 a B7 e G1 passam no protótipo. No `main`, B1 a B6 falham; B7 e G1
  passam. G2 não foi rodado pelo planejador: vem da contraprova do implementador.
- **Mutantes:** 15 defeitos plantados, um por vez, todos detectados (§5). Um sobreviveu na
  primeira rodada; as duas linhas da foto com A, B e D no B1 entraram por causa dele.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Foto e plano**

1. A vendida só aceita uma proteção (B1 a B6).
2. A mesma compra protege mais de uma vendida (B1).
3. As proteções saem da ordem da boleta (B1, B6).
4. Venda maior que a soma das proteções é aceita (B1).
5. Proteção que não foi usada entra nas dependências (B1).
6. Strikes iguais são aceitos no par (B1).
7. Vendida aberta com duas proteções é aceita (B1).
8. Par declarado duas vezes é aceito (B1).
9. Série que é proteção e vendida ao mesmo tempo é aceita (B1).

**Livro**

10. O livro ignora a proteção pedida e usa sempre a primeira (B2 a B6).
11. O livro aceita proteção que não é da perna (B2).

**Motor**

12. O motor só usa a primeira proteção (B3 a B6).
13. O motor consulta o disponível sem dizer a proteção (B3 a B6).
14. O motor reserva sem dizer a proteção (B3 a B6).
15. O recibo traz sempre a primeira proteção (B3 a B6).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado depois do ajuste do auxiliar e dos roteiros;
- alguma âncora ou recibo de sessão oficial mudar;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- B7 ou G1 falharem no `main` (seria defeito já integrado);
- a contraprova do G2 não reproduzir o esperado do repasse.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. B7, G1 e G2 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos dois arquivos, os 15 mutantes, as âncoras
   e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

- **Desmontagem e zeragem de borboleta:** a foto precisa dizer quanto cada proteção cobre
  de uma vendida aberta. Entra na frente de repetir, completar e ajustar estruturas.
- **DL3-PR07A5:** evento externo legítimo, com as decisões de Francisco de 23/11/2026 (a
  boleta da série para de enviar; a conta não bloqueia).

# DL3-PR07B3 — Supercartão: desmontagem da borboleta com conta exata (DP-03)

**Data:** 24/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `689d4e9` (DL3-PR07C1 integrado)
**PR novo**, em rascunho
**Decisão que este cartão implementa.** Francisco, 24/11/2026, em resposta ao planejador,
sobre de onde vem a repartição das proteções na foto: **«Só conta exata»**. A foto é aceita
quando as asas somam exatamente o miolo vendido; a repartição é única e não pede dado novo.
Sobra em alguma asa continua recusada.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- Foto com vendida aberta e mais de uma proteção é recusada com «vendida aberta com mais de
  uma proteção». Quem montou uma borboleta não consegue desmontá-la pelo sistema.
- O saldo livre de cada proteção desconta o miolo **inteiro** em cada par. Com asas de 10 e
  miolo de 20, cada asa ficaria com −10.

**O que este cartão entrega.**

1. **Foto de conta exata é aceita.** Vendida aberta com mais de uma proteção passa quando a
   soma dos saldos das asas é igual ao miolo vendido e nenhuma dessas asas protege outra
   série.
2. **Saldo livre repartido.** O miolo é descontado das asas uma vez só, na ordem dos pares.
   Na conta exata, toda asa fica com saldo livre zero.
3. **Desmontagem.** Com isso, a boleta que recompra o miolo e vende as asas já funciona
   pelas regras existentes: cada unidade recomprada libera uma unidade de asa, e a parte de
   cada asa na recompra é a do plano (DL3-PR07C1).

**O que este cartão não faz.**

- Não aceita asas que somam mais ou menos que o miolo, nem asa que protege duas vendidas.
- Não muda o formato da foto nem dos roteiros.
- Não muda o motor, o livro (fora o saldo livre da foto), o recibo nem a prévia.
- Não cria regra nova de risco para a desmontagem: valem os limites assinados de hoje.
- Vender asa sem recomprar o miolo continua recusado.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | saldo livre repartido; aceitação da conta exata | 487 (477) |
| `tests/unit/derivatives/ticket/test_sequencing.py` | D1 a D6; um caso de teste existente trocado | — |
| `tests/unit/derivatives/ticket/test_engine.py` | D7 e D8 | — |
| `docs/specs/derivatives/fase3/DL3-PR07B3.md` | cópia deste cartão | — |

**Não muda:** `engine.py`, `session.py`, os demais módulos da boleta, o script, roteiros e
fitas, `current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Um teste existente muda, e só ele:**
`test_b1_photo_refuses_ambiguous_attribution_and_incompatible_strikes`. O caso com A em 1,
B em −2 e C em 1 era recusado e agora é conta exata. Troque esse caso por C em 2 (asas
somam 3 contra miolo de 2): a mensagem esperada continua a mesma. Nenhum outro teste muda.
As quatro âncoras e os recibos oficiais não mudam.

## 2. Regra

**Aceitação da foto (`plan_legs`).** Para cada vendida com saldo negativo e mais de uma
proteção nos pares, a foto é recusada com **«vendida aberta com mais de uma proteção»**, a
mensagem de hoje, se:

- a soma dos saldos das suas proteções for diferente do saldo vendido, em módulo; ou
- alguma dessas proteções também aparecer como proteção de outra série.

Caso contrário, a foto segue para as demais conferências.

**Saldo livre (`Position.unpledged`).** Cada vendida deve o seu saldo em módulo. Os pares
são percorridos na ordem em que estão na foto. Cada proteção paga o menor entre o seu saldo
livre (nunca abaixo de zero) e o que a vendida ainda deve; a **última** proteção da vendida
paga tudo o que restar, mesmo que fique negativa.

- Vendida com uma proteção só: o resultado é o de hoje, inclusive o saldo negativo que leva
  a «proteção inicial insuficiente».
- Conta exata: toda asa fica com zero, em qualquer ordem dos pares.

## 3. Cenários

Foto da conta `sim`: A em `+10`, B em `−20`, C em `+10`; A protege B e C protege B.
Boleta de desmontagem, nesta ordem: compra 20 B a 1,20; vende 10 A a 2,00; vende 10 C a
0,60; `net_limit` −2; `gross_cap` 50.

### 3.1 Foto, plano e livro (`test_sequencing.py`)

**D1 — a conta exata é aceita e o plano desmonta.** Saldo livre da foto: A 0, B −20, C 0.
Plano: pernas na ordem B, A, C; `dependencies` (A,B) e (C,B), as duas de desmontagem;
`quotas` `(10, 10)`; `quota` de A em B e de C em B: 10.

**D2 — o que não é conta exata segue recusado**, com a mensagem de hoje:

| Foto | Motivo |
|---|---|
| C em 15 | asas somam 25 |
| C em 5 | asas somam 15 |
| pares A→B, C→B e C→D, com D zerada | C protege duas séries |
| pares C→B, A→B e A→D, com D zerada | A protege duas séries |

Os quatro já são recusados no `main`; são guarda de regressão.

**D3 — as asas não saem sem a recompra.**

| Boleta sobre a foto | Esperado |
|---|---|
| só vende 10 A (`net_limit` −20, `gross_cap` 20) | «saldo livre insuficiente» |
| compra 10 B, vende 10 A e 10 C (−14; 38) | «quantidade de proteção insuficiente» |
| compra 21 B, vende 10 A e 10 C (−0,80; 51,20) | «recompra atravessa saldo conciliado» |
| compra 20 B, vende só 10 A (4; 44) | aceita; `dependencies` só (A,B) |
| compra 10 B, vende 5 A e 5 C (−1; 25) | aceita; `quotas` `(5, 5)` |

**D4 — cada unidade recomprada libera uma unidade de asa.**

| Passo | disponível A | disponível C |
|---|---|---|
| admitida | 0 | 0 |
| recompra de 10 B executada | 10 | 10 |
| reserva de 6 para C | 4 | 4 |
| recompra de mais 10 B executada | 10 | 4 |
| reserva de 10 para A e de 4 para C | 0 | 0 |

**D5 — fotos de uma proteção só não mudam.** Saldo livre de A:

| Foto | A |
|---|---|
| A +10, B −10; A protege B | 0 |
| A +5, B −10; A protege B | −5 |
| A +12, B −10, D −1; A protege B e D | 1 |
| foto do cartão com os pares na ordem C→B, A→B | A 0, C 0 |

**D6 — montar por cima de uma borboleta aberta.** Sobre a foto do cartão: compra 5 A a 2,00;
vende 10 B a 1,20; compra 5 C a 0,60 (`net_limit` 1; `gross_cap` 25). Aceita;
`dependencies` (B,A) e (B,C), de montagem; `quotas` `(5, 5)`.

### 3.2 Motor (`test_engine.py`)

**D7 — desmonta na ordem e conclui.**

| t | Passo | Esperado |
|---|---|---|
| 1 | cotações: A 2,00/2,10; B 1,10/1,25; C 0,60/0,70 | — |
| 2 | confirmação | só `T1:B:1` viva |
| 3 | B 1,10/1,20, tamanho 10 | B parcial; sai `T1:A:1` de 10; 2 ordens ao todo |
| 4 | B 1,10/1,20, tamanho 10 | sai `T1:C:1` de 10; 3 ordens ao todo |
| 5 | A 2,00/2,10; C 0,60/0,70 | `COMPLETED`; bruto executado `50.00`; proteção de `T1:A:1` e de `T1:C:1` no recibo: B |

**D8 — parada no meio deixa uma trava coberta.** Mesmos t=1 e t=2. t=3: B 1,10/1,20,
tamanho 10. t=4: A 2,00/2,10; cancelamento humano de `T1:B:1`. t=5: B 1,10/1,30. Esperado:
`STOPPED`; `T1:B:1` cancelada, `T1:A:1` executada; 2 ordens ao todo; bruto executado
`32.00`. Ficam C +10 e B −10: vendida coberta, sem venda descoberta.

## 4. Evidência do planejador

- **Fatos de hoje.** Conferidos no `main` `689d4e9`.
- **Protótipo descartável:** `sequencing.py` com 482 linhas (5 a mais). `mypy --strict`
  limpo em `backend/`; `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.573 aprovados e 1 reprovado,
  que é o teste existente citado no §1, antes da troca do caso. Nenhum outro mudou; as
  âncoras passam.
- **Cenários:** D1 a D8 passam no protótipo. No `main`, D1 e D3 a D8 falham; D2 já passa.
- **Mutantes:** 10 defeitos plantados, um por vez, todos detectados (§5).

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. Qualquer vendida com duas proteções é aceita (D2).
2. A soma das asas não é conferida (D2).
3. Asa que protege outra vendida é aceita (D2).
4. Asas acima do miolo são aceitas (D2).
5. Asas abaixo do miolo são aceitas (D2).
6. Toda vendida com duas proteções segue recusada (D1, D3, D4, D6, D7, D8).
7. Cada asa desconta o miolo inteiro, como hoje (D1, D3 a D8).
8. A última asa não absorve a falta (D5 e testes existentes).
9. O devido não diminui entre as asas (D1, D3 a D8).
10. A primeira asa não desconta nada (D1, D3 a D8).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado, fora o caso trocado do §1;
- alguma âncora ou recibo de sessão oficial mudar;
- for preciso mudar arquivo de produção fora do §1, ou o teto estourar;
- a desmontagem precisar de mudança no motor ou no formato da foto.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. D2 nasce verde: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas de `sequencing.py`, os 10 mutantes, as âncoras
   e os recibos oficiais comparados byte a byte, o caso de teste trocado, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

A fila do `current_state.md`: apresentação da montagem parcial e do projetado depois de
cancelamento humano; repetir, completar e ajustar estruturas. Asas desiguais ficam para
quando a foto declarar a quantidade de cada par.

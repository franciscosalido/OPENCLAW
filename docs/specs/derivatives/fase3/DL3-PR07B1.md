# DL3-PR07B1 — Supercartão: zeragem de posição comprada em perna única (DP-02)

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `d25c788` (DL3-PR07A4 integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** DP-02 de Francisco (Revisão 2, 22/11/2026): «Quero
vender para zerar uma posição comprada e recomprar para zerar uma vendida, até o saldo livre
conciliado. Na desmontagem de estruturas, a recompra **executada** libera a quantidade
correspondente de proteção. Se solicitei 100 e só 40 executaram, as outras 60 continuam
comprometidas. O PR07B pode demonstrar isso com uma posição sintética, sem persistência.»

**Decisões de Francisco de 23/11/2026, em resposta ao planejador:**

1. O PR07B vem antes do evento externo (segunda metade da DP-13), que fica desenhado antes
   da fase com corretora.
2. Quando chegar um fato externo legítimo numa série que uma boleta em execução usa, a
   boleta **para de enviar**: mantém as ordens já enviadas e contabiliza as execuções, mas
   não envia mais nada.
3. O fato externo legítimo **não bloqueia a conta**; só afeta as boletas da série atingida.

O PR07B foi dividido em dois pelo planejador: este cartão (zeragem) e o DL3-PR07B2
(borboleta), no §8.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- Recomprar para zerar uma vendida, em perna única, já funciona.
- Na desmontagem em par (vende a proteção, recompra a vendida), a venda só é liberada pela
  recompra executada. Já funciona.
- **Vender para zerar uma comprada, em perna única, é recusado** no plano, com «pareamento
  ausente ou ambíguo», mesmo quando a série não protege nada.

**O que este cartão entrega.** A venda em perna única de uma série com saldo comprado, até
o **saldo livre**: o saldo comprado da foto, menos o que protege posições vendidas, menos o
que já foi posto à venda por zeragem. E a demonstração pedida por Francisco, com 100, 40 e
60, pelo motor.

**O que este cartão não faz.**

- Não libera, para a zeragem, a proteção que uma recompra de outra boleta deixou sobrando.
  Isso continua exigindo autorização (DL3-PR07A3B e C).
- Não cria histórico nem persistência; a posição é sintética.
- Não mistura, na mesma perna, saldo livre com saldo liberado por recompra.
- Não trata a borboleta (DL3-PR07B2).

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | plano, livro e exposição parcial | 431 (402) |
| `backend/derivatives/ticket/engine.py` | só `_propose` | 487 (483) |
| `tests/unit/derivatives/ticket/test_sequencing.py` | Z1 a Z4 | — |
| `tests/unit/derivatives/ticket/test_engine.py` | Z5 a Z7 | — |
| `docs/specs/derivatives/fase3/DL3-PR07B1.md` | cópia deste cartão | — |

**Não muda:** os demais módulos da boleta, `scripts/derivatives_ticket_replay.py`,
`current_state.md`, arquivos protegidos. **Nenhum teste existente muda de resultado.** As
âncoras e os recibos das três sessões oficiais não mudam. Linhas novas com até 100 colunas.

## 2. Regra

### 2.1 Plano (`plan_legs`)

Uma perna de venda é **zeragem** quando as duas condições valem:

- a série tem saldo comprado (maior que zero) na foto;
- nenhuma regra de hoje a pareia (a boleta não recompra a vendida que essa série protege).

Na zeragem, a quantidade cabe se for menor ou igual ao saldo comprado da foto menos o que a
série protege (a soma das posições vendidas pareadas com ela). Se não couber: «saldo livre
insuficiente». A dependência registrada é (série, **a própria série**, desmontagem). Com
isso `protection_for` devolve a própria série.

Todo o resto fica como hoje: série sem saldo comprado e sem par segue em «pareamento ausente
ou ambíguo»; a venda que acompanha a recompra do par segue presa à recompra.

Autorização de cobertura (DL3-PR07A3B) não se aplica à zeragem: uma autorização cuja série
só aparece como zeragem é recusada com «autorização sem venda correspondente».

### 2.2 Exposição parcial

`partial_exposure` ganha o parâmetro nomeado `zeroing`, falso por padrão. Quando verdadeiro,
aceita boleta sem compra e sem autorização; o resultado é só o custo conhecido. O motor
passa `zeroing` verdadeiro quando o plano tem alguma perna de zeragem.

### 2.3 Livro de reservas

**Saldo livre de uma série, agora:** saldo comprado da foto, menos o que a série protege na
foto, menos as vendas de zeragem dessa série **de todas as boletas da conta** (saldo vivo
mais executado). A venda de desmontagem presa a uma recompra **não** desconta do saldo
livre, e a zeragem não desconta do que a recompra liberou.

Para a perna de zeragem, `available` e `reserve` usam o menor entre o saldo livre e o que
falta enviar da perna, arredondado ao lote. Com `origin` informado: 0. Boleta parada: 0,
como já é.

**Admissão.** `admissible` e `admit` recusam o plano com zeragem cujo saldo livre é zero ou
menor: «saldo livre indisponível». Como nas outras recusas da admissão, a decisão não é
gasta.

## 3. Cenários

Auxiliares dos próprios arquivos de teste. **Foto P:** conta `sim`, A com +10, B com −6, A
protege B. Saldo livre de A: **4**. **Zeragem de `n`:** boleta de uma perna, vende A `n` a
1,00, líquido `−n`, bruto `n`, prazo `END` e validade `CLOSE`.

### 3.1 Plano e livro (`test_sequencing.py`)

**Z1 — plano.**

| Boleta e foto | Esperado |
|---|---|
| zeragem de 4, foto P | pernas: só a venda; dependências `(("A", "A", True),)`; proteção: `A` |
| zeragem de 5, foto P | «saldo livre insuficiente» |
| zeragem de 10, foto com A +10 e B zerada | aceita |
| zeragem de 11, a mesma foto | «saldo livre insuficiente» |
| zeragem de 7, foto só com A +7, sem pares | aceita |
| vende A 1, foto padrão (A e B zeradas) | «pareamento ausente ou ambíguo», como hoje |
| vende B 1 a 1,50, foto P (B está vendida) | «pareamento ausente ou ambíguo», como hoje |
| `close_plan()` | dependências `(("A", "B", True),)`, como hoje |
| zeragem de 4 com autorização (A, T1, 4), foto P | «autorização sem venda correspondente» |

Exposição parcial da zeragem de 4 com `zeroing=True`: `0`; com custo conhecido `0,07`:
`0,07`. Sem `zeroing`: recusa, como hoje.

**Z2 — o saldo livre é da conta e a reserva é exclusiva.** Foto P. T1 e T2, cada uma com
zeragem de 4. T1 admitida.

| Passo | Disponível T1 | Disponível T2 |
|---|---|---|
| início | 4 | 4 |
| T1 reserva 3 | 1 | 1 |
| 2 executam e 1 é liberada | 2 | 2 |
| T2 é admitida e reserva 2 | 0 | 0 |

No início, T1 com `origin` `T9`: 0. No fim: `admissible` de uma T3 com zeragem de 1 recusa
com «saldo livre indisponível»; reserva de 1 pela T1: «reserva indisponível»; depois de
`close("sim", "T1")`, disponível da T1 = 0.

**Z3 — lote, perna e conta.**

- Foto P, uma T9 reserva 1 de zeragem (saldo livre 3). T1 com zeragem de 4 e lote 2:
  disponível **2**.
- Foto com A +10 e B zerada, livro novo. T1 com zeragem de 2: disponível 2; reserva 2;
  disponível **0**. Uma T2 com zeragem de 9 vê **8**.
- A mesma foto na conta `outra`, no mesmo livro: uma T1 com zeragem de 9 vê **9**.

**Z4 — zeragem e desmontagem não tiram uma da outra.** Foto P. T1: vende A 6 a 1,00 e
recompra B 6 a 1,50 (líquido 3, bruto 15). T2: zeragem de 4. As duas admitidas.

| Passo | T1 (venda de A) | T2 (zeragem) |
|---|---|---|
| início | 0 | 4 |
| T1 recompra 6 B | 6 | 4 |
| T1 reserva 6 | 0 | 4 |
| T2 reserva 4 | 0 | 0 |

No fim, `admissible` de uma T3 com zeragem de 1: «saldo livre indisponível».

### 3.2 Motor (`test_engine.py`)

**Z5 — zerar, e a segunda boleta vê o saldo indisponível.** Foto P.

1. T1 propõe zeragem de 4: exposição parcial 0. Confirma em `at(2)`: ordens
   `{T1:A:1: LIVE}`; único pedido à venue: `T1:A:1`, 4 a 1,00. No recibo, o pedido tem
   `protection` `A` e não tem `origin`.
2. T2 propõe zeragem de 4 e confirma em `at(2)`: `SequenceRefusal` «saldo livre
   indisponível»; T2 em `DRAFT`.
3. A com demanda a 1,00, tamanho 2, em 3: `T1:A:1` em `PARTIAL`. Cancela `T1:A:1` em 3;
   cotação de A em 4. T1 em `STOPPED`; bruto executado 2,00.
4. T2 confirma em `at(4)` **com a mesma decisão**: pedido `T2:A:1`, **2** a 1,00.
5. A com demanda a 1,00, tamanho 5, em 5: `T2:A:1` em `FILLED`; T2 em `STOPPED` (vendeu o
   que havia; a perna era de 4).

**Z6 — zeragem completa.** Foto P. T1 com zeragem de 4 confirmada em `at(2)`; A com demanda
a 1,00, tamanho 4, em 3. T1 em `COMPLETED`; bruto executado 4,00. Sequência do recibo depois
da prévia: `confirm start venue_live venue_fill complete`.

**Z7 — pediu 100, executou 40, as outras 60 seguem comprometidas.** Foto com A +100 e B
−100, A protege B. T1: vende A 100 a 1,00 e recompra B 100 a 1,50 (líquido 50, bruto 250),
confirmada em `at(2)`.

1. Ordens: só `T1:B:1`, viva.
2. B com oferta a 1,50, tamanho 40, em 3: `T1:B:1` em `PARTIAL`; entra `T1:A:1`, **40** a
   1,00.
3. A com demanda a 1,00, tamanho 100, em 4: `T1:A:1` em `FILLED`; continuam 2 pedidos à
   venue.
4. Cancela `T1:B:1` em 4; cotação de B em 5: T1 em `STOPPED`; 2 pedidos à venue.
5. Uma T2 propõe zeragem de 1 de A com a mesma foto: «saldo livre insuficiente». As 60
   seguem protegendo a vendida.

Os passos 1 a 4 **já passam no `main`**; o passo 5 é novo.

## 4. Evidência do planejador

- **Fatos de hoje.** A recusa da zeragem em perna única foi reproduzida no `main` `d25c788`.
- **Protótipo descartável:** `sequencing.py` com 427 linhas (25 a mais) e `engine.py` com
  485 (2 a mais). Tipagem estrita limpa.
- **Portão completo no protótipo** (sem `tests/integration`): 11.478 aprovados, 16 pulados,
  a mesma contagem do `main`. Nenhum teste existente mudou; as âncoras seguem passando.
- **Cenários do §3:** os sete passam no protótipo e falham no `main`.
- **Mutantes:** 16 defeitos plantados, um por vez, todos detectados (§5). Dois sobreviveram
  na primeira rodada; os dois últimos itens do Z3 entraram por causa deles.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

**Plano e exposição**

1. O plano ignora o que a série protege (Z1, Z7).
2. O plano recusa vender exatamente o saldo livre (Z1 e os demais).
3. A zeragem é aceita sem saldo comprado (Z1).
4. A zeragem é marcada como montagem (Z1).
5. Autorização aceita em venda de zeragem (Z1).
6. A exposição parcial ignora `zeroing` (Z1, Z5, Z6).
7. O motor não informa `zeroing` (Z5, Z6).

**Livro**

8. O saldo livre ignora o que a série protege (Z2 a Z5).
9. O saldo livre ignora a zeragem de outra boleta (Z2 a Z5).
10. O saldo livre desconta a venda da desmontagem (Z4).
11. O saldo livre não conta a zeragem já executada (Z2, Z5).
12. O saldo livre soma ordens de outra conta (Z3).
13. A admissão não confere o saldo livre (Z2, Z4, Z5).
14. A zeragem aceita `origin` (Z2).
15. A zeragem não arredonda ao lote (Z3).
16. A zeragem ignora o que a perna já enviou (Z3).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir;
- qualquer teste existente mudar de resultado, ou alguma âncora de sessão mudar;
- for preciso mudar arquivo de produção fora do §1, ou algum teto estourar;
- os passos 1 a 4 do Z7 falharem no `main` (seria defeito já integrado).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde.
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

**DL3-PR07B2 — borboleta (DP-03).** Exige strike na foto de posição e uma vendida protegida
por mais de uma compra, com cada unidade comprada protegendo uma só unidade vendida. Testes
da estrutura completa, de cada asa isolada e de execuções parciais.

Depois: DL3-PR07A5 (evento externo, com as decisões 2 e 3 do cabeçalho), que também leva
as pendências do DL3-PR07A4: três testes de identidade de relato e a conferência do relato
recebido com a ordem incerta.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `4510616`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.486 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho | Z1 a Z7 falham na base; os passos 1 a 4 do Z7 já passavam | implementador; logs conferidos |
| 16 mutantes do §5 e 1 adicional, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidências conferidas |
| Manifesto de 112 evidências (`4d039e45…ee27`) e hashes dos dois relatórios | conferem | revisor (21 arquivos) e Francisco (todos, no Mac) |
| Diff | cinco arquivos; `sequencing.py` com 426 linhas (teto 431) e `engine.py` com 485 (teto 487) | revisor |
| Âncoras e recibos das sessões | iguais byte a byte entre base e cabeça | implementador; log conferido |
| Cópia do cartão | igual à publicada, salvo a quebra de linha final | revisor |
| 7 cenários do protótipo do planejador contra os módulos entregues | todos aprovados | revisor |

A implementação é equivalente à do protótipo e mais simples em um ponto: o saldo que cada
série tem livre na foto virou um método de `Position`, usado pelo plano e pelo livro, e a
perna de zeragem reaproveita o fim do cálculo que já existia (perna, lote).

Este PR e o #176 saíram da mesma base e foram validados separadamente. Antes de integrar, o
revisor juntou os dois e rodou a suíte sem integração (11.497 aprovados, 16 pulados) e o
mypy estrito (0 erros) na árvore combinada, que não tinha portão completo.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Observação, não bloqueante (skill; lacuna do cartão do planejador): nenhum teste tem um par
em que a série «vendida» está com saldo positivo. Trocar o sinal da dedução deixaria esse
saldo aumentar o livre da proteção, e a suíte não perceberia. A cabeça recusa corretamente.
Uma linha a mais na tabela do Z1 resolve; entra no próximo cartão.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`ce5369b8…0948` e `ab968a41…abbd`): sem bloqueante.

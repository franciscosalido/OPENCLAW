# DL3-PR06B — Supercartão de correção: identidade sem caixa, `after_seq=0` e pasta de saída

**Data:** 22/11/2026 · **Autor:** Claude · **Para:** Codex
**PR:** #162, mesma branch, em rascunho · **Cabeça revisada:** `742b852` · **Base:** `main` = `51fd6d2`
**Complementa** o `DL3-PR06.md`. O que este cartão não cita continua valendo como está lá.
**Decisões de produto que implementa:** DP-18 (na versão aceita por Francisco em 22/11/2026)
e DP-19 (autorizado sem modificação).

---

## 0. Parecer

**NO-GO, por pouco.** O PR entrega o cartão: no Linux x86_64 as três sessões reproduzem os
quatro hashes, duas vezes iguais. Portão sobre `742b852`: 11.196 aprovados, 16 pulados, 261
subtestes; mypy estrito (backend e script) e Pyright com zero erros. Rodei 43 mutantes meus:
34 morrem; dos 9 vivos, 6 são lacunas reais e 3 são equivalentes. Li os relatórios da skill
depois (SHA-256 conferido).

| Nível | Id | Achado | Quem achou |
|---|---|---|---|
| Crítico | — | nenhum | |
| Bloqueante | B1 | `T1` e `t1`: o comando sai com 0 no Linux e 2 no Mac | skill |
| Bloqueante | B2 | fita com primeiro `seq` 0: `after_seq=0` deixa de significar "antes do primeiro evento" | skill |
| Não bloqueante | N1 | pasta de saída reutilizada mistura recibos de sessões diferentes; a publicação faz vários `replace` | skill e revisor |
| Não bloqueante | N2 | `except Exception` no `open` transforma erro de programação em "roteiro inválido" | revisor |
| Não bloqueante | N3 | propriedade `ledger` da sessão não tem nenhum uso | skill e revisor |
| Lacuna de teste | L1–L6 | seis mutantes sobrevivem: três da skill, três só meus | skill e revisor |

**B1, B2, N2 e N3 são lacunas do meu cartão:** o DL3-PR06 não tratou caixa nos ids, não
exigiu sequência positiva, mandou capturar "qualquer exceção" no `open` e pediu uma
propriedade que ninguém usa.

## 1. Arquivos e limites

| Arquivo | Mudança |
|---|---|
| `backend/derivatives/ticket/session.py` | S1, S2 e S3 (§2). Continua ≤ 150 linhas (hoje 119) |
| `scripts/derivatives_ticket_replay.py` | C1 e C2 (§2). Continua ≤ 220 linhas (hoje 195) |
| `tests/unit/derivatives/ticket/test_session.py` | U1–U6, novos |
| `tests/unit/derivatives/test_ticket_replay_script.py` | V1–V13; os casos de entrada inválida mudam de preparo (V11) |
| `docs/specs/derivatives/fase3/DL3-PR06B.md` | cópia deste cartão |
| `docs/specs/derivatives/fase3/DECISOES_PRODUTO_DP01-DP19.md` | cópia byte a byte de `reports/fase03/DECISOES_PRODUTO_DP01-DP19_2026-11-22.md`, SHA-256 `0d3d1b4d053dc9bce0899e70ec0ebdfc4985a06967c6813372b397bb3b85233f` |

- Os seis arquivos de fita e roteiro não mudam. Os esperados das três sessões oficiais
  (estados, ordens, recusas e os quatro hashes) **não mudam**.
- Nenhum outro módulo de `backend/` muda. `load_replay` e o motor ficam como estão.
- Teto do PR continua em 370 linhas de produção (hoje 314).

## 2. Regras

### Sessão

**S1 — Id único sem diferenciar maiúsculas (DP-18).** `open` recusa com `SessionRefusal`
quando `ticket.casefold()` é igual ao `casefold()` de um id já aberto na sessão. Isso cobre
também o id repetido exato. A recusa vem antes de construir o motor. O motor não muda: ele
continua aceitando `T1` e `t1`.

**S2 — Fita com sequência positiva (DP-19).** O construtor de `ReplaySession` recusa com
`SessionRefusal` a fita cujo primeiro evento tem `seq <= 0`. A mensagem diz que `after_seq=0`
é reservado para "antes do primeiro evento". `load_replay` continua aceitando essas fitas.
Fita sem nenhum evento não é recusada por esta regra.

**S3 — Sem `ledger` público.** Remova a propriedade `ledger`. O livro de decisões continua
único e compartilhado entre todos os motores da sessão, só que interno.

### Script

**C1 — Pasta de saída nova.**
- `--out` **não pode existir**. Se o caminho existe (pasta, mesmo vazia, ou arquivo), o
  comando sai com código 2 antes de ler a fita e o roteiro, sem tocar em nada.
- Publicação: grava todos os arquivos numa pasta temporária criada no diretório pai de
  `--out` (criando os pais que faltarem) e, no fim, faz **um único** `rename` dela para
  `--out`.
- Qualquer falha: a pasta temporária é removida, `--out` não é criado, código 2.
- Depois de um código 0, `--out` tem exatamente `resumo.json` e um recibo por boleta aberta.

**C2 — Exceções no passo `open`.** Capture só `ValueError`. Todas as recusas do domínio já
são subclasses dela (`EngineRefusal`, `SequenceRefusal`, `SessionRefusal`, e o
`ValidationError` do pydantic). Qualquer outra exceção sobe: é erro de programação, não
entrada inválida.

## 3. Cenários, com o esperado

Sessão de referência: fita, posição e proposta do `calmo` (`T1` compra A 10 a 1,00, vende B
10 a 1,50), salvo indicação.

### 3.1 Sessão (`test_session.py`)

| # | Passos | Esperado |
|---|---|---|
| U1 (DP-18) | `advance_to(2)`; `open("T1", …)` às 14:00:02; `open("t1", …)` com a mesma posição e proposta | o segundo levanta `SessionRefusal`; `engine("T1")` continua sendo o primeiro; `engine("t1")` levanta `KeyError` |
| U2 | `open("T1", …)` duas vezes | o segundo levanta `SessionRefusal` (o N1 do DL3-PR06 continua valendo) |
| U3 (DP-19) | fita `calmo` com todos os `seq` diminuídos de 1 (o primeiro vira 0); construir `ReplaySession` | `SessionRefusal` no construtor |
| U4 (DP-19) | idem, diminuídos de 2 (o primeiro vira −1) | `SessionRefusal` no construtor |
| U5 (L2) | `advance_to(2)`; abre `T1` e `T2` às 14:00:02; decisão EXECUTE de `T1` com `nonce` `"x"`, válida de 14:00:02 a 14:01:02; `T1.confirm` às 14:00:02; decisão EXECUTE de `T2` com o **mesmo** `nonce` `"x"`; `T2.confirm` às 14:00:02 | `T1` `WORKING` com `T1:A:1` `LIVE`. `T2.confirm` levanta `DecisionRefusal`; `T2` segue `DRAFT`, sem ordens |
| U6 (L5) | `check_time(datetime(2026, 11, 23, 14, 0, 2))`, sem fuso | `SessionRefusal` |

### 3.2 Script (`test_ticket_replay_script.py`)

| # | Entrada | Esperado |
|---|---|---|
| V1 (DP-18) | fita `calmo`; roteiro `calmo` com um segundo passo `open` igual ao primeiro, trocando só `ticket` para `"t1"`, logo depois dele | código 2; `--out` não é criado. Mesmo resultado no Mac e no Linux |
| V2 (DP-19) | fita `calmo` com todos os `seq` diminuídos de 1; roteiro com as `positions` do `calmo` e um só passo: `open` de `T1` com `after_seq` 0 e `at` 14:00:00 | código 2; `--out` não é criado (hoje esse comando sai com 0) |
| V3 (DP-19) | fita `calmo`; roteiro com as `positions` do `calmo` e dois passos: `open` de `T1` com o `draft` do `calmo`, `after_seq` 0 e `at` 13:59:59; `confirm` de `T1` com `after_seq` 0 e `at` 13:59:59 | código 0; `eventos` 9; `T1` `DRAFT`, sem ordens, `pausada` falso; recibo com 1 evento (`preview`) e hash `474a8476f8851b9ee8314a7060198405a5413fef1258ef52768a20cf8995aabc`; `recusas`: passo 2, `confirm`, `T1`, `EngineRefusal` |
| V4 (L1) | fita `rapido`; roteiro `rapido` só com os 4 primeiros passos | código 0; `eventos` 8; `contas_bloqueadas` = `["sim"]`; `T1` `UNCERTAIN` com `T1:B:1` `UNCERTAIN` e executado 4; recibo de `T1` com 5 eventos (`preview`, `confirm`, `start`, `uncertain`, `uncertain`) e hash `6bf3c975f168427df88334f84ee736801339f7403e5ded0f408f9afd5fcf9ead`; `T2` `DRAFT`, 1 evento, hash `fbcaafa8eb7934ed7fe77a9f497b676904c5cc1647d42e0b8f5a77da4df3e2b5`; `recusas`: passo 4, `confirm`, `T2`, `EngineRefusal` |
| V5 (L4) | fita `calmo`; roteiro `calmo` só com os 4 primeiros passos (sem o `resume`) | código 0; `eventos` 9; `T1` `STOPPED` com `pausada` **verdadeiro**; `T1:A:1` `FILLED` 10 e nenhuma ordem de venda; recibo com 9 eventos (`preview`, `arm`, `trigger`, `confirm`, `start`, `venue_live`, `pause`, `venue_fill`, `stop`) e hash `d285d7d125b6f024311510e96a90af72da458755e2191db19dd937ae510346da`; sem recusas |
| V6 (L3) | texto do roteiro `calmo` com `"decision_ttl_s":60,` trocado por `"decision_ttl_s":60,"decision_ttl_s":60,` | código 2; `--out` não é criado |
| V7 (L6) | roteiro `calmo` com `after_seq` −1 no primeiro passo | código 2; `--out` não é criado |
| V8 (C1) | roda `calmo` com `--out X`, `X` inexistente; depois roda `leilao` com o mesmo `--out X` | a primeira sai com 0; a segunda com 2, e `X` continua com exatamente os arquivos do `calmo`, byte a byte |
| V9 (C1) | sessão `calmo` com `--out` apontando para uma pasta vazia que já existe; e para um arquivo que já existe | código 2 nos dois; a pasta segue vazia; o arquivo fica intacto |
| V10 (C1) | sessão `calmo` com `--out` = `a/b/c` dentro de uma pasta temporária, sem `a` existir | código 0; `c` tem só `resumo.json` e `recibo_T1.jsonl`; em `b` só existe `c` |
| V11 (C1) | os casos de entrada inválida do DL3-PR06 (N3 a N10 e os seis extras) com `--out` **inexistente** | código 2 em todos; `--out` continua inexistente; no diretório pai não sobra pasta temporária |
| V12 (C2) | `ReplaySession.open` trocado por função que levanta `RuntimeError`; sessão `calmo` | `main` levanta `RuntimeError`; `--out` não é criado |
| V13 (C2) | roteiro `calmo` com `account` do `open` trocado para `"ausente"` | código 2 (já passa hoje; passa a depender só da validação prévia) |

As três sessões oficiais continuam nos testes como estão: mesmos esperados e mesmos hashes,
cada execução em pasta inexistente.

**Por que V3 demonstra o DP-19:** 13:59:59 é anterior à primeira cotação da fita (14:00:00).
Se o primeiro evento fosse processado com `after_seq=0`, `check_time` recusaria o passo e o
comando sairia com 2.

Como conferi: executei na cabeça `742b852`, com as peças reais, U5, U6, V3, V4, V5, V6, V7 e
V13. Todos dão exatamente o esperado acima, inclusive os três hashes novos. U1, U3, U4, V1,
V2, V8 a V12 dependem de código novo; conferi o comportamento de hoje para saber o que muda:
V1 sai com 0 no Linux, V2 sai com 0, e todas as recusas do domínio são subclasses de
`ValueError`. Esperado que não reproduzir: **pare e relate**.

## 4. Mutantes que devem morrer, um por vez

1. `open` comparando o id exato, sem `casefold` (U1, V1);
2. sessão aceitando fita com primeiro `seq` 0 (U3, V2);
3. recusa só de `seq` negativo, `< 0` no lugar de `<= 0` (U3);
4. primeiro evento processado mesmo com `after_seq=0` (V3);
5. `contas_bloqueadas` sempre vazio (V4);
6. um livro de decisões por boleta (U5);
7. `pausada` sempre falso (V5);
8. `check_time` aceitando instante sem fuso (U6);
9. roteiro sem a checagem de chave duplicada (V6);
10. `after_seq` negativo aceito (V7);
11. `--out` existente aceito (V8, V9);
12. `--out` ou pasta temporária sobrando depois de código 2 (V11);
13. `except Exception` de volta no `open` (V12);
14. validação prévia da conta do `open` removida (V13).

Os 16 mutantes do DL3-PR06 continuam obrigatórios na cabeça nova.

## 5. Critérios de parada

Pare e relate se: algum esperado do §3 não reproduzir; algum dos quatro hashes das sessões
oficiais mudar; for preciso mudar o motor, `load_replay` ou qualquer arquivo de fita ou
roteiro; `session.py` passar de 150 linhas, o script de 220 ou o PR de 370.

## 6. Limitações registradas (não corrigir neste PR)

- No Windows e em outros sistemas, o `rename` de pasta tem semântica própria. O alvo é
  macOS e Linux.
- As demais decisões DP-01 a DP-17 ficam para cartões seguintes, conforme o registro.

## 7. Entrega

1. Mesma branch e mesmo PR #162, em rascunho. Commit vermelho com U e V; depois o verde. No
   vermelho já passam U2, U5, U6, V3 a V7, V11 e V13: é o esperado.
2. Portão completo em clone limpo no Mac, mais `mypy --strict` no script. O revisor roda o
   Linux.
3. Descrição do PR: cabeça, contagens, linhas por arquivo, mutantes (16 + 14), desvios.
4. Copie este cartão e o registro de decisões para os caminhos do §1. Não edite
   `docs/04_MEM/current_state.md` e não escreva o relatório de fechamento.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

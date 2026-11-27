# DL4-PR03D — Supercartão: cotação antiga avisa, não bloqueia

**Data:** 26/11/2026 · **Autor:** Claude (planejador) · **Implementa:** qualquer agente
**Base:** `main` = `5395015` (DL4-PR03C integrado, PR #199), ou a `main` seguinte se a
diferença for só `docs/04_MEM/current_state.md`.
**PR novo**, em rascunho. Entra antes do Adendo 2 à ADR-0024 e do DL4-PR03E.

**Origem:**

- Decisão de Francisco assinada em 25/11/2026: «cotação antiga nunca bloqueia, só avisa».
  Reverte a L3 de 24/11 só nesse ponto.
- `PROPOSTA_TELA_V3_PARA_PLANNER_2026-11-25.md`, §4, do revisor.
- Revisão do PR #199 (26/11/2026): achados L-1, L-2 e S-3, absorvidos aqui.

## 0. Especificação

### 0.1 Objetivo, em uma frase verificável

Com a cotação de uma perna mais velha que o limite configurado (15 s), a guarda diz
«cotação antiga» em **cautela**, a boleta **pode ser confirmada** e a venda coberta **não
fica retida**; leilão, suspensão, livro inválido, livro incompleto, perda de sequência,
tempo inválido e falta de cotação continuam bloqueando.

### 0.2 Critérios de sucesso (todos medidos; ver §5)

1. Portão: **11.738 aprovados, 16 pulados** (11.733 da base mais 5).
2. Das seis sessões, só a `bova_vencida` muda: 2 dos 13 arquivos. Os outros 11 ficam
   idênticos à base, e 6 das 7 âncoras não mudam.
3. Nova âncora da `bova_vencida`: `88908b798f83…`, 8 eventos, **nenhuma recusa**.
4. As 18 respostas do gabarito batem com a visão e com a tela (B3, S1).
5. 24 mutantes do §6 derrubados, um a um.

### 0.3 O que acontece hoje (conferido em `5395015`)

- `guards.assess` marca `idade > max_quote_age_s` como «cotação vencida», **bloqueante**.
  O limite em `config/ticket_sim.yaml` é 5,0 s.
- O motor usa a guarda em dois lugares: ao confirmar (`_admissible`) e **a cada envio**
  durante a execução (`_drive`). Com cotação vencida, hoje ele recusa a confirmação e
  também segura a venda coberta até chegar cotação nova.
- A sessão `bova_vencida` existe para mostrar esse bloqueio: a primeira confirmação é
  recusada (idade 10 s) e a segunda passa.
- A tela tem o texto «cotação vencida» escrito à mão (achado S-3).

### 0.4 O que este cartão entrega

1. Guarda: o motivo passa a se chamar **«cotação antiga»**, numa constante só, e deixa de
   bloquear.
2. Configuração: `max_quote_age_s` de 5,0 para **15,0**.
3. Tela e visão: leem a constante da guarda (S-3). Nenhum campo muda.
4. Sessão `bova_vencida`, gabarito e âncora refeitos (§3.3).
5. L-1 e L-2 do revisor: testes reforçados (W8 e S7).

### 0.5 Não-objetivos

| Fora | Por quê | Onde fica |
|---|---|---|
| Outras guardas virarem aviso | a decisão assinada fala só de cotação antiga | não previsto |
| Recibo registrar que a confirmação ocorreu sob cautela | o recibo hoje não registra cautela nenhuma (nem «spread aberto»); mudar é formato novo de recibo | pendência (§10) |
| Venda sem cobertura rastreada | motor e Adendo 2 | DL4-PR03E |
| Renomear a sessão `bova_vencida` e a foto `bova-vencida-2` | são identificadores; renomear mexe em seis arquivos sem ganho | não previsto |
| Validador da curva em `ExpiryView` (S-1 do revisor) | a visão sempre monta a curva certa; endurecer o contrato é outro assunto | pendência |
| Ciclo de atualização, cadeia, simulador de quantidade | como no DL4-PR03C | M4, depois do M2, vetado por ora |

Não muda: o formato da visão, o esquema publicado, o recibo, `engine.py`, `sequencing.py`,
`models.py`, as fitas e os roteiros das outras cinco sessões, o script da tela,
`current_state.md`. Nenhuma dependência nova. Nenhum arquivo protegido.

### 0.6 Riscos

| Risco | Mitigação |
|---|---|
| **A venda coberta sai com o livro velho.** Antes o motor esperava cotação nova | é o que a decisão pede («nunca bloqueia»). O preço-limite continua protegendo o preço. Fixado no teste X3b e posto como decisão vetável D2 |
| Tirar o bloqueio enfraquece os testes que usavam cotação vencida como bloqueio temporário | S14, X3 e G8 passam a usar leilão; mutantes 9 e 10 |
| Cotação antiga esconder outro bloqueio | G18 e V1 (leilão às 14:00:17): antiga **e** leilão continua bloqueada; mutantes 6 e 7 |
| Falso «derrubado» por arquivo faltando ou bytecode velho na cópia de mutação | rodar a linha de base da cópia antes; `-B` e sem cache (aconteceu com o revisor e com o planejador) |

## 1. Referência externa

- Nenhuma fonte nova. A regra vem da decisão assinada e do §4 da proposta do revisor.
- A afirmação da proposta de que, em séries pouco líquidas da B3, o livro passa minutos sem
  mudar **não foi verificada** pelo planejador (baixo nível de evidência). Ela não é
  premissa deste cartão: a regra vale por decisão de Francisco.
- Python 3.12, pydantic 2.14.4: nada novo.

## 2. Arquivos e tetos

| Arquivo | O que muda | Linhas (protótipo) |
|---|---|---|
| `backend/derivatives/ticket/guards.py` | constante `STALE_QUOTE`; a condição deixa de bloquear | 97 |
| `backend/derivatives/ticket/view.py` | reexporta `STALE_QUOTE` | 294 (teto 295) |
| `backend/derivatives/ticket/screen.py` | importa a constante da visão | 262 |
| `config/ticket_sim.yaml` | `max_quote_age_s: 15.0` | — |
| `…/sessions/bova_vencida.replay.json` | 4 horários | — |
| `…/sessions/bova_vencida.roteiro.json` | uma confirmação só, às 14:00:20Z | — |
| `…/sessions/bova.gabarito.json` | instante e respostas 4, 5 e 6 da `bova_vencida` | — |
| `tests/unit/derivatives/ticket/test_{guards,engine,view,bova_sessions,screen}.py` | §4 | — |
| `docs/specs/derivatives/fase4/DL4-PR03D.md` | cópia deste cartão | — |

Patch de referência: `DL4-PR03D_PROTOTIPO.patch`, SHA-256 `05bec331fb4c…`, aplica limpo
sobre `5395015`. Doze arquivos, +151 −94.

Novos SHA-256: fita `c98ce2f12aff…`, roteiro `d7ab70705478…`, gabarito `c0c3c72fa53a…`.

## 3. Regra

### 3.1 Guarda

`STALE_QUOTE = "cotação antiga"` em `guards.py`. Na tabela de condições de `assess`, a
linha da idade passa a `(age > config.max_quote_age_s, STALE_QUOTE, False)`. Nada mais muda
na guarda: ordem das condições, limite inclusivo (idade igual ao limite não avisa), demais
bloqueios.

Consequências, todas pelo código que já existe:

| Situação | Antes | Depois |
|---|---|---|
| só cotação antiga | BLOCKED; confirmação recusada | CAUTION; **confirma** |
| cotação antiga e leilão | BLOCKED | BLOCKED, com os dois motivos |
| cotação antiga e spread aberto | BLOCKED | CAUTION, com os dois motivos |
| execução: compra executou, livro da venda está antigo | venda retida até cotação nova | **venda enviada** |
| execução: venda em leilão | retida | retida |

O texto «cotação vencida» some do código, dos testes e das fixtures vivas. Os cartões e
decisões antigos em `docs/` ficam como estão: são história.

### 3.2 Tela e visão

`view.py` reexporta a constante (`from …guards import STALE_QUOTE as STALE_QUOTE`).
`screen.py` a importa da visão, como tudo o mais; continua sem importar a guarda.
A idade da perna ganha a marca da guarda: agora laranja, porque a guarda é cautela.

### 3.3 Sessão `bova_vencida`: «cotação antiga, só aviso»

| | Antes | Depois |
|---|---|---|
| Evento 3 (BOVAM1500) | 14:00:09 | 14:00:19 |
| Evento 4 (BOVAM1450) | 14:00:12 | 14:00:22 |
| Evento 5 (BOVAM1450) | 14:00:14 | 14:00:24 |
| Evento 6 (BOVAM1500) | 14:00:15 | 14:00:25 |
| Roteiro | confirma às 14:00:10 (recusada) e às 14:00:13 | **uma** confirmação, às 14:00:20, depois do evento 3 |
| Foto do gabarito | passo 1, evento 3, 14:00:10 | passo 1, evento 3, **14:00:20** |

Preços, tamanhos, séries, abertura e os eventos 1 e 2 não mudam. Na foto, a BOVAM1450 tem
20,0 s (acima de 15) e a BOVAM1500 tem 1,0 s.

Respostas da `bova_vencida` no gabarito (1 a 3 não mudam):

| # | Antes | Depois |
|---|---|---|
| 4 | BOVAM1450 10.0 s, BOVAM1500 1.0 s; foto bova-vencida-2 | BOVAM1450 **20.0 s**, BOVAM1500 1.0 s; foto bova-vencida-2 |
| 5 | BLOCKED: cotação vencida | **CAUTION: cotação antiga** |
| 6 | não avança: cotação vencida | **pode confirmar** |

Resultado do roteiro inteiro: Concluída, 200 e 200 executados a 1,9000 e 3,9000, bruto
1160,00, recibo com 8 eventos, âncora
`88908b798f830069c5c72169edc46dd00bf73a8bab349f2ccf939bcb170e1665`, lista de recusas vazia.

## 4. Cenários

**Testes existentes que mudam, e só estes** (todos trocam «cotação vencida» por «cotação
antiga»; abaixo, o que mais muda):

| Teste | Esperado novo |
|---|---|
| G2, G3 (`test_guards`) | idade 15 → OK; idade 15,000001 → CAUTION («cotação antiga») |
| S14 (`test_engine`) | a recusa inicial passa a ser por **leilão** na série A |
| X3 | o bloqueio temporário passa a ser **leilão** na série B |
| G8 (renomeado `…blocked_then_fresh…`) | idem, leilão na B às 3599 s |
| V1 `calmo` 5, 21:00 | mercado CAUTION; perna B CAUTION, 25186,0 s |
| V1 `leilao` 1, 14:00:07 | só «leilão, leilão»; idades 7,0 e 6,0 (abaixo de 15) |
| V1 `leilao` 4, 21:00 | mercado CAUTION; perna A CAUTION, 24600,0 s |
| V1 `rapido` 9, 21:00 | só o texto; segue BLOCKED por perda de sequência |
| V3 | borda às 14:00:28 (15,0 e 14,0 s, OK); às 14:00:29, PODE_CONFIRMAR com CAUTION na perna de 16,0 s |
| V4 | às 15:00:00 em ponto, PODE_CONFIRMAR com CAUTION dupla; «prazo precede mercado» provado com boleta em leilão |
| V14 | `leilao`: «BLOCKED: leilão, leilão» |
| W2 | limite 15,0; com configuração de 30,0 a mesma foto fica OK e sem motivo |
| B2, B3, B5, B6, B7, B8 | §3.3; B6 «depois que a fita muda»: evento 4, 14:00:22, OK com 0,0 e 3,0 s |
| S1, S9, S10, S10b, S11, S12, S13 (`test_screen`) | instante 14:00:20; «Cautela: cotação antiga»; «Pode confirmar»; limite «15,0 s»; idade em laranja; com a guarda forçada a BLOCKED, marca-texto |

**Testes novos (5):**

- **G18:** cotação de 3600 s em leilão → BLOCKED («cotação antiga», «leilão»).
- **G19:** 16 s, spread aberto e pouca profundidade → CAUTION, três motivos nessa ordem.
- **G20:** duas pernas, 16 s e 86400 s → CAUTION («cotação antiga», «cotação antiga»).
- **V1, `leilao` 1 às 14:00:17:** BLOQUEADA; «cotação antiga, leilão, cotação antiga,
  leilão»; idades 17,0 e 16,0.
- **X3b:** proposta de referência confirmada aos 3000 s, com as cotações de 0 e 1 s:
  confirma, estado WORKING, compra enviada aos 3000 s. Chega cotação da A aos 3500 s com
  ask 1: A executa e a venda da B sai **aos 3500 s**, com o livro da B ainda de 1 s.

**Testes reforçados, sem teste novo (achados do revisor):**

- **W8 (L-1):** duas compras sem par, multiplicadores 1 e 100, nas duas ordens →
  «multiplicador diferente de 1». O auxiliar `custom` ganha `multipliers` por série.
- **S7 (L-2):** oito cargas hostis em `boleta`, `resumo`, `lado_rotulo` das duas pernas,
  `preco_unidade_indisponivel` e `vencimento_indisponivel`. O conjunto de tags da página
  não cresce e cada texto volta idêntico.

**SHA-256 das três telas do protótipo** (só valem seguindo o patch byte a byte): calmo
`fb18135b8e21…`, vencida `e04863eb1598…`, adverso `e6282a01b7b7…`. As três mudam: a legenda
passa a dizer «15,0 s».

## 5. Evidência do planejador

`5395015`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Portão completo, sobre os bytes finais do patch:** **11.738 aprovados, 16 pulados, 261
  subtestes**, código 0.
- `mypy backend/ --strict`: limpo em 185 arquivos. `pyright backend/`: 0 erros.
  `tests/architecture`: 136 aprovados.
- **Seis sessões**, base × protótipo: mudam só `bova_vencida/recibo_T1.jsonl`
  (`63f3f4bed89b…`) e `bova_vencida/resumo.json` (`a21d78f9596f…`); os outros 11 idênticos.
- **Vermelho, medido** (testes e fixtures novos contra `guards.py`, `view.py`, `screen.py`
  e o YAML da base): **24 falham, 690 passam** em `tests/unit/derivatives/ticket`. Os
  reforços do W8 e do S7 **nascem verdes**: o código já estava certo; a prova deles são os
  mutantes 13 a 20.
- **Mutantes:** 24 plantados, 24 derrubados, em cópia com linha de base conferida (714
  aprovados) e sem bytecode.
- **Olhei a tela** da `bova_vencida`: «Pode confirmar», mercado em laranja, idade 20,0 s em
  laranja. Imagem anexa.
- **Tropeço do planejador:** a primeira cópia de mutação não tinha `docs/specs`; dois
  testes de esquema falhavam nela por isso e apareciam como «derrubou» em todo mutante.
  Refiz com a cópia completa. Nenhum mutante dependia só deles.

**Não conferido pelo planejador:** Mac arm64; `tests/integration`; o contêiner; Windows.

## 6. Mutantes obrigatórios

Um por vez, em cópia cuja linha de base passa inteira. Entre parênteses, quem derrubou.

**Guarda e configuração**

1. Cotação antiga volta a bloquear (B3, B5 a B8, S1, S11, S12, X3b).
2. Limite volta a 5 s (S12, V1, V3, V14, W2).
3. Idade igual ao limite já avisa (V3, G2).
4. Cotação antiga nunca é dita (B3, B6, S1, S12, S13, V1).
5. Texto antigo «cotação vencida» (B3, B6, S1, S12, V1, V3).
6. Cautela sozinha vira OK (B3, B6, S1, S13, V1).
7. Cotação antiga desfaz o bloqueio do leilão (V1, V4).

**Motor** (não muda; os mutantes provam que os testes reescritos ainda o vigiam)

8. Cautela tratada como bloqueio (B1 a B8).
9. Confirmação sem conferir o mercado (S14, B5, B7).
10. Envio sem conferir o mercado (X3, G8).

**Tela e visão**

11. Tela com o texto antigo escrito à mão (S13).
12. Idade antiga sempre em marca-texto (S13).
13. Multiplicador: basta uma perna com 1 (W8).
14. Multiplicador: só a primeira perna (W8).
15. `lado_rotulo` sem escape (S7).
16. Motivo do preço indisponível sem escape (S7).
17. Motivo da curva indisponível sem escape (S7).
18. `<title>` sem escape (S7).
19. `<h1>` sem escape (S7).
20. `veredito.pernas` sem escape (S7).
24. Limite de idade constante na visão (S12, W2).

**Fixtures**

21. Roteiro confirma às 14:00:19 (B2, B7).
22. Gabarito: resposta 6 da vencida ainda «não avança» (B2, B3, B8).
23. Fita: evento 1 um segundo mais tarde (B2, B3, B6, S1, S13).

## 7. Critérios de parada

Pare e relate se:

- a `main` diferir de `5395015` fora de `docs/04_MEM/current_state.md`;
- algum esperado do §3.3 ou do §4 não reproduzir;
- mudar algum arquivo de saída das sessões além dos dois da `bova_vencida`, ou alguma
  âncora além da dela;
- o esquema publicado da visão ou o da prévia mudar;
- for preciso tocar em `engine.py`, `sequencing.py`, `models.py`, `receipt.py`,
  `session.py`, nas outras cinco sessões ou no script da tela;
- sobrar «cotação vencida» em `backend/`, `config/`, `scripts/` ou `tests/`;
- `tests/integration` der resultado diferente da linha de base (as mesmas 4 falhas, pelos
  IDs).

**Adendos:** vale a pré-autorização de Francisco de 25/11/2026 (restaurar regra que o
cartão já declara, ou fortalecer teste e mutante). Fora disso, Francisco decide.

**Reversão:** reverter o commit verde devolve o bloqueio e os 5 s, mas **não** as fixtures.
Para voltar tudo, reverta os dois commits.

## 8. Entrega

1. **Commit vermelho:** os cinco arquivos de teste e as três fixtures (fita, roteiro,
   gabarito). O cenário e o gabarito vêm antes do código, como Francisco pediu. Vai ao
   GitHub antes do verde, **com o PR em rascunho já aberto**, para a ordem ficar
   comprovável (nota do revisor no PR #199).
2. **Commit verde:** `guards.py`, `view.py`, `screen.py`, `config/ticket_sim.yaml`.
3. Portão no Mac arm64 em clone limpo e portão Linux no contêiner, imagem do lock da
   cabeça. Esperado: **11.738 aprovados, 16 pulados**; `mypy backend/ --strict` e
   `pyright backend/` limpos.
4. Integração só no contêiner: as mesmas 4 falhas conhecidas, pelos IDs.
5. Os 13 arquivos das seis sessões, base × candidato, com SHA-256.
6. As três telas pelo script, com SHA-256 e imagem. A da `bova_vencida` agora é
   `--passos 1 --avanca-ate 3 --instante 2026-11-25T14:00:20Z`.
7. Na descrição do PR: cabeça, arquitetura, imagem, versões, comandos, logs, contagens, os
   24 mutantes, desvios. Declare os reforços que nascem verdes.
8. Copie este cartão para o caminho do §2. Não edite `current_state.md`.
9. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada.

**Revisor:** roda a suíte, a tipagem e os 24 mutantes em ambiente próprio, sem bytecode.
Refaz à mão as idades da foto (20,0 e 1,0 s) e confere que X3b prova o envio com livro
antigo. Abre a tela da `bova_vencida`.

**Prova de uso (Francisco), depois do GO:** as 6 perguntas nas três telas. Critério
binário: 18 de 18 **na primeira tentativa**. Vale também como a prova do DL4-PR03C, que
ficou pendente: as telas são as mesmas, e a da `bova_vencida` já sai na regra nova.

## 9. Decisões

### 9.1 Do planejador, que Francisco pode vetar

| # | Decisão | Por quê |
|---|---|---|
| D1 | O motivo passa a se chamar **«cotação antiga»** | é a sua palavra; «Cautela: cotação vencida · Pode confirmar» se contradiz na tela |
| D2 | **A venda coberta também não espera cotação nova.** A cotação antiga não segura nada, nem na confirmação nem no envio | «nunca bloqueia». A alternativa é avisar na confirmação e ainda reter o envio da venda; isso é regra nova no motor e pede outro cartão |
| D3 | Só a cotação antiga vira aviso | leitura estreita da decisão assinada; leilão, suspensão, livro inválido ou incompleto, perda de sequência, tempo inválido e falta de cotação seguem bloqueando |
| D4 | Sessão e foto mantêm os nomes `bova_vencida` e `bova-vencida-2` | identificadores; renomear não muda comportamento |
| D5 | O recibo não registra a cautela | já é assim com «spread aberto»; mudar o recibo é formato novo |
| D6 | S-1 do revisor (validador da curva) fica fora | sem efeito hoje; pendência |

### 9.2 De Francisco

- Assinada em 25/11/2026: cotação antiga nunca bloqueia, só avisa; limite configurável de
  15 s. **Este cartão a executa.**
- Assinada em 25/11/2026: venda sem cobertura rastreada com aviso de verificação. **Não
  entra aqui** (DL4-PR03E). Com ela, o argumento «o pior caso da cotação antiga é ficar
  comprado» deixa de valer; o Adendo 2 tem de dizer isso.

## 10. Depois deste cartão

Fila até o M2: **DL4-PR03D** → prova de uso → Adendo 2 à ADR-0024 (minuta do planejador,
commit de Francisco) → DL4-PR03E → DL4-PR04.

Pendências sem cartão:

- o recibo não registra que a confirmação ocorreu sob cautela (D5);
- o motor ignora o multiplicador do contrato em todo valor em reais (antes do M4);
- validador da curva em `ExpiryView` e comentário sobre o contexto exato (S-1 das duas
  revisões);
- as 4 falhas de `tests/integration`; a docstring de `series_code`; a fonte do spread do
  DL4-PR07.

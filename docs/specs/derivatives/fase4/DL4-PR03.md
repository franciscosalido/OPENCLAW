# DL4-PR03 — Supercartão: a tela da boleta e a prova de uso do M1

**Data:** 25/11/2026 · **Autor:** Claude (planejador) · **Implementa:** Codex
**Base:** `main` = `6ca0e5f` (DL4-PR02 integrado, PR #191), ou a `main` seguinte se o PR #190
(só `docs/04_MEM/current_state.md`) já estiver integrado. Confira que
`git diff 6ca0e5f origin/main --stat` está vazio ou lista só esse arquivo.
**PR novo**, em rascunho. Fecha o marco M1.

**Origem:**

- Blueprint da Fase 4, §6 (M1, «a tela, lendo só o modelo») e §2 (prova de uso: 18 de 18,
  sem consultar JSON). L1 da blueprint: HTML estático, sem servidor e sem dependência.
- Plano de PRs do colaborador, cartão «DL4-PR03».
- Regra de apresentação de Francisco (20/11/2026): alerta é marca-texto no fundo; vermelho
  só em número negativo; preto no resto.
- DL4-PR01 (D4): formatar dinheiro é da tela. DL4-PR02: o gabarito já está gravado.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos em `6ca0e5f`:

- `ticket_view` devolve tudo o que a prova de uso pergunta, mas só como objeto ou JSON.
  Francisco não tem como ler uma boleta sem abrir terminal.
- O gabarito do M1 (`bova.gabarito.json`) fixa três fotos e 18 respostas.
- Em `scripts/`, só `derivatives_ticket_replay.py` pode importar o emissor de decisões
  (`gate.issue`); `tests/architecture/test_ticket_boundaries.py` confere isso.

**O que este cartão entrega.**

1. **`render_ticket(view)`**: função pura que transforma a visão num documento HTML
   autocontido. Só formata. Não calcula, não decide, não lê motor, sessão nem guarda.
2. **`scripts/derivatives_ticket_screen.py`**: gera a tela de uma boleta num ponto de um
   replay e grava um arquivo `.html` novo.
3. **O roteiro da prova de uso do M1** (§9), que Francisco executa depois da integração.

**O que este cartão não faz.**

- Não tem servidor, FastAPI, JavaScript, rede, fonte ou imagem externa.
- Não tem botão, formulário nem ação. Confirmar é do DL4-PR04.
- Não mostra execução por perna, ordens nem recibo (DL4-PR05 e DL4-PR06).
- Não muda `view.py`, o motor, a sessão, o esquema da visão nem o script de replay.
- Não muda fixtures, gabarito nem teste existente.
- Não imita a tela do PnT. A referência de telas do projeto é «não verificada».

Nenhuma dependência nova: só biblioteca padrão (`html`, `decimal`, `datetime`).

## 1. Referência externa

Não há matéria de FIX nem de OIC. Conferido na documentação do Python 3.12:

- `html.escape(s)` troca `&`, `<` e `>`; com `quote=True` (padrão), também aspas.
- `Decimal.quantize`, `abs()` e o operador unário arredondam pelo **contexto de quem
  chama**; `copy_abs()` e `is_signed()` não usam contexto. A tela usa os dois últimos e um
  contexto exato próprio no `quantize`. É a mesma classe de defeito do Adendo 1 do DL4-PR01,
  e **o primeiro protótipo deste cartão caiu nela** (§5).

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (protótipo) |
|---|---|---|
| `backend/derivatives/ticket/screen.py` | **novo**: `render_ticket`, `brl`, `seconds`, `clock` | 165 (155) |
| `scripts/derivatives_ticket_screen.py` | **novo** | 90 (81) |
| `tests/unit/derivatives/ticket/test_screen.py` | **novo**: S1 a S11 | — |
| `docs/specs/derivatives/fase4/DL4-PR03.md` | cópia deste cartão | — |

**Não muda:** nenhum outro arquivo de produção, nenhum teste existente, nenhuma fixture,
`visao.schema.json`, `current_state.md`. Linhas novas com até 100 colunas.

Patch de referência: `DL4-PR03_PROTOTIPO.patch`, SHA-256 `e53e90cc156d…`, aplica limpo
sobre `6ca0e5f`. Pode ser reescrito, desde que §3, §4 e §6 se cumpram.

## 3. Regra

### 3.1 `screen.py`

Importa **só** `datetime`, `decimal`, `html` e `backend.derivatives.ticket.view`.

**`brl(value: Decimal) -> str`**

- `adjusted() > 15`: devolve `"R$ "` mais o texto decimal do motor, sem reformatar.
- Senão: duas casas, vírgula decimal, ponto de milhar, sinal antes do `R$`.
- Zero negativo não leva sinal. Não depende do contexto decimal de quem chama.

| Entrada | Saída |
|---|---|
| `0` | `R$ 0,00` |
| `0.10` | `R$ 0,10` |
| `-210.00` | `-R$ 210,00` |
| `1234567.5` | `R$ 1.234.567,50` |
| `1E+2` | `R$ 100,00` |
| `15E-1` | `R$ 1,50` |
| `-0.00` | `R$ 0,00` |
| `1E+15` | `R$ 1.000.000.000.000.000,00` |
| `1E+16` | `R$ 1E+16` |
| `-1E+16` | `R$ -1E+16` |

**`seconds(value: float) -> str`**: uma casa, vírgula, sufixo ` s`. `4.96` dá `5,0 s`;
`0.05` dá `0,1 s`; `25186.0` dá `25186,0 s`.

**`clock(value: datetime) -> str`**: `DD/MM/AAAA HH:MM:SS UTC`.

**`render_ticket(view: TicketView) -> str`**

Documento HTML5 completo, `lang="pt-BR"`, UTF-8, CSS embutido, terminado em quebra de
linha. Começa por `<!DOCTYPE html>`. Traz
`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">`.
Não tem `script`, `img`, `link`, `a`, `iframe`, `form`, `input` nem `button`. Todo texto que
vem da visão passa por `html.escape`. Duas chamadas com a mesma visão dão os mesmos bytes.

Cada valor fica num elemento com `data-campo`, sem repetição:

| `data-campo` | Texto visível |
|---|---|
| `aviso`, `boleta`, `conta`, `foto_cotacao` | o texto da visão |
| `instante`, `prazo_envio`, `validade_ordens` | `clock` |
| `rotulo` | o rótulo; com `pausada`, mais ` · pausada` |
| `versao` | o número |
| `resumo` | os 12 primeiros caracteres |
| `avanco` | «Pode confirmar»; «Não avança: *motivo*»; «Não se aplica: *rótulo*» |
| `pernas.N.lado` | `lado_rotulo` |
| `pernas.N.quantidade`, `pernas.N.serie` | o valor |
| `pernas.N.tipo` | «Call» ou «Put», espaço, o ativo |
| `pernas.N.strike`, `pernas.N.preco_limite` | `brl` |
| `pernas.N.vencimento` | `DD/MM/AAAA` |
| `pernas.N.cotacao.compra`, `.venda` | `brl`, ` × `, a quantidade; lado vazio é `—` |
| `pernas.N.cotacao.fase` | «Contínuo», «Leilão» ou «Suspenso» |
| `pernas.N.cotacao.idade_s` | `seconds` |
| `pernas.N.cotacao` | **só quando não há cotação**: «sem cotação»; os quatro acima somem |
| `pernas.N.guarda` | o nível traduzido; com motivos, `: ` e os motivos separados por vírgula |
| `custo.liquido_assinado` | «Paga no máximo », «Recebe no mínimo » ou «Líquido zero: », mais `brl` do valor absoluto |
| `custo.bruto_teto`, `risco.exposicao_montagem` | `brl` |
| `risco.vencimento.pior_resultado`, `.melhor_resultado` | `brl`; extremo ilimitado é «ilimitado» |
| `risco.vencimento` | **só com perfil indisponível**: «indisponível: *motivo*»; os dois acima somem |
| `mercado` | como a guarda da perna |

Níveis: `OK` → «Sem aviso», `CAUTION` → «Cautela», `BLOCKED` → «Bloqueado». **Os motivos
saem literais**, como o motor os escreve.

Rótulos fixos dos dois riscos: «Desembolso se só a compra executar» e «Pior resultado no
vencimento» (mais «Melhor resultado no vencimento»). Nunca «perda máxima».

**Classes** (regra de Francisco de 20/11/2026):

- `alerta` (marca-texto): `avanco` quando bloqueada; guarda `BLOCKED`; «sem cotação».
- `cautela` (marca-texto mais fraco): guarda `CAUTION`; perfil indisponível.
- `neg` (vermelho): **só** em valor monetário negativo. Nenhum outro elemento é vermelho.
- «Pode confirmar» e «Não se aplica» não levam marca-texto, mesmo com o mercado em cautela.

A tela não lê `mercado.nivel` para pintar o avanço. Quem diz se avança é `avanco`.

### 3.2 `scripts/derivatives_ticket_screen.py`

```
--replay ARQ --roteiro ARQ --passos N --avanca-ate SEQ --boleta ID --instante ISO --out ARQ
```

1. Lê roteiro e fita com `_read` e `load_replay`; cria a sessão com a configuração padrão.
2. Executa os **N primeiros passos** como o script oficial (mesma ordem: `advance_to`,
   `check_time`, o passo; recusa do motor é ignorada e segue). `N` fora de
   `1..len(passos)` é erro. **Não chama `finish`.**
3. `advance_to(SEQ)`; `ticket_view(sessão, boleta, instante)`; `render_ticket`.
4. Grava com modo exclusivo (`"x"`), UTF-8, quebra de linha `\n`. Destino existente é erro
   e fica intocado.

Devolve 0 e grava, ou devolve 2, registra o motivo com `loguru` e **não cria arquivo**:
passos fora do roteiro; boleta não aberta naquele ponto; instante sem fuso, ilegível ou
fora da janela do cursor; avanço que retrocede; arquivo de entrada inválido.

**Fronteira:** o script reaproveita `_read`, `_act`, `_Open`, `_External` e `_Script` de
`scripts.derivatives_ticket_replay`. **Não importa `gate.issue`**; o teste de arquitetura
existente continua valendo sem mudança.

## 4. Cenários

Fotos do gabarito: `bova_calmo` (1 passo, seq 2, 14:00:02Z), `bova_vencida` (1, 3,
14:00:10Z), `bova_adverso` (1, 2, 14:00:02Z). O leitor de teste usa `html.parser` e lê só
o texto visível e as classes dos elementos com `data-campo`.

**S1 — as 18 respostas estão na tela.** Montadas só do texto visível:

| | `bova_calmo` | `bova_vencida` | `bova_adverso` |
|---|---|---|---|
| 1 | Compra 100 BOVAA1500 Call BOVA11 R$ 150,00 a R$ 4,20; Venda 100 BOVAA1550 Call BOVA11 R$ 155,00 a R$ 2,10 | Compra 200 BOVAM1450 Put BOVA11 R$ 145,00 a R$ 1,90; Venda 200 BOVAM1500 Put BOVA11 R$ 150,00 a R$ 3,90 | Compra 200 BOVAA1550 Call BOVA11 R$ 155,00 a R$ 2,15; Venda 200 BOVAA1600 Call BOVA11 R$ 160,00 a R$ 0,95 |
| 2 | Paga no máximo R$ 210,00; teto bruto R$ 630,00 | Recebe no mínimo R$ 400,00; teto bruto R$ 1.160,00 | Paga no máximo R$ 240,00; teto bruto R$ 620,00 |
| 3 | desembolso R$ 420,00; pior resultado -R$ 210,00 | desembolso R$ 380,00; pior resultado -R$ 600,00 | desembolso R$ 430,00; pior resultado -R$ 240,00 |
| 4 | 2,0 s e 1,0 s; foto bova-calmo-2 | 10,0 s e 1,0 s; foto bova-vencida-2 | 2,0 s e 1,0 s; foto bova-adverso-2 |
| 5 | Sem aviso | Bloqueado: cotação vencida | Bloqueado: spread aberto, pouca profundidade, leilão |
| 6 | Pode confirmar | Não avança: cotação vencida | Não avança: spread aberto, pouca profundidade, leilão |

São as mesmas 18 respostas do gabarito, agora no formato da tela.

**S2 — campo a campo.** Nas três fotos e em `bova_adverso` 2 passos, seq 3, 14:00:04Z: o
conjunto de `data-campo` é exatamente o do §3.1 para uma boleta de duas pernas com cotação
e perfil; cada texto é o campo da visão formatado; cada valor em reais, desfeito o formato,
é igual ao `Decimal` da visão.

**S3 — formatos na borda.** A tabela de `brl` do §3.1 e os casos de `seconds`, sem contexto
especial e sob `Context(prec=3)` com a armadilha ligada e desligada. A tela inteira da
`bova_vencida` sai com os mesmos bytes sob `prec=3`.

**S4 — ausência dita por extenso.** (fitas montadas no teste, como no V5 do DL4-PR01)

- série sem cotação: `pernas.1.cotacao` «sem cotação» com `alerta`; nenhum
  `pernas.1.cotacao.*`; guarda «Bloqueado: sem cotação»;
- lado de venda vazio: `venda` é `—`; `compra` é `R$ 0,95 × 50`;
- fase suspensa: «Suspenso»; a outra perna, «Contínuo»;
- `rapido` 2 passos: `risco.vencimento` «indisponível: posição inicial não nula»; não há
  `pior_resultado`;
- compra seca de 10 a 1,00: pior `-R$ 10,00`, melhor «ilimitado».

**S5 — marca-texto e vermelho.** `bova_adverso` 1: `avanco` e `mercado` com `alerta`; perna
0 com `cautela`, perna 1 com `alerta`; fase da perna 1 «Leilão»; `neg` em **todo** campo
cujo texto começa por `-R$` e em nenhum outro. `bova_calmo`: nenhum `alerta` nem
`cautela`. `bova_adverso` 2 passos, seq 3, 14:00:04Z: `avanco` «Pode confirmar» **sem**
`alerta`; `mercado` «Cautela: spread aberto, pouca profundidade» com `cautela`.

**S6 — fora da confirmação.** `calmo` 5 passos, seq 9, 21:00:00Z: «Não se aplica:
Concluída», sem `alerta`; líquido «Recebe no mínimo R$ 5,00»; pior resultado `R$ 5,00`
(positivo, preto). `bova_calmo` pausada: `rotulo` «Proposta · pausada»; `avanco` «Não
avança: boleta pausada». Líquido zero: «Líquido zero: R$ 0,00».

**S7 — inerte, escapada, determinística.** Duas chamadas dão a mesma página. A CSP está
presente. Não há nenhuma das etiquetas proibidas nem `http:`, `https:`, `javascript:`,
`url(`, `@import` ou atributo de evento. Com `<script>alert("x")</script>&<b>` em `rotulo`,
`foto_cotacao`, `conta`, `aviso`, no motivo do avanço, nos motivos do mercado e da perna 0,
na série e no ativo: nenhuma etiqueta `script` ou `b` é criada, e o texto lido de volta é o
original.

**S8 — a tela só conhece a visão.** Os módulos importados por `screen.py` são exatamente
`datetime`, `decimal`, `html` e `backend.derivatives.ticket.view`.

**S9 — o script grava os bytes da visão e não sobrescreve.** `bova_vencida`, 1 passo, seq
3, 14:00:10Z: devolve 0; o arquivo é `render_ticket(ticket_view(...))` em UTF-8; a pasta só
tem esse arquivo. Com destino existente: devolve 2 e o conteúdo antigo fica igual.

**S10 — pontos inválidos devolvem 2 e não criam arquivo.** Sobre o ponto do S9, um por
vez: `--passos 0`; `--passos 4`; `--boleta T9`; `--instante` sem fuso; `14:00:08Z` (antes
do último evento); `14:00:13Z` (depois do próximo); `ontem`; `--avanca-ate 1`.

**S10b — passos que o fatiamento aceitaria.** `--passos 4` com seq 6 e 14:00:15Z, e
`--passos -1` com seq 4 e 14:00:13Z: devolvem 2. Sem a conferência de `N`, os dois gravariam
uma tela. O protótipo só pegou isso com mutante (§5).

**S11 — confirmações como no roteiro oficial.** `bova_vencida`, 3 passos, seq 6,
14:00:15Z: `rotulo` «Concluída»; `avanco` «Não se aplica: Concluída».

## 5. Evidência do planejador

`6ca0e5f`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Portão completo no protótipo:** **11.717 aprovados, 16 pulados, 261 subtestes**,
  código 0. São os 11.697 da base mais 20 novos. Nenhum teste existente mudou.
- `mypy backend/ --strict`: limpo em 184 arquivos. `pyright` em `backend/` e no script:
  0 erros. `tests/architecture`: passa.
- **Sessões oficiais** pelo script de replay: os 7 arquivos idênticos à base.
- **A tela foi vista**, não só testada: renderizada em Chrome sem interface. A imagem da
  `bova_adverso` vai anexa (`DL4-PR03_tela_bova_adverso.png`).
- **Mutantes:** 29 plantados, 29 detectados (§6).
- **Três defeitos do próprio protótipo:**
  1. `brl` usava `abs()` e `quantize` no contexto de quem chama; sob `prec=3`, R$
     1.234.567,50 sairia arredondado. Corrigido com `copy_abs` e contexto exato; S3 prende.
  2. A conferência de `--passos` não tinha teste que a exigisse; o mutante sobreviveu e
     nasceu o S10b.
  3. A tradução da fase não era conferida; o mutante sobreviveu e entrou em S4 e S5.
- **Código morto removido por mutante:** classe `neg` em strike e preço-limite (sempre
  positivos) e escape do nome do campo (constante interna).

**Ressalva:** depois do portão completo, o protótipo recebeu três ajustes só de CSS
(largura, fonte da tabela e `white-space`). Depois deles rodaram `test_screen.py` e
`tests/architecture` (156 aprovados) e a tela foi vista de novo; **o portão completo não
foi repetido**. Nenhum teste lê o CSS.

**Não conferido pelo planejador:** Mac arm64; Safari; `tests/integration`; o contêiner.

## 6. Mutantes obrigatórios

Um por vez. Entre parênteses, quem derrubou no protótipo.

*Tela:*

1. O campo do desembolso mostra o pior resultado (S1, S2, S5).
2. Texto sem escape (S7).
3. Verbos do líquido trocados (S1, S6).
4. Líquido com sinal, sem valor absoluto (S1, S2, S6).
5. Idade com ponto decimal (S1, S3).
6. Milhar sem ponto (S1, S3).
7. Série sem cotação vira `R$ 0,00 × 0` (S4).
8. Bloqueio sem marca-texto (S5).
9. «Pior» mostra o melhor (S1, S2, S4, S5, S6).
10. Extremo negativo sem vermelho (S5).
11. Motivo do bloqueio omitido (S1, S6, S7).
12. `mercado` tirado da guarda da primeira perna (S1, S2).
13. Sem CSP (S7).
14. «ilimitado» vira traço (S4).
15. `quantize` no contexto de quem chama (S3).
16. Sinal negativo perdido (S1 a S5).
17. Lado vazio vira zero (S4).
18. Motivo do perfil indisponível some (S4).
19. A pausa não aparece (S6).
20. Cautela no mercado pinta o avanço de alerta (S5).
21. A tela importa o motor (S8).
22. `brl` sem limite de escala (S3).
23. Guarda da perna sem motivos (S1, S2, S4, S5).
24. Fase sem tradução (S4, S5).

*Script:*

25. Sobrescreve o destino (S9).
26. Ignora `--avanca-ate` (S9, S10, S11).
27. Não confere o número de passos (S10b).
28. Consome a fita inteira (S9).
29. Boleta ausente vira sucesso (S10).

## 7. Critérios de parada

Pare e relate se:

- a `main` diferir de `6ca0e5f` fora de `docs/04_MEM/current_state.md`;
- algum esperado do §4 não reproduzir;
- for preciso mudar `view.py`, o motor, a sessão, o script de replay, o esquema ou qualquer
  fixture;
- qualquer teste existente mudar de resultado, inclusive os de arquitetura;
- alguma das 7 âncoras (4 oficiais e 3 de BOVA11) mudar;
- a tela precisar de JavaScript, rede ou dependência;
- `tests/integration` der resultado diferente da linha de base (as mesmas 4 falhas, pelos
  IDs).

**Reversão:** o PR só acrescenta arquivos.

## 8. Entrega

1. Commit vermelho só com `test_screen.py`; depois o verde com `screen.py` e o script.
2. Portão no Mac arm64 em clone limpo e portão Linux no contêiner, imagem do lock da
   cabeça. Esperado: **11.717 aprovados, 16 pulados**; `mypy backend/ --strict` e `pyright`
   limpos (inclua o script novo no `pyright`).
3. Integração só no contêiner: as mesmas 4 falhas conhecidas.
4. **Gere as três telas do §9 na cabeça candidata e anexe os três `.html`, com SHA-256, e
   uma captura de cada uma**, Mac e Linux. Os bytes têm de ser iguais nas duas plataformas.
   Com o protótipo: calmo `c81d16490db4…`, vencida `5089cfb5c31b…`, adverso
   `5c1f6c493bd0…`. **Hash diferente não é parada** se você mudou CSS ou marcação dentro do
   §3; declare o seu.
5. Para o revisor e na descrição do PR: cabeça, arquitetura, imagem, versões, comandos,
   logs, contagens, linhas dos dois arquivos, os 29 mutantes, desvios.
6. Copie este cartão para o caminho do §2. Não edite `current_state.md`.
7. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, no ambiente do
   lock; relatórios fora do Git, SHA-256 na descrição.
8. Adendo só entra na cópia versionada com a autorização de Francisco colada na descrição
   do PR, com data.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda por conta
própria o S1, o S7 e os mutantes 2, 15 e 27, e **abre as três telas num navegador**.

## 9. Prova de uso do M1 (Francisco, depois da integração)

**Não faz parte do PR.** É o critério de aceite do marco.

**Gerar as três telas**, no Mac:

```bash
cd ~/projetos/OPENCLAW && git switch main && git pull --ff-only && uv sync --locked
S=tests/fixtures/derivatives/synthetic/ticket/sessions
P="$HOME/prova-m1" && mkdir -p "$P"
tela() { uv run python scripts/derivatives_ticket_screen.py \
  --replay "$S/$1.replay.json" --roteiro "$S/$1.roteiro.json" \
  --passos 1 --avanca-ate "$2" --boleta T1 \
  --instante "2026-11-25T$3Z" --out "$P/$1.html"; }
tela bova_calmo 2 14:00:02
tela bova_vencida 3 14:00:10
tela bova_adverso 2 14:00:02
open "$P"/bova_*.html
```

**Regras da prova:**

- Olhando só para cada tela, responder as 6 perguntas do gabarito (§3.4 do DL4-PR02).
- **Sem abrir** JSON, terminal, o cartão do DL4-PR02 nem o arquivo de gabarito.
- As 18 respostas vão para o chat de planejamento, que as confere contra o gabarito, por
  valor.

**Aceite, binário:** 18 de 18. Com 17 ou menos, o M1 não está aceito, e a resposta errada
vira cartão de correção da tela (ou do gabarito, se o erro for dele). O resultado é
registrado no `current_state.md`.

## 10. Decisões do planejador que Francisco pode vetar

| # | Decisão | Por quê |
|---|---|---|
| D1 | Horas em UTC, com o rótulo «UTC» | é o que a visão guarda; converter para Brasília é cálculo novo e depende de base de fusos |
| D2 | Níveis traduzidos («Sem aviso», «Cautela», «Bloqueado»); motivos literais | o nível é rótulo de tela; o motivo é do motor |
| D3 | O script novo reaproveita funções privadas do script de replay | a alternativa é refatorar o script oficial, o que este cartão proíbe |
| D4 | Os bytes do HTML não são presos por hash no teste | prender obrigaria a copiar o CSS do protótipo; o contrato são os campos e os textos |
| D5 | `resumo` com 12 caracteres | basta para conferir a versão a olho; o M2 usa o resumo inteiro por dentro |
| D6 | A nota N-1 do DL4-PR01 (`formato` aceita `true` e `1.0`) continua pendente | a tela recebe o objeto da visão, não lê JSON; não há leitura a endurecer |

## 11. Depois deste cartão

Com 18 de 18, o M1 fecha. DL4-PR04: confirmação de uma versão exata no simulador, com a
confirmação antiga recusada à vista. Antes de escrevê-lo, Francisco responde a L2 da
blueprint: confirmar pelo terminal ou por página local.

Pendências sem cartão: as 4 falhas de `tests/integration`; a docstring de `series_code`
(nota N-1 do parecer do DL4-PR02); a fonte do spread do DL4-PR07.

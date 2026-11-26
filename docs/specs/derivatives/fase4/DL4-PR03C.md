# DL4-PR03C — Supercartão: tela v3 da boleta em replay

**Data:** 26/11/2026 · **Autor:** Claude (planejador) · **Implementa:** qualquer agente (§0.6)
**Base:** `main` = `2bd6613` (DL4-PR03B integrado, PR #196), ou a `main` seguinte se a
diferença for só `docs/04_MEM/current_state.md`.
**PR novo**, em rascunho. Entra antes do DL4-PR03D.

**Origem:**

- Prova de uso do M1 (25/11/2026): 18 de 18 de conteúdo, layout reprovado por Francisco.
- `PROPOSTA_TELA_V3_PARA_PLANNER_2026-11-25.md` e `PROTOTIPO_V3_BOLETA_CADEIA.html`, do revisor.
- Revisão pós-merge do PR #196 (26/11/2026): achados L-1 e S-2, pré-requisitos deste cartão.
- Escolhas de Francisco: **Bid antes de Ask** e **coluna Meio**.

## 0. Especificação

### 0.1 Objetivo, em uma frase verificável

Nas três fotos do gabarito BOVA, a tela mostra o destino da ordem, o veredito com a guarda
de cada perna, o preço da estrutura por unidade numa régua, a curva do resultado no
vencimento com o equilíbrio, e a foto ao lado das idades, **lendo só a visão formato 2**.

### 0.2 Critérios de sucesso (todos medidos; ver §5)

1. As 18 respostas do gabarito continuam legíveis só pelo texto da tela (S1).
2. Todo campo novo da tela desfaz para o valor da visão (S2).
3. Portão: **11.733 aprovados, 16 pulados** (11.724 da base mais 9).
4. Os 13 arquivos de saída das seis sessões ficam idênticos à base.
5. 40 mutantes do §6 derrubados, um a um.
6. Nenhum `<script>`, rede ou recurso externo na página (S7).

### 0.3 O que acontece hoje (conferido em `2bd6613`)

- A tela é a do DL4-PR03: lista de campos no topo, tabela, custo e risco. Não lê nenhum dos
  campos do formato 2 (ambiente, meio, preço por unidade, equilíbrios, curva, modalidade,
  limite de idade).
- A foto fica no cabeçalho e as idades na tabela: foi o que obrigou Francisco a caçar a
  resposta 4 na prova de uso.
- `acima_do_meio` ignora o multiplicador do contrato (achado S-2). O motor também ignora o
  multiplicador em todo valor em reais; o perfil no vencimento já recusa multiplicador
  diferente de 1.
- Nenhum teste fixa o arredondamento do equilíbrio em meio centavo (achado L-1).

### 0.4 O que este cartão entrega

1. Tela v3 estática (`screen.py` refeito, `screen_draw.py` novo).
2. S-2: preço por unidade indisponível com multiplicador diferente de 1 (`view.py`, +4 linhas).
3. L-1: teste do meio centavo no equilíbrio (W9).

### 0.5 Não-objetivos (o freio de escopo)

| Fora | Por quê | Onde fica |
|---|---|---|
| **Simulador de quantidade** | exige script na página; o portão não executa JavaScript, e seria o único número da tela que não vem do motor | decisão D1 (§9); se Francisco quiser, cartão próprio |
| Ciclo de atualização de 15 s, botão de pausa | só existe com fonte ao vivo | M4 |
| Cadeia espelhada | não há fonte de cadeia | depois do M2 |
| Cotação antiga como aviso | muda a guarda | DL4-PR03D |
| Venda sem cobertura rastreada | muda o motor e exige o Adendo 2 | DL4-PR03E |
| Nome da estratégia, PoP, extrínseco, faixa de VI | lógica nova ou modelo | DL4-PR09 |
| Zonas de lucro e perda pintadas na curva | enfeite; a linha, o zero e o equilíbrio já respondem | não previsto |

Não muda: o formato da visão (segue 2), o esquema publicado, a guarda, o motor, os
roteiros, as fitas, o gabarito, o script da tela, `current_state.md`. Nenhuma dependência
nova. Nenhum arquivo protegido.

### 0.6 Cartão agnóstico de agente

Este cartão serve a qualquer implementador (Codex, Claude Code ou outro) e a qualquer
revisor. Ele não usa comando, ferramenta nem formato de um fornecedor. As regras do
repositório vêm de `AGENTS.md` e `CLAUDE.md`, que dizem o mesmo sobre este trabalho. O que o
agente precisa está aqui: base, arquivos, regra, esperados, mutantes, critérios de parada.
Quem implementa não revisa o próprio PR.

### 0.7 Riscos

| Risco | Mitigação |
|---|---|
| A tela passa a decidir (comparar idade com limite, classificar risco) | a idade só ganha marca quando a guarda da perna traz «cotação vencida», e com o nível da guarda (S13; mutantes 3 a 5) |
| Desenho depende do contexto decimal de quem chama | coordenadas por `Fraction`; S17 sob `prec=3` |
| Bandeira não aparece em alguns sistemas | `title` e `aria-label` com o texto (S14; mutante 14) |
| Texto hostil dentro do SVG | todo texto passa por `escape`; S7 |
| A tela v3 muda de novo no DL4-PR03D | a marca da idade segue o nível da guarda; nada aqui depende de bloqueio |

## 1. Referência externa

- **MDN, `Content-Security-Policy: script-src`** e **OWASP, CSP Cheat Sheet**: script
  embutido só roda com `'unsafe-inline'`, nonce ou hash. A página mantém
  `default-src 'none'; style-src 'unsafe-inline'`, sem `script-src`: nenhum script roda.
  Foi o que pesou na decisão D1.
- **Python 3.12, `fractions` e `decimal`**: `Fraction(Decimal)` é exata. `format(d, "f")`
  sem precisão não arredonda. `quantize` sem contexto usa o de quem chama (lição repetida).
- **Pydantic 2.14 (lock 2.14.4)**: nada novo. A tela recebe um `TicketView` já validado; os
  testes hostis usam `model_validate_json`, como no DL4-PR03.
- **Pydantic AI** (documentação oficial, lida em 26/11/2026): biblioteca de agentes,
  agnóstica de modelo, com saída estruturada validada por Pydantic. **Não se aplica a este
  PR**: não há chamada de modelo numa tela estática. Adotar exigiria dependência nova e
  provedor remoto, o que `CLAUDE.md` veda sem sprint e ADR. Fica registrada como candidata
  para quando houver agente em tempo de execução.
- **AGENTS.md** (formato aberto, hoje sob a Linux Foundation): Markdown livre, sem campos
  obrigatórios. Base do §0.6. As fontes consultadas são secundárias; o repositório já tem o
  arquivo.
- Fontes de mercado da proposta do revisor (tastytrade, OpLab): **não relidas pelo
  planejador**. Aqui só entra a convenção de mostrar meio, limite e natural.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (protótipo) |
|---|---|---|
| `backend/derivatives/ticket/screen.py` | tela v3 | 275 (263) |
| `backend/derivatives/ticket/screen_draw.py` | **novo**: régua e curva em SVG | 80 (72) |
| `backend/derivatives/ticket/view.py` | recusa por multiplicador | 295 (293) |
| `tests/unit/derivatives/ticket/test_screen.py` | S1, S2, S4, S7, S8 alterados; S12 a S17 novos | — |
| `tests/unit/derivatives/ticket/test_view.py` | W8 e W9 novos | — |
| `docs/specs/derivatives/fase4/DL4-PR03C.md` | cópia deste cartão | — |

Linhas com até 100 colunas. Patch de referência: `DL4-PR03C_PROTOTIPO.patch`, SHA-256
`b16936f8fcaf…`, aplica limpo sobre `2bd6613`.

**Testes existentes que mudam, e só estes:**

| Teste | Por quê |
|---|---|
| S1 | preço e strike da tabela saem sem «R$» (`150,00 a 4,20`) |
| S2 | conjunto de campos maior; cotação da tabela em número |
| S4 | cotação sem «R$»; meio, preço por unidade e curva indisponíveis ditos em palavras |
| S7 | a página passa a ter `svg` e `strong`; o texto hostil também é conferido no veredito |
| S8 | `screen.py` importa `screen_draw`; `screen_draw` só importa a biblioteca padrão |

S3, S5, S6, S9 a S11 e todo o resto de `test_view.py` passam sem edição.

## 3. Regra

A tela **só formata**. Não compara, não soma, não classifica. A única aritmética é a
posição dos desenhos.

### 3.1 Blocos, de cima para baixo

1. **Aviso** (`aviso`), como hoje.
2. **Topo**: título; linha com boleta, estado (e «· pausada»), versão, resumo (12
   caracteres), conta, prazo de envio, validade. À direita, o cartão **Destino**
   (`ambiente`): «Simulador local» e, abaixo, «D0 · nenhuma ordem sai desta máquina».
3. **Veredito**: «Pode confirmar agora?»; `avanco` com os três textos de hoje; `mercado`;
   e `veredito.pernas`, uma linha com **todas** as pernas, na ordem:
   «Compra BOVAA1550: Cautela: spread aberto, pouca profundidade; Venda BOVAA1600:
   Bloqueado: leilão».
4. **Painel**, dois quadros: preço por unidade (3.3) e curva (3.4).
5. **Tabela**, com legenda: «Cotações da foto `foto_cotacao`, vistas em `instante`. Limite
   de idade da guarda: `limite_idade_s`.» A foto, o instante e o limite ficam **na
   legenda**, logo acima das idades.
6. **Custo** e **Risco**, como hoje, mais «Ponto de equilíbrio (preço do ativo)».

### 3.2 Tabela

Colunas, nesta ordem: Lado · Qtd · Ticker · Tipo · Mod · Strike · Venc. · Limite ·
**Bid × qtd · Ask × qtd** · Meio · Data · Hora · Idade · Fase · Guarda da perna.

- **Lado**: etiqueta verde «Compra» ou vermelha «Venda». É o único vermelho que não é
  número negativo.
- **Mod**: 🇺🇸 com `title` e `aria-label` «Americana»; 🇪🇺 com «Europeia»; sem modalidade,
  «—» com «não informada».
- **Preços da tabela** (strike, limite, bid, ask, meio): número pt-BR **sem «R$»**, exato,
  com ao menos duas casas: `2,15`, `1,975`, `1.234,50`. Fora da escala, o texto do motor.
- **Data** e **Hora** são as da cotação (`cotacao.instante`), em UTC.
- **Idade**: só ganha marca quando «cotação vencida» está nos motivos da guarda **daquela
  perna**, e a marca é a do nível da guarda (marca-texto se bloqueada; laranja se cautela).
  A tela não compara idade com limite.
- Sem cotação: uma célula «sem cotação», em marca-texto, ocupando as sete colunas.
- Valores em reais (custo, risco, rótulos da curva) continuam com «R$».

### 3.3 Preço da estrutura, por unidade

Com `preco_unidade`:

- régua com três marcas, Meio, Limite e Natural, da menor para a maior; marcas de mesmo
  valor viram uma só, com os nomes unidos por « = » («Limite = Natural»);
- os três números por extenso (`preco_unidade.meio`, `.limite`, `.natural`);
- `preco_unidade.acima_do_meio`: «R$ 40,00 pior que o meio» se positivo; «R$ 0,15 melhor
  que o meio» se negativo; «no meio» se zero. Rótulo: «Limite nas N unidades».
- nota fixa: «Positivo é débito por unidade; negativo é crédito. Natural: compra no ask e
  venda no bid. À direita é pior para você.»

Sem `preco_unidade`: «indisponível: » mais o motivo, em laranja.

**Posição na régua:** x = 60 + (valor − menor) ÷ (maior − menor) × 480, com uma casa. Com
os três iguais, x = 300,0.

### 3.4 Curva do resultado no vencimento

Só com `risco.vencimento`. Sem ele: «indisponível: » mais o motivo, em laranja.

- **Janela:** margem = último strike − primeiro strike (1,00 se houver um só). De
  (primeiro − margem, nunca abaixo de zero) até (último + margem).
- **Linha:** ponta esquerda, cada ponto da `curva` depois do preço zero, ponta direita. A
  ponta esquerda fica na reta entre o preço zero e o primeiro strike. A ponta direita vale
  último resultado + `inclinacao_final` × margem.
- **Eixo vertical:** do menor ao maior resultado da linha, **sempre incluindo o zero**. O
  maior fica em y = 24 e o menor em y = 104.
- Em cada strike: o preço embaixo e o resultado em reais junto do vértice (vermelho se
  negativo).
- **Equilíbrio:** linha tracejada e o número, só se cair dentro da janela (bordas
  incluídas). Fora dela, o número continua no bloco de Risco.

### 3.5 Preço por unidade e multiplicador (S-2)

Em `view.py`, `preco_unidade` fica indisponível com o motivo «multiplicador diferente de 1»
quando alguma série da boleta tem multiplicador diferente de 1. A ordem das recusas passa a
ser: quantidades diferentes → multiplicador → cotação incompleta.

O formato da visão não muda: nenhum campo entra ou sai, e o esquema fica igual.

## 4. Cenários

Fotos: `bova_calmo` (1 passo, seq 2, 14:00:02Z), `bova_vencida` (1, 3, 14:00:10Z),
`bova_adverso` (1, 2, 14:00:02Z).

**S12 — destino, veredito, legenda.** Nas três: «Simulador local» e a frase do D0;
`limite_idade_s` «5,0 s»; os três campos dentro de `<caption>`, antes da primeira idade.
`veredito.pernas`:

| Foto | Texto |
|---|---|
| calmo | Compra BOVAA1500: Sem aviso; Venda BOVAA1550: Sem aviso |
| vencida | Compra BOVAM1450: Bloqueado: cotação vencida; Venda BOVAM1500: Sem aviso |
| adverso | Compra BOVAA1550: Cautela: spread aberto, pouca profundidade; Venda BOVAA1600: Bloqueado: leilão |

Ordem das células da perna e dos 16 cabeçalhos, como no §3.2.

**S13 — idade.** vencida: perna 0 com marca-texto, perna 1 sem. adverso: nenhuma das duas
(há bloqueio e cautela, mas não «cotação vencida»). A mesma visão da vencida com a guarda
da perna 0 em `CAUTION`: laranja. Com a guarda `OK` sem motivos e `limite_idade_s` 0,5: sem
marca, embora a idade (10,0 s) passe do limite; a legenda mostra «0,5 s».

**S14 — etiqueta, bandeira, número.** Classes `lado compra` e `lado venda`. Bandeiras com
`title` e `aria-label`. Meios do adverso `1,975` e `0,975`. Sessão oficial: «—».
`num`: `0`→`0,00`; `1.975`→`1,975`; `2.1`→`2,10`; `-0.515`→`-0,515`; `1234.5`→`1.234,50`;
`1E+2`→`100,00`; `15E-1`→`1,50`; `-0.00`→`0,00`; `0.025`→`0,025`;
`1234567.125`→`1.234.567,125`; `1E+16`→`1E+16`; `-1E+16`→`-1E+16`;
`1E+15`→`1.000.000.000.000.000,00`. Igual sob `prec=3`, armadilha ligada e desligada.

**S15 — preço por unidade e régua.**

| Foto | Meio, limite, natural | Distância | Marcas (x) | Rótulos |
|---|---|---|---|---|
| calmo | `2,05`, `2,10`, `2,10` | R$ 5,00 pior que o meio | 60,0 e 540,0 | Meio; Limite = Natural |
| vencida | `-2,05`, `-2,00`, `-2,00` | R$ 10,00 pior que o meio | 60,0 e 540,0 | idem |
| adverso | `1,00`, `1,20`, `1,20` | R$ 40,00 pior que o meio | 60,0 e 540,0 | idem |

Oficial `calmo` (meio −0,515, limite −0,50, natural −0,43): marcas em 60,0, **144,7** e
540,0. Conta: 60 + 0,015 ÷ 0,085 × 480. `rapido` 2 passos: «R$ 0,15 melhor que o meio».
Visão do calmo com limite e natural iguais ao meio e distância zero: «no meio» e uma marca
só, em 300,0. Compra 3 e vende 1: «indisponível: quantidades diferentes por perna».

**S16 — curva.** Linha, zero e equilíbrio:

| Foto | Linha | y do zero | x do equilíbrio |
|---|---|---|---|
| calmo | 60,0;104,0 → 220,0;104,0 → 380,0;24,0 → 540,0;24,0 | 70,4 | 287,2 |
| vencida | a mesma | 56,0 | 316,0 |
| adverso | a mesma | 84,8 | 258,4 |

Conta do adverso: janela de 150 a 165; pior −240 em y 104, melhor 760 em y 24; zero em
24 + 760 ÷ 1000 × 80 = 84,8; equilíbrio 156,20 em 60 + 6,2 ÷ 15 × 480 = 258,4.
Rótulos do adverso, na ordem: `155,00`, `-R$ 240,00`, `160,00`, `R$ 760,00`, `156,20`; um
rótulo vermelho.

Mais quatro:

| Caso | Linha | Zero | Equilíbrio |
|---|---|---|---|
| compra seca de 10 calls 10 a 1,00 | 60,0;104,0 → 300,0;104,0 → 540,0;24,0 | 24,0 | 540,0 (na borda) |
| compra 3 calls 10 a 1,00, vende 1 call 11 a 2,00 | … → 380,0;56,0 → 540,0;24,0 | 88,0 | 272,8; texto `10,33` |
| oficial `calmo` (resultados 5, 5, 15) | 60,0;77,3 → 220,0;77,3 → 380,0;24,0 → 540,0;24,0 | 104,0 | nenhum; «não há» |
| compra seca de 10 calls 10 a 5,00 | 60,0;104,0 → 300,0;104,0 → 540,0;88,0 | 24,0 | fora da janela: não desenha; texto `15,00` |

**S17 — contexto decimal.** As três telas com os mesmos bytes sob `prec=3`, armadilha
ligada e desligada.

**W8 — multiplicador.** Boleta CALM/CREDIT com multiplicador 100: `preco_unidade` nulo,
«multiplicador diferente de 1». Compra 3 e vende 1 com multiplicador 100: «quantidades
diferentes por perna» (a ordem das recusas). Multiplicador 1: preço presente.

**W9 — meio centavo (L-1).** Compra 2 calls 10, vende 1 call 12 a 0,01. Equilíbrio em
10 + p − 0,005:

| Compra a | Equilíbrio exato | Sai |
|---|---|---|
| 1,01 | 11,005 | `11.00` |
| 1,02 | 11,015 | `11.02` |

São precisos os dois: um só não distingue «para o par» de «para baixo» ou «para cima».

**SHA-256 das três telas do protótipo** (só valem se o patch for seguido byte a byte):
calmo `4b9982dadd44…`, vencida `5e2b45dbe8bc…`, adverso `f0de0febb5ce…`.

## 5. Evidência do planejador

`2bd6613`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Portão completo, sobre os bytes finais do patch:** **11.733 aprovados, 16 pulados, 261
  subtestes**, código 0. São os 11.724 da base mais 9 (S12 a S17, W8, W9 com dois casos).
- `mypy backend/ --strict`: limpo em 185 arquivos. `pyright backend/`: 0 erros.
  `tests/architecture`: 136 aprovados.
- **Seis sessões** pelo script de replay, base × protótipo: os 13 arquivos idênticos.
- **Vermelho, medido contra a produção da base:** `test_screen.py` não é coletado (falta
  `num`); em `test_view.py`, W8 falha. **O W9 nasce verde**: ele fixa um comportamento que
  já existe. A prova dele são os mutantes 38 e 39.
- **Mutantes:** 40 plantados, 40 derrubados. Na primeira rodada sobreviveram quatro (6, 25,
  31, 33); os testes foram reforçados e os quatro caíram.
- **Olhei a tela**: as três fotos renderizadas no Chrome. Imagem da `bova_adverso` anexa.
- **Defeitos do próprio protótipo, pegos antes do cartão:**
  1. o rótulo do strike era formatado por divisão decimal no contexto de quem chama; passou
     a vir pronto da tela;
  2. a tela usava `<b>`, que o S7 proíbe por ser o marcador do texto hostil; virou `<strong>`;
  3. o rótulo do resultado negativo caía em cima da linha do zero; foi para baixo do vértice.

**Não conferido pelo planejador:** Mac arm64; `tests/integration`; o contêiner; Windows
(bandeiras); as fontes de mercado da proposta. A estética fina (espaçamento dos rótulos da
curva) foi vista em uma largura só, 1.500 px.

## 6. Mutantes obrigatórios

Um por vez. Entre parênteses, quem derrubou no protótipo.

**Tela (`screen.py`)**

1. Destino fixo, sem ler `ambiente` (S12).
2. `veredito.pernas` omite pernas sem aviso (S12).
3. Idade marcada por comparação com o limite (S13).
4. Idade marcada sempre que a guarda não é OK (S13).
5. Idade marcada sempre como alerta (S13).
6. Ask antes de Bid nas células (S12).
7. Ask antes de Bid no cabeçalho (S12).
8. Lado trocado nas cotações (S2, S4).
9. Meio arredondado ao centavo (S2, S14).
10. `num` corta em duas casas (S2, S14, S15).
11. `num` no contexto de quem chama (S14).
12. Etiqueta de lado sempre «compra» (S14).
13. Bandeiras trocadas (S14).
14. Bandeira sem texto (S14).
15. «pior» e «melhor» invertidos (S15).
16. Distância ao meio com sinal (S15).
17. «no meio» nunca dito (S15).
18. Régua com o limite no lugar do natural (S15).
19. Preço indisponível sem motivo (S4, S15).
20. Equilíbrios omitidos (S2, S16).
21. Sem equilíbrio vira vazio (S16).
22. Curva indisponível sem motivo (S4).
23. Curva ignora `inclinacao_final` (S16).
24. Foto fora da legenda (S1, S2, S12).
25. Limite de idade constante na tela (S13).
40. Página com `<script>` (S7).

**Desenho (`screen_draw.py`)**

26. Marcas iguais não unidas (S15).
27. Régua com escala a partir de zero (S15).
28. Intervalo nulo posto no início (S15).
29. Janela sem margem à esquerda (S16).
30. Ponta direita plana (S16).
31. Eixo vertical sem incluir o zero (S16).
32. Eixo vertical invertido (S16).
33. Equilíbrio fora da janela desenhado (S16).
34. Equilíbrio na borda omitido (S16).
35. Rótulo negativo sem vermelho (S16).

**Visão (`view.py`)**

36. Multiplicador ignorado (W8).
37. Multiplicador antes das quantidades (W8).
38. Meio centavo para cima (W9).
39. Meio centavo para baixo (W9).

## 7. Critérios de parada

Pare e relate se:

- a `main` diferir de `2bd6613` fora de `docs/04_MEM/current_state.md`;
- algum esperado do §4 não reproduzir;
- qualquer dos 13 arquivos das seis sessões, ou das 7 âncoras, mudar;
- o esquema publicado da visão mudar (o hash segue `0655d7ef91ca…`);
- mudar algum teste fora dos listados no §2;
- for preciso tocar em `guards.py`, `engine.py`, `sequencing.py`, `models.py`, nos
  roteiros, nas fitas, no gabarito ou no script da tela;
- a página precisar de `<script>` ou de recurso externo;
- `tests/integration` der resultado diferente da linha de base (as mesmas 4 falhas, pelos
  IDs).

**Adendos:** vale a pré-autorização de Francisco de 25/11/2026 (restaurar regra que o
cartão já declara, ou fortalecer teste e mutante). Mudar cor, espaçamento ou tamanho de
letra **sem** mudar texto, ordem, classe ou coordenada conferida no §4 é livre e não pede
adendo. Fora disso, Francisco decide.

**Reversão:** reverter o commit verde devolve a tela do DL4-PR03 e o preço por unidade sem
a recusa do multiplicador.

## 8. Entrega

1. Commit vermelho com os testes; depois o verde com `screen.py`, `screen_draw.py` e
   `view.py`. O vermelho vai ao GitHub antes. Declare na descrição que o W9 nasce verde.
2. Portão no Mac arm64 em clone limpo e portão Linux no contêiner, imagem do lock da
   cabeça. Esperado: **11.733 aprovados, 16 pulados**; `mypy backend/ --strict` e
   `pyright backend/` limpos.
3. Integração só no contêiner: as mesmas 4 falhas conhecidas, pelos IDs.
4. Os 13 arquivos das seis sessões, base × candidato, com SHA-256. O hash do esquema.
5. As três telas geradas pelo script (`--passos`, `--avanca-ate` e `--instante` do
   gabarito), com SHA-256, e a imagem de cada uma.
6. Na descrição do PR: cabeça, arquitetura, imagem, versões, comandos, logs, contagens,
   linhas dos três arquivos, os 40 mutantes, desvios.
7. Copie este cartão para o caminho do §2. Não edite `current_state.md`.
8. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada; relatórios fora do
   Git, SHA-256 na descrição.

**Revisor:** desta vez **roda** a suíte, a tipagem e os 40 mutantes num ambiente próprio,
como na revisão pós-merge do PR #196, e refaz à mão a régua da sessão oficial `calmo`
(144,7) e o zero da curva do adverso (84,8). Abre as três telas e olha.

**Prova de uso (Francisco), depois do GO e antes do DL4-PR03D:** as 6 perguntas nas três
telas novas. Critério binário: 18 de 18 **na primeira tentativa**.

## 9. Decisões

### 9.1 Do planejador, que Francisco pode vetar

| # | Decisão | Por quê |
|---|---|---|
| D1 | **Sem simulador de quantidade** nesta tela | precisa de script; o portão não testa JavaScript; seria o único número fora do motor. Mudar quantidade de verdade é versão nova da boleta, assunto do M2 |
| D2 | A idade só é marcada pela guarda, nunca por comparação na tela | a tela não decide; e a marca muda sozinha de marca-texto para laranja quando o DL4-PR03D entrar |
| D3 | Preços da tabela sem «R$»; reais só em custo, risco e rótulos da curva | separa preço por unidade de valor total, que foi a confusão do protótipo v2 |
| D4 | «Tipo» continua «Call BOVA11» | o protótipo v3 tirou o ativo; a resposta 1 do gabarito precisa dele |
| D5 | Curva sem zonas pintadas | linha, zero e equilíbrio bastam; menos desenho, menos teste |
| D6 | Equilíbrio fora da janela não é desenhado | o número segue no bloco de Risco; alargar a janela achataria a parte que importa |
| D7 | S-2 resolvido por **recusa**, não por multiplicar | o motor ignora o multiplicador em todo valor em reais; multiplicar só aqui criaria um número que não bate com o custo |
| D8 | S-1 (comentário restringindo o contexto exato) fica fora | sugestão sem efeito hoje; entra no próximo PR que mexer na aritmética da visão |

### 9.2 De Francisco, já tomadas

- Bid antes de Ask; coluna Meio (25/11/2026).
- Vermelho só em número negativo e na etiqueta «Venda».
- As duas decisões assinadas de 25/11/2026 (cotação antiga como aviso; venda sem cobertura
  rastreada como aviso) **não entram aqui**: DL4-PR03D e DL4-PR03E.

## 10. Depois deste cartão

Fila até o M2: **DL4-PR03C** → prova de uso → DL4-PR03D (cotação antiga como aviso) →
Adendo 2 à ADR-0024 e DL4-PR03E → DL4-PR04.

Pendências sem cartão:

- as 4 falhas de `tests/integration`;
- a docstring de `series_code`;
- a fonte do spread do DL4-PR07 (candidato: `natural` do preço por unidade);
- S-1 do revisor (D8);
- **o motor ignora o multiplicador do contrato em todo valor em reais.** Hoje é inofensivo:
  as fixtures usam 1. Precisa de decisão antes de qualquer dado real (M4).

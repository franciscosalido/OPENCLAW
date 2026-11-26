# DL4-PR03B — Supercartão: visão formato 2 (os dados da tela v3)

**Data:** 25/11/2026 · **Autor:** Claude (planejador) · **Implementa:** Codex
**Base:** `main` = `de2d871` (DL4-PR03 integrado, PR #193), ou a `main` seguinte se a
diferença for só `docs/04_MEM/current_state.md`.
**PR novo**, em rascunho. Entra antes do DL4-PR04 (M2).

**Substitui** o cartão de mesmo nome escrito pelo revisor em 25/11/2026. Aquele cartão
juntava dado, tela, script de página e fixtures num PR só, sem protótipo de código. Este
fica com **os dados**; a tela v3 é o cartão seguinte (DL4-PR03C).

**Origem:**

- Prova de uso do M1 (25/11/2026) e decisões R1 a R9 de Francisco sobre a tela.
- Protótipo v2 aprovado por Francisco com cinco ressalvas (25/11/2026).
- `PROPOSTA_TELA_V3_PARA_PLANNER_2026-11-25.md`, do revisor, com o protótipo v3.

## 0. Escopo

### 0.1 Resultado da prova de uso do M1 (registro)

Francisco respondeu as 6 perguntas do gabarito nas três telas do DL4-PR03, olhando só para
elas: `bova_calmo` 6 de 6, `bova_vencida` 6 de 6, `bova_adverso` 6 de 6 **na segunda
tentativa**. **18 de 18 de conteúdo.** Todo valor estava na tela; o que falhou foi a tela
obrigar o humano a caçar a resposta (idade na tabela e foto no cabeçalho, para uma
pergunta que pede as duas). Ele julgou o layout ruim. Daí a tela v3.

### 0.2 Como a proposta do revisor foi fatiada

A proposta tem 12 itens. **Não cabem num PR**, e três deles nem são desta fase.

| Fatia | Conteúdo | Cartão |
|---|---|---|
| Dados | o que a tela v3 precisa e a visão ainda não tem | **este** |
| Tela | destino, veredito, régua, mini-curva, tabela nova, simulador de quantidade | DL4-PR03C |
| Guarda | cotação antiga passa de bloqueio a aviso | DL4-PR03D, **autorizado por Francisco em 25/11/2026** (§9.2) |
| Cobertura | venda sem cobertura rastreada passa de recusa a aviso de verificação | DL4-PR03E, **autorizado por Francisco em 25/11/2026**; exige o Adendo 2 à ADR-0024 (§9.2) |
| Cadeia espelhada | precisa de uma fonte de cadeia que não existe | fora da fila; depois do M2 |
| Ciclo de atualização de 15 s | só existe com fonte ao vivo | M4 |
| PoP, P50, extrínseco, faixa de VI | modelos do Laboratório | junto do DL4-PR09 |

### 0.3 O que acontece hoje (conferido em `de2d871`)

- A visão é `formato` 1 e não tem: modalidade de exercício, meio da cotação, preço da
  estrutura por unidade, ponto de equilíbrio, curva do resultado, ambiente de destino nem o
  limite de idade que a guarda usa.
- `Holding` não tem modalidade. `expiry_profile` já calcula os equilíbrios, mas a visão os
  descarta. `expiry_result` já dá o resultado em qualquer preço do ativo.
- `Literal[1]` do `formato` aceita `true` e `1.0` na leitura (nota N-1 do DL4-PR01).

### 0.4 O que este cartão entrega

1. `Holding.style` opcional, e a modalidade nas três sessões BOVA.
2. Visão `formato` 2, com sete acréscimos (§3.2).
3. O esquema publicado regerado.

### 0.5 O que este cartão não faz

- **Não muda a tela.** `screen.py` e o script da tela ficam como estão; a tela atual
  continua funcionando, porque só lê campos que não mudam.
- **Não muda a guarda**, a configuração, `engine.confirm`, o recibo, a prévia nem o resumo.
  As 7 âncoras e os 13 arquivos de saída das seis sessões ficam idênticos.
- Não classifica a estrutura («trava de alta», «débito»): dar nome a estratégia é lógica
  nova e fica fora.
- Não cria avisos novos, nem o da vendida americana com proteção europeia.
- Não toca `bova.gabarito.json` nem as fitas.

Nenhuma dependência nova. Nenhum arquivo protegido.

## 1. Referência externa

- **Pydantic 2.14, documentação oficial** («Literals», «Strict Mode»): valores `Literal` são
  validados em modo estrito. **Observado por execução**, não basta: `Literal[2]` aceita
  `2.0` porque compara por igualdade. Por isso o `formato` leva um validador que exige
  `type(v) is int` (§3.2).
- **Python 3.12, `decimal`:** `+`, `-`, `*`, `/` e `quantize` sem contexto explícito
  arredondam pelo contexto de quem chama. **É a terceira vez que um protótipo desta fase
  cai nisso** (§5). Toda conta nova usa os métodos de um contexto exato.
- **Preço médio e preço natural** de estrutura (compra no ask, venda no bid) e a convenção
  de mostrar o meio como referência vêm da pesquisa do revisor sobre a tastytrade e o robô
  da OpLab (§2 da proposta). **O planejador não releu essas fontes.** Aqui o meio é só
  informação: nenhuma guarda, limite ou decisão do motor usa o meio.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (protótipo) |
|---|---|---|
| `backend/derivatives/ticket/sequencing.py` | `Holding.style` | +1 linha |
| `backend/derivatives/ticket/engine.py` | `Reading.quote_age_limit_s` | 580 (577) |
| `backend/derivatives/ticket/view.py` | formato 2 e os campos novos | 295 (285) |
| `docs/specs/derivatives/fase4/schemas/visao.schema.json` | regerado | — |
| `tests/fixtures/.../sessions/bova_{calmo,vencida,adverso}.roteiro.json` | só `style` em cada série | — |
| `tests/unit/derivatives/ticket/test_view.py` | W1 a W7; esperados de V7, V9, V10 e V15 | — |
| `tests/unit/derivatives/ticket/test_bova_sessions.py` | só os 3 SHA-256 dos roteiros | — |
| `docs/specs/derivatives/fase4/DL4-PR03B.md` | cópia deste cartão | — |

**Não muda:** `screen.py`, os dois scripts, `guards.py`, `models.py`, `receipt.py`,
`session.py`, `test_screen.py`, as fitas, o gabarito, as sessões oficiais,
`current_state.md`. Linhas novas com até 100 colunas.

**Testes existentes que mudam, e só estes:**

| Teste | Por quê |
|---|---|
| V7, V9, V10 (`test_view.py`) | comparam o bloco `vencimento` inteiro, que ganha três chaves |
| V15 | ordem das chaves, `formato` 2, hash do esquema; passa a recusar `formato` 1 e 3 |
| B2 (`test_bova_sessions.py`) | os três roteiros ganham `style`; os SHA-256 mudam |

Novos SHA-256 dos roteiros: calmo `6d956042f507…`, vencida `2e85fd042cdf…`, adverso
`bbf79b930c25…`. Do esquema: `0655d7ef91ca…`. Se você renomear campo ou classe, o hash do
esquema muda: gere o seu e declare. Renomear campo do §3.2 é desvio e pede adendo.

Patch de referência: `DL4-PR03B_PROTOTIPO.patch`, SHA-256 `238053af11cf…`, aplica limpo
sobre `de2d871`.

## 3. Regra

### 3.1 Modalidade na posição

`Holding.style: Literal["AMERICAN", "EUROPEAN"] | None = None`. São os nomes do campo
`maturity-type` da OpLab. Opcional, para as sessões oficiais não mudarem.

| Série | `style` |
|---|---|
| `BOVAA1500` | `AMERICAN` |
| `BOVAA1550` | `EUROPEAN` |
| `BOVAA1600` | `AMERICAN` |
| `BOVAM1450`, `BOVAM1500` | `EUROPEAN` |

É a tabela do protótipo que Francisco aprovou. A mesma série tem a mesma modalidade em
todas as sessões. Nos roteiros, `"style"` entra depois de `"balance"`, sem outra mudança.

### 3.2 Visão, formato 2

| Campo novo | Onde | Regra |
|---|---|---|
| `formato` | topo | só o inteiro 2 |
| `ambiente` | topo, depois de `aviso` | `preview.environment` (`SIMULATED`) |
| `limite_idade_s` | topo, depois de `validade_ordens` | `Reading.quote_age_limit_s`, que o motor lê de `max_quote_age_s` |
| `modalidade` | perna, depois de `tipo` | `Holding.style` |
| `meio` | cotação, depois de `venda_qtd` | (compra + venda) / 2; nulo se faltar um lado |
| `preco_unidade`, `preco_unidade_indisponivel` | topo, depois de `pernas` | ver 3.3 |
| `equilibrios`, `curva`, `inclinacao_final` | `risco.vencimento` | ver 3.4 |

**`formato`**: recusa `True`, `2.0`, `"2"`, `1`, `3`, `None` e `Decimal(2)` em Python; e
`true`, `2.0`, `2e0`, `"2"`, `1`, `3` e `null` em JSON.

**`limite_idade_s`** não pode ser constante na visão. Com a configuração em 15 s, a visão
mostra 15.0.

**Valores com meio centavo.** O meio pode ter três casas (`1.975`). Esses campos são
`Decimal`, não `Money`. Regra de apresentação do valor: duas casas quando ele cabe em
centavos (`1.00`, `40.00`); senão, o valor exato (`1.975`, `0.025`). Nunca arredondar.

### 3.3 Preço da estrutura por unidade

`preco_unidade`: `quantidade`, `limite`, `natural`, `meio`, `acima_do_meio`.

- Em cada um dos três preços, **compra soma e venda subtrai**. Positivo é débito por
  unidade; negativo é crédito.
- `limite`: os preços-limite das pernas.
- `natural`: cruzando o livro agora. Compra no preço de venda da cotação; venda no preço de
  compra.
- `meio`: os meios das pernas.
- `acima_do_meio` = (`limite` − `meio`) × `quantidade`, em reais. **Positivo é pior que o
  meio para o humano**: paga mais, ou recebe menos.

Indisponível (`preco_unidade` nulo, com o motivo), nesta ordem:

1. quantidades diferentes entre as pernas → «quantidades diferentes por perna»;
2. alguma perna sem cotação ou sem um dos lados → «cotação incompleta».

Leilão, cotação vencida e os demais avisos **não** tiram o preço por unidade: quem fala de
mercado é a guarda. Boleta de uma perna só tem preço por unidade.

### 3.4 Equilíbrio e curva

Só existem com o perfil disponível (as condições do DL4-PR01 não mudam).

- `equilibrios`: os de `expiry_profile`, na ordem dele, **arredondados ao centavo, meio
  para o par, por aritmética de frações** (`round(fração × 100)`). Não use divisão decimal
  no contexto exato: um terço não termina. Sem equilíbrio, lista vazia.
- `curva`: pontos (`preco`, `resultado`) no preço 0 e em cada strike distinto, em ordem
  crescente. O resultado vem de `expiry_result`, aos preços-limite. Entre dois pontos o
  resultado é reta.
- `inclinacao_final`: resultado(último strike + 1,00) − resultado(último strike). É quanto
  o resultado muda por real de alta do ativo depois do último strike. Zero nas travas.

## 4. Cenários

Fotos BOVA: `bova_calmo` (1 passo, seq 2, 14:00:02Z), `bova_vencida` (1, 3, 14:00:10Z),
`bova_adverso` (1, 2, 14:00:02Z).

**W1 — `formato`.** As recusas do §3.2, em Python e em JSON. O JSON começa por
`{"formato":2,`.

**W2 — ambiente e limite.** `bova_calmo`: `SIMULATED` e `5.0`. `bova_vencida` aberta numa
sessão com `max_quote_age_s` 15,0, às 14:00:10Z depois do evento 3: `limite_idade_s` 15.0 e
avanço `PODE_CONFIRMAR` (prova de que o limite vem da mesma configuração que a guarda).

**W3 — modalidade.** calmo `AMERICAN`, `EUROPEAN`; vencida `EUROPEAN`, `EUROPEAN`; adverso
`EUROPEAN`, `AMERICAN`. Sessão oficial `calmo`: nulo nas duas. `style` com `BERMUDAN`,
`american` ou vazio é recusado na posição.

**W4 — meio e preço por unidade, à mão.**

| Foto | Meios | `limite` | `natural` | `meio` | `acima_do_meio` |
|---|---|---|---|---|---|
| `bova_calmo` | `4.175`, `2.125` | `2.10` | `2.10` | `2.05` | `5.00` |
| `bova_vencida` | `1.875`, `3.925` | `-2.00` | `-2.00` | `-2.05` | `10.00` |
| `bova_adverso` | `1.975`, `0.975` | `1.20` | `1.20` | `1.00` | `40.00` |
| oficial `calmo` 1, 14:00:02 | `0.985`, `1.50` | `-0.50` | `-0.43` | `-0.515` | `0.15` |

Conta do adverso: limite 2,15 − 0,95 = 1,20; natural 2,15 (venda da comprada) − 0,95
(compra da vendida) = 1,20; meio 1,975 − 0,975 = 1,00; (1,20 − 1,00) × 200 = 40,00.
Conta da vencida: 1,90 − 3,90 = −2,00; meio 1,875 − 3,925 = −2,05; (−2,00 + 2,05) × 200 =
10,00, ou seja, recebe R$ 10,00 a menos que no meio.

Mais: `rapido` 2 passos, T1: `acima_do_meio` `-0.15` (limite melhor que o meio). Compra
seca de 1 unidade a 1,00 com livro 0,95 × 1,00: `meio` `0.975`, `acima_do_meio` `0.025`.
`leilao` 1, 14:00:02: avanço `BLOQUEADA` **e** preço por unidade presente.

**W5 — indisponível.** Compra 3 e vende 1: «quantidades diferentes por perna». Perna
comprada sem oferta de venda: «cotação incompleta», meio dessa perna nulo. Série sem
cotação: «cotação incompleta», cotação nula.

**W6 — equilíbrio e curva.**

| Foto | `equilibrios` | `curva` | `inclinacao_final` |
|---|---|---|---|
| `bova_calmo` | `152.10` | (0, −210), (150, −210), (155, 290) | `0.00` |
| `bova_vencida` | `148.00` | (0, −600), (145, −600), (150, 400) | `0.00` |
| `bova_adverso` | `156.20` | (0, −240), (155, −240), (160, 760) | `0.00` |

Compra 3 calls 10 a 1,00 e vende 1 call 11 a 2,00: equilíbrio em 10 + 1/3, que sai
`10.33`; `inclinacao_final` `2.00`; ganho ilimitado; curva (0, −1), (10, −1), (11, 2).
Sessão oficial `calmo` (V7): `equilibrios` vazio. Compra seca de 10 (V9): `11.00`,
`inclinacao_final` `10.00`, curva (0, −10), (10, −10).

**W7 — contexto decimal de quem chama.** As três fotos BOVA saem com o mesmo JSON sob
`Context(prec=3)`, armadilha ligada e desligada. Trava sintética com preços de seis
dígitos (strikes 1234,56 e 2345,67; compra a 1234,57, vende a 0,01; livros 1234,55 ×
1234,57 e 0,01 × 0,03; 10 unidades): mesmo JSON sob `prec=3`; preço por unidade `1234.56`,
`1234.56`, `1234.54`, `0.20`; sem equilíbrio; último ponto da curva (2345,67; −1234,50).
A compra seca dessa série, sob `prec=3`: `inclinacao_final` `10.00`.

**Sem mudança:** V1 a V6, V8, V11 a V14, V16, B1, B3 a B8 e todo o `test_screen.py` passam
como estão.

## 5. Evidência do planejador

`de2d871`, Linux x86_64, Python 3.12.3, pydantic 2.14.4.

- **Portão completo no protótipo:** **11.724 aprovados, 16 pulados, 261 subtestes**, código
  0. São os 11.717 da base mais 7 novos (W1 a W7).
- `mypy backend/ --strict`: limpo em 184 arquivos. `pyright backend/`: 0 erros.
  `tests/architecture`: passa.
- **As seis sessões** pelo script de replay, base × protótipo: os 13 arquivos idênticos
  byte a byte. `Holding.style` não entra em recibo, prévia nem resumo: **medido**, não só
  lido.
- **Mutantes:** 23 plantados, 23 detectados (§6).
- **Três defeitos do próprio protótipo, pegos antes do cartão:**
  1. o sinal das pernas era aplicado com `sinal * preço`, no contexto de quem chama; sob
     `prec=3` o meio da `bova_calmo` saía `2.06` em vez de `2.05`. O W7 pegou;
  2. o ponto além do último strike era somado no contexto de quem chama; o mutante
     sobreviveu até entrar a compra seca de seis dígitos no W7;
  3. o planejador esperava equilíbrio em 2469,12 na trava de seis dígitos; o motor está
     certo, a trava nunca dá lucro. O esperado errado era do planejador.

**Não conferido pelo planejador:** Mac arm64; `tests/integration`; o contêiner; as fontes
de mercado citadas na proposta do revisor.

## 6. Mutantes obrigatórios

Um por vez. Entre parênteses, quem derrubou no protótipo.

1. `formato` sem o validador de inteiro (W1).
2. `limite_idade_s` constante (W2).
3. O motor entrega outro número da configuração (W2).
4. `modalidade` sempre nula (W3).
5. Meio com um lado só (W4, W5).
6. Meio sem dividir por dois (W4, W5, W7).
7. Natural pelo lado errado do livro (W4, W7).
8. Venda soma em vez de subtrair (W4, W7).
9. `acima_do_meio` sem multiplicar pela quantidade (W4, W7).
10. `acima_do_meio` medido do natural (W4).
11. Preço por unidade com quantidades diferentes (W5).
12. Lado ausente conta como zero (W5).
13. Equilíbrio com um centavo a mais (V7, V9, V10, W6).
14. Curva sem o ponto zero (V7, V9, V10, W6).
15. `inclinacao_final` fixa em zero (V9, W6).
16. Soma das pernas no contexto de quem chama (W7).
17. Ponto além do último strike no contexto de quem chama (W7).
18. Meio no contexto de quem chama (W7).
19. `style` aceita qualquer texto (W3).
20. `style` obrigatório (quase tudo).
21. Meio centavo arredondado (W4, W5).
22. `equilibrios` sempre vazio (V7, V9, V10, W6).
23. Curva com o mesmo resultado em todo ponto (V7, V10, W6, W7).

## 7. Critérios de parada

Pare e relate se:

- a `main` diferir de `de2d871` fora de `docs/04_MEM/current_state.md`;
- algum esperado do §4 não reproduzir;
- **qualquer** dos 13 arquivos de saída das seis sessões, ou das 7 âncoras, mudar;
- mudar algum teste fora dos listados no §2, ou algum de `test_screen.py`;
- for preciso tocar em `screen.py`, `guards.py`, `models.py`, `receipt.py`, `session.py`,
  nas fitas ou no gabarito;
- `tests/integration` der resultado diferente da linha de base (as mesmas 4 falhas, pelos
  IDs).

**Adendos:** vale a pré-autorização de Francisco de 25/11/2026, nos limites que o revisor
registrou (restaurar regra que o cartão já declara, ou fortalecer teste e mutante). Fora
disso, Francisco decide.

**Reversão:** reverter o commit verde devolve a base, inclusive os roteiros e o esquema.

## 8. Entrega

1. Commit vermelho com os testes novos e os esperados alterados; depois o verde com
   produção, esquema e os três roteiros. O vermelho vai ao GitHub antes.
2. Portão no Mac arm64 em clone limpo e portão Linux no contêiner, imagem do lock da
   cabeça. Esperado: **11.724 aprovados, 16 pulados**; `mypy backend/ --strict` e
   `pyright backend/` limpos.
3. Integração só no contêiner: as mesmas 4 falhas conhecidas, pelos IDs.
4. Os 13 arquivos das seis sessões, base × candidato, com SHA-256. O hash do esquema
   **gerado** na cabeça.
5. Para o revisor e na descrição do PR: cabeça, arquitetura, imagem, versões, comandos,
   logs, contagens, linhas de `view.py`, os 23 mutantes, desvios.
6. Copie este cartão para o caminho do §2. Não edite `current_state.md`.
7. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, no ambiente do
   lock; relatórios fora do Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda por conta
própria o W4, o W7 e os mutantes 7, 16 e 20, e refaz à mão a conta do preço por unidade da
`bova_vencida`.

## 9. Decisões

### 9.1 Do planejador, que Francisco pode vetar

| # | Decisão | Por quê |
|---|---|---|
| D1 | A tela v3 sai em dois PRs: dados (este) e tela (DL4-PR03C) | o cartão do revisor tocava motor, visão, tela, script de página e fixtures de uma vez, sem protótipo de código |
| D2 | `acima_do_meio` mede o **limite** contra o meio, não o natural | é o que você paga se a ordem executar no seu limite; o natural muda a cada cotação |
| D3 | Leilão e cotação vencida não escondem o preço por unidade | quem avisa é a guarda; esconder o número tiraria informação |
| D4 | Equilíbrio arredondado ao centavo | o passo de preço do ativo é R$ 0,01; mais casas não são informação |
| D5 | Nome de estratégia («trava de alta», «débito») fica fora | classificar estrutura é lógica nova; o lado e a natureza do líquido já dizem o essencial |
| D6 | Modalidades das séries BOVA como no protótipo v2 | é o que você aprovou; a vendida americana do `bova_adverso` fica registrada, sem aviso |

### 9.2 De Francisco, assinadas em 25/11/2026

Texto dele, no chat de planejamento:

> 1. Ao aprovar o protótipo v2, você disse que cotação antiga «nunca bloqueia, só avisa».
> Isso reverte a sua decisão L3 de 24/11, e o revisor pediu confirmação escrita.
> AUTORIZADO PELO HUMANO E ASSINADO FAS.
>
> 2. nunca vendido a descoberto. Sim podemos vender uma Call ou uma Put “descoberta” ou
> coberta por ativo que vc não tem rastreamento na carteira (por exemplo ação ou dinheiro).
> Deve haver um aviso de verificação. Proibir ou travar não deve estar na nossa Versão 4.
> APROVADA E ASSINADA - FAS.

**Nenhuma das duas muda este cartão.** Aqui a guarda, a cobertura e o plano de pernas ficam
intocados; a visão continua repetindo o que o motor disser. Cada decisão tem cartão próprio.

**Decisão 1 — cotação antiga é aviso (DL4-PR03D).** Reverte a L3 de 24/11 só nesse ponto.
«cotação vencida» passa de bloqueio a cautela, com limite configurável de 15 s. Perda de
sequência, leilão, suspensão, livro inválido e livro incompleto continuam bloqueando. A
sessão `bova_vencida`, o recibo dela, a âncora e as respostas 5 e 6 do gabarito são
refeitos **antes do código**.

**Decisão 2 — venda sem cobertura rastreada é aviso, não recusa (DL4-PR03E).** Reverte a
regra de 21/11 («a venda só é liberada depois da compra de proteção executada e na
quantidade coberta») e o que a ADR-0024 fixa sobre cobertura. Consequências que o cartão
dela tem de tratar, e que o planejador registra desde já:

- **Precisa do Adendo 2 à ADR-0024**, datado e com commit de autoria de Francisco, como o
  Adendo 1. A assinatura no chat autoriza; o adendo é o registro que os outros agentes leem.
- É a maior mudança de motor da fase: hoje `plan_legs` recusa venda sem par
  («pareamento ausente ou ambíguo»), a exposição da montagem exige compra protetora e o
  livro de reservas só libera venda coberta.
- A venda de call sem cobertura tem **perda ilimitada**. A visão já tem `perda_ilimitada`;
  a tela terá de dizer isso por extenso, junto do aviso de verificação.
- O aviso tem de dizer o que o QUIMERA **não sabe**: ele não rastreia ação nem dinheiro na
  carteira, então não confirma a cobertura; quem verifica é o humano.
- Garantia: o Adendo 1 diz que margem ausente bloqueia novos envios na modalidade nova. O
  Adendo 2 precisa dizer como isso convive com a venda descoberta.
- **Efeito sobre a decisão 1:** o argumento «o pior caso da cotação antiga é ficar comprado,
  nunca vendido a descoberto» deixa de valer para boletas com venda descoberta. O
  preço-limite continua protegendo o preço, e só ele.
- Continua tudo em simulador D0. `CLAUDE.md` e a ADR-007 não mudam: nenhuma ordem real.

## 10. Depois deste cartão

Fila até o M2: DL4-PR03C (tela v3) → DL4-PR03D (cotação antiga como aviso) → Adendo 2 à
ADR-0024 e DL4-PR03E (venda sem cobertura rastreada como aviso) → DL4-PR04.

DL4-PR03C, a tela v3 em replay, lendo só a visão formato 2: cartão «Destino», faixa de
veredito, régua de preço, mini-curva, tabela nova (Lado, Qtd, Ticker, Tipo, Mod, Strike,
Venc., Limite, Bid × qtd, Ask × qtd, Meio, Data, Hora, Idade, Fase, Guarda) e simulador de
quantidade com script de página sob CSP de hash. Duas escolhas suas entram naquele cartão:
**Bid antes de Ask** (o revisor inverteu a ordem que você pediu) e a **coluna Meio**.

Pendências sem cartão: as 4 falhas de `tests/integration`; a docstring de `series_code`;
a fonte do spread do DL4-PR07, que agora tem um candidato natural no `natural` do §3.3.

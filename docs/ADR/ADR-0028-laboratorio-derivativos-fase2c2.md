# ADR-0028 — Laboratório de Derivativos, Fase 2C2: QuantLib como oráculo de teste, fora do repositório

- **Status:** Accepted. Francisco aprovou E1 a E5 em 2026-11-20, com as ressalvas da seção
  "Ressalvas de Francisco", que valem sobre o resto do texto onde houver conflito.
- **Data:** 2026-11-21 (UTC). **Autor:** Claude. **Dono das decisões:** Francisco.
- **Depende de:** ADR-0025, ADR-0026 (Revisão 1), ADR-0027 e o Adendo 1 do cartão DL2C1.
- **Nome da fase:** 2C2, na contagem de Francisco. É a fase que o roteiro chamava de 2C.
- **Destino no repositório:** `docs/ADR/ADR-0028-laboratorio-derivativos-fase2c2.md`.

## Contexto

O laboratório tem dois motores americanos próprios: a árvore CRR, dona do número da linha, e
as diferenças finitas, só diagnóstico. Quando os dois divergem, nada no projeto diz quem
errou. A Fase 2C2 traz um árbitro de fora: preços americanos calculados pelo QuantLib,
gravados uma vez num arquivo versionado e usados só por testes.

O autor deste ADR rodou o QuantLib 1.44 num ambiente descartável, fora do repositório, antes
de escrever. Quatro fatos medidos mudam o desenho:

1. **A árvore "CRR" do QuantLib não é a nossa árvore.** Com os mesmos insumos e 200 passos,
   o `BinomialCRRVanillaEngine` e a árvore do projeto diferem em 7,7e-4. São discretizações
   diferentes do mesmo modelo. Comparar árvore com árvore mediria a diferença entre
   discretizações, não erro. O oráculo tem de ser um método que aproxime o limite contínuo.
2. **A volatilidade implícita embutida do QuantLib não serve de referência.** Para opção
   americana, `impliedVolatility` devolveu 0,24974 onde a volatilidade verdadeira era 0,25:
   erro de 2,6e-4, do tamanho do erro que queremos medir. A referência de volatilidade tem
   de sair da inversão explícita do motor escolhido, ou, mais simples, do desenho "preço a
   partir de volatilidade conhecida": o oráculo dá o preço, nossos motores invertem, e o
   resultado é comparado com a volatilidade que gerou o preço.
3. **O melhor motor do QuantLib também tem erro, e ele é mensurável.** O
   `QdFpAmericanEngine` implementa a colocação espectral de Andersen, Lake e Offengenden. Na
   put de dois anos com juros de 14,9% e sem rendimento, os esquemas prontos do motor
   divergem entre si em até 3e-4, e o esquema `highPrecisionScheme` fica a 2,6e-5 de um
   esquema mais fino. Nos outros 68 casos a dispersão mediana é 5e-8. A referência usa o
   esquema mais fino e publica, por caso, a incerteza observada.
4. **As diferenças finitas do QuantLib convergem devagar para americana.** Em malha de 2000
   por 2000 ficam a até 2,4e-3 da referência. Servem de conferência grosseira, não de árbitro.

Resultado preliminar do protótipo, 69 casos, contra a referência (não é o resultado da fase;
a fase repete isso com o código de produção):

| Grupo | Casos | Erro de VI da árvore, 200 passos | Erro de VI das diferenças finitas, 400 x 200 | Maior diferença entre os dois |
|---|---:|---:|---:|---:|
| A: call sem rendimento | 18 | 3,2e-4 | 3,4e-5 | 3,6e-4 |
| B: call com rendimento | 27 | 2,5e-4 | 6,1e-5 | 2,5e-4 |
| C: put americana | 18 | 2,6e-4 | 3,2e-5 | 2,3e-4 |
| D: regimes de borda | 6 | 3,7e-4 | 2,3e-4 | 4,9e-4 |

Leitura: os dois motores convergem para a referência nas ordens esperadas (erro da árvore cai
para 9% ao multiplicar os passos por dez; o das diferenças finitas, para 24% ao dobrar a
malha). O BSM europeu do projeto coincide com o analítico do QuantLib em 3e-14. E o limiar
de alerta de 0,0005 fica a um fio do ruído numérico: a diferença entre os motores chega a
4,9e-4 sem que nenhum dos dois esteja errado.

## Decisão

### R1 — O oráculo é um arquivo, não uma dependência

O QuantLib não entra em `pyproject.toml` nem em `uv.lock`, não é importado por nenhum módulo
de `backend/`, `config/`, `scripts/` ou `tests/`, e não roda em tempo de teste. A referência
é um JSON versionado, gerado uma vez num contêiner descartável com o QuantLib fixado por
versão e por hash do pacote. Os testes leem o JSON.

### R2 — Qual motor do QuantLib, e com que incerteza

- Preço americano de referência: `QdFpAmericanEngine` com
  `QdFpLegendreTanhSinhScheme(40, 100, 40, 1e-12)`, equação de ponto fixo automática.
- Incerteza por caso: a maior diferença entre esse valor e duas conferências do mesmo motor
  (equação `FP_A` no mesmo esquema; `highPrecisionScheme`). Todo teste soma essa incerteza à
  tolerância.
- Conferência grosseira: `FdBlackScholesVanillaEngine` 2000 por 2000, Crank-Nicolson.
- Europeia: `AnalyticEuropeanEngine`.
- Fora: a árvore do QuantLib, as aproximações de Barone-Adesi-Whaley e Bjerksund-Stensland e
  a `impliedVolatility` embutida.

### R3 — Mesmos insumos por construção

O prazo de cada caso é um número inteiro de dias corridos, e o QuantLib usa
`Actual/365 (Fixed)`. O gerador confere, caso a caso, que o prazo do QuantLib é exatamente
`dias / 365` em ponto flutuante, e os testes passam esse mesmo número aos motores do projeto.
Taxa e rendimento são contínuos e constantes dos dois lados.

Isso valida os motores **dado o prazo**. Não valida a contagem de dias úteis do projeto
(`(D0,Dv]`, ainda marcada como hipótese em `config/derivatives.yaml`) contra o
`Business/252` do QuantLib, que conta `[D0,Dv)`. Essa conferência é outra pergunta e fica
fora desta fase.

### R4 — Quem gera

A referência é de quem não escreveu o código que ela confere. O gerador é do Claude; o Codex
o copia sem editar, roda no contêiner e grava o resultado. O Claude roda o mesmo gerador em
outra arquitetura (x86-64) e as duas saídas têm de coincidir em 1e-9 relativo. O SHA-256 do
gerador e o do JSON ficam presos por teste.

Limite declarado: o Claude também escreveu a especificação das diferenças finitas. A
independência aqui vem do QuantLib, não de quem aperta o botão.

### R5 — O que o oráculo decide e o que não decide

Decide, por teste: se cada motor do projeto está dentro do erro esperado da sua discretização.
Não decide em tempo de execução: nenhuma linha consulta o oráculo, e ele não vira motor,
alternativa nem desempate automático.

### R6 — Fechamento com decisões

A fase fecha com a tabela de resultados entregue e duas decisões de Francisco tomadas sobre
ela:

1. Passos da árvore (D0 do ADR-0026). Regra de escolha já fixada: o menor número de passos
   que passe nos testes de precisão e de tempo **no pior caso**, não no caso médio.
2. Malha das diferenças finitas e orçamento de tempo (D4 do ADR-0027). Mesma regra: a malha
   mais leve que passe no pior caso.

Enquanto a tabela roda, nada muda: árvore CRR como motor principal, 200 passos, malha
400 por 200.

O limiar de 0,00050 e a sombra BSM já estão decididos nas ressalvas abaixo e não seguram o
fechamento.

## Ressalvas de Francisco (2026-11-20)

### S1 — O oráculo pode ser refeito

Esta fase é o marco de conferência com dados sintéticos. Refazer a conferência com o QuantLib
em outros momentos não é proibido, inclusive com dados reais, depois que a OpLab estiver
integrada ao QUIMERA e o QUIMERA fornecer os mesmos insumos aos motores do projeto e ao
QuantLib.

O que continua valendo em qualquer repetição: o QuantLib fora das dependências do
repositório (R1) e mesmos insumos por construção (R3). Cada repetição é um marco próprio,
com cartão próprio. A que usar dado real depende, antes, da ativação da OpLab, que tem rito e
autorização separados; este ADR não autoriza dado real, token nem OpLab.

Nota de vocabulário, para não misturar duas coisas: o que o oráculo faz é conferir se os
motores calculam certo dados os insumos. Com dado real ele continua fazendo só isso. Ele não
diz se o preço de mercado está certo nem ajusta modelo ao mercado.

### S2 — O limiar de 0,00050 é aviso de diagnóstico

O valor fica. Ele é aviso de diagnóstico, não alarme acionável: não recusa linha, não
reprova teste, não pede ação e não sugere operação. Nenhuma das fontes consultadas justifica
um corte universal nesse valor; ele é uma escolha do projeto.

### S3 — Dois níveis, com papéis separados

1. **Alarme técnico, offline.** Com a mesma volatilidade e os mesmos insumos, o preço de
   cada motor é comparado com o do QuantLib, e o erro é medido por prazo, strike e
   rendimento. Motor fora da faixa esperada pede revisão, com spread largo ou não. É o que
   os testes desta fase fazem. Comparar dois motores depois de ajustar ambos ao mesmo preço
   de mercado não testa isso.
2. **Alerta de relevância, só depois da homologação com dado real.** Com compra e venda
   válidas e sincronizadas, cada motor inverte os dois lados, e a margem de erro numérica
   entra na conta. Faixas de VI que se sobrepõem: mostrar a diferença, sem alarme. Faixas
   que não se sobrepõem **e** diferença material em reais por unidade: mandar para revisão.
   Cotação velha, sem um lado ou sem sensibilidade para identificar a VI: "não comparável",
   nunca "os motores concordam". Faixas separadas não significam arbitragem nem autorizam
   operação.

O nível 2 é desenho registrado. Não é construído nesta fase.

### S4 — Sombra BSM

Fica como controle onde o exercício antecipado não acrescenta valor (call sem rendimento).
Não é terceiro voto nas outras americanas. Nenhum PR para expô-la por linha é aberto antes
da tabela; se for aberto, é junto de uma nova rodada de conferência.

### Fontes trazidas por Francisco para as ressalvas

Registradas como vieram. O Claude não leu nenhuma delas nesta fase:

- Hentschel, *Errors in implied volatility estimation*, Journal of Financial and
  Quantitative Analysis: erro pequeno no preço ou na cotação do ativo vira erro grande de VI
  quando a opção é pouco sensível à volatilidade.
- Burkovska et al. (2018), *Quantitative Finance*: lido pelo Claude na Fase 2C1 (ADR-0027).
- Uma resposta do Quant Stack Exchange sobre limpeza de volatilidades observadas antes de
  calibrar e uma discussão do r/quant sobre exigir que duas VIs do meio do spread coincidam.
  Relatos de praticantes, sem revisão por pares (baixo nível de evidência). O primeiro site é
  bloqueado para as ferramentas do Claude.

## Alcance

Estado A, offline. Zero linha de produção nova. Zero dependência nova. Sem dado real, sem
OpLab, sem token. Dividendo discreto, gregas americanas e calendário brasileiro ficam fora.

## O que esta fase não prova

- Que o QuantLib está certo. Ela mostra que três métodos independentes (árvore, diferenças
  finitas e colocação espectral) convergem para o mesmo número, com erro declarado.
- Nada sobre o modelo. Volatilidade constante, juros constantes e rendimento contínuo são
  premissas dos três.
- Nada sobre dias úteis, proventos discretos ou dado de mercado.

## Decisões de Francisco (2026-11-20)

| # | Decisão |
|---|---|
| E1 | QuantLib 1.44 como oráculo, só em arquivo; nunca dependência nem motor. Aprovado, com S1. |
| E2 | Motor de referência e incerteza por caso, como em R2. Aprovado. |
| E3 | Prazo em dias corridos sobre 365; a conferência de dias úteis fica para depois. Aprovado. |
| E4 | Gerador do Claude, execução do Codex em contêiner, conferência cruzada em x86-64. Aprovado. |
| E5 | Fechamento como em R6, com S2 e S4 já decididos. Aprovado. |

## Referências

Conferidas para este ADR:

- QuantLib 1.44, pacote Python instalado e executado pelo autor: assinaturas dos motores,
  comportamento medido nos itens 1 a 4. Licença BSD de três cláusulas, sem dependências de
  instalação (metadados do pacote).
- Andersen, Lake e Offengenden, *High-performance American option pricing*, Journal of
  Computational Finance. Só o resumo foi lido: método de colocação espectral, com preços
  de dez ou onze dígitos significativos em menos de um décimo de segundo. O item 3 acima
  mostra um caso em que os esquemas prontos do QuantLib não chegam a isso.
- Código-fonte do `Business252` do QuantLib 1.44 e `backend/derivatives/pricing/calendar.py`
  do projeto, para a nota de R3 (conferidos em 2026-11-20).

Não relidas: Kim (1990) e Healy (2021), citadas em ADRs anteriores.

Não consultado: Quant Stack Exchange. O site é bloqueado para as ferramentas do Claude, e
nenhuma afirmação deste ADR se apoia nele. O que estava ao alcance foi medido direto na
biblioteca.

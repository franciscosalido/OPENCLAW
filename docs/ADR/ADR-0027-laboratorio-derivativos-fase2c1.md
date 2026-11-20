# ADR-0027 — Laboratório de Derivativos, Fase 2C1: volatilidade implícita por tipo de contrato e segundo motor americano

- **Status:** Accepted. Francisco aprovou em 2026-11-20, com ressalvas em D4 e D5 já
  incorporadas. O que está aprovado é o segundo motor. A malha, o orçamento de tempo e o
  limiar de alerta são valores **provisórios**, revistos no fechamento da Fase 2C.
- **Data:** 2026-11-20. **Autor:** Claude. **Dono das decisões:** Francisco.
- **Depende de:** ADR-0025 (núcleo CRR), ADR-0026 com a Revisão 1 (árvore CRR como motor da
  linha americana; BSM europeu como sombra).
- **Altera o roteiro:** a Fase 2C1 entra antes da Fase 2C (QuantLib como oráculo de teste).
  Decisão de Francisco em 2026-11-20.
- **Destino no repositório:** `docs/ADR/ADR-0027-laboratorio-derivativos-fase2c1.md`.

## Contexto

O Marco 2B fechou com a volatilidade implícita (VI) da linha americana invertida na árvore
CRR e com o BSM europeu da Fase 1 rodando como sombra sobre o mesmo prêmio. Francisco pediu,
antes do oráculo, um segundo método de VI para americanas, para comparar com a árvore, e a
regra escrita de que cada tipo de contrato tem o seu método.

Três fatos medidos ou lidos antes deste ADR mudam o desenho:

1. **A sombra BSM direta não mede erro da árvore, exceto num caso.** Inverter o BSM europeu
   sobre um prêmio americano responde a outra pergunta: qual volatilidade explicaria esse
   preço num contrato sem exercício antecipado. Medido no protótipo deste ADR, com juros de
   14,9% a.a.: put no dinheiro de um ano, VI verdadeira de 25,00%, BSM direto 29,60%; call
   dentro do dinheiro com rendimento de 10%, VI de 20,00%, BSM direto 24,28%; put muito
   dentro do dinheiro, sem solução. O caso em que as duas coincidem é a call sem rendimento
   com juros positivos, em que exercer antes nunca é ótimo (Merton, 1973): ali a diferença
   entre a árvore e o BSM é só erro numérico da árvore.
2. **A desamericanização não produz uma segunda VI neste laboratório.** O método estudado
   por Burkovska et al. (2018) ajusta uma árvore binomial ao prêmio americano e reprecifica
   o contrato como europeu na mesma árvore. Com volatilidade única, que é o nosso caso,
   inverter esse preço europeu devolve a própria volatilidade ajustada. O que o método
   entrega aqui é o **preço europeu equivalente** e o **prêmio de exercício antecipado**, e
   os dois já saem da ponte do 2B (`european_same_trees` e `early_exercise_premium`). O erro
   que o artigo mede aparece quando o modelo calibrado não é o da árvore (CEV, Heston,
   Merton com saltos), e cresce com juros altos, prazo longo e opção dentro do dinheiro.
3. **Na B3, a put listada sobre ação, BDR e ETF é só europeia** (Manual de Procedimentos
   Operacionais de Negociação, versão de 01/07/2026, item 3.3.1; ver ADR-0025, Adendo 1). O
   motor americano só tem uso prático em call. Em call com strike ajustado por proventos e
   sem rendimento residual, americana e europeia valem o mesmo. O segundo motor só acrescenta
   informação de mercado em call com rendimento não compensado; no resto, ele confere a
   árvore.

## Decisão

### R1 — Cada contrato é invertido no seu próprio modelo

| Contrato | Motor do preço e da VI da linha | Origem |
|---|---|---|
| Europeia | BSM em fórmula fechada | Fase 1, sem mudança |
| Americana | Árvore CRR, média do par N e N+1, busca por bisseção | ADR-0026 R1, sem mudança |

A inversão do BSM europeu sobre prêmio americano não é VI da linha e nunca é publicada como
tal. Isso já vale no código do 2B; este ADR só escreve a regra.

### R2 — Segundo motor americano: diferenças finitas, só como diagnóstico

Entra um segundo motor para a americana, de outra família numérica: a equação de
Black-Scholes em diferenças finitas, com Crank-Nicolson, partida de Rannacher e a restrição
de exercício tratada por separação de operador (Ikonen e Toivanen, 2004). Nome estável:
`fd_cn_os_v1`.

- Ele roda **só como diagnóstico**. Não altera preço, VI nem recusa da linha.
- A VI dele é invertida só em preços dele. Continua valendo "um motor por número".
- Ele não importa a árvore, o BSM nem a ponte. A independência é verificada por guarda de
  arquitetura, não por promessa.
- Preço e VI do segundo motor usam o mesmo esquema e a mesma malha. Malhas mais finas
  (800 por 400, 1600 por 800) servem só para validação offline; nunca são padrão nem
  alternativa automática.
- Nenhum motor substitui o outro em caso de falha. Isso vale também para o QuantLib na
  Fase 2C: oráculo de teste, não resultado da linha nem alternativa.

### R3 — Como ler os três números de uma linha americana

| Comparação | O que mede |
|---|---|
| VI da árvore menos VI das diferenças finitas | Erro numérico, dos dois motores somados. Mesmo contrato, mesmo prêmio. |
| VI da árvore menos VI do BSM direto | Erro numérico **mais** o efeito do exercício antecipado. Só é erro puro quando o prêmio de exercício antecipado é zero. |
| Prêmio de exercício antecipado | Preço americano menos europeu, na mesma árvore. É a desamericanização em unidade de preço. |

A comparação segue esta ordem:

1. **Preço com a mesma VI.** Os dois motores precificam o contrato na VI da linha. A
   diferença sai em preço por unidade.
2. **VI do mesmo preço-alvo.** Cada motor inverte o meio da cotação. A diferença sai em
   volatilidade.
3. **Sensibilidade.** Se mover a volatilidade em `divergence_vol` muda o preço menos que
   `low_sensitivity_price`, a comparação de VI é marcada como pouco informativa.

`|diferença de VI| > divergence_vol` gera um **alerta de diagnóstico**. Não é reprovação: não
recusa a linha, não escolhe vencedor e não derruba teste por si só. Com `divergence_vol` de
0,0005, uma VI de 20,00% contra 20,05% está exatamente no limiar. Quem arbitra é o oráculo
da Fase 2C.

Na homologação com dado real (estado B, fora deste marco), a diferença em reais aparece ao
lado do tick e do spread observado da série.

### R4 — Nada de VI "europeia equivalente" separada

Com volatilidade única ela é igual à VI americana por construção. Publicar as duas daria a
impressão de dois números independentes. Fica o prêmio de exercício antecipado.

### R5 — Mesmos insumos antes de comparar

Dois motores só são comparados depois de conferido que receberam os mesmos insumos: spot,
strike, tempo até o vencimento, taxa contínua, rendimento e preço-alvo. Na Fase 2C1 isso é
garantido por construção (os dois recebem os mesmos números da mesma linha) e preso por
teste.

Registro para a Fase 2C, conferido em 2026-11-20: o QUIMERA conta dias úteis na convenção
`(D0,Dv]` (`config/derivatives.yaml`, marcada lá como hipótese), e o `Business252` do
QuantLib 1.44 usa a contagem padrão do calendário, que inclui a primeira data e exclui a
última. As duas contagens divergem quando só um dos extremos é dia útil. Perto de feriado,
isso pareceria erro de motor sem ser. O cartão da Fase 2C passa o tempo ao oráculo como
número já calculado pelo QUIMERA, ou prova a igualdade das contagens caso a caso.

### R6 — Apresentação do alerta

Em qualquer tela ou planilha futura, o alerta aparece como realce de fundo da célula
(marca-texto). Vermelho fica reservado a número negativo e preto a número positivo, mesmo
onde não exista valor negativo possível. Este marco não constrói tela; a regra fica
registrada para quando houver.

### R7 — Alcance

Estado A, offline, fixture sintética. Sem OpLab, sem token, sem dado real. Zero dependência
nova: Python puro, biblioteca padrão. O QuantLib continua fora do repositório.

## Alternativas consideradas para o segundo motor

| Método | Por que não agora |
|---|---|
| Barone-Adesi e Whaley (1987), aproximação quadrática | É aproximação sem controle de erro. Uma divergência contra a árvore não diria quem errou. Broadie e Detemple (1996) documentam o erro em prazo longo. |
| Bjerksund e Stensland (2002) | Mesmo problema: limite inferior fechado, não método convergente. |
| Árvores melhores (Leisen-Reimer, BBSR de Broadie e Detemple) | Mesma família da CRR; erros correlacionados. Boas candidatas a motor principal no futuro, ruins como conferência independente. |
| Equação integral de Kim (1990) e colocação espectral (Andersen, Lake e Offengenden, 2016) | É o método mais preciso conhecido, e o mais difícil de implementar e revisar em Python puro. Fica para o oráculo. |
| Série de curto prazo de Medvedev e Scaillet, na forma de Goard (2021) | Expansão válida perto do vencimento; fora dela o erro não é controlado. |
| Monte Carlo com regressão (Longstaff e Schwartz, 2001) | Ruído estatístico em problema de uma dimensão. Sem vantagem. |

Diferenças finitas ficam com a escolha por três razões: convergem para o mesmo limite
contínuo da árvore por outro caminho, o erro cai de forma previsível ao refinar a malha, e
cabem em cerca de 150 linhas revisáveis.

## Consequências

- O relatório da demo mista ganha chaves novas, só aditivas. As chaves do formato v1 e as da
  sombra BSM não mudam.
- Custo: uma inversão por diferenças finitas na malha padrão custa cerca de 2 a 4 vezes a da
  árvore com 200 passos. É diagnóstico offline; não entra no teto de 210 ms da árvore, e o
  orçamento dele não tem relação com a frequência de consulta à OpLab.
- Até o oráculo existir, uma divergência entre árvore e diferenças finitas fica sinalizada e
  sem veredito.
- O protótipo mostrou as diferenças finitas em 400 por 200 cerca de dez vezes mais precisas
  em VI que a árvore com 200 passos, a quatro vezes o custo. Isso **não** muda o motor
  principal neste ADR. A pergunta volta, com o oráculo na mão, junto com a D4 do ADR-0026.

## O que este marco não prova

- Qual dos dois motores está certo quando divergem. Dois motores próprios concordando é
  evidência forte, não prova.
- Nada sobre dividendo discreto. Os dois motores usam rendimento contínuo. Whaley (1982)
  mostra viés em call americana quando o provento é tratado de forma simplificada; o
  tratamento por série depende da regra da B3 e segue na pendência D3 do ADR-0026.
- Nada com dado real.

## Decisões de Francisco (2026-11-20)

| # | Decisão |
|---|---|
| D1 | Segundo motor: diferenças finitas sobre a equação de Black-Scholes. Aprovado. |
| D2 | Papel: referência independente, só diagnóstico. A árvore CRR segue produzindo preço e VI das americanas. Aprovado. |
| D3 | Sombra BSM direta mantida até o fim da Fase 2C, com **revisão explícita no fechamento**. Ela mostra o efeito de comparar com uma referência europeia; não arbitra o preço de uma americana. |
| D4 | Malha padrão: `space_nodes: 400` e `time_steps: 200`. São 400 divisões no eixo de preço (401 nós com as extremidades) e 200 passos no tempo. Orçamento **provisório**: 700 ms no p95 de tempo de relógio de uma inversão completa no caso B1. Registrar p95 de relógio e mediana de CPU, separados. Repetir no código final antes do aceite. |
| D5 | `|diferença de VI| > 0,0005` é alerta de diagnóstico, não reprovação. Comparação na ordem de R3. Valor **provisório**. |

Medição que sustenta D4, feita sobre o protótipo do cartão (relato recebido por Francisco em
2026-11-20; MacBook Pro M4 Pro, macOS nativo, Python 3.12.13; 22 inversões por malha no caso
B1, depois de aquecimento; alvos analíticos onde não há prêmio de exercício antecipado e
malha 3200 por 1600 nos demais). Ordem: preço por tempo.

| Malha | p95 da inversão em B1 | Maior diferença de preço | Maior diferença de VI |
|---|---:|---:|---:|
| 400 x 200 | 477 ms | 0,000623 | 0,00188 p.p. |
| 200 x 400 | 393 ms | 0,004105 | 0,01242 p.p. |
| 800 x 400 | 1.870 ms | 0,000080 | 0,00042 p.p. |
| 1600 x 800 | 7.872 ms | 0,000014 | 0,00009 p.p. |

Mediana de CPU em 400 por 200 nessa rodada: 469 ms. O autor do cartão mediu 338 ms de CPU
numa máquina virtual Linux no Mac, com outro arranjo de medição; os números de precisão
coincidem (0,000623 e 1,9e-5). Isso mostra convergência do protótipo. Não é validação
independente: essa é a do oráculo.

## Referências

Lidas em texto integral para este ADR (arquivos enviados por Francisco em 2026-11-20):

- Burkovska, Gaß, Glau, Mahlstedt, Schoutens e Wohlmuth (2018). Calibration to American
  options: numerical investigation of the de-Americanization method. *Quantitative Finance*
  18(7), 1091-1113. (Estudo numérico; conclusões valem para os modelos e cenários testados.)
- Sahu e Patel (2025). Variable time step operator splitting methods with stability and
  error estimates for pricing American options. *International Journal of Computer
  Mathematics* 102(12), 2271-2298. (Análise de estabilidade da família usada aqui; passo
  variável não é adotado.)
- Goard (2021). An improvement of an analytical approximation method for American options.
  *Applied Mathematical Modelling* 98, 134-142. (Curto prazo; descartada como segundo motor.)
- Nabubie e Wang (2023). Numerical techniques for determining implied volatility in option
  pricing. *Journal of Computational and Applied Mathematics* 422, 114913. (Volatilidade
  dependente do tempo em europeias; fora do escopo, registrada para a Fase 3.)
- OptionMetrics, folheto do IvyDB Asia: europeias por Black-Scholes, americanas por algoritmo
  proprietário baseado em Cox-Ross-Rubinstein. (Material comercial de fornecedor: viés
  comercial; serve como evidência de prática de mercado, não de método.)

Citadas pela literatura acima ou de conhecimento do autor, **não relidas** para este ADR
(conferir identidade antes de citar fora do projeto):

- Merton (1973), *Bell Journal of Economics* 4(1): call americana sem dividendo.
- Cox, Ross e Rubinstein (1979), *Journal of Financial Economics* 7(3).
- Brennan e Schwartz (1977), *Journal of Finance* 32(2): diferenças finitas para a put
  americana.
- Whaley (1982), *Journal of Financial Economics* 10(1): call americana com dividendo.
- Rannacher (1984), *Numerische Mathematik* 43; Giles e Carter (2006), *Journal of
  Computational Finance* 9(4); Pooley, Vetzal e Forsyth (2003), *Journal of Computational
  Finance* 6(4): partida amortecida e suavização do payoff.
- Barone-Adesi e Whaley (1987), *Journal of Finance* 42(2).
- Kim (1990), *Review of Financial Studies* 3(4); Carr, Jarrow e Myneni (1992),
  *Mathematical Finance* 2(2): decomposição do prêmio de exercício antecipado.
- Broadie e Detemple (1996), *Review of Financial Studies* 9(4), 1211-1250. (Só o resumo foi
  conferido.)
- McDonald e Schroder (1998), *Journal of Computational Finance* 1(3): simetria entre call e
  put americanas.
- Forsyth e Vetzal (2002), *SIAM Journal on Scientific Computing* 23(6): método de
  penalidade.
- Ikonen e Toivanen (2004), *Applied Mathematics Letters* 17, 809-814. (Só o resumo foi
  conferido.)
- Andersen, Lake e Offengenden (2016), *Journal of Computational Finance* 20(1).

Não consultados: Quant Stack Exchange (bloqueado para as ferramentas do Claude) e a página do
PMC do artigo de Burkovska (a leitura foi do PDF enviado).

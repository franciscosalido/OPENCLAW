# Referências Black–Scholes–Merton — europeias, dividend yield constante

## Entrega

`bsm_reference_cases.json` contém **92 casos sintéticos analíticos**, calculados
com `mpmath` 1.3.0 a **50 dígitos decimais de precisão de trabalho**. Os parâmetros
numéricos e os resultados são publicados como **strings decimais com 20 dígitos
significativos**, usando notação científica e zeros finais explícitos.

O gerador usa exclusivamente **mpmath e a biblioteca padrão do Python**.
Não usa SciPy, NumPy, bibliotecas de opções, cotações, APIs ou componentes do
QUIMERA. A geração e a revisão ocorreram em uma pasta temporária fora de
qualquer repositório; nenhum arquivo de projeto foi modificado.

Arquivos principais:

- `bsm_reference_cases.json`: metadados em `metadata`; registros em `cases`.
- `gerador.py`: geração determinística e conferência a 100 dps.
- `bsm_reference_cases.sha256`: SHA-256 dos bytes UTF-8 do JSON, incluindo LF final.
- `README.md`: estas convenções.
- `validation_report.json`: relatório da revisão matemática independente.

SHA-256 do JSON desta entrega:

```text
aa15a6dedd03da14adbc809fdcbd4f2195d462449ad0cc77bb79dcce4892d74d
```

O JSON não contém um hash de si mesmo. Não há timestamp variável na geração.
Para reprodução byte a byte, use `mpmath==1.3.0` e mantenha o gerador fornecido.
A precisão de trabalho não constitui certificação intervalar de 50 dígitos
corretos em toda operação; os **20 dígitos publicados** foram confirmados pela
recomputação a 100 dps, inclusive nos limites de cauda.

## Cobertura

| Grupo | Quantidade | Parâmetros |
|---|---:|---|
| Hull | 1 | S=42, K=40, r=0.10, q=0, sigma=0.20, T=0.5 |
| Grade | 80 | S=100, r=0.10, q=0; K/S={0.70,0.85,1.00,1.15,1.30} × sigma={0.05,0.20,0.60,2.00} × T nominal={1/252,10/252,0.5,2.0} |
| q constante | 5 | S=100, K={70,85,100,115,130}, r=0.10, q=0.03, sigma=0.20, T=0.5 |
| Limite de volatilidade | 3 | S=100, K={90,100,110}, r=q=0, sigma=1e-6, T=0.5 |
| Limite de tempo | 3 | S=100, K={90,100,110}, r=0.10, q=0, sigma=0.20, T=1e-9 |

Os seis casos-limite têm `case_type: "limit"` e `case_id` iniciado por `limit_`.
Os dois limites são exercitados separadamente. Não há sigma=0, T=0 ou
substituição por payoff intrínseco. S, K, sigma e T são estritamente positivos.

## Contrato dos campos

Cada registro contém todos os campos solicitados:

```text
case_id, S, K, r_cont, q, sigma, T_years,
call_price, put_price, delta_call, delta_put, gamma,
vega_per_pct_point, theta_per_day_252, theta_per_day_365,
rho_per_pct_point_call, rho_per_pct_point_put, d1, d2
```

Há três campos adicionais: `case_type`, `parity_residual` e
`parity_residual_serialized`. Todos os valores dos registros são strings.
`case_id` e `case_type` são identificadores textuais; os demais valores são
decimais com uma mantissa de 1+19 algarismos. O zero usa
`"0.0000000000000000000e+0"`; matematicamente, zero exato não tem uma quantidade
intrínseca de algarismos significativos, e esse é seu formato convencional.

Exemplo: sigma=20% aparece como `"2.0000000000000000000e-1"`.

## Parâmetros publicados são a entrada autoritativa

As entradas são primeiro representadas com 20 dígitos significativos. Essas
mesmas strings são então convertidas para `mpmath.mpf` no contexto de 50 dps,
antes de calcular preços e gregas. Não há passagem por `float` binário.

Isso é necessário porque 1/252 e 10/252 não têm expansão decimal finita.
Neste arquivo, os pontos nominais da grade são representados por:

```text
1/252  -> T_years = "3.9682539682539682540e-3"
10/252 -> T_years = "3.9682539682539682540e-2"
```

Os resultados correspondem a esses decimais publicados, avaliados a 50 dps.
O racional nominal permanece identificado no `case_id` e nos metadados.
Não se deve trocar o `T_years` publicado por um racional de maior precisão
e exigir identidade dos últimos dígitos: em caudas extremas, a sensibilidade
ao arredondamento da entrada pode superar a do arredondamento do resultado.

## Modelo e fórmulas

Usamos T como tempo **restante** até o vencimento, em anos. Para distinguir
tempo restante de tempo corrente, theta usa t como tempo corrente.

O ativo tem dividend yield contínuo constante q; r é a taxa anual de juros
**continuamente capitalizada**. r, q e sigma são decimais: 0.10 significa 10%
ao ano e 0.20 significa volatilidade anual de 20%. q não representa uma agenda
de dividendos discretos. S e K têm a mesma unidade monetária.

Defina A=S exp(-qT), B=K exp(-rT), N como a CDF normal padrão e phi como sua
densidade:

```text
d1 = [ln(S/K) + (r - q + sigma²/2) T] / (sigma sqrt(T))
d2 = d1 - sigma sqrt(T)

call = A N(d1) - B N(d2)
put  = B N(-d2) - A N(-d1)

delta_call = exp(-qT) N(d1)
delta_put  = -exp(-qT) N(-d1)
gamma     = exp(-qT) phi(d1) / [S sigma sqrt(T)]
vega      = A phi(d1) sqrt(T)

rho_call = T B N(d2)
rho_put  = -T B N(-d2)

theta_call_annual = -A phi(d1) sigma / [2 sqrt(T)]
                    - r B N(d2) + q A N(d1)
```

Call e put são calculadas por suas próprias expressões. Não se calcula put
pela paridade, nem se corrige qualquer preço para fazer a checagem passar.
A CDF usa `erfc(-x/sqrt(2))/2` para preservar caudas negativas; o delta da put
usa diretamente `-exp(-qT) N(-d1)` para evitar subtração de números próximos.

Os preços são por **uma unidade do ativo subjacente**, sem multiplicador de
contrato, lotes, custos de negociação ou arredondamento para centavos.

## Unidades das gregas

| Campo | Convenção |
|---|---|
| delta_call / delta_put | Derivada do preço em relação a S |
| gamma | Segunda derivada em relação a S; igual para call e put |
| vega_per_pct_point | Derivada em relação a sigma multiplicada por 0.01; igual para call e put |
| rho_per_pct_point_call / put | Derivada em relação a r_cont multiplicada por 0.01, mantendo q fixo |
| theta_per_day_252 | **Theta da call** anual dividido por 252 |
| theta_per_day_365 | **Theta da call** anual dividido por 365 |

Um ponto percentual significa, por exemplo, sigma de 0.20 para 0.21 ou r_cont
de 0.10 para 0.11. Vega e rho são sensibilidades locais escaladas; não são o
resultado exato de um bump finito de um ponto percentual.

**Theta é a derivada em relação ao avanço do tempo corrente:**

```text
theta = dC/dt = -dC/dT
```

Mantêm-se S, K, r, q e sigma constantes nessa derivada. Como os nomes
solicitados não distinguem call de put, `theta_per_day_252` e
`theta_per_day_365` representam explicitamente **CALL**. Não são um theta
comum às duas opções. O theta anual da put, caso necessário, é:

```text
theta_put_annual = theta_call_annual - q A + r B
```

Dividir theta por 252 ou 365 é uma conversão da sensibilidade anual. Isso não
reprecifica a opção após um dia finito, não altera T, não conta feriados e não
seleciona implicitamente um calendário B3. Para T muito pequeno, a variação
de um dia pode ultrapassar o vencimento; a derivada local continua definida
para os T positivos dos casos, mas não é previsão de uma variação finita.

## Paridade e arredondamento

O resíduo assinado é:

```text
R = C - P - S exp(-qT) + K exp(-rT)
```

`parity_residual` é calculado a 50 dps com os preços internos antes de
arredondá-los para publicação. Cada caso exige **abs(R) < 1e-30**. O próprio
resíduo é então publicado com 20 algarismos na mantissa.

Resultado desta geração:

```text
92/92 casos aprovados
max abs(parity_residual) = 2.7103724727908924200e-49
```

`parity_residual_serialized` é uma segunda checagem, feita com as strings dos
preços já exportados e os parâmetros publicados, usando novamente aritmética
a 50 dps. Seu máximo nesta entrega é:

```text
max abs(parity_residual_serialized) = 9.9355086190394243586e-19
```

O limite 1e-30 vale para a checagem interna. Não se deve aplicá-lo aos preços
arredondados a 20 dígitos. Essa distinção mantém a checagem honesta e evita
uma falsa exigência de 30 casas de cancelamento em dados com 20 dígitos.

## Caso Hull

| Resultado | Valor com 20 dígitos significativos |
|---|---|
| call_price | 4.7594223928715332196 |
| put_price | 0.80859937290009358326 |
| delta_call | 0.77913129094266894042 |
| delta_put | -0.22086870905733105958 |
| gamma | 0.049962670405911855657 |
| vega_per_pct_point | 0.088134150596028513379 |
| theta_per_day_252 | -0.018091635692827882918 |
| theta_per_day_365 | -0.012490663546829113686 |
| rho_per_pct_point_call | 0.13982045913360281139 |
| rho_per_pct_point_put | -0.050425425766539990428 |
| d1 | 0.76926262810603138091 |
| d2 | 0.62784127186872187603 |

Esses preços reproduzem os valores aproximados call=4.76 e put=0.81.

## Limites e conversão para float

Valores pequenos permanecem positivos, sem truncamento artificial. Por
exemplo, a put de `limit_sigma_1e-6_K90` vale:

```text
2.5135053973201656494e-4821032816
```

Essa string é válida em aritmética de precisão arbitrária. Um `float` IEEE754
não consegue representar sua magnitude e pode produzir zero por underflow.
Não expanda a notação científica em formato fixo: seriam bilhões de zeros.
Use as strings diretamente com `mpmath.mpf` para conferir os 20 dígitos.
Um sistema implementado em float deve ter critérios explícitos de tolerância
absoluta/relativa e de underflow; isso é distinto da precisão deste oráculo.

## Reprodução fora de repositórios

Requisitos: Python 3.10 ou superior e `mpmath==1.3.0` disponíveis no ambiente.
O gerador não instala dependências. A geração desta entrega usou Python
3.12.14 e uma instalação já disponível de mpmath 1.3.0.

Na pasta que contém a entrega, **fora de qualquer repositório**, confira que
a regeneração produz exatamente os mesmos bytes:

```bash
python3 gerador.py --check
```

Para gerar novos arquivos em outra pasta vazia fora de repositórios:

```bash
python3 gerador.py --output-dir /tmp/bsm_reference_reproduced
```

O destino padrão é a pasta do próprio script. O gerador recusa diretórios
contidos em Git, Mercurial, Subversion ou Bazaar pelos marcadores conhecidos,
e detecta a estrutura de um possível Git bare. Não inicializa repositórios.
Saídas existentes não são sobrescritas: use `--check` ou outra pasta.

Conferência independente de hash no macOS:

```bash
shasum -a 256 -c bsm_reference_cases.sha256
```

## Verificação matemática

O gerador calcula a 50 dps e, antes de emitir o JSON, recompõe as mesmas
entradas publicadas a 100 dps. Exige igualdade dos arredondamentos a 20
dígitos para os **1.104 resultados**: 92 casos × 12 campos de resultado.

Além dessa checagem, uma revisão independente, sem importar o gerador:

- Recalculou os 92 casos a 100 dps e confirmou todos os resultados publicados.
- Usou a expressão alternativa de d2 e obteve theta pela PDE de Black–Scholes.
- Conferiu 48 derivadas com `mpmath.diff` em Hull e nos cinco casos com q=0.03,
  com tolerância relativa de 1e-60.
- Recalculou os 92 resíduos a partir dos preços serializados.
- Conferiu a grade cartesiana, os seis limites, a positividade dos preços,
  o formato das strings, os imports permitidos e o SHA-256 do JSON.

Essas verificações constam em `validation_report.json`. São referências
analíticas sintéticas, não homologação de preços de mercado nem de um sistema
de negociação ou de precificação em produção.

## Referências

1. *Pricing and Hedging Derivative Securities*, capítulo 9, fórmulas BSM com
   dividend yield contínuo, gregas e paridade:
   https://book.derivative-securities.org/Chapter_BlackScholes.html
2. Documentação oficial mpmath: precisão de trabalho e criação de números:
   https://mpmath.org/doc/current/basics.html
3. Documentação oficial mpmath: `nstr`, strings e dígitos significativos:
   https://mpmath.org/doc/current/general.html
4. Documentação oficial mpmath: `erfc` e avaliação das caudas:
   https://mpmath.org/doc/current/functions/expintegrals.html
5. A documentação original de QFRM reproduz o exemplo de Hull, 9ª edição,
   exemplo 15.6, e seus preços aproximados. Foi consultada somente como
   referência bibliográfica; QFRM não foi usado na geração ou validação:
   https://search.r-project.org/CRAN/refmans/QFRM/html/BS_Simple.html

---
## Nota de integração QUIMERA (Claude, 07/11/2026)
- Origem: Colaborador 2 (Codex), tarefa (a) do Departamento de Produções; gerado fora do repositório com `mpmath==1.3.0`.
- Verificação independente (Claude): SHA-256 confere; 92 casos; recomputação em `float64` dos 86 casos não-limite (call, put, d1, d2 = 344 valores) difere do oráculo em no máximo **3,2e-14** — compatível com precisão dupla.
- `gerador.py` guardado como `gerador_reference.py.txt` (referência, **não** é código do repo nem importável; recusa rodar dentro de git por desenho).
- Convenções a respeitar nos testes: `theta_per_day_*` é theta da **CALL** (theta da put = theta_call − q·S·e^{−qT} + r·K·e^{−rT}); casos `limit` têm valores abaixo do alcance de `float` — testar só regime/ausência de exceção, nunca igualdade.
- `provenance=synthetic_analytic_reference`, `purpose=test`.

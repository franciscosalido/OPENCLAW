---
tipo: conceito
dominio: investimentos
subdominio: gestao_de_risco
nivel: intermediario
status: ativo
fonte_principal: Kelly (1956) / Van Tharp / Ralph Vince
fontes_relacionadas:
  - "Kelly Criterion"
  - "Risk Management"
  - "Portfolio Construction"
conceitos_relacionados:
  - "[[Kelly_Criterion]]"
  - "[[Volatilidade]]"
  - "[[Risco_Per_Posicao]]"
  - "[[Drawdown_Maximo]]"
  - "[[Value_at_Risk]]"
tags:
  - liberdade-financeira
  - investimentos
  - gestao-risco
  - operacional
  - conceito
---

## Definição Curta

Position Sizing é a prática de determinar quanto capital alocar a cada investimento individual, baseado no risco que você está disposto a tomar, no risco específico do ativo, e na probabilidade esperada de ganho/perda. É o que diferencia investidores profissionais de amadores.

## Explicação

### Conceito Fundamental

Dois investidores com R$ 100k:

**Investidor A (Amador):**
- Acredita em ação X; aloca R$ 50k (50% do patrimônio)
- Ação cai 30%; perde R$ 15k (15% do patrimônio)
- Ação sobe 50% depois; ganha R$ 22,5k
- Resultado: Ganho R$ 7,5k, mas sofreu
- **Decisão de tamanho foi visceral** ("Gosto muito desta ação")

**Investidor B (Profissional):**
- Acredita em ação X; analisa volatilidade (25% aa), risco máximo tolerado (2% do patrimônio)
- Aloca R$ 40k, com stop loss em R$ 39,2k
- Se cai 30%, vende em ~R$ 28k; perde R$ 12k (12% do patrimônio) — DIFERENTE
- Risco máximo conhecido: R$ 2k
- **Decisão de tamanho foi matemática**

Diferença crítica: Investidor A descobriu risco após entrar. Investidor B definiu risco antes.

### Métodos de Position Sizing

**1. Fixed Fractional (Kelly Criterion Simplificado)**

Aloque uma % fixa do patrimônio por posição:
- Regra clássica: "Nunca mais de 5% em posição"
- Médico com R$ 1M: Máximo R$ 50k por ação

Vantagem: Simples, força disciplina
Desvantagem: Ignora risco específico do ativo

**2. Volatility-Based Sizing**

Aloque baseado na volatilidade do ativo:

- Ação A: Volatilidade 15% aa → Aloque 4% do portfólio
- Ação B: Volatilidade 40% aa → Aloque 1,5% do portfólio

Lógica: Ativo mais volátil = posição menor para manter risco total constante

Fórmula: **Posição (%) = Risco-Alvo (%) / Volatilidade do Ativo**

Se risco-alvo é 2% e ação tem vol 20%:
- Tamanho = 2% / 20% = 10% do portfólio

**3. Kelly Criterion (Matemática Ótima)**

Quando você sabe probabilidade de ganho/perda:

**f* = (p × b - q) / b**

Onde:
- f* = fração ótima do capital a apostar
- p = probabilidade de ganho
- q = probabilidade de perda (1 - p)
- b = razão ganho/perda esperado

Exemplo:
- Estratégia com 60% de chance de ganhar R$ 1 (e 40% de chance de perder R$ 0,75)
- p = 0,6; q = 0,4; b = 1/0,75 = 1,33
- f* = (0,6 × 1,33 - 0,4) / 1,33 = 0,40

Interpretação: Aloque 40% do capital nesta estratégia para crescimento máximo de longo prazo

**Aviso:** Kelly Criterion gera volatilidade muito alta (drawdowns de -30% são comuns). Usar "Fractional Kelly" (25-50% de Kelly) para reduzir volatilidade.

**4. Dollar-Cost Based (Risco Absoluto)**

Defina risco máximo em R$ para cada posição:

- Risco máximo por posição: R$ 5k (1% do R$ 500k de patrimônio)
- Ação X com volatilidade 20% e suporte em R$ 95 (você compra em R$ 100)
- Pode comprar: R$ 5k / (R$ 100 - R$ 95) = R$ 5k / 5 = 1,000 ações
- Posição: 1,000 × R$ 100 = R$ 100k

Vantagem: Risco absoluto é sempre controlado
Desvantagem: Tamanho de posição varia com preço da ação

## Por Que Isso Importa

Para um médico investindo:

1. **Evita Ruína**: Amador com posição de 50% em uma ação pode sofrer drawdown de 50%+. Profissional com posição de 5% sofre drawdown de 5%. Diferença entre recuperação e falência.

2. **Permite Convicções sem Destruição**: Você pode ter visão forte em ação X sem comprometer portfólio. Aloca 5-10%, deixa o resto diversificado.

3. **Acomoda Oportunidades**: Se tem cash, pode alocar a nova ideia sem vender tudo que já tem. Position sizing disciplinado clarifica capacidade de tomar novas posições.

4. **Compounding Sem Volatilidade Excessiva**: Kelly Criterion maximiza crescimento geométrico de longo prazo. Mas usar versão "fracionária" reduz volatilidade a nível tolerável.

5. **Psicologia**: Saber que máximo risco de posição é 2% dá paz mental. Você tolera volatilidade diária porque sabe que downside é limitado.

## Aplicação para Médico

**Cenário 1: Construção de Carteira Diversificada**

Médico com R$ 500k em líquido:

Decisão: 15-20 ações diferentes, + renda fixa.

Position sizing apropriado:
- Máximo por ação: 5% = R$ 25k
- Mínimo por ação: 1% = R$ 5k
- Divisão: 10 ações de R$ 25k + 10 ações de R$ 5k = R$ 300k em ações
- Renda fixa + cash: R$ 200k

Resultado: Risco idiossincrático reduzido (pior ação cai 50% = perda 2,5% total), crise setorial reduzida (setor cai 30% = perda ~6% total).

**Cenário 2: Decisão sobre Posição Nova (Healthcare)**

Médico quer adicionar ação de healthcare que acredita muito:

Análise:
- Patrimônio: R$ 1M
- Volatilidade da ação: 35% aa (muito alta)
- Risco-alvo do portfólio: 2% aa

Position Sizing:
- Tamanho ótimo = 2% / 35% = 5,7% → R$ 57k

Interpretação: Apesar de convicção forte, posição deve ser ~R$ 50k-60k. Se quiser maior posição, precisa aceitar maior volatilidade total.

**Cenário 3: Stop Loss e Position Sizing**

Médico compra ação em R$ 100 per share:

Decisão: "Não perco mais que 10% nesta posição"
- Risco máximo: R$ 10 por ação (stop em R$ 90)
- Patrimônio total: R$ 500k
- Risco máximo aceitável: 2% = R$ 10k

Posição máxima: R$ 10k / R$ 10 = 1,000 ações = R$ 100k de capital

Se patrimônio fosse R$ 1M, poderia comprar 2,000 ações = R$ 200k (mantendo risco de 2%)

Insight: O mesmo stop loss justifica tamanho diferente de posição dependendo do patrimônio. Médico mais rico aloca mais, mas mantém risco relativo constante.

**Cenário 4: Timing e Position Sizing (DCA)**

Médico quer entrar em ação que acredita estar cara:

Opção A (Amador): Espera ficar mais barata, aloca 10% quando entrar
- Risco: Nunca fica barata; fica para trás

Opção B (Profissional): Dollar Cost Averaging com position sizing
- Mês 1: Aloca 3% (R$ 30k) se preço > 100
- Mês 2: Aloca 2% (R$ 20k) se preço > 95
- Mês 3: Aloca 2% (R$ 20k) se preço > 90
- Total máximo: 7% ao fim

Resultado: Entra gradualmente, reduz risco de pior timing, força disciplina.

**Cenário 5: Rebalanceamento Dinâmico**

Médico com alocação alvo 60% ações / 40% renda fixa:

Em year 1, mercado sobe 40%:
- Ações crescem para 65% do portfólio
- Renda fixa cai para 35%

Rebalanceamento com position sizing:
- Vende 5% em ações (as melhores), reinveste em renda fixa
- Volta a 60/40

Position sizing aqui é **disciplina**: Não tenta pegar momentum ("Deixo em 70% ações, mercado vai subir mais"). Força venda do que cresceu, compra do que está barato. Historicamente, isto melhora retornos.

## Relações Importantes

Position Sizing conecta a:
- [[Kelly_Criterion]] — fórmula matemática para sizing ótimo
- [[Volatilidade]] — input crítico para determinar tamanho
- [[Risco_Per_Posicao]] — risco individual de cada posição
- [[Drawdown_Maximo]] — constrains em drawdown informam sizing
- [[Value_at_Risk]] — técnica para medir risco de posição
- [[Stop_Loss]] — define perda máxima, informa sizing
- [[Rebalanceamento]] — rebalanceamento é execução de position sizing alvo

## Armadilhas Comuns

1. **Confundir Position Sizing com Timing**: Position sizing é "quanto alocar", não "quando alocar". Primeira é técnica, segunda é especulação. Position sizing funciona com timing errado; timing sem sizing pode destruir.

2. **Aplicar Kelly Criterion Sem Histórico Suficiente**: Kelly exige saber probabilidade de ganho/perda. Sem 50+ trades anteriores, estimativa é especulativa. Usar versão mais conservadora (5% Kelly inicial).

3. **Ignorar Correlações no Portfolio**: Médico aloca 5% em 20 ações sem checar correlações. Se 15 são do setor financeiro (correlação 0,8+), "diversificação" é ilusória. Position sizing deve considerar correlação cruzada.

4. **Aumentar Tamanho com Convicção Pessoal**: "Tenho certeza absoluta nesta ação" leva a aloca 20%. Certeza psicológica ≠ certeza estatística. Position sizing não muda com sentimento.

5. **Ajustar Position Sizing Retroativamente**: Após ganho, aumenta posição ("Está ganhando, boto mais"). Após perda, reduz ("Perdi confiança"). Isto é emocional. Position sizing deve ser regra **fixa** beforehand.

6. **Kelly Criterion Sem Fractionalização**: Kelly puro gera volatilidade intolerável (50%+ drawdowns). Sempre usar "fractional Kelly" (25-50% de alocação Kelly) para tolerance psicológico.

7. **Risco Nominal vs Risco Relativo**: "R$ 100k em ouro" soa grande. Mas se patrimônio é R$ 2M, é apenas 5%. Sempre pensar em % de portfólio, não valor absoluto.

## Regra Prática

**Para médico implementando position sizing:**

1. Defina risco máximo aceitável por posição: **2-5% do portfólio**
2. Defina risco máximo do portfólio total: **Drawdown máximo 15-20%** (depende de tipo de investidor)
3. Para cada posição, calcule tamanho:
   - **Tamanho (%) = Risco-Alvo (%) / Volatilidade da Posição (%)**
4. Estabeleça stop loss: **Risco-Alvo em R$ ÷ (Preço Entrada - Preço Stop) = Quantidade**
5. Revise allocation mensalmente; rebalanceie se desvio > 2% do target
6. Nunca aloque tudo em posição; deixe 20-30% em cash/renda fixa para oportunidades e psicologia

**Implementação Prática:**
- Planilha Excel com coluna "Volatilidade 60d", coluna "Tamanho Ótimo (%)", coluna "Valor em R$"
- Recalcular mensalmente (volatilidade muda, portfólio muda)
- Sistema de ordem: Sempre incluir stop loss ao comprar

**Ferramentas:**
- Excel: STDEV() para volatilidade histórica
- Bloomberg/FactSet: Volatilidade implícita (para opções)
- Moneymanagement softwares (TradeStation, NinjaTrader) têm calculadores built-in

## Fonte

KELLY, John L. A New Interpretation of Information Rate. *The Bell System Technical Journal*, v. 35, n. 4, p. 917-926, 1956.

VAN THARP, Van K. Trade Your Way to Financial Freedom. McGraw-Hill, 1999.

VINCE, Ralph. The Handbook of Portfolio Mathematics: Formulas for Optimal Portfolio Construction. 2nd ed. Wiley, 2007.

POUNDSTONE, William. Fortune's Formula: The Untold Story of the Scientific Betting System That Beat the Casinos and Wall Street. Hill & Wang, 2005.

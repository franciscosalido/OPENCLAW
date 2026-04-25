---
tipo: conceito
dominio: investimentos
subdominio: gestao_de_risco
nivel: intermediario
status: ativo
fonte_principal: Sortino & Price (1994) / CFA Institute
fontes_relacionadas:
  - "Sharpe Ratio"
  - "Downside Deviation"
  - "Volatilidade Assimétrica"
conceitos_relacionados:
  - "[[Sharpe_Ratio]]"
  - "[[Downside_Deviation]]"
  - "[[Volatilidade]]"
  - "[[Risco_Cauda]]"
  - "[[Taxa_Livre_Risco]]"
tags:
  - liberdade-financeira
  - investimentos
  - gestao-risco
  - performance
  - conceito
---

## Definição Curta

Sortino Ratio é uma métrica de retorno ajustado ao risco que, diferentemente de Sharpe Ratio, penaliza apenas a volatilidade para baixo (downside volatility). Presume que volatilidade para cima não é risco, apenas volatilidade negativa é.

## Explicação

O Sortino Ratio (1994) é calculado como:

**Sortino Ratio = (Retorno Investimento - Taxa Alvo) / Downside Deviation**

Onde Downside Deviation é o desvio padrão calculado **apenas com retornos abaixo de um alvo** (frequentemente, a taxa livre de risco).

### Diferença Crítica vs Sharpe Ratio

**Sharpe Ratio**
- Penaliza volatilidade em ambas as direções (cima e baixo)
- Ação que sobe 15% (acima do esperado) é "penalizada" no risco

**Sortino Ratio**
- Penaliza apenas desvios negativos (downside)
- Ação que sobe 15% (acima do esperado) NÃO aumenta o "risco"

### Exemplo Numérico

Dois ativos com retorno médio 10% aa:

**Ativo A**: Retornos = [8%, 10%, 12%, 10%]
- Volatilidade (Sharpe): 1,63%
- Downside Dev (Sortino): 1% (apenas retornos abaixo de baseline)
- Sharpe (vs 4% Rf): (10-4)/1,63 = 3,68
- Sortino (vs 4% Rf): (10-4)/1 = 6,0

**Ativo B**: Retornos = [5%, 10%, 15%, 10%]
- Volatilidade (Sharpe): 4,08%
- Downside Dev (Sortino): 2,5% (apenas retorno de 5%)
- Sharpe: (10-4)/4,08 = 1,47
- Sortino: (10-4)/2,5 = 2,4

Interpretação:
- Sharpe favorece Ativo A (3,68 > 1,47): Menos variável em geral
- Sortino também favorece Ativo A (6,0 > 2,4): Menos downside
- **Mas Sortino reduz penalidade a Ativo B** porque a volatilidade extra foi para cima (+15% em um ano)

### Por que isso importa?

Em investimentos, você geralmente **gosta de volatilidade para cima**. O "risco" que importa é não atingir seus objetivos (downside), não fazer melhor que o esperado (upside).

## Por Que Isso Importa

Para um médico com objetivos de riqueza:

1. **Diferencia Ativos com "Upside Surpreendente"**: Ação que historicamente sobe 25% em bons anos e cai 5% em ruins tem downside baixo mas "volatilidade alta" em Sharpe. Sortino a avalia melhor.

2. **Alinha com Psicologia Realista**: Você se importa com perdas (downside), não com ganhos acima do esperado. Sortino reflete isto; Sharpe não.

3. **Valida Estratégias Assimétrica**: Estratégias com "risco pequeno, retorno grande" têm Sortino muito melhor que Sharpe. Exemplo: comprar opções out-of-the-money (perda limitada, ganho grande).

4. **Corrige Viés do Sharpe em Distribuições Assimétricas**: Retornos de ativos nem sempre seguem distribuição normal (simétrica). Muitos têm "caudas pesadas" no downside. Sortino captura isto melhor.

## Aplicação para Médico

**Cenário 1: Análise de Estratégia de Opções**

Médico considera estratégia de Covered Call (vender call sobre ações que possui):

Sem estratégia (apenas ações):
- Retorno esperado: 10% aa
- Volatilidade: 15%
- Sharpe: (10-4)/15 = 0,40

Com Covered Call (vende upside >12%, mas coleta prêmio):
- Retorno esperado: 9% aa (prêmio recebido)
- Volatilidade: 10% (volatilidade reduzida)
- Downside Dev: 3% (perdas limitadas)
- Sharpe: (9-4)/10 = 0,50
- Sortino: (9-4)/3 = 1,67

Interpretação: Covered Call sacrifica 1% de retorno anual, mas reduz downside de 15% para 3%. Sharpe melhora marginalmente (0,40 → 0,50), mas Sortino **melhora dramaticamente** (0,40 → 1,67). Para investidor focado em proteção de downside, isto faz sentido.

**Cenário 2: Comparação de Fundos de Ações**

Médico compara dois fundos de ações brasileiras:

**Fundo Agressivo:**
- Retorno: 12% aa
- Volatilidade total: 16%
- Downside Dev: 8% (quando o mercado cai, cai junto)
- Sharpe: (12-4)/16 = 0,50
- Sortino: (12-4)/8 = 1,0

**Fundo Defensivo:**
- Retorno: 10% aa
- Volatilidade total: 9%
- Downside Dev: 4% (proteção em crises)
- Sharpe: (10-4)/9 = 0,67
- Sortino: (10-4)/4 = 1,5

Análise:
- Sharpe diz "Fundo Defensivo é melhor" (0,67 > 0,50)
- Sortino diz "Fundo Defensivo é **muito** melhor" (1,5 >> 1,0)
- A diferença: Fundo Defensivo não apenas tem menos volatilidade geral, tem muito menos downside
- Não é apenas retorno/risco bruto; é proteção efetiva em quedas

**Cenário 3: Decisão de Posição em Dólar**

Médico com 20% do patrimônio em Dólar:

Cenário: Dólar historicamente sobe 4% aa em termos reais, mas com volatilidade 10%
- Downside Dev: 6% (perdas em anos de apreciação do Real)
- Sharpe: (4-4)/10 = 0
- Sortino: (4-4)/6 = 0 (ambos zero porque retorno = taxa livre)

**Mas mudança de análise:**
Se objetivo é proteção contra inflação/depreciação, o downside Dev baixo (6% vs volatilidade 10%) significa "a maioria da volatilidade é para cima (apreciação)". Isto não é ruim para hedge; é bom. Sortino melhor capta isto que Sharpe.

## Relações Importantes

Sortino Ratio conecta a:
- [[Sharpe_Ratio]] — métrica "irmã"; Sortino é versão que penaliza apenas downside
- [[Downside_Deviation]] — denominador de Sortino
- [[Volatilidade]] — Sharpe usa volatilidade total; Sortino apenas downside
- [[Risco_Cauda]] — relacionado a risco de perdas extremas
- [[Taxa_Livre_Risco]] — ou alvo de retorno; baseline para cálculo
- [[Opcoes_Estrategias]] — beneficia estratégias com risco assimétrico

## Armadilhas Comuns

1. **Dados Insuficientes para Downside Dev**: Downside Dev precisa de muitos pontos de dados para ser confiável. Com apenas 3 anos de história, Downside Dev pode ser instável. Preferir Sharpe com histórico curto.

2. **Escolher Alvo ("Baseline") Incorreto**: Qual é o retorno alvo para calcular "downside"? Taxa livre? Seu requisito de riqueza? Diferentes alvos geram Sortinos diferentes. Sempre explicitar o alvo.

3. **Confundir Baixo Downside Dev com "Sem Risco"**: Um ativo pode ter downside dev baixo porque sobe 95% do tempo mas cai 40% em 1 de cada 20 anos. Este "risco de cauda" não é capturado bem por Downside Dev puro.

4. **Usar Sortino para Comparar Diferentes Classes de Ativo**: Ação tem volatilidade típica 15-20%. Renda fixa tem 2-5%. Downside Dev será proporcional. Sortino de renda fixa pode parecer superior apenas por isto, não por melhor retorno ajustado.

5. **Ignorar que Sortino pode Ser Enganosamente Alto**: Estratégia que ganha 1% na maioria dos anos mas perde 30% uma vez a cada 10 anos pode ter Sortino muito alto (upside pequeno não penaliza, downside é raro). Mas a perda ocasional é devastadora. Considerar Value at Risk também.

6. **Período de Medida Muito Curto**: Em período de alta geral (bull market), downside dev é artificialmente baixo. Em bear market, é artificialmente alto. Usar múltiplos ciclos (5+ anos).

## Regra Prática

**Para médico usando Sortino Ratio:**

1. Use Sortino quando avaliar estratégias com retorno assimétrico (opções, hedge funds, covered calls)
2. Use Sharpe para comparar ações e fundos convencionais
3. Sempre explicitite o alvo/baseline usado (ex: "Sortino vs SELIC 10%")
4. Compare Sortino de apples-to-apples (ações vs ações, não ação vs renda fixa)
5. Se Sortino >> Sharpe (ex, 2,0 vs 0,5), investigar por quê: é proteção de downside real ou apenas falta de dados?
6. Combinar com análise qualitativa: downside dev baixo porque ativos são de verdade mais estáveis, ou é ilusão estatística?

**Implementação:**
- Excel: Calcular manualmente retornos abaixo de target, depois STDEV() apenas deles
- Python: pandas com condicional para downside
- Plataformas de análise (Bloomberg, FactSet) incluem Sortino

## Fonte

SORTINO, Frank A.; PRICE, Lee N. Performance Measurement in a Downside Risk Framework. *The Journal of Investing*, v. 3, n. 3, p. 59-65, 1994.

SORTINO, Frank A.; VAN DER MEER, Robert. Downside Risk. *The Journal of Portfolio Management*, v. 17, n. 4, p. 27-31, 1991.

ESTRADA, Javier. The Cost of Equity in Emerging Markets: A Downside Risk Framework. *Emerging Markets Review*, v. 1, n. 3, p. 239-261, 2000.

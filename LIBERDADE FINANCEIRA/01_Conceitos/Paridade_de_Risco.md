---
tipo: conceito
dominio: investimentos
subdominio: asset_allocation
nivel: avancado
status: ativo
fonte_principal: Dalio, R. (Principles) / Asness, C. et al. (The Idea Is Busted) / AQR Capital Research
fontes_relacionadas: []
conceitos_relacionados: []
tags:
  - liberdade-financeira
  - investimentos
  - risk-parity
  - avancado
  - conceito
---

# Risk Parity (Paridade de Risco)

## Definição Curta

Risk Parity é uma estratégia de alocação que aloca capital de forma inversamente proporcional ao [[Volatilidade|risco]] (volatilidade) de cada ativo, tal que cada classe de ativo contribua igualmente para o risco total da carteira — em vez de alocar em pesos de capital iguais ou fixos.

## Explicação

**Alocação tradicional vs. Risk Parity:**

Alocação tradicional é por *capital*: 60% ações, 40% títulos.

Problema: Ações são ~18% voláteis, títulos são ~5% voláteis. Logo, apesar de 60/40 em capital, o risco vem 95% de ações e apenas 5% de títulos. Desequilíbrio.

**Risk Parity:** Cada ativo contribui *igualmente* para risco total.

Se ações têm volatilidade 3.6x maior que títulos, aloca 1/3.6 em ações e 1 em títulos por unidade de capital.

Exemplo prático:
- Ações: volatilidade 18%, valor R$200k → risco contribuído = 0.18 × 200k = R$36k
- Títulos: volatilidade 5%, valor R$400k → risco contribuído = 0.05 × 400k = R$20k

Isso ainda não é paridade. Para paridade:
- Ações: volatilidade 18%, valor R$500k → risco = 0.18 × 500k = R$90k
- Títulos: volatilidade 5%, valor R$1500k → risco = 0.05 × 1500k = R$75k

Ainda desequilibrado. Para verdadeira paridade com 2 ativos:
- Ações: R$556k (contribui R$100k de risco)
- Títulos: R$2000k (contribui R$100k de risco)
- Razão capital: Ações/Títulos = 556/2000 = 0.278 (28% ações, 72% títulos!)

**Implicação:** Uma carteira Risk Parity é muito mais conservadora em termos de *alocação de capital* que uma carteira tradicional 60/40, porque investe muito mais em ativos baixo-risco.

Porém, compensação via alavancagem é possível (usar margem), resultando em carteira Risk Parity alavancada com risco similar a 60/40 mas melhor diversificação.

## Por Que Isso Importa

1. **Reduz concentração de risco**: Carteira 60/40 tem 95% do risco em ações. Se ações caem 40%, carteira cai ~24%. Risk Parity: risco equilibrado, menos dependência de uma classe.

2. **Melhor diversificação de verdade**: Não é "Tenho 3 fundos" diversificação. É "Cada ativo contribui igualmente para risco" — diversificação real.

3. **Reduz drawdowns**: Períodos de crise (quando correlações viram 1.0, tudo cai junto), carteiras Risk Parity sofrem menos porque têm menos exposição absoluta a risco.

4. **Pode melhorar retorno ajustado a risco**: Para mesmo nível de risco, Risk Parity pode oferecer retorno maior devido a melhor alocação eficiente.

5. **Funciona em múltiplos regimes**: Inflação alta (commodities sobem), deflação (títulos sobem), estaflação (ações caem). Risk Parity se beneficia de múltiplos cenários.

## Aplicação para Médico

Risk Parity é técnica avançada. Mas princípio é aplicável.

**Médico tradicional 70% ações / 30% renda fixa:**

Volatilidade esperada:
- Ações: 16% a.a.
- Renda fixa: 4% a.a.
- Carteira: ~0.70 × 16% + 0.30 × 4% + correlação = ~12.2%

Mas risco é concentrado: ~85% em ações.

**Médico com abordagem Risk Parity modificada:**

Responde: "Quero que ações e renda fixa contribuam igualmente para meu risco."

Mantendo diversificação, mas realocando:
- Ações: 60% capital → contribui 9.6% de risco
- Renda fixa: 40% capital → contribui 1.6% de risco

Ainda desequilibrado. Para paridade:
- Ações: 15% capital (volatilidade 16% × 0.15 = 2.4% risco)
- Renda fixa: 85% capital (volatilidade 4% × 0.85 = 3.4% risco)

Resultado: Carteira muito conservadora (85% renda fixa!). Retorno esperado cai.

**Solução: Adicionar ativos com volatilidade intermediária:**

- Ações Brasil (16% vol): 30%
- Ações Internacional (14% vol): 20%
- Imóveis (8% vol): 25%
- Renda Fixa (4% vol): 25%

Risco de cada classe:
- Ações Brasil: 0.16 × 0.30 = 4.8%
- Ações Intl: 0.14 × 0.20 = 2.8%
- Imóveis: 0.08 × 0.25 = 2.0%
- Renda Fixa: 0.04 × 0.25 = 1.0%

Ajusta pesos para igualar contribuição:
- Ações Brasil (alta vol): reduz para 20% → 0.16 × 0.20 = 3.2%
- Ações Intl (média vol): mantém 25% → 0.14 × 0.25 = 3.5%
- Imóveis (baixa vol): aumenta para 30% → 0.08 × 0.30 = 2.4%
- Renda Fixa (muito baixa vol): aumenta para 25% → 0.04 × 0.25 = 1.0%

Aproximação de paridade: cada classe contribui com risco similar.

Resultado prático:
- Médico obtém diversificação real
- Risco vem de múltiplos ativos (não 85% ações)
- Retorno similar (talvez 7-8% a.a. esperado) com risco mais baixo ou distribuído

## Relações Importantes

- [[Alocacao_Estrategica|Alocação Estratégica]]: Risk Parity é alternativa à SAA tradicional
- [[Alocacao_de_Ativos|Alocação de Ativos]]: Risk Parity é refinamento da alocação
- [[Volatilidade|Volatilidade]]: Métrica central para Risk Parity
- [[Correlacao_Ativos|Correlação de Ativos]]: Determina se risco é reduzido na carteira
- [[Diversificacao|Diversificação]]: Risk Parity é diversificação "real" de risco
- [[Fronteira_Eficiente|Fronteira Eficiente]]: Risk Parity busca estar na fronteira

## Armadilhas Comuns

1. **Risk Parity NÃO é "baixo risco"**: Carteira Risk Parity com alavancagem pode ser tão arriscada quanto 100% ações. Paridade de risco, não redução de risco.

2. **Complexidade excessiva**: Implementar Risk Parity verdadeira exige alavancagem (use margem), derivativos, rebalanceamento frequente. Para médico, adicional de complexidade pode não justificar ganho marginal.

3. **Alavancagem adiciona custos**: Se usa margem para alavancar Risk Parity, paga juros sobre dívida. Em período de taxas altas (como Brasil 2023-2024), custos podem superar benefícios.

4. **Viés em períodos de bull market acionário**: Bull markets de ações puro (2009-2019), Risk Parity underperformou 60/40 porque tinha menos exposição a ações. Psicologicamente, dói.

5. **Rebalanceamento frequente e custoso**: Risk Parity exige rebalanceamento quando volatilidades mudam, não apenas quando preços mudam. Mais transações = mais custos.

6. **Não funciona em todos os ambientes**: Risk Parity funciona bem quando ações, títulos, commodities se comportam diferente. Em crises, correlações sobem para 1.0 e benefício desaparece.

7. **Médico brasileiro: complexidade fiscal**: Rebalanceamento frequente em conta corrente (com imposto de renda) vs. NUVEM (sem imposto por 30+ dias) muda análise custo-benefício.

## Regra Prática

**Para médico brasileiro:**

Risk Parity puro é **luxo técnico**. Para maioria:

1. **Sem alavancagem**: Risk Parity não-alavancado (tipo 20% ações, 80% títulos) é muito conservador. Retorno insuficiente para atingir RF em tempo razoável.

2. **Com alavancagem simples**: Usar margem em broker para alavancar carteira Risk Parity é complexo. Custos de juros (Brasil: 10%+ a.a.) frequentemente superam benefícios.

3. **Abordagem Risk Parity modificada**: Em vez de igualar risco de verdade, busque "reduzir concentração de risco":
   - Em vez de 70% ações / 30% renda fixa
   - Use 50% ações / 25% imóveis / 15% renda fixa / 10% internacional
   - Resultado: risco mais distribuído, sem alavancagem

4. **Revisitar a cada 2-3 anos**: Volatilidades históricas mudam. Recalcule contribuição de risco de tempos em tempos.

**Fórmula simplificada para Risk Parity modificado:**

Para 4 classes com volatilidades: ações (18%), imóveis (8%), renda fixa (4%), ouro (15%):

Peso = 1 / volatilidade (normalizado)
- Ações: 1/18 = 0.056
- Imóveis: 1/8 = 0.125
- Renda fixa: 1/4 = 0.250
- Ouro: 1/15 = 0.067

Total = 0.498

Peso percentual:
- Ações: 0.056/0.498 = 11% ← muito baixo, impraticável
- Imóveis: 0.125/0.498 = 25%
- Renda fixa: 0.250/0.498 = 50%
- Ouro: 0.067/0.498 = 13% ← ausência de ações prejudica crescimento

Ajuste para praticidade:
- Ações: 40% (acima da fórmula pura, por necessidade de crescimento)
- Imóveis: 25%
- Renda fixa: 25%
- Ouro: 10%

Resultado: carteira com risco mais distribuído que 70/30 tradicional, mas viável para crescimento.

## Fonte

- Dalio, R. (2017). Principles: Life & Work. Simon & Schuster.
- Asness, C. S., Frazzini, A., & Pedersen, L. H. (2012). "Leverage Aversion and Risk Parity." Financial Analysts Journal, 68(7), 47-59.
- Roncalli, T. (2013). Introduction to Risk Parity and Budgeting. Chapman and Hall/CRC.
- AQR Capital Research. (2014). "Risk Parity: An Introduction." White Paper.
- Maillard, S., Roncalli, T., & Teïletche, J. (2010). "The Properties of Equally Weighted Risk Contribution Portfolios." Journal of Portfolio Management, 36(4), 60-70.

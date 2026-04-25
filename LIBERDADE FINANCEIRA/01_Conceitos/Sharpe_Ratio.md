---
tipo: conceito
dominio: investimentos
subdominio: gestao_de_risco
nivel: intermediario
status: ativo
fonte_principal: Sharpe, W.F. (1966) / CFA Institute
fontes_relacionadas:
  - "Sortino Ratio"
  - "Information Ratio"
  - "Risk-Adjusted Returns"
conceitos_relacionados:
  - "[[Sortino_Ratio]]"
  - "[[Information_Ratio]]"
  - "[[Volatilidade]]"
  - "[[Taxa_Livre_Risco]]"
  - "[[Retorno_Esperado]]"
tags:
  - liberdade-financeira
  - investimentos
  - gestao-risco
  - performance
  - conceito
---

## Definição Curta

Sharpe Ratio é uma métrica de retorno ajustado ao risco que mede quantas unidades de excesso de retorno um investimento gera por unidade de risco (volatilidade) assumido. Quanto maior, melhor a relação risco-retorno.

## Explicação

O Sharpe Ratio (1966) é calculado como:

**Sharpe Ratio = (Retorno Investimento - Taxa Livre de Risco) / Volatilidade (Desvio Padrão)**

### Descomposição

**Numerador: Excesso de Retorno**
- Retorno esperado menos taxa livre de risco (ex: título do Tesouro)
- Se ação teve 12% de retorno e Tesouro SELIC 10%, excesso = 2%
- Apenas este "extra" compensa o risco assumido

**Denominador: Volatilidade (Desvio Padrão)**
- Mede variabilidade dos retornos
- Ação com retorno variando entre -5% e +25% tem volatilidade alta
- Ação com retorno entre 11% e 13% tem volatilidade baixa

### Interpretação Prática

**Sharpe Ratio = 0,5**
- Para cada 1% de volatilidade, você ganha 0,5% de excesso de retorno
- Relativamente pobre

**Sharpe Ratio = 1,0**
- Para cada 1% de volatilidade, você ganha 1% de excesso de retorno
- Aceitável (muitas carteiras profissionais têm 0,8-1,2)

**Sharpe Ratio = 1,5+**
- Excelente (raro em carteiras reais após custos)
- Sugere estratégia com relação risco-retorno excepcional

### Comparação de Investimentos

Médico comparando duas opções:

**Fundo A**: Retorno 10% aa, Volatilidade 8%, Sharpe = (10-4)/8 = 0,75
**Fundo B**: Retorno 12% aa, Volatilidade 12%, Sharpe = (12-4)/12 = 0,67

Conclusão: Fundo A tem melhor relação risco-retorno (0,75 > 0,67), apesar de retorno menor. Retorno extra de 2% em Fundo B não compensa risco adicional de 4%.

## Por Que Isso Importa

Para um médico gerenciando patrimônio:

1. **Corrige "Ilusão de Retorno Alto"**: Fundo que promete 18% aa pode parecer ótimo até você ver que a volatilidade é 35%. Sharpe Ratio o expõe. Muitos investidores confundem retorno absoluto com retorno eficiente.

2. **Compara Maçã com Maçã**: Ao invés de comparar apenas retorno (arriscado) ou apenas volatilidade (incompleto), Sharpe compara ambos simultaneamente. Dois fundos com retornos similares mas Sharpe diferentes têm qualidades muito diferentes.

3. **Evita Overleverage**: Uma estratégia com Sharpe 1,2 não fica "mais segura" usando alavancagem 2x para gerar 24% de retorno. O Sharpe piora porque você assumiu 2x de volatilidade. Alavancagem não melhora eficiência.

4. **Guia Decisão de Alocação**: Se sua carteira tem Sharpe 0,8 e oportunidade surgir com Sharpe 1,2, substitua parcialmente. Se nova oportunidade tem Sharpe 0,6, ignore mesmo que retorno pareça atrativo.

## Aplicação para Médico

**Cenário 1: Análise de Carteira Pessoal**

Médico tem carteira com:
- 50% Ibovespa: Retorno 8% aa, Vol 18%
- 30% Títulos Tesouro: Retorno 10% aa, Vol 3%
- 20% Dólar: Retorno 5% aa, Vol 12%

Retorno carteira ponderado: 8,3% aa
Volatilidade carteira: ~10% aa (correlações reduzem volatilidade geral)
Sharpe Ratio da carteira: (8,3 - 4) / 10 = 0,43

Interpretação: Carteira com Sharpe baixo (0,43). Para cada 1% de risco, ganha 0,43% de retorno. Pode melhorar alocação.

**Cenário 2: Decisão de Investimento Alternativo**

Médico avalia imóvel de aluguel:
- Retorno esperado (aluguel + apreciação): 7% aa
- Volatilidade (risco de vacância, desgaste, mercado): 8%
- Sharpe: (7 - 4) / 8 = 0,375

Comparando com alternativas:
- Ação de Vale (Sharpe 0,6): Melhor relação risco-retorno
- Fundo de Renda Fixa (Sharpe 0,9): Muito melhor

Conclusão: Imóvel não é "mau", mas financeiramente é menos eficiente que papel. Decisão de imóvel deve ser por outros motivos (segurança, tangibilidade, diversificação de classes de ativo).

**Cenário 3: Avaliação de Gestor Profissional**

Médico contrata gestor com histórico:
- Retorno: 14% aa
- Volatilidade: 10%
- Sharpe: (14 - 4) / 10 = 1,0

Benchmark (CDI + 3%): Retorno 7% aa, Vol 0,5%, Sharpe = (7-4)/0,5 = 6,0

Insight: O benchmark tem Sharpe absurdo porque é quase "sem risco". Melhor comparar gestor contra benchmark com risco similar. Se benchmark for "50% Ibovespa + 50% Tesouro" com Sharpe 0,7, então gestor com Sharpe 1,0 agregou valor ao selecionar ativos melhor.

## Relações Importantes

Sharpe Ratio conecta a:
- [[Volatilidade]] — denominador da fórmula; volatilidade alta penaliza Sharpe
- [[Taxa_Livre_Risco]] — numerador usa taxa livre de risco como baseline
- [[Retorno_Esperado]] — numerador depende de retorno estimado
- [[Sortino_Ratio]] — variação que penaliza apenas downside
- [[Information_Ratio]] — compara gestor ao benchmark
- [[CAPM]] — relacionado ao conceito de compensação risco-retorno
- [[Fronteira_Eficiente]] — carteira na fronteira tem Sharpe ótimo

## Armadilhas Comuns

1. **Sharpe Ratio Retroativo é Enganoso**: Fundo que teve Sharpe 1,5 nos últimos 3 anos pode ter simplesmente aproveitado um bull market. No próximo ciclo, Sharpe pode ser 0,3. Sempre considere múltiplos períodos.

2. **Ignorar Custos**: Retorno de 12% menos 2% de taxa deixa 10%. Volatilidade permanece 12%. Sharpe cai de 0,67 para 0,50. Muitos analyses usam "retorno bruto" ignorando custos reais.

3. **Não Ajustar pela Taxa Livre de Risco Correta**: Se você investe a longo prazo (5+ anos), taxa livre deve ser a de título de 5 anos, não a taxa de curto prazo (SELIC). Taxa livre errada = Sharpe errado.

4. **Confiança Excessiva em Um Número**: Sharpe é útil mas não conta toda história. Dois ativos com mesmo Sharpe mas distribuições diferentes de retorno (um com caudas grossas, outro com distribuição normal) têm riscos diferentes.

5. **Sharpe Negativo Causa Confusão**: Se retorno < taxa livre de risco, Sharpe é negativo. -0,5 é "pior" que -2,0? Não diretamente. Para comparações com retornos negativos, use outras métricas.

6. **Alavancagem Falsa**: Você não melhora Sharpe usando alavancagem, apenas redimensiona. Sharpe = (retorno - Rf) / Vol. Com 2x alavancagem: (2×retorno - Rf) / (2×Vol). Simplificando, Sharpe fica ≈ 50% maior, não porque você é mais inteligente, mas porque assumiu 2x de risco.

## Regra Prática

**Para médico avaliando investimentos:**

1. Calcule Sharpe Ratio para cada oportunidade usando dados dos últimos 3+ anos
2. Compare Sharpe entre opções, não retorno isolado
3. Use taxa livre de risco apropriada ao horizonte (SELIC para <1 ano, Tesouro 5-10 anos para longo prazo)
4. Sharpe > 1,0 é bom; > 1,5 é excepcional
5. **Prefira Sharpe 1,0 com vol 8% a Sharpe 1,0 com vol 20%** — mesmo Sharpe, mas primeiro é mais confortável
6. Reavalie Sharpe anualmente; mudanças > 0,3 podem indicar mudança de dinâmica

**Implementação:**
- Excel: Use AVERAGE() para retorno, STDEV() para volatilidade
- Planilhas de gestoras têm Sharpe já calculado
- Cuidado: diferentes fontes usam taxas livres diferentes = Sharpes diferentes

## Fonte

SHARPE, William F. Mutual Fund Performance. *The Journal of Business*, v. 39, n. 1, p. 119-138, 1966.

SHARPE, William F. The Sharpe Ratio. *The Journal of Portfolio Management*, v. 21, n. 1, p. 49-58, 1994.

BACON, Carl R. Practical Portfolio Performance Measurement and Attribution. 2nd ed. Wiley, 2008.

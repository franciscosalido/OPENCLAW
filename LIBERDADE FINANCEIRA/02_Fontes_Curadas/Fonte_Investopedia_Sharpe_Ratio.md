---
tipo: fonte
origem: investopedia
status: curada
tema: sharpe_ratio
url: https://www.investopedia.com/terms/s/sharperatio.asp
data_leitura: 2026-04-13
tags:
  - fonte
  - investopedia
  - liberdade-financeira
  - sharpe-ratio
  - metricas
---

# Fonte: Índice de Sharpe (Sharpe Ratio)

## Resumo em 5 linhas

O Índice de Sharpe (Sharpe Ratio) mede retorno excedente (acima da taxa livre de risco) por unidade de risco (volatilidade) assumido. Fórmula simples: (Retorno Portfólio - Taxa Livre de Risco) / Desvio Padrão. Permite comparação de eficiência entre carteiras diferentes ou estratégias de investimento; carteira com maior Sharpe Ratio oferece melhor retorno por risco tomado. É métrica fundamental para avaliar gestores de fundo, estratégias de investimento e alocações de ativos. Facilita resposta à pergunta "este retorno é recompensa do risco ou apenas sorte?".

## Ideias centrais

- **Retorno ajustado ao risco**: Sharpe Ratio não avalia apenas retorno bruto, mas eficiência de transformar risco em retorno; discrimina estratégias que ganham por sorte vs. habilidade
- **Comparabilidade entre estratégias**: permite comparar carteira agressiva (alto retorno, alto risco) com conservadora (baixo retorno, baixo risco) em base comum
- **Taxa livre de risco como baseline**: escolha da taxa (título governo de curto, longo prazo) influencia resultado; em Brasil, Selic vs. Bond Prefixado produzem índices diferentes
- **Maior não é sempre melhor**: Sharpe Ratio muito alto pode indicar estratégia instável, altamente alavancada, ou resultado de otimização "data mining" em dados históricos
- **Interpretação**: Sharpe positivo significa retornos excedem custo do risco; Sharpe elevado (acima de 1,0) é geralmente considerado bom em contexto histórico

## Termos importantes

- **Retorno excedente (excess return)**: retorno da carteira menos taxa livre de risco; numerador de Sharpe Ratio
- **Volatilidade (desvio padrão)**: variação dos retornos no tempo; denominador de Sharpe Ratio
- **Taxa livre de risco**: retorno de investimento seguro (em Brasil: Selic, Tesouro Direto prefixado)
- **Sharpe Ratio negativo**: ocorre quando retorno é menor que taxa livre de risco; carteira perdeu valor em relação a aplicação segura
- **Índice de Treynor**: variação que usa beta (risco sistemático) em vez de volatilidade total; compara com CAPM

## O que é útil para o projeto

O Índice de Sharpe é essencial para LIBERDADE FINANCEIRA porque:
- Fornece métrica objetiva para avaliar se alocação está sendo eficiente (retorno adequado para risco)
- Permite comparar sua [[Alocacao_de_Ativos|alocação pessoal]] contra índices de mercado ou outras estratégias
- Facilita discussão sobre trade-off risco-retorno de forma quantificada
- Base para otimizar [[Diversificacao|diversificação]] (buscar combinações com maior Sharpe)
- Conecta-se a [[Modern_Portfolio_Theory|MPT]] e carteira tangente (aquela com maior Sharpe)

## Limitações

- **Pressuposto de volatilidade bidirecional**: Sharpe trata quedas e altas com igual peso; investidor riscos "para baixo" (downside) mais que oscilações para cima
- **Sensível a período analisado**: Sharpe Ratio calculado em períodos diferentes pode variar muito; escolha de data inicial/final influencia resultado
- **Penaliza proteção**: ativos defensivos (renda fixa, ouro) têm Sharpe Ratio baixo em períodos de expansão; isso não reflete seu valor em crises
- **Não capta risco extremo**: medida é limitada em capturar "cisnes negros" ou perdas catastróficas; Value-at-Risk ou expected shortfall são complementares
- **Brasil: escolha de taxa livre de risco ambígua**: Selic é taxa curta (muito volátil), Tesouro Prefixado é longo prazo; escolha muda o resultado; em mercados desenvolvidos há consenso (Treasuries de 10 anos)
- **Data mining risk**: em backtests, é fácil encontrar combinações com Sharpe Alto por acaso; em tempo real, retorna à realidade

## Notas derivadas

- [[Modern_Portfolio_Theory]] — Sharpe Ratio é métrica central de otimalidade em MPT
- [[Alocacao_de_Ativos]] — métrica para avaliar qualidade da alocação
- [[Volatilidade]] — componente fundamental de Sharpe Ratio
- [[Risco_Retorno]] — relação que Sharpe Ratio quantifica
- [[Metricas_Performance]] — Sharpe é uma de várias métricas de eficiência
- [[Sortino_Ratio]] — variação que penaliza apenas downside

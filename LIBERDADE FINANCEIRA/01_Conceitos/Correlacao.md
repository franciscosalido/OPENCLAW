---
tipo: conceito
dominio: investimentos
subdominio: gestao_de_risco
nivel: intermediario
status: ativo
fonte_principal: CFA Institute / Statistics fundamentals
fontes_relacionadas:
  - "Diversificação"
  - "Covariância"
  - "Correlação Dinâmica"
conceitos_relacionados:
  - "[[Diversificacao]]"
  - "[[Covariancia]]"
  - "[[Risco_Sistematico]]"
  - "[[Risco_Idiossincrático]]"
tags:
  - liberdade-financeira
  - investimentos
  - gestao-risco
  - estatistica
  - conceito
---

## Definição Curta

Correlação é uma medida estatística que quantifica como dois ativos (ou retornos) se movem juntos, variando de -1 (movimento perfeitamente oposto) a +1 (movimento perfeitamente sincronizado), sendo crucial para construir carteiras diversificadas.

## Explicação

A correlação mede o **grau de relação linear** entre dois ativos. Formalmente, é o coeficiente de Pearson normalizado entre -1 e +1:

**Correlação = Covariância(A,B) / (Desvio Padrão A × Desvio Padrão B)**

### Interpretação

**Correlação = +1**: Movimento perfeito em conjunto
- Se Ação A sobe 10%, Ação B sobe 10%
- Exemplo: duas ações do mesmo setor em mercado em alta
- Diversificação zero

**Correlação = 0**: Sem relação linear
- Movimento de A não prediz movimento de B
- Exemplo: ações de tech + preço do ouro
- Diversificação máxima (em teoria)

**Correlação = -1**: Movimento perfeitamente oposto
- Se A sobe 10%, B cai 10%
- Exemplo: ações + bonds em contexto de queda de taxas
- Melhor diversificação possível (raro)

**Correlação entre 0 e 1** (mais comum):
- Se correlação = 0,5: movimento de A prediz 25% do movimento de B
- Se correlação = 0,3: movimento de A prediz apenas 9% do movimento de B
- Correlações altas (0,7+) oferecem pouca diversificação

### Por que não é correlação perfeita?

Mercados reais raramente têm correlações extremas porque:
- Ciclos econômicos afetam ativos diferentemente
- Notícias setoriais vs macroeconômicas têm impactos variados
- Fundamentos empresariais divergem

**Correlação Histórica vs Dinâmica:**
A correlação medida no passado (ex: últimos 3 anos) pode não ser a mesma no futuro. Estudos mostram que durante crises, correlações **aumentam dramaticamente** (comportamento de "rebanho"), reduzindo benefícios da diversificação justamente quando você mais precisa.

## Por Que Isso Importa

Para um médico construindo portfólio de longo prazo:

1. **Reduz Volatilidade sem Reduzir Retorno**: Se você tem dois ativos com retorno esperado igual (8% aa) mas correlação 0,3 vs 0,8, a carteira com correlação menor terá volatilidade significativamente menor. Isto é o "almoço grátis" das finanças.

2. **Quantifica Benefício de Diversificação**: Correlação alta entre seus ativos = desperdício da diversificação. Você acredita estar diversificado, mas na verdade está concentrado.

3. **Informa Alocação Ótima**: Modelos como [[Black_Litterman]] e [[Otimizacao_Carteiras]] dependem de matriz de correlação correta. Erro aqui = carteira subótima.

4. **Alerta para Falsos Benefícios**: Muitos vendedores de produtos financeiros prometem "ativos não-correlacionados" que na realidade têm correlação 0,6-0,7. Correlação quantificada evita enganos.

## Aplicação para Médico

**Cenário 1: Análise da Carteira Atual**

Médico com R$ 1M investido em:
- 40% Ibovespa
- 30% Ações Americanas (S&P 500)
- 20% Títulos do Tesouro Brasil
- 10% Ouro

Correlações históricas (10 anos):
- Ibovespa + S&P 500: 0,65 (moderada-alta)
- Ibovespa + Tesouro Brasil: -0,10 (quase nenhuma; pequeno hedge)
- Ibovespa + Ouro: 0,25 (baixa)

Análise: A carteira tem alguma diversificação (80% em ações positivamente correlacionadas não é ideal; Tesouro oferece pouca proteção; Ouro ajuda um pouco). Volatilidade esperada: ~14-16% aa.

**Cenário 2: Decisão Setorial**

Médico quer adicionar ações de healthcare. Correlação históricas:
- Ações saúde Brasil × Ibovespa: 0,55
- Ações saúde Brasil × Tesouro: -0,05
- Ações saúde Brasil × Ouro: 0,15

Interpretação: Saúde reduz pouco a volatilidade vs Ibovespa (correlação 0,55), mas oferece alguma diferenciação. Pode ser justificado por convicção de crescimento do setor, não por diversificação.

**Cenário 3: Planejamento para Aposentadoria**

Médico em pré-aposentadoria precisa de redução de volatilidade. Opções:

**Carteira A**: 60% Ações / 40% Renda Fixa
- Correlação média ações = 0,60
- Volatilidade esperada: 10-12% aa

**Carteira B**: 50% Ações Brasil / 20% Ações Ext / 30% Renda Fixa
- Correlação Ações = 0,55
- Volatilidade esperada: 9-11% aa

A diversificação geográfica (adicionando ações internacionais) reduz volatilidade sem cortar retorno.

## Relações Importantes

Correlação se conecta a:
- [[Diversificacao]] — correlação baixa é o mecanismo por trás da diversificação
- [[Covariancia]] — covariância é a versão "não-normalizada" da correlação
- [[Risco_Sistematico]] — ativos com correlação alta vs mercado têm beta elevado
- [[Risco_Idiossincrático]] — reduzível via ativos com correlação baixa
- [[Sharpe_Ratio]] — otimização de Sharpe usa matriz de correlação
- [[Fronteira_Eficiente]] — fronteira eficiente depende de correlações

## Armadilhas Comuns

1. **Confundir Correlação com Causalidade**: Correlação 0,7 entre A e B não significa A causa B. Ambas podem ser causadas por fator C (ex: ambas reagem ao crescimento do PIB).

2. **Usar Correlações Históricas para Futuro**: A correlação do S&P 500 com Ibovespa foi 0,65 (2015-2020) vs 0,45 (2010-2015). O passado não garante o futuro.

3. **Ignorar Correlação Dinâmica em Crises**: Em março de 2020, praticamente tudo caiu junto (correlações saltaram a 0,8+). Seu diversificador de correlação 0,3 em tempos normais não protegeu em crise.

4. **Achar que Correlação Negativa é "Berço de Ouro"**: Correlação -1 é rara. Buscar obsessivamente isto leva a ativos com retornos baixos (ex: títulos muito longos, ouro puro) que ferem retorno geral.

5. **Negligenciar Matriz de Correlação Inteira**: Você tem 6 ativos. Não basta olhar correlação de A vs B. A matriz 6×6 inteira importa. Correlações "transitivas" (A correlaciona com B, B com C) importam.

## Regra Prática

**Para construir carteira diversificada:**

1. Meça correlação dos últimos 3-5 anos entre seus principais ativos
2. Inclua ativos com correlação média < 0,6 para diversificação mínima aceitável
3. Inclua 1-2 ativos com correlação negativa (renda fixa, ouro) como amortecedor
4. Reavalie correlações anualmente (mudanças > 0,15 justificam realocação)
5. **Nunca confie em correlação 0,3 para proteção em crise** — reduza volatilidade geral ao invés

**Ferramentas Práticas:**
- Excel: função CORREL()
- Python: pandas.corr()
- Bloomberg Terminal, FactSet, Yahoo Finance (históricos)

## Fonte

MARKOWITZ, Harry. Portfolio Selection. *The Journal of Finance*, v. 7, n. 1, p. 77-91, 1952.

ENGLE, Robert F. Dynamic Conditional Correlation: A Simple Class of Multivariate GARCH Models. *Journal of Business & Economic Statistics*, v. 20, n. 3, p. 339-350, 2002.

LONGIN, François; SOLNIK, Bruno. Extreme Correlation of International Equity Markets During Crises. *Journal of Finance*, v. 56, n. 2, p. 649-676, 2001.

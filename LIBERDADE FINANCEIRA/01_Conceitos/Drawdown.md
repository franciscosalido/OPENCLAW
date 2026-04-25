---
tipo: conceito
dominio: investimentos
subdominio: gestao_de_risco
nivel: intermediario
status: ativo
fonte_principal: Dowd, K. (Measuring Market Risk) / CFA Institute / Investments Performance Council
fontes_relacionadas: []
conceitos_relacionados: []
tags:
  - liberdade-financeira
  - investimentos
  - risco
  - drawdown
  - conceito
---

# Drawdown (Queda Acumulada)

## Definição Curta

Drawdown é a redução no valor de uma carteira, medida do seu pico histórico até o vale seguinte, expressa como percentual. O Maximum Drawdown (MDD) é a maior queda pico-a-vale observada em um período.

## Explicação

Drawdown é a métrica mais *intuitiva* de risco. Enquanto [[Volatilidade|volatilidade]] é estatística (desvio-padrão), drawdown é experiência real.

**Exemplo prático:**

Sua carteira:
- Jan/2023: R$100k (pico)
- Fev/2023: R$95k (queda 5%)
- Mar/2023: R$85k (queda 10%)
- Abr/2023: R$80k (pico de queda = drawdown de -20%)
- Mai/2023: R$92k (recuperação)

Seu Maximum Drawdown nesse período é **-20%** (de R$100k para R$80k).

**Tipos de drawdown:**

1. **Drawdown simples**: Qualquer queda do pico. Pode recuperar rapidamente.

2. **Maximum Drawdown (MDD)**: A maior queda pico-a-vale em um período (mês, ano, história toda).

3. **Duration of Drawdown**: Quanto tempo levou para recuperar do pico ao vale. Psicologicamente, duração importa tanto quanto magnitude.

**Exemplo de Duration:**
- Queda -30% em 2 meses, recuperação em 6 meses = drawdown profundo mas rápido na recuperação
- Queda -20% em 1 mês, recuperação em 24 meses = drawdown menor mas longo sofrimento

Ambos têm impacto psicológico diferente.

## Por Que Isso Importa

1. **Realidade do risco**: Volatilidade não diz que você perdeu R$200k em um mês. Drawdown diz.

2. **Impede "sequência de retornos ruim"**: Se precisa sacar dinheiro em 2024 e sua carteira despencar em 2022 (queda -40%), você vende tudo no fundo (lock-in loss). Entender drawdown ajuda a ser resiliente.

3. **Teste de tolerância real**: Você diz tolerar -30%? Quando chega -25% real, costuma dudar. Drawdown passado é proxy melhor de tolerância verdadeira.

4. **Impacto composto**: Drawdown de -50% exige ganho de +100% para recuperar (não +50%). Isso é impacto composto negativo.
   - R$100k → queda -50% = R$50k
   - R$50k → ganho +50% = R$75k (não volta para R$100k!)
   - Precisa +100% de ganho para voltar

5. **Informação sobre cauda**: Drawdowns revelam "eventos de cauda" (crises raras) que volatilidade média mascara.

## Aplicação para Médico

Um médico precisa entender drawdowns de sua alocação para dormir à noite.

**Cenário 1: Médico 35 anos, alocação 75% ações / 25% renda fixa, patrimônio R$300k**

Dado histórico:
- Carteira similar em 2008 (crise financeira): MDD = -45%
- Carteira similar em 2020 (COVID): MDD = -35%
- Carteira similar em 2000-2002 (bolha tech): MDD = -50%

Implicação:
- Existem períodos onde R$300k vira R$165k em meses
- Se está perto de RF naquele momento, é desastre (força a vender no fundo)
- Se está 20+ anos longe de RF, é oportunidade (compra ações baratas via [[Rebalanceamento|rebalanceamento]])

Psicológico:
- Pode dormir sabendo que pode perder -45% em ciclo?
- Se resposta é "não", precisa reduzir ações

**Cenário 2: Mesmo médico, mas alocação 50% ações / 50% renda fixa**

Dado histórico:
- MDD de carteira similar: -25% a -30%

Mais tolerável. R$300k vira R$225k no pior caso.

**Cenário 3: Médico 58 anos, quer RF em 5 anos, alocação 30% ações / 70% renda fixa, patrimônio R$1.5M**

MDD esperado: -15% a -20%

Por quê é crítico?
- R$1.5M → -20% = R$1.2M
- Plano era viver de R$1.5M
- Redução de -20% = redução de -20% de renda
- Se planejou viver de R$60k/ano (4% de R$1.5M), queda significa viver de R$48k/ano

Risco sequencial catastrófico: se crise acontece em ano 1 de RF, pode não recuperar.

**Proteção:** Esse médico deveria ter 2-3 anos de despesas em renda fixa, não investido em ações — para evitar sacar de ações no fundo.

## Relações Importantes

- [[Volatilidade|Volatilidade]]: Medida estatística de risco; drawdown é experiência real
- [[Gestao_Risco|Gestão de Risco]]: Drawdown é métrica central
- [[Tolerancia_Risco|Tolerância a Risco]]: Seu MDD tolerável define sua alocação
- [[Alocacao_de_Ativos|Alocação de Ativos]]: Alocação determina drawdown esperado
- [[Rebalanceamento|Rebalanceamento]]: Reduz drawdowns ao forçar compra em baixas
- [[Recovery_Time|Tempo de Recuperação]]: Complemento de drawdown

## Armadilhas Comuns

1. **Ignorar Duration de Drawdown**: Um drawdown de -30% recupera em 2 meses vs. 3 anos é diferente. Ambos mesma magnitude, impactos diferentes.

2. **Confundir volatilidade com drawdown**: Ação que oscila 30% a.a. em volatilidade pode ter MDD de -60% em período (volatilidade é oscilação, drawdown é queda pico-a-vale).

3. **Dados insuficientes**: Se olha apenas últimos 5 anos e maior crise foi -15%, assume MDD de -15%. Mas história de 40 anos mostra -50%. Dados históricos longos importam.

4. **Não considerar cenários extremos**: "Em 100 anos, o maior drawdown foi -60%, logo meu risco é -60%." Mas em 200 anos (se houvesse), talvez fosse -80%. Tail risk é real.

5. **Psicologia: subestimar tolerância real**: Você pensa que tolera -40%, mas quando chega -30%, quer vender. Honestidade sobre tolerância verdadeira é crítica.

6. **Ignorar sequência de retornos**: Carteira com 7% retorno médio é ótima. Mas se vai de -40%, +15%, +10%, +10%, +10%, +20%, +8%, +8% — a queda de -40% no ano 1 de RF é catastrófico mesmo se recupera depois.

## Regra Prática

**Para médico brasileiro:**

1. **Pesquise MDD histórico** de sua alocação (use Morningstar, Vanguard backtest):
   - 75/25: MDD = -35% a -45%
   - 60/40: MDD = -25% a -35%
   - 50/50: MDD = -20% a -25%
   - 40/60: MDD = -15% a -20%

2. **Teste honestidade**:
   - Imagine essa queda em valor real (R$500k → R$350k para MDD -30%)
   - Consegue dormir? Consegue não vender no pânico?
   - Se não, reduz alocação a risco

3. **Calcule tempo de recuperação**:
   - MDD -40% precisa de retorno +67% para voltar ao pico
   - Se retorno esperado é 7% a.a., leva ~9 anos para recuperar
   - Se está 20+ anos de RF, é suportável
   - Se está 5 anos de RF, é risco sequencial crítico

4. **Hedge/Proteção**:
   - Antes de RF, mantenha 2+ anos de despesas em caixa/renda fixa
   - Dessa forma, queda de -40% em ações não força liquidação no fundo
   - Pode deixar ações se recuperarem nos anos seguintes

**Exemplo prático para RF:**

Médico precisa de R$100k/ano para viver. Planejava viver de 4% de R$2.5M.

Antes de ativar RF:
- Aloca R$300k em Tesouro (3 anos de despesas)
- R$2.2M em ações/diversificação
- Se mercado cai -40%, ações viram R$1.32M
- Mas tem R$300k em tesouro para viver 3 anos
- Ações se recuperam (historicamente, levam 3-4 anos em ciclo)
- Volta a viver de 4% de ativos (sem liquidar no fundo)

Isso é **proteção contra drawdown sequencial** — crítica para RF.

## Fonte

- Dowd, K. (2007). Measuring Market Risk. John Wiley & Sons.
- CFA Institute. (2023). "Risk Management: Drawdown and Maximum Drawdown Analysis." Level III Curriculum.
- Pezier, J., & White, A. (2006). "The Relative Merits of Investable Hedge Fund Indices and of Funds of Hedge Funds in Optimal Portfolios." ICMA Centre Working Paper.
- Grossman, S. J., & Zhou, Z. (1993). "Optimal Investment Strategies for Controlling Drawdowns." Mathematical Finance, 3(3), 241-276.
- Magdon-Ismail, M., Atiya, A. F., Pratap, A., & Abu-Mostafa, Y. S. (2004). "On the Maximum Drawdown of a Brownian Motion." Journal of Applied Probability, 41(1), 147-161.

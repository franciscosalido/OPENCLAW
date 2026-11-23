# Autorização de Francisco — análise de estruturas no Laboratório de Derivativos

**Data:** 22/11/2026 · **Registro:** Claude · Texto de Francisco, na íntegra. Vale para o
Laboratório de Derivativos em simulação. Não altera a ADR-0024 nem as proibições de
`CLAUDE.md` e do ADR-007.

---

Claude,

Autorizo você a estudar em profundidade o OptionLab e os projetos relevantes dos catálogos `awesome-quant` e `awesome-quant-ai`. Quero aproveitar o que esses projetos já resolveram bem e trazer para o Quimera as capacidades que ainda nos faltam. Minha prioridade é que eu consiga olhar uma estrutura e responder três perguntas com confiança: **quanto ela ganha ou perde em cada cenário, qual posição eu realmente tenho depois de uma execução parcial e quais datas de negociação ou vencimento entraram na conta.**

**1. Comece pelo payoff e pelo resultado da estrutura.** Use o OptionLab como referência para o resultado por perna e para a soma da estratégia. Quero enxergar o débito ou crédito de entrada, os custos, os pontos de equilíbrio, o ganho máximo e a perda máxima quando existirem. Quando a perda ou o ganho for ilimitado, isso precisa aparecer mesmo que o gráfico mostre apenas uma faixa estreita de preços. Mostre separadamente o resultado no vencimento e a estimativa antes dele. Se houver vencimentos diferentes, deixe explícita a data de avaliação e como foi estimado o valor das pernas que continuam abertas.

A primeira prova que eu quero é uma **borboleta de calls de três pernas**, no mesmo ativo e vencimento. Compre uma call de strike 95, venda duas de strike 100 e compre uma de strike 105. Com débito líquido de R$ 2 por unidade, multiplicador 1 e custos zero, o resultado no vencimento deve ser **−R$ 2** se o ativo terminar em 95 ou abaixo, **+R$ 3** se terminar em 100 e **−R$ 2** se terminar em 105 ou acima. Os equilíbrios são **97 e 103**. Esses números ficam escritos no teste antes da implementação. Depois, quero a borboleta de puts, as travas e o iron condor, com quantidades, multiplicadores e custos explícitos.

**2. Trate a montagem parcial como uma posição que merece sua própria análise.** Quero ver lado a lado a estrutura planejada e a posição formada pelas execuções confirmadas, aos preços efetivos. Se executei uma asa da borboleta e apenas uma das duas vendas centrais, mostre o risco dessa combinação e identifique o que ainda depende de execução. Cada unidade de proteção só pode sustentar a quantidade compatível com ela. Uma ordem enviada não cria cobertura, e um pedido de cancelamento mantém a reserva até a confirmação. Para desenhar os testes, pode estudar os simuladores de preenchimento por volume do Backtrader. No Quimera, a evidência continua vindo do nosso livro de reservas e do replay. [Referência de execução parcial do Backtrader](https://www.backtrader.com/docu/filler/)

**3. Use o calendário da bolsa que rege o contrato.** Para instrumentos da B3, quero a sessão oficial do segmento, os feriados, os horários especiais e a regra de vencimento aplicável. O OptionLab conta fins de semana e feriados por país e usa os Estados Unidos por padrão. O `exchange_calendars` oferece um calendário BVMF que pode servir de segunda conferência. A fonte para resolver divergências brasileiras é a B3. Teste especialmente as datas em que incluir o dia inicial ou o final muda o resultado. Se a data ou o horário estiver fora da cobertura comprovada, quero ver essa limitação na análise. [Calendário oficial da B3](https://www.b3.com.br/pt_br/noticias/calendario-de-negociacao-da-b3-confira-o-funcionamento-da-bolsa-em-2026.htm) · [Calendário do OptionLab](https://github.com/rgaveiga/optionlab/blob/main/optionlab/utils.py) · [Calendário BVMF](https://github.com/gerrymanoim/exchange_calendars)

**4. Faça a validação de forma independente.** Use o QuantLib para conferir o preço teórico de cada perna quando coincidirem exercício, prazo, juros, dividendos e volatilidade. Para o payoff no vencimento, use primeiro a conta feita à mão e depois confronte o resultado com o OptionLab. Para execução parcial, use sequências de eventos com quantidades e preços conhecidos. Se dois resultados divergirem, quero uma explicação que eu consiga verificar: qual perna, qual premissa e qual foi a diferença em reais.

**5. Fica autorizada a adaptação funcional, com origem registrada.** Pode estudar fórmulas, documentação, exemplos e casos extremos e escrever a implementação que melhor se encaixar no Quimera. Para cada componente aproveitado, registre o projeto, a versão ou commit e o que aprendemos com ele. Se houver vantagem real em incorporar código de terceiros, identifique o trecho, a licença e as obrigações antes de colocá-lo no nosso repositório. O uso inicial é pessoal, e quero preservar a possibilidade de manter e compartilhar o Quimera corretamente no futuro.

Esta autorização vale para o **Laboratório de Derivativos em simulação**. Organize a execução em cartões pequenos, começando pela borboleta com resultado conhecido e pela mesma borboleta montada apenas em parte. Para mim, essas duas demonstrações juntas são o primeiro critério de sucesso.

Francisco

# DL3-PR08D — Supercartão: estimativa antes do vencimento

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `49ace06` (DL3-PR08C integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** autorização de Francisco de 22/11/2026 para a análise
de estruturas, item 1 ("mostre separadamente o resultado no vencimento e a estimativa antes
dele") e item 4 (QuantLib confere o preço teórico de cada perna).

## 0. Escopo

O resultado no vencimento já existe (`expiry_payoff`). Este cartão entrega a **estimativa
antes do vencimento**: quanto a estrutura vale e quanto ganha ou perde hoje, dadas premissas
declaradas.

**O módulo novo não calcula preço teórico.** Ele recebe, para cada perna, o resultado que as
pontes já homologadas na Fase 2 devolvem (`price_contract` para europeias, BSM;
`price_american_contract` para americanas, árvore CRR) e faz a conta da estrutura. Assim o
repositório continua com uma só fonte de preço teórico, com carry, estilo e recusas
governados pelas ADRs da Fase 2.

**Premissas são de quem chama.** Preço do ativo, prazo, taxa, volatilidade por perna e carry
entram nas pontes. O módulo não escolhe nem infere nenhuma.

**Fora deste cartão:** volatilidade implícita; calendário (o prazo chega pronto às pontes);
estruturas com vencimentos diferentes (recusadas aqui, com o motivo); gregas da estrutura;
ligação com o motor da boleta e com o recibo; tabela real de custos; tela. Nenhuma
dependência nova. Nenhum código de terceiros.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto |
|---|---|---|
| `backend/derivatives/pricing/pre_expiry.py` | módulo novo | 90 linhas |
| `tests/unit/derivatives/test_pre_expiry.py` | J1 a J7 e K1 a K4 | — |
| `docs/specs/derivatives/fase3/DL3-PR08D.md` | cópia deste cartão | — |

**Não muda:** o resto de `backend/`, os testes existentes, fixtures, `current_state.md`,
arquivos protegidos. O módulo novo importa só a biblioteca padrão, `PricingOutcome` (de
`contract_pricing`) e `ExpiryLeg` e `PayoffRefusal` (de `expiry_payoff`). Ele **não** importa
`bsm`, `binomial`, `fd_american`, `american_bridge` nem `implied_vol`.

## 2. Definição

Nomes fixos: `PreExpiryEstimate` e
`pre_expiry_estimate(legs, outcomes, *, multiplier=1, costs=Decimal(0), max_legs=8)`.

**Entradas.** `legs`: sequência de 1 a `max_legs` pernas `ExpiryLeg`, em que o prêmio é o
preço de entrada. `outcomes`: sequência de `PricingOutcome`, **um por perna, na mesma ordem**.
`multiplier`: inteiro maior que zero. `costs`: `Decimal` finito, maior ou igual a zero.
`max_legs`: inteiro de 1 a 64, padrão 8.

**Contas.** Quantidade assinada da perna = multiplicador × quantidade, negativa na venda.

- Resultado da perna = quantidade assinada × (preço teórico − prêmio), antes dos custos.
- Entrada (`net_entry`) = soma de quantidade assinada × prêmio. É a mesma do perfil de
  vencimento.
- Valor teórico (`theoretical_value`) = soma de quantidade assinada × preço teórico.
- Resultado (`result`) = valor teórico − entrada − custos.

**Aritmética exata.** O resultado não depende do contexto decimal de quem chama. Se a conta
não couber de forma exata, `PayoffRefusal`.

**Saída.** Objeto imutável com `net_entry`, `theoretical_value`, `result`, `leg_results`
(tupla, na ordem das pernas) e `outcomes` (tupla com os mesmos objetos recebidos, na mesma
ordem, para que modelo e premissas de cada perna fiquem à vista).

**Recusas.** Toda entrada inválida levanta `PayoffRefusal`:

- quantidade de preços diferente da quantidade de pernas; sequência vazia; mais pernas que
  `max_legs`; item que não é `ExpiryLeg` ou `PricingOutcome`; iterador no lugar de sequência;
- preço recusado pela ponte (`supported` falso), mesmo que venha com número. A mensagem traz
  a posição da perna, contada a partir de 1, e o motivo dado pela ponte;
- preço ausente ou negativo;
- preço de outra série: `inputs_echo["kind"]` diferente do tipo da perna, ou
  `inputs_echo["strike"]` diferente de `float(strike)` da perna;
- premissas diferentes entre as pernas: `inputs_echo["spot"]` ou `inputs_echo["time_years"]`
  não é o mesmo em todos os preços. Vencimentos diferentes ficam fora da cobertura;
- `multiplier`, `costs` ou `max_legs` fora do definido acima (`True` não é inteiro válido).

## 3. Evidência do planejador

Protótipo descartável, que não é entregue: módulo de 76 linhas, mypy estrito sem erro, 39
testes, e 25 defeitos plantados, um por vez, todos detectados. Os testes de arquitetura do
Laboratório passam com o módulo presente.

Os preços de K1 e K2 vieram das pontes que estão na `main`. Conferência com o QuantLib 1.44,
fora do repositório, perna a perna, em três preços do ativo (95, 100 e 105):

| Pernas | Referência do QuantLib | Maior diferença por unidade |
|---|---|---|
| Puts europeias (BSM) | fórmula de Black | 1,4 × 10⁻¹⁴ |
| Calls americanas (CRR, 200 passos, média de duas árvores) | diferenças finitas, exercício americano | R$ 0,0012 |

A diferença das calls é o erro de discretização da árvore de 200 passos, já conhecido da
Fase 2. Sem dividendo, a call americana vale o mesmo que a europeia, e a fórmula de Black dá
a mesma diferença.

## 4. Cenários

Dinheiro em `Decimal`. Borboleta de calls de Francisco: compra 1 call 95 a 7,00; vende 2
calls 100 a 3,50; compra 1 call 105 a 2,00.

### 4.1 Preços declarados (contas exatas)

Os preços teóricos destes cenários são números escolhidos à mão. Monte cada um como
`PricingOutcome` com `supported=True`, `model="declarado"`, o preço, e `inputs_echo` com
`kind` e `strike` da perna, `spot` 101.0 e `time_years` 0.25.

**J1 — borboleta.** Preços 7,40; 3,90; 1,90.
Entrada 2,00; valor teórico 1,50; resultado −0,50. Por perna: +0,40; −0,80; −0,10.
`outcomes` devolve os três objetos recebidos, na ordem. O objeto devolvido é imutável.

**J2 — quantidade, multiplicador e custos, com contexto decimal de 2 dígitos.** A borboleta
com 10, 20 e 10, multiplicador 100, custos 12,50, mesmos preços, chamada dentro de
`localcontext` com `prec = 2`.
Entrada 2.000,00; valor teórico 1.500,00; resultado −512,50. Por perna: +400,00; −800,00;
−100,00.

**J3 — iron condor a crédito.** Compra put 90 a 1,00; vende put 95 a 2,50; vende call 105 a
2,50; compra call 110 a 1,00. Preços 0,60; 1,70; 1,80; 0,70.
Entrada −3,00; valor teórico −2,20; resultado +0,80. Por perna: −0,40; +0,80; +0,70; −0,30.

**J4 — preço com 17 dígitos, com contexto decimal de 2 dígitos.** Uma perna: compra 7 calls
100 a 3,50, multiplicador 100, preço `3.2457812345678912`, dentro de `localcontext` com
`prec = 2`. Compare por valor, com `==`.
Entrada 2.450,00; valor teórico `2272.04686419752384`; resultado e perna
`-177.95313580247616`.

**J5 — limite de pernas.** Nove pernas iguais (compra 1 call 100 a 5,00), preço 5,50 em cada.
Com o padrão: `PayoffRefusal`. Com `max_legs=9`: resultado 4,50. Oito pernas com o padrão:
resultado 4,00. `max_legs` igual a 0, 65, `True` ou `8.0`: `PayoffRefusal`.

**J6 — recusas.** Sobre a borboleta e os preços de J1, cada caso levanta `PayoffRefusal`:

1. dois preços para três pernas; três preços para duas pernas; pernas e preços vazios; preços
   vazios;
2. segundo preço com `supported=False` e `reason="iv_unavailable:x"`, com o número 3,90
   preenchido;
3. segundo `PricingOutcome` com `price=None`; segundo com preço −0,01;
4. segundo preço com `kind` de put; segundo preço com `strike` 101;
5. segundo preço com `spot` 102.0; segundo preço com `time_years` 0.5;
6. `None` no lugar do segundo `PricingOutcome`; `None` no lugar da primeira perna;
7. `multiplier` 0 e `True`; `costs` −1, `1.5` (float) e `NaN`;
8. iterador no lugar das pernas; iterador no lugar dos preços.

**J7 — mensagem da recusa.** No caso 2 de J6, a mensagem contém `perna 2` e
`iv_unavailable:x`.

### 4.2 Preços das pontes

Premissas declaradas, sintéticas, iguais em todas as pernas: preço do ativo 100; 21 dias
úteis (`TimeToExpiry(21, 21/252, "synthetic", "test", 252, False)`); `rate_cont` 0,10;
`sigma` 0,30.

- Calls americanas: um `OptionContract` por perna, com o tipo e o strike da perna, por
  `price_american_contract`, `steps=200`, termos com política `PROTECTED` e evidência
  sintética da B3, carry `NONE`. É o mesmo molde de `test_american_bridge.py`.
- Puts europeias: um `OptionContract` por perna, por `price_contract`, com `Conventions()`.

Tolerância de 1 × 10⁻⁸ nos preços e nos resultados de K1 e K2.

**K1 — borboleta de calls americanas.** Preços das pontes: 7,013498439; 3,870317449;
1,838002754. Modelo `crr_american_v1` nas três. Entrada 2,00, exata. Resultado
−0,889133705. O resultado é exatamente valor teórico − entrada.

**K2 — borboleta de puts europeias.** Compra 1 put 95 a 2,00; vende 2 puts 100 a 3,50;
compra 1 put 105 a 7,00. Preços das pontes: 1,223926336; 3,040496887; 5,966987738. Modelo
`bsm_european_v1` nas três. Entrada 2,00, exata. Resultado −0,890079700.

**K3 — no dia do vencimento, a estimativa é o resultado no vencimento.** Prazo zero
(`TimeToExpiry(0, 0.0, "synthetic", "test", 252, True)`). Para as duas borboletas e para o
ativo em 90, 95, 100, 105 e 110, `result` é **exatamente igual** a `expiry_result` das
mesmas pernas.

**K4 — recusa da ponte chega à estimativa.** Contrato americano da perna do meio entregue a
`price_contract`: a ponte recusa. Com as outras duas pernas precificadas, a estimativa
levanta `PayoffRefusal` com `perna 2` na mensagem.

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, o cenário que derrubou o
mutante no protótipo do planejador.

1. Resultado da perna com sinal trocado (J1).
2. Venda sem inverter a quantidade (J1, K3).
3. Multiplicador ignorado (J2, J4).
4. Custos somados em vez de descontados (J2).
5. Custos multiplicados pelo multiplicador (J2).
6. Custos cobrados uma vez por perna (J2).
7. Resultado sem descontar a entrada (J1, K1).
8. Preço recusado pela ponte aceito (J6, J7).
9. Preço com tipo de outra série aceito (J6).
10. Preço com strike de outra série aceito (J6).
11. Preços calculados com preços do ativo diferentes aceitos (J6).
12. Preços calculados com prazos diferentes aceitos (J6).
13. Quantidade de preços diferente da de pernas aceita (J6).
14. Preço negativo aceito (J6).
15. Limite padrão diferente de 8, ou limite superior de `max_legs` ignorado (J5).
16. Conta feita no contexto decimal de quem chama (J4).
17. Resultados por perna devolvidos em ordem invertida (J1).
18. `outcomes` devolvido em ordem invertida (J1, K1).
19. Mensagem de recusa sem o motivo da ponte (J7).
20. Iterador aceito no lugar de sequência (J6).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §4 não reproduzir, ou K1 e K2 passarem da tolerância em um dos dois
  sistemas;
- o módulo precisar calcular preço teórico, ou importar algo fora do que o §1 permite;
- outro arquivo existente de `backend/` ou algum teste existente precisar mudar;
- os testes de arquitetura precisarem de exceção;
- o teto do §1 estourar.

## 7. Entrega

1. Commit vermelho com os testes; depois o verde.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   **Não rode `tests/integration` no Mac:** só no contêiner isolado.
3. Conferência com o QuantLib, fora do repositório, de cada perna de K1 e K2: tabela com
   perna, premissas, preço da ponte, preço do QuantLib e diferença em reais. A referência é
   o valor convergido do QuantLib (fórmula de Black, ou diferenças finitas com exercício
   americano em malha fina), não uma árvore de 200 passos. Diferença acima de R$ 0,002 por
   unidade em qualquer perna é critério de parada.
4. Descrição do PR: cabeça, contagens, linhas do módulo, os 20 mutantes, a tabela do item 3,
   desvios.
5. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
6. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Confronta os
cenários com o protótipo próprio e com o QuantLib, fora do repositório.

## 8. Depois deste cartão

O calendário pedido na carta (item 3) já existe em boa parte no repositório: calendário de
negociação da B3 com cobertura declarada, contagem de dias úteis e recusa fora da cobertura.
O planejador confere o que falta frente à carta antes de escrever o cartão seguinte.
PR07A3, PR07A4 e PR07B continuam atrás desta frente.

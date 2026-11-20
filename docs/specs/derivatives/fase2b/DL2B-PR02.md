# DL2B-PR02 — IV americana por preço observado

**Candidato local, pendente de revisão por Claude. Estado A.** Francisco autorizou o
empilhamento sobre o PR01A local `f848b199aee3bf01bd3923a24b4b4abb41811ee3`.
A sequência de integração do ADR-0026 continua a depender do coordenador e dos pareceres.

## Autoridade e alcance

O SDD vigente exige, no critério 6, pelo menos 40 idas e voltas do preço da ponte com
erro absoluto de IV até 1e-6 e orçamento fixado no Mac antes do código. Os critérios
5, 9 e 10 regem isolamento, regressão, paridade de plataformas e até 400 linhas de produção.
O preço da ponte é a média aritmética das árvores americanas CRR de N e N+1 passos.
A IV vive em `american_bridge.py` e recebe os termos e o carry da série.

Francisco decidiu D1. CALL com q resolvido exatamente zero e r estritamente positivo
usa a IV europeia da Fase 1. Em r=0 a função inverte o par CRR. PUT, taxa negativa
e CALL com rendimento positivo também passam pelo par. O caminho é escolhido antes da
busca. Cada falha encerra o caminho escolhido.

**Ajuste de redação proposto para o critério 6, sujeito a Claude e Francisco.** Exigir
pelo menos 40 idas e voltas identificáveis pelo mesmo par CRR e, separadamente, paridade
do atalho com o oráculo BSM da Fase 1. Com S=K=100, T=1, r=0,05, q=0, sigma=0,20,
o par 200/201 precifica a 10,449949594185 e o BSM a 10,450583572186. A IV BSM do
preço CRR é 0,199983104711, com desvio de 1,6895e-5 em relação a 0,20. Este alvo
cruzado testa D1 e evidencia o erro de discretização. A grade CRR mantém 1e-6.
A redação oficial encontra-se em [SDD_FASE2B.md](SDD_FASE2B.md).

## Contrato de engenharia proposto para revisão

`american_implied_vol(contract, *, terms, carry, spot, target_price, rate_cont, tte, steps)`
inverte um preço por unidade em Decimal. Bid e ask são duas chamadas independentes;
cada uma devolve solução imutável (sigma anual em fração, modelo usado na inversão e
bracket final) ou recusa imutável (motivo estável e sigma nulo). O chamador fornece N.
Estilo, termos, carry e identidade da série seguem a precedência da ponte de preço.
As recusas dos isolados conservam o prefixo e o código. O atalho também exige
spot Decimal, taxa e prazo float finitos, 1 ≤ N ≤ 4999, S e K positivos.

- T=0, alvo inválido, preço fora dos limites de arbitragem, proximidade dos limites,
  ausência de bracket, sensibilidade insuficiente e esgotamento têm recusas específicas.
  O piso considera exercício imediato e valor europeu descontado. O teto é S na CALL
  e K vezes max(1, exp(-rT)) na PUT. Dentro da resolução de preço de um limite, a IV
  é indeterminada.
- Na árvore, bracket de sigma inicial [max(0,0001, |r-q|√(T/N) + 1e-8), 2].
  O piso respeita a probabilidade estrita de CRR no par. Os resíduos extremos devem
  envolver o alvo estritamente. Coincidência dentro da resolução de um extremo da busca
  dá recusa conservadora, inclusive quando a raiz poderia coincidir com esse extremo.
- Bisseção, até 64 iterações, largura ≤ 1e-8 e resíduo de preço ≤
  1e-10 × max(1, alvo). Para publicar a solução, preços a ±1e-6 da candidata devem
  separar o alvo por mais que essa resolução dos dois lados, dentro do bracket inicial.
  Esta sondagem testa identificabilidade local. Nenhuma grega americana entra na API.
- D1 usa `implied_vol` com `Iv()` da Fase 1 e sua tolerância dupla original.
  Apenas solução bem condicionada pode publicar sigma. A função preserva o bracket da
  Fase 1 e devolve uma recusa quando a precisão de preço não distingue 1e-6 de sigma.
- Estes intervalos, resolução, tipo de retorno e orçamento são escolhas provisórias de
  engenharia. D2 e D3 pertencem aos cartões seguintes. D4 pertence a Francisco após a medição.

## Orçamento medido antes de RED e GREEN

Mac arm64, macOS 15.8.1, Darwin 24.6.0, CPython 3.12.13, pydantic 2.13.3,
pytest 9.0.3. Microbenchmark local de referência sobre o PR01A, uma thread, um aquecimento
e nove inversões por cenário. Spot e strike 100, r=0,05. O alvo sai da ponte antes do
cronômetro. A referência usa bisseção sobre os dois CRR existentes, com os parâmetros acima;
D1 mede o oráculo existente sobre o alvo cruzado. CPU por processo (`process_time`) e tempo
decorrido (`perf_counter`) em milissegundos. Cada amostra da API candidata deve caber no
orçamento de CPU da sua linha, na mesma máquina. O tempo decorrido é descritivo.

| Caso (q, T, sigma, N) | CPU mín / med / máx | Decorrido mín / med / máx | Teto CPU |
|---|---:|---:|---:|
| PUT (0, 0,25, 0,275, 50) | 9,02 / 9,30 / 9,77 | 9,02 / 9,31 / 9,90 | 20 ms |
| CALL (0,08, 1, 0,23, 200) | 134,67 / 136,41 / 139,11 | 134,73 / 136,67 / 139,15 | 210 ms |
| PUT (0, 1, 0,37, 400) | 487,90 / 490,86 / 496,56 | 488,28 / 491,09 / 496,74 | 750 ms |
| D1 CALL (0, 1, 0,20, 200) | 0,069 / 0,074 / 0,082 | 0,071 / 0,074 / 0,081 | 0,50 ms |

Os tetos valem para esses cenários dimensionados. O custo de cada avaliação CRR cresce com
o quadrado de N. O teto algorítmico por busca é de 68 pares (extremos, bisseção e sondagem).

## Provas exigidas

1. RED comportamental e commit próprio. GREEN com 48 idas e voltas CRR identificáveis
   (tipo/carry/taxa, prazo, moneyness e sigma variados), mais D1 contra o oráculo,
   o caso cruzado e as fronteiras q positivo minúsculo, r nulo e r negativo.
2. Precedência, arbítrio de exercício imediato, limites com juros negativos, platô,
   sensibilidade local, bracket, entradas inválidas, par N/N+1 e término delimitado.
   Um lado inválido de cotação deve poder coexistir com outro lado identificável.
3. Mutações focais em cópias descartáveis. Regressão em ambos os SO, pytest sem integração
   com timeout 120, mypy strict, pyright, demo contra base por cmp e CLI padrão rc 3 com
   LIVE_NOT_ACTIVATED. Conferir isolamento, diff, contagem e escopo dos arquivos.
4. O coordenador mantém o índice de base/head. Claude emite parecer independente sobre o
   candidato local, examina a evidência e leva a proposta de redação à decisão humana.

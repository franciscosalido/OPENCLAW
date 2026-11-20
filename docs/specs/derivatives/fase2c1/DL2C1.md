# DL2C1 — Segundo motor americano por diferenças finitas (cartão único da Fase 2C1)

- **Autor do cartão:** Claude, 2026-11-20. **Implementa:** Codex. **Revisa e integra:** Claude.
- **Autoridade:** ADR-0027, Accepted em 2026-11-20. Malha, orçamento de tempo e limiar de
  alerta são provisórios (D4 e D5).
- **Base:** `main` em `49b12dd`. **Estado:** A, offline, fixture sintética.
- **Destino:** `docs/specs/derivatives/fase2c1/DL2C1.md`.
- **Entrega em dois PRs, um por vez:** PR 1 (motor e inversão, sem consumidor) e PR 2 (ligação
  na demo mista e fechamento).

## Objetivo

Ter na demo mista offline uma segunda volatilidade implícita para a linha americana,
calculada por um motor de diferenças finitas que não compartilha código com a árvore, e a
diferença entre as duas publicada por linha e no agregado. O número da linha continua sendo
o da árvore CRR.

## Não objetivos

Trocar o motor principal. Gregas americanas. Dividendo discreto. Passo de tempo variável.
Malha não uniforme. Método de penalidade, PSOR ou Brennan-Schwartz. Barone-Adesi-Whaley,
Bjerksund-Stensland, Leisen-Reimer, BBSR. QuantLib. NumPy ou qualquer dependência. Retirar
ou renomear a sombra BSM. Dado real, OpLab, token. Caminho de mercado. Refatorar
`american_bridge.py`, `binomial.py`, `bsm.py` ou `implied_vol.py`.

## Critérios de aceite

Tolerâncias fixadas a partir do protótipo do autor do cartão (seção "Âncoras"). Preços por
unidade, com `S` perto de 100.

1. **Europeia contra fórmula fechada.** Nos nove casos da tabela de âncoras, modo europeu,
   malha 400 por 200: `|FD - BSM| <= 3e-4`. Observado: 1,0e-4.
2. **Call sem rendimento (Merton).** Casos A1 a A3, modo americano, malha 400 por 200:
   `|FD americana - BSM europeia| <= 2e-4`. Observado: 4,9e-5.
3. **Âncoras do esquema.** Os dezoito valores "FD amer." e "FD eur." da tabela são
   reproduzidos com erro absoluto `<= 1e-6`. Se não reproduzir, pare e reporte a diferença;
   não ajuste a tolerância nem o esquema por conta própria.
4. **Contra a árvore, motor de produção.** Nos nove casos: `|FD 400x200 - par CRR
   2000/2001| <= 1.5e-3`, com o par calculado por `crr_price` dentro do teste. Observado:
   5,8e-4.
5. **Convergência.** Nos nove casos, com malhas 400x200, 800x400 e 1600x800:
   `|FD800 - FD1600| <= |FD400 - FD800| / 2.5`. Observado: razão entre 3,3 e 9,0.
6. **Simetria de McDonald e Schroder.** Em pelo menos 20 casos:
   `|C(S,K,r,q) - P(K,S,q,r)| <= 1.5e-3` na malha 400 por 200. Observado: 5,5e-4.
7. **Invariantes em grade** de pelo menos 500 casos, zero exceção não tipada: americana
   `>=` intrínseco (exato); preço não decrescente em sigma (folga de 1e-9); americana `>=`
   BSM europeia menos 3e-4.
8. **Recusas tipadas.** Malha inadmissível, volatilidade zero, entrada não finita, fora do
   domínio, tipo errado, vencimento. Nenhuma devolve número; nenhuma exceção escapa das
   funções públicas para entrada de qualquer tipo.
9. **Ida e volta da VI.** Preço do motor com sigma conhecido, invertido, devolve sigma com
   erro `<= 1e-6`, em pelo menos 40 casos identificáveis.
10. **VI contra alvo independente da malha.** Nos nove casos, alvo = coluna "Alvo" da tabela:
    `|VI FD 400x200 - sigma| <= 5e-5`. Observado: 1,9e-5.
11. **VI entre motores.** Nos nove casos, mesmo alvo: `|VI CRR 200 - VI FD 400x200| <= 5e-4`,
    com a VI da árvore calculada por `american_implied_vol`. Observado: 2,1e-4. Este teste
    prende os nove casos sintéticos; na demo, passar de 5e-4 gera alerta, não falha.
12. **Isolamento.** O módulo novo importa só biblioteca padrão e os enums de domínio. Nenhum
    módulo de produção o importa no PR 1; no PR 2, só `service/american_demo.py`. Ele não
    importa `binomial`, `bsm`, `implied_vol` nem `american_bridge`, nem por intermediário.
13. **Diagnóstico inofensivo.** Com o segundo motor falhando, recusando ou devolvendo
    qualquer valor, toda linha é idêntica à do `49b12dd` fora das chaves `fd_*`.
14. **Chave desligada.** Demo padrão idêntica byte a byte à de `49b12dd`. CLI padrão devolve
    `LIVE_NOT_ACTIVATED`, rc 3.
15. **Compatibilidade.** Na demo mista, nenhuma chave existente muda de nome, tipo ou valor.
    As chaves novas são só aditivas.
16. **Tempo.** No código final, caso B1, malha padrão, macOS nativo: 22 inversões completas
    depois de aquecimento. Registrar na descrição do PR, separados, o p95 de tempo de relógio
    e a mediana de CPU, com modelo da máquina e versão do Python. Orçamento provisório:
    p95 de relógio `<= 700 ms`. É medição, não teste automático. Referência no protótipo:
    477 ms de p95 e 469 ms de mediana de CPU num M4 Pro.
17. **Disciplina.** Suíte verde; no máximo 400 linhas de produção por PR; zero dependência
    nova; protegidos intactos; mesma contagem de testes em macOS e Linux; `mypy --strict` e
    `pyright` sem erro; docstring em toda função e classe pública; linhas de até 100 colunas.
18. **Mesmos insumos.** Na demo, o segundo motor recebe spot, strike, tempo, taxa, rendimento
    e preço-alvo idênticos (`==`) aos que a árvore recebeu na mesma linha.
19. **Uma malha só.** O preço e a VI do segundo motor usam a malha da configuração. Nenhum
    caminho de produção troca de malha, refina sozinho ou recorre a outro motor.

## Método (especificação do esquema `fd_cn_os_v1`)

Variável `x = ln S`, tempo até o vencimento `tau`. Equação:

```
dV/dtau = (sigma^2 / 2) V_xx + (r - q - sigma^2 / 2) V_x - r V
```

com `V >= g` na americana, `g(x) = max(0, sinal * (exp(x) - K))`, `sinal = +1` call, `-1` put.

**Malha de espaço.** `nx = space_nodes` é o número de **divisões** do eixo de preço; os nós
vão de `0` a `nx`, portanto `nx + 1` nós com as extremidades (400 divisões, 401 nós). `nx`
par (se vier ímpar, recusa). Meia largura:

```
L  = max(width_stdevs * sigma * sqrt(T) + |r - q - sigma^2 / 2| * T,
         |ln(S / K)| + sigma * sqrt(T))
dx = 2 L / nx
x_i = ln S - L + i dx,   i = 0..nx      (o spot é o nó nx / 2)
```

**Admissibilidade.** Se `sigma^2 < |r - q - sigma^2 / 2| * dx`, recusa
`grid_not_admissible`. Sem diferença a montante, sem correção silenciosa.

**Condição inicial.** `V_i = g(x_i)`, exceto no único nó cuja célula
`[a, b] = [x_i - dx/2, x_i + dx/2]` contém `ln K` no interior. Ali entra a média exata:

```
call: V_i = (exp(b) - K - K (b - ln K)) / dx
put:  V_i = (K (ln K - a) - (K - exp(a))) / dx
```

O obstáculo `g` usa sempre o payoff pontual, sem média.

**Operador.** Coeficientes constantes nos nós internos:

```
alpha = sigma^2 / (2 dx^2)       beta = (r - q - sigma^2 / 2) / (2 dx)
inferior = alpha - beta          diagonal = -2 alpha - r          superior = alpha + beta
```

**Tempo.** `nt` passos de `dt = T / nt`. Os primeiros `rannacher_steps` passos são trocados,
cada um, por dois meios passos de Euler implícito (`theta = 1`, `h = dt / 2`). Os demais são
Crank-Nicolson (`theta = 1/2`, `h = dt`).

**Passo com separação de operador.** `lambda` começa em zero. Em cada passo:

```
(I - theta h A) W = (I + (1 - theta) h A) V + h lambda        (sistema tridiagonal)
para cada nó interno i:
    tentativa = W_i - h lambda_i
    se tentativa > g_i:   V_i = tentativa;  lambda_i = 0
    senão:                lambda_i = max(0, lambda_i + (g_i - W_i) / h);  V_i = g_i
```

No modo europeu não há projeção e `lambda` fica em zero.

**Bordas.** Nos nós `0` e `nx`, no tempo `tau` do fim do passo:

```
e = sinal * (S_i exp(-q tau) - K exp(-r tau))
americana: max(0, e, g_i)        europeia: max(0, e)
```

**Resultado.** Valor no nó `nx / 2`. Com `T = 0`, o intrínseco. O sistema tridiagonal é
resolvido por eliminação direta (Thomas), com a fatoração reaproveitada entre passos de
mesmo `h` e `theta`.

**Inversão.** Bisseção em sigma sobre o preço americano deste motor, no intervalo
`[piso, bracket_hi]`. `piso` é o maior entre `bracket_lo` e a menor volatilidade admissível
para a malha. Parada: `hi - lo <= tol_vol` e resíduo `<= tol_price_rel * max(1, alvo)`.
Mesma sondagem de identificabilidade do 2B: se o preço não se move mais que a tolerância a
`1e-6` de cada lado da solução, o estado é `not_identifiable`.

## Interface

**Arquivo novo** `backend/derivatives/pricing/fd_american.py`, até 230 linhas:

```python
FD_MODEL: Final = "fd_cn_os_v1"

class FdRefusalCode(StrEnum): ...   # invalid_input_type, non_finite_input,
                                    # input_out_of_domain, zero_volatility,
                                    # invalid_grid, grid_not_admissible, not_representable

class FdRefusal(Exception): ...     # carrega o código

@dataclass(frozen=True, slots=True)
class FdGrid:
    space_nodes: int; time_steps: int; width_stdevs: float; rannacher_steps: int

def fd_price(*, kind: OptionKind, style: ExerciseStyle, spot: float, strike: float,
             time_years: float, rate_cont: float, dividend_yield: float, sigma: float,
             grid: FdGrid) -> float: ...

@dataclass(frozen=True, slots=True)
class FdIvResult:
    status: str                # ok, unbracketed, not_identifiable, no_convergence,
                               # grid_not_admissible, invalid_input
    sigma: float | None
    iterations: int = 0

def fd_implied_vol(*, kind: OptionKind, spot: float, strike: float, time_years: float,
                   rate_cont: float, dividend_yield: float, target_price: float,
                   grid: FdGrid, bracket_lo: float, bracket_hi: float, max_iterations: int,
                   tol_price_rel: float, tol_vol: float) -> FdIvResult: ...
```

`fd_price` levanta `FdRefusal`. `fd_implied_vol` nunca levanta: devolve estado. Tipos são
conferidos com `type(x) is float`, como no núcleo binomial.

**Configuração nova** `config/american_fd.yaml` e `config/american_fd_config_model.py`, no
molde de `american_iv`: modelo pydantic estrito, congelado, sem valor padrão no código.

```yaml
# Segundo motor americano (diagnóstico). Não afeta a árvore nem a Fase 1.
space_nodes: 400
time_steps: 200
width_stdevs: 6.0
rannacher_steps: 2
bracket_lo: 1.0e-3
bracket_hi: 2.0
max_iterations: 64
tol_price_rel: 1.0e-10
tol_vol: 1.0e-8
divergence_vol: 5.0e-4          # alerta, não reprovação (provisório)
low_sensitivity_price: 1.0e-4   # por unidade (provisório)
```

`space_nodes` conta divisões do eixo de preço, não nós; dizer isso no comentário do YAML e
na docstring do modelo.

**Ligação (PR 2)** em `service/american_demo.py`, depois da sombra BSM e só em linha
suportada. Mesmo padrão: `try` em volta, `except Exception` vira `fd_iv_status = "error"`.

Chaves novas por linha, em `assumptions`:

| Chave | Conteúdo |
|---|---|
| `fd_engine` | `"fd_cn_os_v1"` |
| `fd_grid` | `"400x200"` |
| `fd_iv_status` | estado da inversão |
| `fd_iv_mid` | VI do meio pelo segundo motor (só com estado `ok`) |
| `fd_price_gap` | preço da linha menos o preço do segundo motor na VI da linha, por unidade |
| `fd_iv_gap` | VI da linha menos `fd_iv_mid` (só com estado `ok`) |
| `fd_iv_comparison` | `"informative"` ou `"low_sensitivity"` (só com estado `ok`) |
| `fd_iv_alert` | `true` se `|fd_iv_gap| > divergence_vol` e a comparação é informativa |

`low_sensitivity`: o preço do segundo motor em `VI da linha + divergence_vol` menos o preço
na VI da linha é menor que `low_sensitivity_price`. Linha pouco informativa nunca gera
alerta; o `fd_iv_gap` continua publicado.

Chaves novas na chain, em `model_assumptions`: `american_fd_engine`, `american_fd_grid`,
`american_fd_rows` (linhas comparadas), `american_fd_max_abs_gap` (só se houver comparação),
`american_fd_alert_rows` (linhas com `fd_iv_alert`), `american_fd_low_sensitivity_rows`.

O alerta não muda `supported`, `reason`, preço nem VI da linha, e não altera o código de
saída do CLI. Realce visual (fundo de célula, não vermelho) é regra do ADR para tela futura;
este cartão não constrói tela.

A configuração entra pela raiz de composição da demo, como `iv_config`. YAML ausente ou
inválido: demo padrão idêntica; demo mista devolve `DEMO_UNAVAILABLE`.

## Âncoras

Geradas pelo protótipo do autor do cartão, em Python 3.12, iguais em x86-64 Linux e em
aarch64 Linux no Mac. `R = math.log1p(0.149)`. Os números entram nos testes como `float`.

| Caso | Opção | S | K | T | r | q | sigma | FD amer. 400x200 | FD eur. 400x200 | BSM eur. | Alvo (FD amer. 1600x800) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | CALL | 100 | 100 | 1 | R | 0 | 0.25 | 17.1763409420 | 17.1763409420 | 17.1763291968 | 17.1763298697 |
| A2 | CALL | 110 | 100 | 0.5 | R | 0 | 0.30 | 19.3912219359 | 19.3912219359 | 19.3912184537 | 19.3912186245 |
| A3 | CALL | 95 | 100 | 21/252 | R | 0 | 0.35 | 2.2781935933 | 2.2781935933 | 2.2781444026 | 2.2781474390 |
| B1 | CALL | 100 | 100 | 1 | R | 0.06 | 0.25 | 13.0277106261 | 13.0276447430 | 13.0276065835 | 13.0276741026 |
| B2 | CALL | 110 | 100 | 1 | 0.05 | 0.10 | 0.20 | 11.7698519902 | 10.1546263116 | 10.1546830895 | 11.7702532627 |
| B3 | CALL | 120 | 100 | 0.75 | R | 0.08 | 0.30 | 25.6872917374 | 25.6625238259 | 25.6624290236 | 25.6871730143 |
| C1 | PUT | 100 | 100 | 1 | R | 0 | 0.25 | 5.6962274996 | 4.2084278734 | 4.2085311115 | 5.6968511479 |
| C2 | PUT | 110 | 100 | 0.25 | R | 0 | 0.35 | 2.5062680054 | 2.3893161497 | 2.3893041740 | 2.5065055226 |
| C3 | PUT | 100 | 100 | 5/252 | R | 0 | 0.30 | 1.5688683123 | 1.5493677643 | 1.5493716835 | 1.5689431768 |

Notas:

- Os casos C são puts americanas. Testam o motor; não correspondem a instrumento listado em
  ações, BDRs ou ETFs na B3 (manual de 01/07/2026, item 3.3.1).
- A coluna "Alvo" é a melhor estimativa disponível do preço contínuo, não a verdade. Quem
  confere a verdade é o oráculo da Fase 2C.
- Sensibilidade do esquema, para o revisor: sem Rannacher os valores mudam entre 7e-6 e
  1,6e-4; sem a média do payoff, entre 1e-5 e 1,0e-3. O critério 3 pega as duas trocas.
- Rannacher não melhora todos os casos na malha padrão: ajuda no dinheiro (A1, B1) e piora
  pouco em C1 a C3. Fica pelo ganho com poucos passos de tempo (teste T12) e por robustez.

Desvio de VI observado contra o alvo, para referência dos critérios 10 e 11:

| Caso | VI CRR 200 | VI FD 400x200 | CRR menos FD | BSM direto |
|---|---:|---:|---:|---:|
| A1 | +9,9e-5 | -3,5e-7 | +9,9e-5 | +2,6e-8 |
| A2 | -1,4e-4 | -1,6e-7 | -1,4e-4 | +6,5e-9 |
| A3 | -8,1e-5 | -4,5e-6 | -7,7e-5 | +2,9e-7 |
| B1 | +3,4e-5 | -1,1e-6 | +3,5e-5 | +2,0e-6 |
| B2 | -3,2e-5 | +1,3e-5 | -4,5e-5 | +4,3e-2 |
| B3 | +4,2e-6 | -4,9e-6 | +9,1e-6 | +1,1e-3 |
| C1 | +8,2e-5 | +1,9e-5 | +6,3e-5 | +4,6e-2 |
| C2 | -1,9e-4 | +1,5e-5 | -2,1e-4 | +7,5e-3 |
| C3 | -7,6e-5 | +1,3e-5 | -8,9e-5 | +3,5e-3 |

O protótipo fica em `reports/fase02/dl2c1-prototipo/` (fora do Git; `fd.py` SHA-256
`8c143996…fa44a2`). Ele é a referência do autor do cartão; a implementação sai da seção
"Método", sem copiar o protótipo.

**Limite declarado.** O protótipo foi executado na medição de D4, antes da implementação.
Se quem mediu for quem implementa, o critério 3 deixa de ser evidência de implementação
independente e passa a ser só regressão do esquema. A descrição do PR 1 diz quem abriu o
protótipo e quando. A independência que conta fica com a guarda de arquitetura (critério 12)
e com o oráculo da Fase 2C.

## PR 1 — DL2C1-PR01: motor e inversão, sem consumidor

Arquivos de produção permitidos: `pricing/fd_american.py`, `config/american_fd.yaml`,
`config/american_fd_config_model.py`. Mais a guarda de arquitetura em `tests/architecture/`.
Nenhum arquivo de produção existente muda.

**Commit 0 — documentação.** ADR-0027 (Accepted), este cartão e o bloco "Fase 2C1" no
`current_state.md`, com o roteiro novo: 2C1, depois 2C (QuantLib como oráculo), Fase 3,
Fase 4 (Kronos). Registrar: decisão de Francisco em 2026-11-20.

**RED, em commits próprios, antes de qualquer produção:**

- RED-1: âncoras A1 a C3 americanas e europeias (critério 3). Falha por módulo inexistente.
- RED-2: ida e volta da VI (critério 9).

**Testes** em `tests/unit/derivatives/test_fd_american.py` e
`tests/unit/derivatives/test_fd_american_iv.py`:

| # | Teste | Critério |
|---|---|---|
| T1 | Dezoito âncoras, `<= 1e-6` | 3 |
| T2 | Europeia contra `bsm.price`, nove casos | 1 |
| T3 | Call sem rendimento contra BSM, A1 a A3 | 2 |
| T4 | Contra `crr_price`, par 2000/2001, nove casos | 4 |
| T5 | Convergência em três malhas, nove casos (marcar como lento se passar de 20 s) | 5 |
| T6 | Simetria call e put, 20 casos de semente fixa | 6 |
| T7 | Grade de 500 casos: intrínseco, monotonia em sigma, piso europeu | 7 |
| T8 | Tabela de recusas: cada código com um caso; nenhuma devolve número | 8 |
| T9 | Malha inadmissível: `sigma = 0.005`, `r = R`, `T = 1` recusa; `sigma = 0.05` aceita | 8 |
| T10 | `T = 0` devolve o intrínseco, call e put, dentro e fora do dinheiro | método |
| T11 | Modo europeu não aplica o obstáculo: C1 europeia menor que C1 americana | método |
| T12 | A1 em malha 400 por 20: o erro contra o BSM com `rannacher_steps = 2` é menor que um quinto do erro com `0` (observado: 3,1e-3 contra 3,4e-2) | método |
| T13 | Ida e volta, 40 casos identificáveis, `<= 1e-6` | 9 |
| T14 | VI contra o alvo, nove casos, `<= 5e-5` | 10 |
| T15 | VI entre motores, com `american_implied_vol`, `<= 5e-4` | 11 |
| T16 | Estados: preço no intrínseco dá `not_identifiable`; alvo acima do preço em `bracket_hi` dá `unbracketed`; `max_iterations = 1` dá `no_convergence` | 8 |
| T17 | `fd_implied_vol` com tipos errados em cada argumento devolve `invalid_input`, sem exceção | 8 |
| T18 | YAML: campo a mais, campo a menos, inteiro como texto, `bracket_lo >= bracket_hi`, `space_nodes` ímpar; todos recusados | config |
| T19 | Guarda: o módulo não importa `binomial`, `bsm`, `implied_vol`, `american_bridge`; nenhum módulo de produção o importa | 12 |

**Mutantes mínimos do autor** (registrar morto ou vivo, com o teste que matou):

1. Retirar a projeção da americana.
2. Não somar `h * lambda` no lado direito.
3. Não zerar `lambda` quando a tentativa fica acima do obstáculo.
4. Trocar `inferior` por `superior`.
5. Diagonal sem `- r`.
6. Borda sem desconto (`e = sinal * (S - K)`).
7. Retirar a média do payoff.
8. Retirar os meios passos de Rannacher.
9. Crank-Nicolson com `theta = 1`.
10. Spot fora do nó central (`L` sem recentrar em `ln S`).
11. Admissibilidade com `>` no lugar de `<`.
12. Bisseção com o sinal do resíduo invertido.
13. Retirar a sondagem de identificabilidade.
14. `piso` sem a menor volatilidade admissível.

**Medição.** Protocolo do critério 16, sobre o código final do PR.

## PR 2 — DL2C1-PR02: ligação na demo mista e fechamento

Só depois do PR 1 integrado. Arquivos de produção permitidos: `service/american_demo.py`,
`service/demo_chain.py` e a raiz de composição que carrega a configuração. Meta de até 70
linhas de produção.

**RED próprio:** linha americana suportada da demo mista sem as chaves `fd_*`.

| # | Teste | Critério |
|---|---|---|
| U1 | Linha suportada tem as chaves da tabela; `fd_iv_gap` igual à VI da linha menos `fd_iv_mid` | 15 |
| U2 | `|fd_iv_gap| <= 5e-4` na série sintética com 200 passos | 11 |
| U3 | Linha recusada e linha europeia não têm chave `fd_*` | 13 |
| U4 | Segundo motor levantando exceção: `fd_iv_status = "error"`, resto da linha idêntico | 13 |
| U5 | Segundo motor devolvendo estado sem sigma: estado preservado, sem `fd_iv_mid` nem `fd_iv_gap`, resto idêntico | 13 |
| U6 | Segundo motor devolvendo sigma deslocada em 0,01: `fd_iv_alert` verdadeiro, `american_fd_alert_rows == 1`, agregado publica o módulo; `supported`, `reason`, preço e VI da linha inalterados; rc do CLI igual | R3 do ADR |
| U7 | Duas linhas suportadas, a segunda com módulo maior: o agregado escolhe a segunda | R3 do ADR |
| U8 | Todas as chaves anteriores da linha e da chain com o mesmo valor do `49b12dd` | 15 |
| U9 | Demo padrão idêntica byte a byte; CLI padrão `LIVE_NOT_ACTIVATED`, rc 3 | 14 |
| U10 | YAML do segundo motor ausente: demo padrão idêntica, demo mista `DEMO_UNAVAILABLE` | config |
| U11 | Guarda: só `service/american_demo.py` importa o módulo novo | 12 |
| U12 | Insumos capturados nas chamadas da árvore e do segundo motor são idênticos (`==`) na mesma linha | 18 |
| U13 | Preço quase insensível à volatilidade: `fd_iv_comparison == "low_sensitivity"`, sem alerta mesmo com desvio acima do limiar, `fd_iv_gap` publicado | R3 do ADR |
| U14 | Desvio exatamente igual a `divergence_vol` não gera alerta; acima, gera | R3 do ADR |
| U15 | `fd_price_gap` é calculado com a VI da linha, na mesma malha da inversão | 19 |

**Mutantes mínimos:** rodar o segundo motor em linha recusada; usar o primeiro desvio no
agregado; agregado sem módulo; `fd_iv_gap` com o sinal trocado; alerta com `>=`; alerta em
linha pouco informativa; alerta mudando `supported`; engolir o estado e publicar `ok`;
inverter no preço da linha em vez do meio da cotação; passar ao segundo motor um tempo
recalculado em vez do tempo da linha.

**Fechamento.** Tabela "Provas dos critérios 1 a 19" no documento de evidências do PR 2,
`current_state.md` com a Fase 2C1 fechada e a próxima ação (ADR e cartão da Fase 2C).

## Portão e rito, nos dois PRs

- `python -m pytest tests/ -q --ignore=tests/integration --timeout=120` em macOS arm64 e em
  Linux aarch64, mesma contagem. `mypy backend/ --strict` e `pyright backend/` sem erro.
- PR em rascunho, sem merge. Squash no GitHub e avanço local por `--ff-only`, feitos pelo
  Claude.
- Skill `quimera-lab-review` em sessão separada, sobre o head publicado. Parecer fora do Git;
  só o SHA-256 na descrição. A avaliação de simplificação usa a v0.2 do projeto e diz isso.
- Uma edição em teste existente só com autorização escrita do Claude, linha por linha.
- Parar e perguntar, sem contornar, se: uma âncora não reproduzir; um critério exigir mexer
  em arquivo fora da lista; o tempo passar do teto; aparecer necessidade de dependência.

## Riscos

| Risco | Mitigação |
|---|---|
| Ler a concordância dos dois motores como prova | ADR-0027, "O que este marco não prova"; oráculo na Fase 2C |
| Segundo motor virar motor principal por inércia | Critério 13; ADR R2; mudança de motor exige ADR próprio |
| Ruído numérico com volatilidade muito baixa | Recusa `grid_not_admissible` (T9) |
| Oscilação de Crank-Nicolson perto do vencimento | Rannacher e média do payoff, presos por T1 e T12 |
| Custo em chain grande | Medição do critério 16; só o meio da cotação é invertido |
| Alerta lido como reprovação | U6 e U14; ADR R3 |
| Diferença de insumo lida como erro de motor | Critério 18; ADR R5 (contagem de dias no 2C) |
| Implementação copiada do protótipo | Limite declarado na seção "Âncoras"; revisão compara com a seção "Método"; oráculo na Fase 2C |
| Escopo crescer para dividendo discreto ou gregas | Não objetivos; pendência D3 do ADR-0026 segue com Francisco |

## Bloco para colar no Codex

```
Fase 2C1, cartão DL2C1 (reports/fase02/dl2c1/DL2C1_CARD.md) e ADR-0027
(reports/fase02/dl2c1/ADR-0027_FASE2C1.md). Base: main 49b12dd.

PR 1 (DL2C1-PR01), em rascunho, sem merge:
0. Commit de documentação: ADR-0027 em docs/ADR/ com status Accepted
   (Francisco, 2026-11-20; D4 e D5 provisórios), cartão em
   docs/specs/derivatives/fase2c1/DL2C1.md e bloco "Fase 2C1" no
   current_state.md com o roteiro 2C1 -> 2C -> 3 -> 4.
1. RED-1 e RED-2 em commits próprios.
2. Produção só em pricing/fd_american.py, config/american_fd.yaml e
   config/american_fd_config_model.py. Implementar pela seção "Método".
   Não copiar código de reports/fase02/dl2c1-prototipo/.
3. Testes T1 a T19, 14 mutantes, medição pelo critério 16 (22 inversões
   em B1; p95 de relógio e mediana de CPU, separados).
   Dizer na descrição quem abriu o protótipo e quando.
4. Portão em macOS e Linux, skill quimera-lab-review em sessão separada,
   SHA-256 do parecer na descrição.
Se uma âncora não reproduzir em 1e-6, pare e reporte a diferença.
O PR 2 só começa depois do PR 1 integrado pelo Claude.
```

## Adendo 1 (Claude, 2026-11-20) — critério 7 na malha padrão

Vale sobre o texto acima onde houver conflito. Francisco pode vetar.

O critério 7 pedia `americana >= BSM europeia - 3e-4` sem dizer a malha. O limite absoluto
foi tirado dos nove casos das âncoras e não vale fora deles: é defeito do cartão, não da
implementação. O erro do esquema é de truncamento de segunda ordem e escala com `S dx^2`,
em que `dx` é o passo em `ln S` da seção "Método". Medido na revisão do PR 1:

| Medida | 400 x 200 | 800 x 400 | 200 x 100 |
|---|---:|---:|---:|
| `|FD europeia - BSM| / (S dx^2)`, máximo | 0,52 | 0,36 | 0,52 |
| `(BSM - FD americana) / (S dx^2)`, máximo | 0,17 | 0,17 | 0,04 |

Os máximos vêm de 1.500 casos aleatórios (400 x 200), 300 (800 x 400), 600 (200 x 100) e da
matriz de 1.000 preços do teste T7. A razão não muda quando a malha dobra.

O critério 7 passa a ser, em qualquer malha, inclusive a padrão:

- `|FD europeia - BSM| <= 0.8 * S * dx^2`;
- `BSM europeia - FD americana <= 0.3 * S * dx^2`;
- americana `>=` intrínseco, exato; preço não decrescente em sigma, com folga de 1e-9.

O limite absoluto de 3e-4 continua valendo na malha 800 por 400 para a matriz do T7, como
qualificação offline. Na malha padrão ele falha em 93 dos 1.000 preços dessa matriz, com
desvio máximo de 9,06e-4; um teste prende esse número para a limitação não sumir.

Consequência para a leitura do diagnóstico: com `sigma * sqrt(T)` acima de 1, o erro de preço
da malha padrão chega a 1e-2 por unidade e o de volatilidade a 2e-4, da mesma ordem do erro
da árvore com 200 passos. A vantagem de precisão medida nas âncoras não vale nesse regime.

## PR 1 — revisão independente: GO (Claude, 2026-11-20)

Head do autor: `4b34e61`.

- Portão em clone limpo, Linux aarch64: 10.225 aprovados, 16 pulados, 261 subtestes;
  `mypy --strict` (164 arquivos) e `pyright` sem erro. macOS não reproduzido pelo revisor.
- ADR-0027 e cartão copiados sem alteração (SHA-256 conferidos).
- Produção: três arquivos novos, 283 linhas. Nenhum arquivo de produção existente muda.
- O motor do autor e o protótipo do revisor, escritos em separado, coincidem em 300 casos
  aleatórios fora das âncoras, com diferença relativa máxima de 2e-13. É o mesmo esquema; não
  é validação do esquema.
- 20.818 chamadas com tipos e valores errados nas duas funções públicas: nenhuma exceção
  fora de `FdRefusal`, nenhum estado `ok` sem sigma.
- Mutação do revisor: 24 trocas, 19 mortas. Das cinco vivas, três eram lacunas de teste,
  fechadas no commit do parecer (largura mínima por moneyness; borda europeia sem obstáculo;
  parada da bisseção só por sigma). Duas são equivalentes: o `max(0, ...)` em `lambda` é
  redundante, porque o ramo só é alcançado com o termo não negativo; e a borda americana sem
  o payoff muda o preço em 4e-4 mesmo com a borda a um desvio do spot, porque a projeção
  nos nós internos repõe o obstáculo.
- Medição do autor, código final, M4 Pro: p95 de relógio de 340 ms e mediana de CPU de
  336 ms em 22 inversões de B1. Orçamento provisório: 700 ms.
- O protótipo foi aberto por outro colaborador na medição de D4, antes da implementação; a
  sessão autora declara não ter aberto o código. O critério 3 fica como regressão do esquema.

Parecer da skill sobre `4b34e61` (SHA-256 `08f04a16…cc42`), lido depois do veredito e antes
do merge: sem bloqueante de código; pediu decisão sobre a malha do critério 7, com um
contraexemplo reproduzido aqui. A decisão é o Adendo 1. O teste T7 do autor rodava em
800 por 400 e dizia isso na docstring e na descrição do PR.

Testes do revisor, não revistos por outro agente:
`test_review_error_scales_with_the_mesh_on_the_default_grid`,
`test_review_default_grid_misses_the_absolute_floor_and_says_so`,
`test_review_narrow_grid_keeps_the_strike_and_the_european_edge` e
`test_review_stop_needs_the_price_residual_too`.

## PR 2 — revisão independente: GO (Claude, 2026-11-20)

Head do autor: `02c97e9`. Duas autorizações escritas do revisor no caminho: a edição das três
linhas do T19 (o cartão pedia zero importadores no PR 1 e um no PR 2) e a alteração pontual
em `mcp/derivatives_server.py` (o cartão pedia a diferença publicada por linha e não listava
o arquivo que monta a saída). As duas inconsistências eram do cartão.

- Portão em clone limpo, Linux aarch64, no head do autor: 10.255 aprovados, 16 pulados, 261
  subtestes; `mypy --strict` sem erro em 164 arquivos. macOS não reproduzido pelo revisor.
- Produção: 84 inserções e 6 remoções em três arquivos. Passa da meta de 70 e fica abaixo
  do teto de 400. Em `_row_view`, sete inserções.
- Saída pública: a chave `diagnostics` só aparece em linha americana suportada e só traz as
  chaves `fd_*`. A sombra BSM por linha continua fora da saída pública; fica para a revisão
  de fechamento da Fase 2C (D3 do ADR-0027).
- Mutação do revisor: 17 trocas, 16 mortas. A viva calculava os preços auxiliares no estilo
  europeu; a série sintética é call sem rendimento, em que os dois estilos valem o mesmo.
  Fechada no commit do parecer com `test_review_fd_diagnostic_prices_the_american_contract`,
  não revisto por outro agente.
- O alerta compara os decimais nominais das duas volatilidades; o desvio publicado é a
  subtração dos floats. Diferença exatamente igual ao limiar não alerta.
- Medição do autor, M4 Pro, 22 inversões de B1: p95 de relógio de 376 ms, mediana de CPU de
  345 ms. Orçamento provisório: 700 ms.

Parecer da skill sobre `02c97e9` (SHA-256 `5337afec…f42d`), lido depois do veredito e antes
do merge: sem bloqueante; duas notas (classificação de um mutante no resumo automático e a
meta de tamanho).

Limite que fica registrado: a demo mista tem uma única linha americana suportada, call sem
rendimento. Nela o prêmio de exercício antecipado é zero. O caso em que o segundo motor
acrescenta informação (call com rendimento não compensado) é exercitado só por testes com
registro sintético alterado, não pela fixture publicada.

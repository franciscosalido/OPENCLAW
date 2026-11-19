# DL2-PR04 — Referência independente, grade de invariantes e fechamento do Marco 2A

Estado: **SPEC_PRONTA** (Claude, 2026-11-19). Autoridade: ADR-0025 e `SDD_FASE2A.md`,
critérios 3, 4, 7, 8, 9 e 10, com os dois adendos que acompanham este cartão.
Base: `main` em `1dc7760595d29f8e867b0b54124e29ec7f926915`.
Branch: `feat/dl2-pr04-reference-invariants`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Como usar: o primeiro commit do branch traz seis cópias de `reports/fase02/dl2-pr04/`, sem
alteração de um byte, e mais nada.

```sh
SRC=reports/fase02/dl2-pr04
FIX=tests/fixtures/derivatives/reference
cp $SRC/DL2-PR04_CARD.md docs/specs/derivatives/fase2/DL2-PR04.md
printf '\n' >> docs/specs/derivatives/fase2/SDD_FASE2A.md
cat $SRC/SDD_FASE2A_ADENDO_2.md >> docs/specs/derivatives/fase2/SDD_FASE2A.md
printf '\n' >> docs/ADR/ADR-0025-laboratorio-derivativos-fase2a.md
cat $SRC/ADR-0025_ADENDO_1.md >> docs/ADR/ADR-0025-laboratorio-derivativos-fase2a.md
cp $SRC/crr_american_reference.json $SRC/crr_american_reference.sha256 \
   $SRC/crr_reference_generator.py $FIX/
```

SHA-256 dos cinco arquivos que acompanham o cartão:

```text
916fede14714a4c7266d7a589df02f1e12a563016ee6e1d8b41b6a5016162ab7  SDD_FASE2A_ADENDO_2.md
42ae4d7aaa1b52b91f50227944b14eb1e6f8ed4769a2cdad9bc36c1381f78b7d  ADR-0025_ADENDO_1.md
04fbaa7c5bd00e2bfabd52176be0a54a7ba8ddfc4d0892e50d74fec17201d135  crr_american_reference.json
a26a6973c8c9635378dcb15098c9d8f6fef87b72e250ea3303d54d075bd4a461  crr_american_reference.sha256
4d8f7eef3151a036cd4d4cd5f8dffaeb5e0fde3f1599aa5d2f9cab6f30d922a0  crr_reference_generator.py
```

As evidências entram abaixo do cartão, em seções novas.

## Objetivo

Fechar o Marco 2A com prova e sem tocar em produção. São quatro provas: os preços do
binomial batem com uma referência escrita por outro agente e com outra aritmética; as
desigualdades e igualdades que todo preço americano tem de obedecer valem numa grade de
milhares de pontos; os testes novos derrubam, sozinhos, os sete erros clássicos de árvore; e
o custo de um preço fica medido no Mac para a decisão de NumPy no Marco 2B.

## Escopo

| Arquivo | Quem escreve | O que entra |
|---|---|---|
| `tests/fixtures/derivatives/reference/crr_american_reference.json` | Claude | cópia |
| `tests/fixtures/derivatives/reference/crr_american_reference.sha256` | Claude | cópia |
| `tests/fixtures/derivatives/reference/crr_reference_generator.py` | Claude | cópia |
| `tests/unit/derivatives/test_binomial_validation.py` (novo) | Codex | testes T1 a T7 |
| `docs/specs/derivatives/fase2/DL2-PR04.md` | os dois | este cartão e as evidências |
| `docs/specs/derivatives/fase2/SDD_FASE2A.md` | Claude | só o Adendo 2, no fim |
| `docs/ADR/ADR-0025-laboratorio-derivativos-fase2a.md` | Claude | só o Adendo 1, no fim |
| `docs/04_MEM/current_state.md` | Codex | só o bloco "Fase 02 — Marco 2A" |

**Produção: zero linha.** Nenhum arquivo de `backend/`, `config/` ou `scripts/` muda. Os
testes já existentes também não mudam: `tests/unit/derivatives/test_binomial.py` e
`tests/architecture/` ficam idênticos à base. Zero dependência nova.

## Não-objetivos

- Alterar `binomial.py`. Isso inclui a simplificação de `crr_parameters` sugerida no piloto
  da skill: ela continua sendo sugestão para outro PR.
- Editar a referência ou o gerador. Se um caso parecer errado, o autor para e avisa no PR.
  Não corrige, não regenera com outra lista, não ajusta tolerância.
- Comparar a americana com o modelo contínuo, extrapolar (Richardson), suavizar a árvore ou
  trocar a parametrização. Nada disso é critério do marco.
- Ligar o binomial à chain, ao MCP, ao CLI ou a `PricingModel`.
- Decidir NumPy ou otimizar. Este PR só mede (L4 do ADR-0025).
- Instalar ferramenta de mutação. Os mutantes são aplicados à mão, em cópia temporária.
- Teste que afirma tempo de execução. Tempo é registrado, não é condição de aprovação.

## A referência

`crr_american_reference.json` traz 42 casos. Cada caso tem o preço europeu e o americano da
**árvore CRR finita** de `steps` passos, mais `up`, `prob_up` e `discount` da mesma árvore.
Não é o preço do modelo contínuo (Adendo 2 do SDD, item B1).

Como foi gerada, em uma frase: indução retroativa por níveis em `decimal` com 60 dígitos,
partindo do valor binário exato que a produção recebe, com uma exponencial própria para o
preço de cada nó; 20 dígitos publicados, todos confirmados refazendo a conta com 90 dígitos;
a europeia ainda é conferida contra a soma binomial fechada de `N + 1` termos. O método e a
precisão estão declarados no campo `metadata` do próprio arquivo.

Campos de cada caso: `case_id`, `group`, `kind` (`call` ou `put`), `S`, `K`, `r_cont`, `q`,
`sigma`, `T_years` (textos que são o `repr` do `float` de entrada), `steps` (inteiro), `up`,
`prob_up`, `discount`, `european_price`, `american_price` (textos com 20 dígitos).

| Grupo | Casos | O que cobre |
|---|---:|---|
| `hull` | 5 | put de Hull, `S = K = 50`, 5 meses, com 5, 30, 50, 100 e 500 passos |
| `call_yield` | 10 | call com rendimento; inclui exercício já na raiz e um caso sem prêmio |
| `put_rate` | 10 | put com taxa positiva; inclui exercício na raiz, `q > r`, volatilidade 100% |
| `negative_rate` | 5 | três calls com prêmio de exercício e duas puts sem prêmio |
| `no_premium` | 3 | call com `q = 0` e `r >= 0`, onde americana e europeia coincidem |
| `scale_and_tenor` | 5 | `S = 0.5` e `S = 10000`, um dia útil, cinco anos, volatilidade 5% |
| `small_trees` | 4 | árvores de 1, 2, 3 e 4 passos |

São 20 calls e 22 puts. Em 35 casos a americana é estritamente maior que a europeia; 16
deles são calls. Nos outros 7 as duas coincidem nos 20 dígitos publicados: `crr_14`,
`crr_29`, `crr_30`, `crr_31`, `crr_32`, `crr_33` e `crr_39`. Três casos têm exercício ótimo
já na raiz, com americana igual ao intrínseco: `crr_13`, `crr_21` e `crr_28`.

Tolerâncias, com o que foi medido contra a produção em `1dc7760` antes de este cartão sair:

| Grandeza | Tolerância | Maior desvio medido |
|---|---|---|
| `european_price`, `american_price` | `1e-11 * max(1, abs(ref))` | 1.8e-13 |
| `prob_up` | `1e-11 * max(1, abs(ref))` | 7.9e-15 |
| `up`, `discount` | `1e-14 * max(1, abs(ref))` | 1.1e-16 |

A comparação é feita em `Decimal`, sem passar a referência para `float`:

```python
abs(Decimal(obtido) - Decimal(texto)) <= Decimal(limite) * max(Decimal(1), abs(Decimal(texto)))
```

## Testes exigidos

Todos em `tests/unit/derivatives/test_binomial_validation.py`. Os nomes são livres; o que
cada um prova, não.

**T1. O arquivo é o entregue.** O SHA-256 dos bytes do JSON é
`04fbaa7c5bd00e2bfabd52176be0a54a7ba8ddfc4d0892e50d74fec17201d135`, escrito como constante
no teste. O conteúdo de `crr_american_reference.sha256` é esse valor, dois espaços,
`crr_american_reference.json` e uma quebra de linha.

**T2. A referência se regenera.** O teste carrega `crr_reference_generator.py` pelo caminho
do arquivo, chama `build_document()` e compara `.encode("utf-8")` com os bytes do JSON:
iguais. Custa cerca de 3 s. É o que impede edição manual da referência.

**T3. Forma.** 42 casos, `metadata["casos"] == 42`, `case_id` sem repetição. Para os seis
campos de entrada, `repr(float(texto)) == texto`. As contagens do parágrafo acima: 20 calls,
35 com americana maior (16 calls) e a lista exata dos 7 casos de igualdade.

**T4. Preços.** Um teste por caso, com `case_id` no identificador. `crr_price` com estilo
americano e com estilo europeu, cada um dentro da tolerância da tabela.

**T5. Parâmetros.** Um teste por caso: `crr_parameters` devolve `up`, `prob_up` e `discount`
dentro das tolerâncias da tabela.

**T6. Âncora publicada.** Na árvore de `crr_01` (5 passos), formatados com quatro casas:
`up = 1.1224`, `down = 0.8909`, `prob_up = 0.5073` e
`prob_up * (up - down) + down = 1.0084`. Com cinco casas, `T_years / 5 = 0.08333`. Com duas,
`50.0 * down**3 = 35.36`. São os números que Hull imprime para essa árvore.

**T7. Grade.** `S = 100` e o produto cartesiano abaixo, 2.880 pontos:

```text
tipo    call, put
K       60, 85, 100, 115, 140
sigma   0.011, 0.12, 0.3, 0.7
T       0.05, 0.5, 2.0
r       -0.03, 0.0, 0.05, 0.13
q       0.0, 0.04, 0.10
N       50, 51
```

Em cada ponto, `crr_parameters` uma vez e `tree_price` duas vezes na mesma árvore, americana
e europeia. A árvore é admissível quando `abs(r - q) * sqrt(T / N) < sigma`; nenhum ponto da
grade fica a menos de 9% dessa fronteira.

- Ponto inadmissível: tem de levantar `BinomialRefusal` com `probability_out_of_range`.
- Ponto admissível: tem de devolver número. Qualquer outra exceção, em qualquer ponto,
  reprova o teste.

Nos pontos admissíveis, com `tol(x) = 1e-11 * max(1.0, x)`:

| Nº | Onde | Afirmação |
|---|---|---|
| G1 | todos | finito e `americana >= europeia >= 0.0`, sem tolerância |
| G2 | todos | `americana >=` intrínseco na raiz, sem tolerância |
| G3 | call, `q == 0`, `r >= 0` | `abs(americana - europeia) <= tol(europeia)` |
| G4 | put, `r <= 0` | `abs(americana - europeia) <= tol(europeia)` |
| G5 | call, `q == 0`, `r < 0`, `K <= 85`, `sigma >= 0.12` | `americana - europeia > 0.01` |
| G6 | `r >= 0` | simetria, americana e europeia, com `tol` do preço original |

G6: o ponto simétrico troca o tipo, tem `spot = K`, `strike = 100.0`, `rate_cont = q` e
`dividend_yield = r`, com os mesmos `sigma`, `T` e `N`.

O teste conta e afirma os totais: 2.880 pontos, **2.740 precificados** e 140 recusados; G3
em 340 pontos, G4 em 680, G5 em 36 e G6 em 2.080. Sem os contadores, um filtro errado
deixaria uma invariante sem ponto nenhum e o teste passaria vazio.

Medido pelo revisor na base: maior desvio em G3 e G4, 4.8e-15; em G6, 5.6e-13; menor prêmio
em G5, 0.0246. A grade inteira roda em cerca de 1 s.

Por que G6 vale na nossa árvore, em um passo e com `u * d = 1`: `max(S*u - K, 0)` é
`u * max(S - K*d, 0)`, e `exp(-r*dt) * p * u` é igual a `exp(-q*dt) * (1 - p')`, em que
`p'` é a probabilidade com `r` e `q` trocados. O ramo de alta da call vira o ramo de baixa
da put simétrica, e o mesmo vale para o outro ramo. O revisor conferiu o passo único à mão e
o caso geral na grade; não há demonstração formal completa neste cartão.

## Mutação

Este PR não muda produção, então não há RED de implementação. O papel do RED é dos mutantes:
cada teste novo tem de falhar quando o código está errado.

O autor aplica um por vez em cópia temporária de `binomial.py`, roda **só** o arquivo de
teste novo e registra quantos testes falham e quais afirmações. Mínimo: os sete mortos. No
fim, um controle sem alteração passa inteiro e `git status` está limpo.

| Nº | Item do SDD | Troca de uma linha em `binomial.py` |
|---|---|---|
| M1 | 1 | `american = style is ExerciseStyle.AMERICAN` vira `american = False` |
| M2a | 2 | a continuação perde o fator `tree.discount` |
| M2b | 2 | `math.exp(-rate_cont * dt)` vira `math.exp(-(rate_cont - dividend_yield) * dt)` |
| M3 | 3 | na continuação, `prob_up` e `prob_down` trocam de lugar |
| M4 | 4 | `sign = 1.0 if ... else -1.0` vira `sign = -1.0 if ... else 1.0` |
| M5 | 5 | `if american:` vira `if american and rises + k == tree.steps - 1:` |
| M6 | 6 | `if american:` vira `if american and rises == 0 and k == 0:` |

O que o protótipo do revisor viu, para o autor comparar. Casos de T4 que falham, de 42: M1,
35; M2a, 41; M2b, 18; M3, 42; M4, 42; M5, 34; M6, 32. T7 falha nos sete. M2b derruba também
18 casos de T5. Número diferente não é erro por si só; mutante vivo é.

O revisor roda a própria lista, sem reaproveitar a do autor.

## Portabilidade

Mesma contagem de testes em macOS e em Linux, em clone limpo. Em cada plataforma, a partir
da raiz do clone:

```sh
python - > precos_hex.txt <<'EOF'
import hashlib
import json
import platform
import sys
from pathlib import Path

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.binomial import crr_price

path = Path("tests/fixtures/derivatives/reference/crr_american_reference.json")
lines = []
for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
    common = dict(
        kind=OptionKind.CALL if case["kind"] == "call" else OptionKind.PUT,
        spot=float(case["S"]), strike=float(case["K"]), time_years=float(case["T_years"]),
        rate_cont=float(case["r_cont"]), sigma=float(case["sigma"]),
        dividend_yield=float(case["q"]), steps=case["steps"])
    european = crr_price(style=ExerciseStyle.EUROPEAN, **common)
    american = crr_price(style=ExerciseStyle.AMERICAN, **common)
    lines.append(f"{case['case_id']} {european.hex()} {american.hex()}")
text = "\n".join(lines) + "\n"
sys.stdout.write(text)
sys.stderr.write(f"{platform.system()} {platform.machine()} {platform.python_version()} "
                 f"{hashlib.sha256(text.encode()).hexdigest()}\n")
EOF
```

O revisor obteve o mesmo SHA-256 em Linux x86_64 (Python 3.13.18) e em Linux aarch64
(Python 3.12.16): `773a2bcdf3a122bd6662cb4f6e5b26c015106e63b886f43e716243fcee418ef1`.

Se o macOS der o mesmo valor, a diferença entre plataformas é zero e basta registrar a linha
de `stderr`. Se der outro, não é reprovação: o autor cola as linhas que diferem e a maior
diferença relativa. O limite é `1e-9`, e T4 já garante `2e-11`.

## Medição

No Mac, em macOS (não em máquina virtual), a partir da raiz do clone, com a máquina sem
outra carga pesada:

```sh
python - <<'EOF'
import platform
import statistics
import sys
import time

from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing.binomial import crr_price

common = dict(kind=OptionKind.PUT, style=ExerciseStyle.AMERICAN, spot=100.0, strike=100.0,
              time_years=1.0, rate_cont=0.05, sigma=0.2, dividend_yield=0.0)
sys.stdout.write(f"{platform.platform()} {platform.machine()} {platform.python_version()}\n")
for steps, runs in ((1000, 7), (5000, 3)):
    seconds = []
    for _ in range(runs):
        start = time.perf_counter()
        price = crr_price(steps=steps, **common)
        seconds.append(time.perf_counter() - start)
    sys.stdout.write(f"N={steps} preco={price!r} mediana={statistics.median(seconds):.4f}s "
                     f"minimo={min(seconds):.4f}s execucoes={runs}\n")
EOF
```

O autor cola a saída inteira. Os preços servem para conferir que a conta medida é a certa:
em Linux saíram `6.089595282977972` com `N = 1000` e `6.090219408091187` com `N = 5000`.

Para comparação, sem valor de aceite: na máquina virtual Linux aarch64 do mesmo Mac, Python
3.12.16, a mediana foi 0.047 s com `N = 1000` e 1.24 s com `N = 5000`.

## Conferência deste cartão

Antes de entregar, o revisor escreveu um protótipo dos sete testes e executou tudo o que
este cartão afirma contra a produção em `1dc7760`. O protótipo não acompanha o cartão.

- 89 testes, 0 falha. Com eles, o portão completo em Linux aarch64 limpo deu 9.183
  aprovados, 16 pulados e 261 subtestes.
- A referência saiu idêntica byte a byte em três ambientes: Python 3.12.3 e 3.13.18 em
  x86_64, e Python 3.12.16 em aarch64. O gerador passa em `mypy --strict`.
- 16 mutantes mortos só com o arquivo novo: os sete da tabela e mais nove, entre eles sem
  exercício na raiz, intrínseco do nó vizinho, `dt = T / (N + 1)` e desconto multiplicado
  por `1 + 1e-10`. Este último mostra que a referência enxerga erro relativo de 1e-10.

Medição do revisor, sem critério de aceite, para orientar o Marco 2B. Call americana,
`S = 100`, `N = 200`, 60 combinações de `K` (70 a 110), `sigma` (15%, 25%, 40%) e prazo (um
mês a um ano), para cada par de taxa e rendimento:

| `r` | `q` | Combinações com prêmio | Maior prêmio de exercício antecipado |
|---|---|---:|---|
| 13% | 2% | 5 de 60 | 0.00001 |
| 13% | 6% | 34 de 60 | 0.083, sobre um preço de 34.91 |
| 13% | 10% | 57 de 60 | 0.98, sobre um preço de 31.64 |
| 13% | 13% | 60 de 60 | 3.63, sobre um preço de 26.37 |

Leitura: com taxa de 13% ao ano e rendimento contínuo de até 6%, a call americana vale
praticamente o mesmo que a europeia. O exercício antecipado só pesa quando o rendimento
chega perto da taxa. O modelo é de rendimento contínuo; dividendo discreto pode mudar esse
quadro e está fora do marco. (medição do revisor em uma grade pequena; não é resultado de
mercado)

## Regressão e portão

Linha de base em `1dc7760`, Linux aarch64 limpo: 9.094 aprovados, 16 pulados, 261
subtestes. O PR só pode aumentar a contagem de aprovados.

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check 1dc7760 HEAD
git diff --exit-code 1dc7760 HEAD -- backend config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude
git diff --exit-code 1dc7760 HEAD -- tests/unit/derivatives/test_binomial.py \
    tests/architecture
git diff --name-status 1421116 HEAD -- backend config scripts
```

Os dois `--exit-code` têm de sair com rc 0. O último comando lista três adições e nenhuma
modificação: `series_terms.py`, `carry.py` e `binomial.py`.

Demo e CLI, comparados entre a base e a ponta na mesma plataforma:

```sh
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

A primeira saída é idêntica byte a byte à da base. A segunda devolve `LIVE_NOT_ACTIVATED`,
rc 3. A americana continua recusada na chain, no MCP e no CLI. Rodar em macOS e em Linux,
em clone limpo.

Regras do repositório, que valem para o arquivo de teste: anotação de tipos, docstring nos
testes como nos arquivos vizinhos, imports absolutos, linhas com até 100 colunas, nunca
`print`. Sem chamada real à OpLab, sem token, sem leitura de `.env`.

## Fechamento do marco

O autor acrescenta às evidências a tabela abaixo, com a coluna da prova preenchida para os
critérios deste PR. As linhas de PRs anteriores já vão indicadas; o revisor confere todas.

| Nº | Critério | Onde está a prova |
|---|---|---|
| 1 | Caso à mão | `DL2-PR03.md`, RED 1; `test_h1_american_put` |
| 2 | CRR europeu contra BSM | `test_european_bsm_and_parity`; Adendo 1, A1 |
| 3 | Referência independente | T1 a T6 deste PR |
| 4 | Invariantes em grade | T7 deste PR |
| 5 | Recusas do binomial | `test_binomial.py`; Adendo 1, A2 |
| 6 | Recusas de série e de carry | `DL2-PR01.md` e `DL2-PR02.md` |
| 7 | Regressão | portão deste PR; Adendo 2, B3 |
| 8 | Mutação | tabela de mutação deste PR |
| 9 | Portabilidade | contagens e SHA-256 das duas plataformas |
| 10 | Disciplina e medição | 215, 131, 153 e 0 linhas de produção por PR; saída da medição |

Em `current_state.md`, o autor põe "PR atual: DL2-PR04 — EM_REVISAO". O texto de marco
fechado é do revisor, no commit do parecer, e só com GO.

## Decisões deste cartão

Francisco pode vetar qualquer uma antes do primeiro teste.

1. **Quem gera a referência é Claude** (Adendo 1 do ADR-0025). O risco aberto em
   `current_state.md` pedia essa decisão; ela está tomada aqui e continua vetável.
2. **A referência é o preço da árvore finita, não o do modelo contínuo.** É a única
   comparação que admite tolerância de 1e-11. Contra o contínuo, o erro da put americana
   tem ordem `O((ln n)^a / n)` com constante desconhecida (Lamberton); qualquer tolerância
   seria escolhida depois de ver o resultado.
3. **Zero linha de produção.** Um PR de validação que também mexe no que valida perde o
   valor de prova.
4. **O digest sai do critério 7** (Adendo 2, B3). Entra a prova de arquivo inalterado.
5. **Sete mutantes, com a leitura do Adendo 2, B4.**
6. **Os preços de Hull para 5, 30, 50, 100 e 500 passos, citados na revisão do #144, ficam
   fora do arquivo versionado.** A referência reproduz os cinco (4.49, 4.263, 4.272, 4.278
   e 4.283), mas a busca de hoje só alcançou a página com os parâmetros da árvore de 5
   passos. Entra como âncora só o que foi lido na fonte.
7. **O gerador mora ao lado do JSON, como `.py` de verdade.** Assim T2 consegue executá-lo.
   Ele não importa nada do QUIMERA e a guarda de isolamento não o alcança.

## Fora deste PR, com dono

| Item | Dono | Onde |
|---|---|---|
| Simplificação de `crr_parameters` (piloto da skill, S1) | Codex | próximo PR que tocar o módulo |
| Ponte com a chain, valor de `PricingModel`, pontos cegos da guarda | a definir | Marco 2B |
| Erro da americana contra o modelo contínuo e escolha de `N` | a definir | SDD do Marco 2B |
| Decisão de NumPy, com a medição deste PR | Francisco | ADR do Marco 2B (L4) |
| Documento da B3 sobre ajuste de strike em ETF | Francisco | L5 |
| Branches remotos antigos e proteção da `main` | Francisco | GitHub |

## Entrega

PR em rascunho, com a base e o SHA do head na descrição, as contagens do portão nas duas
plataformas e as evidências no cartão. O autor não integra.

Piloto da skill `quimera-lab-review`, em paralelo e às cegas. Uma sessão nova do Codex, sem
o contexto da implementação, roda `reports/fase02/quimera-lab-review/SKILL.md` sobre o PR,
somente leitura. O parecer vai para `reports/fase02/piloto_skill/DL2-PR04_parecer_skill.md`
e não entra no Git. Na descrição do PR entra só o SHA-256 desse arquivo. Claude não abre o
parecer antes de publicar o próprio GO ou NO-GO; a comparação vem depois.

## Base bibliográfica

O rótulo entre parênteses diz o peso da fonte.

- Cox, Ross e Rubinstein (1979), *Option Pricing: A Simplified Approach*, Journal of
  Financial Economics 7(3), 229–263. A árvore e a probabilidade neutra ao risco. (artigo
  original)
- Hull, *Risk Management and Financial Institutions*, apêndice F. Put americana de 5 meses,
  `S = K = 50`, taxa 10%, volatilidade 40%, 5 passos: `dt = 0.08333`, `u = 1.1224`,
  `d = 0.8909`, `a = 1.0084`, `p = 0.5073` e o nó de preço 35.36. (livro-texto; números lidos
  hoje na edição online; a página não traz o valor da opção na raiz)
- McDonald e Schroder (1998), *A parity result for American options*, Journal of
  Computational Finance. No movimento browniano geométrico, a call com `(S, K, r, q)` vale o
  mesmo que a put com `(K, S, q, r)`, europeia ou americana. (revisado por pares; lido só o
  resumo)
- *The Binomial Tree Method and Explicit Difference Schemes for American Options with Time
  Dependent Coefficients*, arXiv:1505.04573, teorema 6.1. A mesma simetria em árvore
  binomial. (arXiv; lido só o trecho devolvido pela busca; a árvore deles capitaliza por
  passo com `1 + r * dt`, diferente da nossa, por isso G6 foi conferida à parte)
- Healy (2021), *Pricing American options under negative rates*, arXiv:2109.15157. Regiões
  sem exercício antecipado usadas em G3 e G4. (arXiv; não conferi se houve publicação com
  revisão por pares; as regiões foram conferidas numericamente na grade)
- Lamberton (2018), *On the binomial approximation of the American put*, arXiv:1802.05614.
  Erro da put americana em `O((ln n)^a / n)`. Motivo da decisão 2. (arXiv; o registro indica
  publicação em Applied Mathematics and Optimization)
- Documentação do módulo `decimal` do Python: `exp` e `sqrt` são corretamente arredondadas
  com `ROUND_HALF_EVEN`. (documentação primária; conferida no texto de ajuda do interpretador)
- Manual de Procedimentos Operacionais de Negociação da B3, versão de 01/07/2026, itens
  3.2.9 e 3.3.1. SHA-256 do PDF:
  `35df8963b85b36774f431ae3c9b04c867a8ea7b863621307a45f3812e8b250ec`.

Quant Stack Exchange: a busca restrita ao site voltou vazia hoje, como na escrita do
DL2-PR03. Nenhuma afirmação deste cartão se apoia nele.

## Evidências do autor — 2026-11-19

**EM_REVISAO · estado A.** Base `1dc7760595d29f8e867b0b54124e29ec7f926915`,
especificação e referência em `5557d25b0a81932876cfc0a1cd3415ea6add2676`, testes
congelados em `487b694bc6fe9e2e45b85b73b863156f846bba88`. O commit dos testes acrescenta
somente `tests/unit/derivatives/test_binomial_validation.py`. Os resultados abaixo foram
obtidos nesta execução. Os logs ficam no Mac em `../evidencias-dl2-pr04/logs/`, a partir
da raiz deste clone.

### Referência e grade

O manifesto da entrega passou em `sha256sum -c SHA256SUMS.txt` (6/6). Nos dois sistemas,
T1 confirmou o SHA-256 dos bytes do JSON e a linha completa do arquivo de soma. T2
regenerou os mesmos bytes em memória. T3 confirmou os 42 identificadores distintos, a
representação das seis entradas e a distribuição de 20 calls, 22 puts, 35 prêmios positivos
(16 em calls) e sete empates nos identificadores prescritos.

T4 comparou 84 preços em `Decimal`. O maior erro dividido por `max(1, |referência|)` foi
`1.705874e-13` para a europeia (`crr_05_hull`) e `1.420966e-13` para a americana
(`crr_14_call_yield`). T5 aprovou as 126 comparações de parâmetros nos limites do cartão;
T6 reproduziu os seis números impressos para a árvore de Hull.

| Grade T7 | Pontos verificados |
|---|---:|
| Produto cartesiano | 2.880 |
| Admissíveis, com G1 e G2 | 2.740 |
| Inadmissíveis, todos com `probability_out_of_range` | 140 |
| G3, call sem rendimento e taxa não negativa | 340 |
| G4, put com taxa não positiva | 680 |
| G5, prêmio da call maior que 0,01 | 36 |
| G6, simetria nos dois estilos | 2.080 |

### Mutação e controle

No Mac, cada rodada partiu dos mesmos bytes de `binomial.py` em um clone temporário do
commit congelado. O diff de cada mutante tinha uma única substituição. Foi executado
somente `python -m pytest -q --tb=short tests/unit/derivatives/test_binomial_validation.py`,
com relatório JUnit por rodada. T4 conta os casos que violaram a tolerância de preço.
Em M2b, T5 falhou especificamente no desconto. A coluna T7 identifica a primeira asserção
que interrompeu a grade.

| Rodada | Falhas T4 | Falhas T5 | Falha T7 | Falhas / 89 | rc |
|---|---:|---:|---|---:|---:|
| M1 · sem exercício antecipado | 35 | 0 | G2, intrínseco na raiz | 36 | 1 |
| M2a · sem desconto | 41 | 0 | G6, simetria europeia | 42 | 1 |
| M2b · desconto com `r - q` | 18 | 18 | G6, simetria europeia | 37 | 1 |
| M3 · probabilidades trocadas | 42 | 0 | G6, simetria americana | 43 | 1 |
| M4 · sinais de call e put trocados | 42 | 0 | G2, intrínseco na raiz | 43 | 1 |
| M5 · exercício só no penúltimo nível | 34 | 0 | G2, intrínseco na raiz | 35 | 1 |
| M6 · exercício só na raiz | 32 | 0 | G5, prêmio maior que 0,01 | 33 | 1 |
| Controle final, módulo original | 0 | 0 | passou | 0 | 0 |

O controle final passou nos 89 testes e `git status --porcelain` devolveu saída vazia.
Em `logs/mutations/`, cada mutante tem seu patch, log e XML. O arquivo `results.json`
registra o SHA-256 do módulo em cada rodada, o comando, os identificadores dos testes
que falharam, as asserções e o estado final do clone.

### Gates, demos e portabilidade

A partir de clones limpos do commit congelado, os dois ambientes executaram
`python -m pytest tests/ -q --ignore=tests/integration --timeout=120`,
`python -m mypy backend/ --strict` e `pyright --venvpath <diretório-do-ambiente> backend/`.
O uv usou o ambiente já preparado com `--offline --frozen --no-sync --no-env-file`.
No Linux, os clones ficaram no sistema de arquivos do contêiner ARM64, com rede desativada.
Imagem local `openclaw-sandbox`, ID
`sha256:943825bb4a63ab6e0c7400dbee77cddeeb31ecd457b3366293b7c45d201ca7d8`.
O Click 8.4.1 já preparado foi montado para leitura e a versão ativa foi conferida contra o
lock. A versão do Python foi 3.12.13 em ambos.

| Verificação | macOS 15.8.1 arm64 | Linux aarch64 |
|---|---:|---:|
| uv / requisitos ativos conferidos | 0.12.1 / 102 | 0.11.20 / 104 |
| Arquivo T1–T7 | 89 aprovados | 89 aprovados |
| Suíte sem integração | 9.183 aprovados, 16 pulados | 9.183 aprovados, 16 pulados |
| Subtestes aprovados / falhas | 261 / 0 | 261 / 0 |
| Mypy estrito | 159 arquivos, 0 erros | 159 arquivos, 0 erros |
| Pyright | 0 erros, 0 avisos de análise | 0 erros, 0 avisos de análise |
| Demo BOVA11, base × testes (`cmp`) | rc 0, 67.097 bytes | rc 0, 67.101 bytes |
| CLI padrão, base e testes | `LIVE_NOT_ACTIVATED`, A, rc 3 | `LIVE_NOT_ACTIVATED`, A, rc 3 |

Os 89 testes novos explicam todo o aumento sobre a linha de base de 9.094 do cartão.
Os comandos do CLI da seção “Regressão e portão” foram executados de novo na base e na
ponta, em cada sistema. A demo sintética de 100 linhas teve SHA-256
`a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3` no Mac e
`f4f8003f2021b2744202c782f6e5245872c09d7f9d1968a3356466a7e85ead08` no Linux.

Em prova adicional nos dois sistemas, dez linhas da captura sintética receberam estilo
americano em memória. ChainService, tool MCP de demo (cliente em memória) e CLI offline
recusaram os mesmos dez símbolos com `american_not_supported_phase1`, preço, gregas e IV
nulos. As outras 90 linhas europeias continuaram suportadas. Saídas em
`logs/{mac,linux}/american.log`.

Saída de stderr do procedimento hexadecimal. A comparação direta dos arquivos com 42 pares
de preços também devolveu rc 0. A diferença máxima entre plataformas foi zero.

```text
Darwin arm64 3.12.13 773a2bcdf3a122bd6662cb4f6e5b26c015106e63b886f43e716243fcee418ef1
Linux aarch64 3.12.13 773a2bcdf3a122bd6662cb4f6e5b26c015106e63b886f43e716243fcee418ef1
```

`git diff --check 1dc7760 HEAD` e os dois `git diff --exit-code` do portão devolveram
rc 0. Desde `1421116`, o diff de `backend config scripts` listou três adições,
`domain/series_terms.py` (215 linhas), `domain/carry.py` (131) e `pricing/binomial.py`
(153), todas em `backend/derivatives/`. O DL2-PR04 acrescentou zero linha de produção.

### Medição nativa

Saída integral do procedimento de medição do cartão, no macOS, antes dos gates e mutações
do autor. Valores para a put americana sintética com `S = K = 100`. A decisão sobre NumPy
cabe ao Marco 2B.

```text
macOS-15.8.1-arm64-arm-64bit arm64 3.12.13
N=1000 preco=6.089595282977972 mediana=0.0468s minimo=0.0457s execucoes=7
N=5000 preco=6.090219408091187 mediana=1.2330s minimo=1.2283s execucoes=3
```

### Provas dos dez critérios do Marco 2A

| Nº | Critério | Onde está a prova |
|---|---|---|
| 1 | Caso à mão | `DL2-PR03.md`, RED 1 e `test_h1_american_put` |
| 2 | CRR europeu contra BSM | `test_european_bsm_and_parity` e Adendo 1 do SDD, A1 |
| 3 | Referência independente | T1–T6, regeneração byte a byte, 84 preços, 126 parâmetros e âncora de Hull |
| 4 | Invariantes em grade | T7, 2.740 pontos precificados e 140 recusas tipadas; contagens G1–G6 acima |
| 5 | Recusas do binomial | `test_binomial.py` e Adendo 1 do SDD, A2 |
| 6 | Recusas de série e de carry | `DL2-PR01.md` e `DL2-PR02.md` |
| 7 | Regressão | Gates, demos e recusas nos três caminhos nos dois sistemas; diff do Adendo 2, B3 |
| 8 | Mutação | Sete mutantes mortos pelo arquivo novo, controle final 89/89 |
| 9 | Portabilidade | Contagens iguais, 84 preços idênticos nas duas listas hexadecimais |
| 10 | Disciplina e medição | 215, 131, 153 e 0 linhas de produção por PR; medição nativa acima |

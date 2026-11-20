# DL2B-PR01A — Correção da ponte: entrada de tipo errado vira recusa, não exceção

Estado: **SPEC_PRONTA** (Claude, 2026-11-19). Autoridade: ADR-0026, `SDD_FASE2B.md` e o
cartão `DL2B-PR01.md`, seção "Ordem das conferências".
Base: `main` em `2132e104bde7c9ee397392a530efdd01a095a7d4`.
Branch: `fix/dl2b-pr01a-bridge-input-types`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Como usar: o primeiro commit copia este arquivo, sem alteração, de
`reports/fase02/dl2b-pr01a/DL2B-PR01A_CARD.md` para
`docs/specs/derivatives/fase2b/DL2B-PR01A.md`, e mais nada.

## O defeito

O cartão do DL2B-PR01 diz que tipo errado de `sigma` chega ao chamador como recusa do
binomial. Não é verdade para todo tipo errado. A ponte monta o eco antes de qualquer
conferência, e o eco só aceita `float` ou texto; um valor que não vira `float` derruba a
construção do próprio resultado de recusa.

Quem achou foi o piloto da skill de revisão. O revisor deu GO e integrou o #146 sem ver:
os ataques dele só usaram tipos válidos. Reproduzido em `2132e10`:

```text
entrada                 obtido                       esperado
sigma = 10**400         ValidationError              binomial:invalid_input_type
sigma = None            ValidationError              binomial:invalid_input_type
rate_cont = 10**400     ValidationError              binomial:invalid_input_type
rate_cont = None        ValidationError              binomial:invalid_input_type
steps = None            TypeError                    binomial:invalid_steps
steps = "a"             decimal.InvalidOperation     binomial:invalid_steps
spot = 100.0 (float)    AttributeError               american_bridge:invalid_spot_type
```

Gravidade: baixa. Nenhuma dessas entradas produz número, e nada em produção chama a ponte.
Mas é quebra de contrato, e o DL2B-PR04 vai ligar a ponte na chain.

## Escopo

| Arquivo | O que entra |
|---|---|
| `backend/derivatives/pricing/american_bridge.py` | a correção; meta de até 25 linhas a mais |
| `tests/unit/derivatives/test_american_bridge.py` | testes F1 a F5, só acréscimo |
| `docs/specs/derivatives/fase2b/DL2B-PR01A.md` | este cartão e as evidências |
| `docs/04_MEM/current_state.md` | só o bloco "Fase 02 — Marco 2B" |

Nenhum outro arquivo muda. Nenhum teste existente é editado ou removido.

## Não-objetivos

- Mudar preço, hipóteses, ordem das sete conferências ou qualquer resultado hoje correto.
- Validar tipo dentro do binomial: ele já recusa. A ponte só precisa não cair antes.
- Volatilidade implícita, configuração, ligação na chain.

## Contrato da correção

**Regra única: para qualquer valor de `spot`, `rate_cont`, `sigma`, `steps` e
`tte.year_fraction`, de qualquer tipo, a ponte devolve `PricingOutcome`. Nunca levanta.**

1. **Eco.** Cada um dos cinco campos numéricos do eco recebe o valor em `float` quando o
   argumento é exatamente do tipo esperado (`float` para `rate_cont`, `sigma` e prazo;
   `Decimal` para `spot`; `int` que não seja `bool` para `steps`) e a conversão não falha.
   Em qualquer outro caso recebe o texto `"invalid"`. Os resultados de hoje para entradas
   de tipo certo não mudam em nenhum byte.
2. **`spot` que não é `Decimal`.** Recusa nova, `american_bridge:invalid_spot_type`, na
   posição 7 da ordem, antes das chamadas ao binomial. Um `float` não é aceito como spot,
   mesmo que o binomial conseguisse calcular com ele.
3. **`steps` que não é `int` exato.** A ponte chama o binomial uma vez com o valor
   recebido e devolve a recusa dele (`binomial:invalid_steps`). Não tenta somar 1.
4. **`sigma`, `rate_cont` e prazo de tipo errado.** Seguem para o binomial como estão; a
   recusa dele (`binomial:invalid_input_type`) chega ao chamador.

A precedência das conferências 1 a 6 não muda: contrato europeu com `sigma = None`
continua devolvendo `american_bridge:not_american`.

Mudança visível no eco, e só para entrada de tipo errado: `sigma = 1` (inteiro) hoje ecoa
`1.0`; passa a ecoar `"invalid"`. O motivo da recusa não muda.

## Testes exigidos

**F1. A tabela do defeito**, uma linha por teste, com o motivo esperado, todos os campos
numéricos nulos, e o campo correspondente do eco igual a `"invalid"`.

**F2. Mais tipos.** `sigma` em `"0.2"`, `True`, `Decimal("0.2")`; `steps` em `True`, `2.5`,
`10**400`; `tte.year_fraction` em `None`; `spot` em `None` e `"100"`. Todos devolvem
recusa com o código da regra acima. `steps = 10**400` é `int`: eco `"invalid"` porque a
conversão falha, motivo `binomial:invalid_steps`.

**F3. Precedência preservada.** Contrato europeu com `sigma = None`: `not_american`. Carry
ausente com `spot = 100.0`: `carry:missing_carry_assumption`.

**F4. Nada mudou para tipo certo.** As âncoras A1 e A2 devolvem o mesmo `PricingOutcome`
de antes, comparado campo a campo com o valor registrado no cartão do DL2B-PR01.

**F5. Três lacunas apontadas pelo piloto, com a produção já correta:**

- lote ausente no contrato com fator divergente, e fator ausente com lote divergente:
  `american_bridge:series_terms_mismatch` nos dois;
- termos adulterados sem moeda, com carry ausente: `terms:unknown_currency`, e não
  `carry:missing_carry_assumption`;
- chamada sem o argumento `steps`: `TypeError` do Python, porque não existe padrão.

## RED exigido

Um RED por comportamento, com a saída colada: F1 na linha `sigma = 10**400`, falhando com
`ValidationError` no head atual.

## Mutação

Mínimo: 6 mortos, 0 sobrevivente. 1. eco sem proteção para `sigma`; 2. idem para
`rate_cont`; 3. `float` aceito como spot; 4. `steps + 1` calculado antes de conferir o
tipo; 5. `bool` aceito como `steps` no eco; 6. recusa de spot antes da de carry.

## Regressão e portão

Linha de base em `2132e10`, Linux aarch64 limpo: 9.245 aprovados, 16 pulados, 261
subtestes. O PR só pode aumentar a contagem.

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check 2132e10 HEAD
git diff --exit-code 2132e10 HEAD -- backend \
    ':(exclude)backend/derivatives/pricing/american_bridge.py'
git diff --exit-code 2132e10 HEAD -- config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude tests/fixtures tests/architecture
git diff 2132e10 HEAD -- tests/unit/derivatives/test_american_bridge.py | grep -c '^-[^-]'
```

Os dois `--exit-code` saem com rc 0 e o último comando imprime `0`. Demo offline idêntica
à da base e CLI padrão com `LIVE_NOT_ACTIVATED`, rc 3, em macOS e em Linux.

## Entrega

PR em rascunho; em `current_state.md`, "PR atual: DL2B-PR01A — EM_REVISAO". O autor não
integra. Revisão pela skill em outra sessão, sobre o head publicado. **Mudança de rito a
partir deste PR:** Claude forma o parecer sem ler o da skill, e só integra depois de ler.

## Evidências da implementação · EM_REVISAO

A cópia em `faa9ce15dcc726336ccafc1bee1d13900767458b` é idêntica à fonte local
(`cmp` rc 0, SHA-256 `bb08d27e92b2b635e35d1bfd8da657aca9022d14279d8f8d0988a8ad75a09ad4`).
Os critérios acima são os do cartão original.

### RED anterior à correção

`a3d87f97a9f9277e9aa6305a1ea105329aeb4d46` acrescenta somente testes. No Mac, antes da
edição da ponte, a seleção F1–F5 teve 26 falhas e 11 aprovações. A reprodução em clone
limpo desse commit, com o mesmo `backend/` da base, deu rc 1 para o caso exigido.

```sh
python -m pytest -q 'tests/unit/derivatives/test_american_bridge.py::test_f1_bad_input[sigma-huge]'
```

Trechos da saída de `mac/red-commit.log`:

```text
reason = 'binomial:invalid_input_type'
```

```text
E       pydantic_core._pydantic_core.ValidationError: 2 validation errors for PricingOutcome
E       inputs_echo.sigma.float
E         Input should be a valid number [type=float_type, input_value=1000000000000000000000000...000000000000000000000000, input_type=int]
```

```text
backend/derivatives/pricing/american_bridge.py:59: ValidationError
=========================== short test summary info ============================
FAILED tests/unit/derivatives/test_american_bridge.py::test_f1_bad_input[sigma-huge]
1 failed in 0.14s
```

### GREEN e limites do contrato

`ad82f0149d48bcfb338756e6b683a42e5b589776` altera apenas a ponte. São 17 linhas
adicionadas, 3 removidas e crescimento líquido de 14. O eco só converte após comparar o
tipo por identidade. Isso evita acionar `__float__` ou igualdade de entradas e subclasses
hostis. O spot inválido é recusado após a conferência de identidade da série. O primeiro
CRR recebe os argumentos originais de taxa, volatilidade, prazo e passos. Só depois de seu
retorno a ponte avalia `steps + 1`.

- **F1 e F2.** Cada caso verifica o código, os campos nulos e o eco. Um teste observa a
  única chamada ao CRR com a própria subclasse de `int` recebida. Os ecos de floats NaN e
  infinitos continuam numéricos. O tratamento anterior de `Decimal("sNaN")` preserva o
  eco NaN e a recusa `binomial:non_finite_input`.
- **Exceção demonstrada à frase «tipo certo não muda em nenhum byte».** Na base,
  `float(Decimal(10**400))` ecoava `inf`. A conversão direta de `int` para `float`
  levanta `OverflowError`. Para esse caso seguiu-se o critério explícito F2, com eco
  `"invalid"` e o mesmo motivo `binomial:invalid_steps`. Ambos os resultados estão em
  `mac/ancoras.diff`.
- **F3.** Estilo, carry e divergência de termos conservam sua precedência. Quando mais de
  um argumento da árvore é inválido, vale a primeira recusa do binomial. Por exemplo,
  com `sigma=None` e `steps=None` juntos, ele devolve `binomial:invalid_input_type`.
  O motivo `invalid_steps` da regra 3 pressupõe que as verificações anteriores do CRR passem.
- **F4.** A1 e A2 comparam o `PricingOutcome` completo, campo a campo e em JSON. Preço e
  prêmio vêm da tabela do PR01. Os campos individuais das árvores, ausentes daquela
  tabela, foram obtidos da base. Os dois JSONs coincidiram byte a byte entre base e GREEN.
- **F5.** Os testes cobrem lote ausente com fator divergente e o inverso, moeda ausente
  junto com carry ausente, e a chamada pública sem o argumento obrigatório `steps`.

### Mutações no Mac

Sete clones do GREEN rodaram todos os testes da ponte. O controle limpo passou nos 83
testes. Cada um dos outros seis recebeu um único patch de produção. O diff dos testes de
cada cópia em relação ao GREEN saiu com rc 0.

| Mutação | Caso que a detectou | Falhas nos 83 testes |
|---|---|---:|
| 1 · eco de sigma sem proteção | `test_f1_bad_input[sigma-huge]` | 9 |
| 2 · eco de taxa sem proteção | `test_f1_bad_input[rate-huge]` | 3 |
| 3 · aceitar spot float | `test_f1_bad_input[float-spot]` | 1 |
| 4 · antecipar a soma de um passo | `test_f1_bad_input[steps-none]` | 5 |
| 5 · aceitar bool no eco de passos | `test_f2_echo_requires_exact_type[steps-bool]` | 1 |
| 6 · recusar spot antes de carry | `test_f3_first_refusal[carry]` | 6 |

Resultado agregado: **6 mortos, 0 sobreviventes**. Os patches, as saídas do pytest e a
tabela com SHA e rc por cópia ficam em `mutacoes/`.

### Portões e consumidores offline

Clones limpos da base `2132e10` e do GREEN `ad82f01` em cada SO, com Python 3.12.13.
O Mac usou o interpretador existente em `/Users/fas/projetos/OPENCLAW/.venv/bin/python`.
O Linux usou o runner aarch64 identificado no `support/linux-run` do PR01, com o git e o
Click cacheados e a imagem `sha256:943825bb4a63ab6e0c7400dbee77cddeeb31ecd457b3366293b7c45d201ca7d8`,
`--pull never` e `--network none`. O pyright recebeu o caminho para o ambiente existente.

| Prova | macOS arm64 | Linux aarch64 |
|---|---:|---:|
| pytest do cartão · aprovados / pulados / subtestes aprovados | 9.282 / 16 / 261 | 9.282 / 16 / 261 |
| Arquivo da ponte · aprovados | 83 | 83 |
| mypy strict · erros / arquivos | 0 / 160 | 0 / 160 |
| pyright · erros / avisos de análise | 0 / 0 | 0 / 0 |
| Demo · `cmp` base × GREEN no mesmo SO | rc 0 · 67.097 bytes | rc 0 · 67.101 bytes |
| CLI padrão na base e no GREEN | `LIVE_NOT_ACTIVATED` · rc 3 | `LIVE_NOT_ACTIVATED` · rc 3 |

A suíte ganhou 37 casos sobre os 9.245 da base. O teste da ponte ganhou 168 linhas por
apêndice. O contador de linhas removidas imprimiu `0`. O `diff --check` e os dois
`diff --exit-code` do cartão passaram. SHA-256 de cada par de demos idênticas:

- macOS · `a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`
- Linux · `f4f8003f2021b2744202c782f6e5245872c09d7f9d1968a3356466a7e85ead08`

No pai deste checkout, `evidencias-dl2b-pr01a/` reúne os logs por SO e commit em
`{mac,linux}/{green,final}/`, o RED reproduzido, as mutações e `SHA256SUMS.txt`.
Cada `gates.log` identifica o commit e a árvore testados. A publicação cabe ao coordenador.
Após a publicação, Claude forma seu parecer independente. Em seguida lê o parecer do
piloto feito em outra sessão, antes de decidir a integração.

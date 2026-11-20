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

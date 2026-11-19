# DL2-PR02 — Premissa de carry e trava de dupla contagem

Estado: **SPEC_PRONTA** (Claude, 2026-11-19). Autoridade: ADR-0025 e `SDD_FASE2A.md`, critério 6.
Base: `main` em `b4238179de156df7e38a6e0f560d033737be19f6`.
Branch: `feat/dl2-pr02-carry-assumption`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Como usar este cartão: o primeiro commit do branch copia este arquivo, sem alteração, para
`docs/specs/derivatives/fase2/DL2-PR02.md`. As evidências (RED, GREEN, mutação, regressão) entram
abaixo dele, em seções novas. O texto da SPEC só muda por pedido registrado na revisão.

## Objetivo

Dado um registro de termos de série (`SeriesTerms`, do DL2-PR01) e uma premissa de carry
declarada, uma função pura devolve o rendimento contínuo `q` que um modelo pode usar, ou recusa
com motivo tipado. Nenhuma combinação devolve `q > 0` para série cujo strike é ajustado pela
bolsa, nem para série com política de ajuste desconhecida. Premissa ausente nunca vira `q = 0`.

"Carry" aqui é só o rendimento do ativo-objeto que entra no modelo como `q`. A taxa de juros
não faz parte deste PR.

## Escopo

| Arquivo | O que entra |
|---|---|
| `backend/derivatives/domain/carry.py` (novo) | modelos, recusas e a função `resolve_carry` |
| `tests/unit/derivatives/test_carry.py` (novo) | testes de contrato |
| `tests/architecture/test_series_terms_imports.py` | guarda por alcance (seção própria) |
| `docs/specs/derivatives/fase2/DL2-PR02.md` | este cartão e as evidências |
| `docs/04_MEM/current_state.md` | só o bloco "Fase 02 — Marco 2A" |

Produção nova: um arquivo, com meta de até 160 linhas (o teto do marco é 400). Zero dependência
nova. `series_terms.py` fica com diff zero. `carry.py` pode importar de lá os auxiliares de
validação (`_TermsModel`, `Text`, `_CivilDate`, `_input_type`, `_input_mapping`,
`_FIXED_DECIMAL`); o revisor conferiu que isso passa em `mypy --strict` e no `pyright`.

## Não-objetivos

- Ligar a premissa à chain, ao `ChainService`, ao MCP, ao CLI ou a qualquer adaptador.
- Tocar em `config/derivatives.yaml`, em `Conventions` ou em `pricing/`. A hipótese da Fase 01
  (`dividend_yield: 0.0` com `strike_adjusted_by_exchange_assumed: true`) segue valendo para as
  europeias, sem mudança de formato, de digest ou de motivo de recusa.
- Ler configuração dentro de `carry.py`. Nenhum valor de `q` vem de arquivo ou de padrão.
- Dar forma ao dividendo discreto (datas, valores). Ele é reconhecido e recusado, nada mais.
- Converter rendimento de outra capitalização para contínuo, ou estimar rendimento a partir
  de dados. Quem fornece a premissa já entrega o número contínuo.
- Unificar `TermsRefusal` e `CarryRefusal`, ou mexer na identidade da série (ISIN, vencimento).
- Adendo ao ADR-0025 sobre o manual da B3. É PR do Claude, separado.

## Contrato

### Tipos públicos de `carry.py`

**`CarryKind`** (`StrEnum`): `NONE`, `CONTINUOUS_YIELD`, `DISCRETE_DIVIDENDS`.

**`CarryRefusalCode`** (`StrEnum`), com os quatro motivos do SDD: `missing_carry_assumption`,
`dividend_double_count`, `strike_adjustment_unknown`, `discrete_dividends_not_supported`.

**`CarryRefusal`** (`Exception`): atributo `code`; a mensagem é só o valor do código, sem ecoar
dado de entrada. Mesmo molde de `TermsRefusal`.

**`CarryAssumption`**: registro imutável, com a mesma configuração de `SeriesTerms` (estrito,
congelado, `extra="forbid"`, revalidação de instâncias, cópia com atualização revalidada).

| Campo | Tipo em Python | Em JSON | Regra |
|---|---|---|---|
| `symbol` | `str` | texto | código da série a que a premissa se aplica |
| `effective_on` | `date` civil | `AAAA-MM-DD` | data em que a premissa é aplicada |
| `source` | `str` | texto | de onde veio a premissa; não vazio |
| `kind` | `CarryKind` | texto | obrigatório |
| `dividend_yield` | `Decimal` ou ausente | texto decimal fixo | ver abaixo |

`dividend_yield` é o rendimento contínuo anualizado, em fração decimal (`0.03` é 3% ao ano), na
mesma base de tempo de `T` (`business_252`). Com `kind = NONE` o campo tem de estar ausente ou
nulo. Com `kind = CONTINUOUS_YIELD` ele é obrigatório e fica em `0 < q < 1`, finito. O limite
superior existe para barrar percentual informado no lugar da fração (`3` em vez de `0.03`).

**`ResolvedCarry`**: resultado imutável de `resolve_carry`, com `terms` (a cópia revalidada dos
termos), `assumption` (a cópia revalidada da premissa), `dividend_yield: float` e o método
`assumptions()`.

### `resolve_carry(terms, carry) -> ResolvedCarry`

Os dois parâmetros são obrigatórios e nenhum tem valor padrão. Passos, nesta ordem:

1. Revalida os termos com `SeriesTerms.model_validate(terms)`. Recusa ou erro dos termos sai
   como veio do DL2-PR01, antes de qualquer avaliação de carry.
2. `carry is None` → `missing_carry_assumption`.
3. Revalida a premissa com `CarryAssumption.model_validate(carry)`.
4. `symbol` ou `effective_on` da premissa diferente dos termos → `missing_carry_assumption`.
   Premissa de outra série ou de outra data não é premissa para esta.
5. Aplica a matriz abaixo.

O `ResolvedCarry` devolvido carrega as cópias revalidadas. `terms` tem tipo exato `SeriesTerms`
e não é o objeto recebido.

### Matriz política de ajuste × premissa

| Política dos termos | `NONE` | `CONTINUOUS_YIELD` (`q > 0`) |
|---|---|---|
| `PROTECTED` | aceita, `q = 0.0` | recusa `dividend_double_count` |
| `UNPROTECTED` | aceita, `q = 0.0` | aceita, `q = float(dividend_yield)` |
| `UNKNOWN` | aceita, `q = 0.0` | recusa `strike_adjustment_unknown` |

`PROTECTED` quer dizer que a bolsa ajusta o preço de exercício por proventos. O provento já
está no strike; contá-lo também em `q` é a dupla contagem. A referência documental é o Manual
de Procedimentos Operacionais de Negociação da B3, versão de 01/07/2026, item 3.2.9, que trata
de opções sobre ações. ETF não aparece ali: BOVA11 segue `UNKNOWN` (L5 do ADR-0025).

### Recusas na construção de `CarryAssumption`

| Entrada | Resultado |
|---|---|
| chave `kind` ausente ou nula | `missing_carry_assumption` |
| `kind = DISCRETE_DIVIDENDS` | `discrete_dividends_not_supported` |
| `kind = CONTINUOUS_YIELD` sem `dividend_yield` (ausente ou nulo) | `missing_carry_assumption` |

Precedência entre recusas, de ponta a ponta: recusas dos termos (ordem do DL2-PR01) → premissa
`None` → `kind` ausente → dividendo discreto → rendimento ausente → série ou data divergente →
matriz. Quando uma condição de recusa tipada e um erro estrutural de outro campo aparecem na
mesma entrada, sai a recusa tipada. É o comportamento que `SeriesTerms` já tem.

### Erros estruturais (`ValidationError`, nunca número)

- `CONTINUOUS_YIELD` com rendimento `0`, negativo, `>= 1`, `NaN`, `sNaN` ou infinito.
- Rendimento em `float`, `int`, `bool` ou `str` no modo Python, inclusive com `strict=False`.
- `NONE` com rendimento informado, mesmo `Decimal("0")`. "Sem carry" tem uma grafia só.
- `kind` como texto no modo Python, inclusive com `strict=False`.
- Em JSON: rendimento como número, ou texto fora da gramática fixa (`"3e-2"`, `".03"`, `"+0.03"`).
- Chave extra (por exemplo `discrete_dividends`), `source` ausente ou em branco, data ausente,
  `datetime` no lugar de `date`.

### `ResolvedCarry.assumptions()`

Devolve exatamente estas cinco chaves, com valores `str` ou `float`:

| Chave | Valor |
|---|---|
| `carry_kind` | `"NONE"` ou `"CONTINUOUS_YIELD"` |
| `carry_dividend_yield` | o `float` usado como `q` |
| `carry_source` | a fonte da premissa |
| `carry_effective_on` | a data em ISO |
| `strike_adjustment_policy` | `"PROTECTED"`, `"UNPROTECTED"` ou `"UNKNOWN"` |

Nenhuma dessas chaves coincide com as de `pricing.conventions.model_assumptions`. O método só
monta o dicionário; ninguém o chama em produção neste PR.

## Guarda por alcance

A guarda do DL2-PR01 vê só import estático direto. Este PR fecha o alcance indireto, para os
dois módulos protegidos: `backend.derivatives.domain.series_terms` e
`backend.derivatives.domain.carry`. Regra: nenhum módulo de `backend/` ou de `scripts/` fora de
`backend/derivatives/domain/` alcança um dos dois.

1. **Estática, transitiva.** Grafo de imports estáticos de `backend/` e `scripts/`, com fecho
   transitivo. Importar `a.b.c` conta como importar também os `__init__.py` de `a` e de `a.b`.
   O relato continua no formato `caminho:linha` do import que inicia o caminho.
2. **Literal de import dinâmico.** Constante de texto com o caminho pontuado de um dos dois
   módulos, em arquivo fora de `domain/`, é ofensa. Vale também para docstring.
3. **Em execução.** Um interpretador novo, a partir da raiz do repositório, importa todos os
   módulos de `backend.derivatives` menos os dois protegidos. Ao fim, nenhum dos dois está em
   `sys.modules`.

Os 12 casos parametrizados que já existem continuam no arquivo, com a mesma expectativa.
Casos novos obrigatórios, em árvore sintética:

| Caso | Arranjo | Esperado |
|---|---|---|
| fachada | `domain/facade.py` importa os termos; `service/s.py` importa a fachada | ofende |
| pacote | `domain/__init__.py` importa os termos; `service/s.py` importa `domain.models` | ofende |
| dois saltos | fachada → `pricing/bridge.py` → `scripts/tool.py` | os dois de fora ofendem |
| carry direto | `service/s.py` importa `domain.carry` | ofende |
| literal | `mcp/s.py` chama `import_module` com o caminho de `carry` em texto | ofende |
| domínio puro | `domain/pure.py` importa `carry` | permitido |
| vizinho | `service/s.py` importa `domain.models`, com `__init__.py` vazio | permitido |

Caminho montado em tempo de execução (texto concatenado) passa pela estática e só é pego pela
verificação em execução se rodar no import. Fica registrado como limitação.

## Testes exigidos em `test_carry.py`

Igualdade exata em todos. Não há tolerância numérica neste PR.

1. **Matriz.** As 6 células da matriz, mais premissa `None` com cada política (3 recusas).
2. **Ausente não é zero.** Os seis caminhos de `missing_carry_assumption`: premissa `None`;
   sem `kind`; `kind` nulo; contínuo sem rendimento; série divergente; data divergente. Nenhum
   devolve objeto.
3. **Propriedade de segurança, em grade.** Para as 3 políticas × premissas válidas ×
   rendimentos `0.0001`, `0.03`, `0.5`, `0.9999`: existe `ResolvedCarry` com `q > 0` somente
   quando a política é `UNPROTECTED`; `q == 0.0` se e somente se `kind` é `NONE`.
4. **Estruturais.** Cada item da lista de erros estruturais, com o campo acusado conferido.
5. **Modo permissivo.** `model_validate(..., strict=False)` e
   `model_validate_json(..., strict=False)` não afrouxam tipo de `kind` nem de rendimento.
6. **JSON.** Ida e volta com igualdade; rendimento sai como texto decimal fixo; escala
   preservada (`0.0300` volta `0.0300`).
7. **Imutabilidade e cópia.** Atribuição falha; `model_copy(update=...)` revalida (trocar
   `kind` para contínuo sem rendimento recusa).
8. **Revalidação na entrada.** Termos feitos com `model_construct` (estilo `UNKNOWN`, sem lote,
   `PROTECTED` sem evidência), termos com `__dict__` adulterado e instância de subclasse:
   nenhum produz `ResolvedCarry` indevido, e o `terms` devolvido é `SeriesTerms` exato. O mesmo
   para premissa feita com `model_construct` (contínuo sem rendimento, discreto, rendimento 5).
9. **Precedência.** Termos sem lote com premissa `None` → `missing_contract_size`. Discreto
   com `symbol` inválido → `discrete_dividends_not_supported`. Contínuo sem rendimento com
   `symbol` inválido → `missing_carry_assumption`.
10. **Sem padrão.** `resolve_carry(terms)` levanta `TypeError`; a assinatura não tem valor
    padrão; `carry.py` não importa `config` nem `backend.derivatives.pricing` (teste por AST).
11. **Hipóteses.** Dicionário exato de `assumptions()` para `NONE` e para contínuo; chaves
    disjuntas das de `model_assumptions` da Fase 01.

## RED exigido

Dois RED por comportamento, com a saída colada neste cartão e o commit do RED identificado.
Falha de coleta ou `ImportError` não vale como RED.

1. Com esqueleto de `resolve_carry` que devolve resultado sem a trava: o teste de `PROTECTED`
   com `CONTINUOUS_YIELD` falha com `DID NOT RAISE CarryRefusal`.
2. Com a guarda do DL2-PR01 intacta: o caso "fachada" falha porque a guarda devolve lista vazia.

## Mutação

O autor aplica, uma por vez em cópia temporária, e registra as falhas de cada uma. Mínimo: 10
mutantes mortos, 0 sobrevivente.

1. remover a recusa de `PROTECTED`; 2. remover a de `UNKNOWN`; 3. trocar os dois códigos;
4. premissa `None` vira `NONE`; 5. contínuo sem rendimento vira `q = 0`; 6. pular a revalidação
dos termos; 7. pular a revalidação da premissa; 8. aceitar rendimento `0`; 9. aceitar rendimento
`>= 1`; 10. ignorar `symbol` divergente; 11. ignorar data divergente; 12. `NONE` aceitar
rendimento informado.

O revisor roda a sua própria lista, sem reaproveitar a do autor.

## Regressão e portão

Linha de base em `b423817`, Linux aarch64 limpo: 8.379 aprovados, 16 pulados, 261 subtestes.
O PR só pode aumentar a contagem de aprovados.

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check b423817 HEAD
git diff --numstat b423817 HEAD -- backend
git diff --exit-code b423817 HEAD -- backend ':(exclude)backend/derivatives/domain/carry.py'
git diff --exit-code b423817 HEAD -- config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude
```

Os dois últimos têm de sair com rc 0: produção da Fase 01 e `series_terms.py` intocados.

Demo e CLI, comparados entre a base e a ponta na mesma plataforma, como no cartão do DL2-PR01:

```sh
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

A primeira saída é idêntica byte a byte à da base (`cmp` rc 0). A segunda devolve
`LIVE_NOT_ACTIVATED`, rc 3. Rodar em macOS e em Linux, em clone limpo.

Regras do repositório que valem aqui: docstring em toda classe e função pública, anotação de
tipos, imports absolutos, linhas com até 100 colunas, `loguru` se houver log, nunca `print`.
Sem chamada real à OpLab, sem token, sem leitura de `.env`.

## Decisões deste cartão

Tomadas dentro do ADR-0025. Francisco pode vetar qualquer uma antes do RED.

- **D1.** Dividendo discreto entra como terceiro valor de `kind`, reconhecido e recusado. Não
  se define formato para algo que o marco não suporta.
- **D2.** Rendimento contínuo restrito a `0 < q < 1`. Zero explícito se escreve `NONE`.
- **D3.** Premissa de outra série ou data é tratada como premissa ausente.
- **D4.** `UNKNOWN` com `NONE` é aceito: o ADR só recusa `UNKNOWN` quando há dividendo > 0. A
  política viaja em `assumptions()` para o consumidor ver que o ajuste não está comprovado.
- **D5.** `UNPROTECTED` com `NONE` é aceito. É premissa declarada, com fonte e data, de que não
  há rendimento a considerar. Não é dupla contagem.
- **D6.** Exceção própria (`CarryRefusal`) e diff zero em `series_terms.py`.

## Fora deste PR, com dono

| Item | Dono |
|---|---|
| Hipótese `dividend_yield: 0.0` da Fase 01 virar premissa com fonte e data | PR da ponte (2B) |
| Autenticar a fonte e separar fixture de observação | primeiro PR que ligar a uma superfície |
| Abrir a guarda por alcance para a ponte | o mesmo PR, com revisão |
| Construção direta de `ResolvedCarry` contorna a trava | a ponte chama `resolve_carry` |
| Identidade da série sem ISIN nem vencimento | PR de cadastro de séries |
| Adendo ao ADR-0025 (itens 3.2.9 e 3.3.1 do manual) | Claude |
| Tolerância CRR × BSM do par 200/201 | adendo antes do GREEN do DL2-PR03 |

## Entrega

1. PR em rascunho contra `main`, com a descrição batendo com os números finais do cartão.
2. Bloco "Fase 02 — Marco 2A" do `current_state.md` em `PR atual: DL2-PR02 — EM_REVISAO`.
3. O autor não mergeia. O revisor revalida em clone limpo, roda a própria mutação e, com GO,
   faz o squash no GitHub e o avanço local (L2).

## Referências

- ADR-0025, seção "DL2-PR02 - premissa de carry", e L5.
- `SDD_FASE2A.md`, critérios 6, 7 e 10.
- `DL2-PR01.md`, seções "Contrato de entrada e persistência" (S2) e "Limitações aceitas".
- Manual de Procedimentos Operacionais de Negociação da B3, versão de 01/07/2026, itens 3.2.9
  e 3.3.1. SHA-256 do PDF conferido:
  `35df8963b85b36774f431ae3c9b04c867a8ea7b863621307a45f3812e8b250ec`.

## Evidências da implementação no macOS — 2026-11-19

A revisão começa na árvore de trabalho de `feat/dl2-pr02-carry-assumption`, sobre o RED 2.
A base é `b4238179de156df7e38a6e0f560d033737be19f6`. O primeiro commit,
`be150eb2f1c7c385a360679bb9d1a75ee6ef567f`, contém só a SPEC. Seus 16.628 bytes, incluindo a quebra de linha final, têm SHA-256
`51b0f32fda7d27717d6ac2ae33668af266a5fa8db12e5ccbbcb9e1527d6985c2`.
O cartão original de reports/fase02/ permanece intacto; as evidências estão abaixo.

### REDs anteriores à implementação

**RED 1 · `4ce0f2125449a6d9cb250ec453256d7cab94fea2`.**
O esqueleto devolvia um resultado para a combinação protegida com rendimento contínuo.
Trecho do log original `red-1.log`:

```text
tests/unit/derivatives/test_carry.py:44: in test_protected_refuses_continuous_yield
    with pytest.raises(CarryRefusal) as error:
E   Failed: DID NOT RAISE <class 'backend.derivatives.domain.carry.CarryRefusal'>
=========================== short test summary info ============================
FAILED tests/unit/derivatives/test_carry.py::test_protected_refuses_continuous_yield
1 failed in 0.06s
```

**RED 2 · `59509ae44ec7e2c197448ccc6ad3fe12e21d3a90`.**
O diff desse commit acrescenta apenas o teste da fachada à guarda do PR01.
Trecho do log original `red-2.log`:

```text
>       assert _offenders(tmp_path) == ["backend/derivatives/service/s.py:1"]
E       AssertionError: assert [] == ['backend/der...rvice/s.py:1']
E
E         Right contains one more item: 'backend/derivatives/service/s.py:1'
E         Use -v to get more diff

tests/architecture/test_series_terms_imports.py:67: AssertionError
```

O pytest registrou `1 failed in 0.02s`. Os dois SHAs permanecem ancestrais da candidata.

### GREEN e fronteiras do contrato

O único arquivo novo de produção tem 131 linhas. A função revalida primeiro os termos,
depois a premissa presente, confere série e data e só então aplica a matriz. As instâncias
devolvidas têm os tipos base exatos. Os testes cobrem construção sem validação, alteração de
`__dict__`, subclasses, precedência das recusas e conjunto exato de hipóteses da Fase 01 e 02.
A revalidação confere consistência. A autenticação da fonte cabe à futura ponte.

**Leitura conservadora de D2 para o revisor.** O intervalo aberto precisa valer também para o
`float` entregue ao motor. `Decimal("1e-1000")` é positivo e arredonda para `0.0`.
`Decimal("0.99999999999999999")` é menor que um e arredonda para `1.0`. Nos dois casos,
Python e JSON acusam `ValidationError` em `dividend_yield`, inclusive sob `strict=False`.
Os vizinhos interiores `math.nextafter(0.0, 1.0)` e `math.nextafter(1.0, 0.0)` são aceitos.
O registro conserva o Decimal original. O JSON de `Decimal("0.0300")` volta como `"0.0300"`.

A guarda estática propaga alcance pelos imports de `backend/` e `scripts/`, inclusive
`__init__.py` dos ancestrais, resoluções relativas e ciclos. O diagnóstico aponta a linha do
import inicial de cada consumidor. A prova em interpretador isolado bloqueia rede e tem
timeout de 60 s. Uma árvore sintética mostra que um nome montado ao inicializar o pacote pai
escapa da análise estática e é detectado em `sys.modules`. Caminhos calculados que só executam
após o import ficam fora da prova. O smoke, conforme a SPEC, importa todo o pacote exceto
os dois módulos protegidos: é deliberadamente mais estrito do que a análise estática.
Se surgir um consumidor legítimo apenas de domínio, poderá exigir rever esse smoke;
neste PR o teste e a regra do cartão permanecem inalterados.

### Mutação do autor

Controle original com 135 testes aprovados. Os 12 mutantes, um por execução, terminaram com
rc 1 e falha de teste identificada. A tabela usa as linhas do `carry.py` de SHA-256
`dc6e771582c162e624d6d29ff53dd67dc15499b224f76d7257deeeb6412b9d21`.
Para reproduzir, execute o controle abaixo numa cópia temporária da candidata. Em cada rodada,
substitua só a instrução indicada na tabela, conserve a indentação, repita o comando e restaure
o arquivo original antes da próxima rodada. Na rodada 4, a fonte sintética é `"mutante"`.

```sh
python -B -m pytest tests/unit/derivatives/test_carry.py -q --tb=line -p no:cacheprovider
```

| Nº | Alteração em carry.py | Falhas | Exemplo de teste que detectou |
|---:|---|---:|---|
| 1 | L127 → `pass` | 5 | `test_protected_refuses_continuous_yield` |
| 2 | L129 → `pass` | 4 | `test_policy_grid[0.0001-UNKNOWN]` |
| 3 | Permutar as instruções L127 e L129 | 9 | `test_protected_refuses_continuous_yield` |
| 4 | L120 → atribuir a `carry` premissa NONE com série e data dos termos | 3 | `test_absent_assumption` |
| 5 | L77 → `return Decimal("0")` | 5 | `test_frozen_models_and_revalidated_copy` |
| 6 | L118 → `pass` | 7 | `test_revalidate_constructed_terms` |
| 7 | L121 → `assumption = carry` | 6 | `test_revalidate_constructed_carry` |
| 8 | L88 → `if not 0 <= float(value) < 1:` | 6 | `test_python_field_errors` |
| 9 | L88 → `if not 0 < float(value):` | 9 | `test_python_field_errors` |
| 10 | L122 → comparar apenas a data | 1 | `test_mismatch_precedes_policy[updates0]` |
| 11 | L122 → comparar apenas a série | 1 | `test_mismatch_precedes_policy[updates1]` |
| 12 | L80 → `return None` | 3 | `test_none_has_no_yield` |

Resultado do autor: **12 mortos, 0 sobreviventes**. O diretório de logs entregue ao Dots
inclui o executor exato `verificacao-candidata/mutacao.py`, o controle `m00.log` e as doze
saídas `m01.log` a `m12.log`. A lista independente é responsabilidade do revisor.

### Regressão e entrega

macOS 15.8.1 arm64, Python 3.12.13, Pydantic 2.13.3. Os gates usaram os executáveis do
venv autorizado, com os proxies removidos. As comparações Git abaixo usaram a árvore de
trabalho contra a base porque o commit GREEN fica com Dots.

| Gate | Resultado | rc |
|---|---|---:|
| Pytest focal, contrato e arquitetura | 165 aprovados | 0 |
| Pytest global sem integração, timeout 120 s | 8.531 aprovados, 16 pulados, 261 subtestes | 0 |
| Mypy estrito em `backend/` | 158 arquivos, zero erros | 0 |
| Mypy estrito nos dois arquivos de testes | Zero erros | 0 |
| Pyright em `backend/` com o interpretador do venv explícito | Zero erros e avisos de análise | 0 |
| `git diff --check b423817` | Diff limpo | 0 |
| Diff da produção contra `b423817` excluindo `carry.py` | Vazio | 0 |
| Diff de config, scripts, dependências e arquivos protegidos | Vazio | 0 |

A contagem global aumentou em 152 sobre a base de 8.379. O Pyright sinalizou que o diretório
da cópia isolada carece da subpasta local `.venv`.

A demo sintética foi executada em três árvores na mesma plataforma: `11838cd` (antes do
PR01), `b423817` (base do PR02) e a candidata. As bases vieram dos objetos Git locais.
As três execuções com `--provider offline_fixture` deram rc 0 e stdout idêntico ao baseline
por `cmp` (67.097 bytes). SHA-256 da demo completa:
`a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`.
O CLI padrão devolveu `LIVE_NOT_ACTIVATED`, estado A, rc 3 nas três execuções.
O verificador do digest numérico histórico continua pendente no PR separado do Claude.

Os commits RED são preservados no ramo do PR. O autor publica apenas o draft;
Claude faz a revalidação independente e decide a integração.

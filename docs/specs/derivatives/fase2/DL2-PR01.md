# DL2-PR01 — Termos vigentes da série

Base `11838cdafae0e3de0ed339a2acca736f480967fb`, branch `feat/dl2-pr01-series-terms`.

## Correção da revisão do draft #142

Head revisado `f36f644ef08c96e5309cbb36d5e841c9c1f7fd1e`, árvore `e55d17c`.
Plano: congelar todos os casos no head, corrigir as fronteiras de entrada e cópia, publicar
a semântica no modelo e validar a leitura do próprio JSON. Repetir os gates macOS e a demo.

### RED observado antes de editar produção

Ambiente macOS arm64, Python 3.12.13, Pydantic 2.13.3. Para reproduzir os comandos abaixo,
usar o ambiente já instalado e executar a partir da raiz do clone. O shell usado foi zsh.

```sh
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY FTP_PROXY
unset http_proxy https_proxy all_proxy no_proxy ftp_proxy
export UV_PROJECT_ENVIRONMENT="$HOME/projetos/OPENCLAW/.venv"
export UV_CACHE_DIR="$(mktemp -d)" PYTHONDONTWRITEBYTECODE=1 UV_NO_ENV_FILE=1
u() { uv run --offline --no-sync "$@"; }
focal() {
  u python -m pytest tests/unit/derivatives/test_series_terms.py \
    -q --tb=short -p no:cacheprovider "$@"
}
```

- B1 — `focal -k b1`, rc 1, 13 falhas. Para os três exemplos do parecer,
  `DID NOT RAISE` ao promover UNKNOWN, inverter PROTECTED ou remover o lote.
  A cópia de evidência aceitou emissor inválido e a fronteira aceitou a instância inválida pronta.
- B2/I1 — `focal -k b2_unsupported_fatcot`, rc 1, uma falha. A entrada com FATCOT 100 lançou
  `TermsRefusal: missing_quotation_form`; o fator estava presente. Este é o RED de comportamento
  do recorte FATCOT. A parte documental tem verificação própria:
  `focal -k 'b2_policy_description or b2_public_docstrings'`, rc 1, duas falhas, incluindo
  `AssertionError: JSON Schema sem 'proventos': ''`. O teste de docstrings/largura é de contrato.
- B3 — `focal -k b3_json_round_trip`, rc 1, três falhas. O JSON de UNKNOWN produziu
  `Input should be a valid date [type=date_type]` e `strike deve ser Decimal finito`.
  Os casos PROTECTED e UNPROTECTED também rejeitaram as duas datas do documento.
- `focal`, rc 1, **47 falhas e 39 aprovações**. A contagem inclui contratos e controles que já
  passavam no head. O congelamento precede todas as correções de produção.

O primeiro congelamento ficou em `6078aac`. Na conferência das APIs públicas, o método
legado `copy` do Pydantic também devolveu uma instância com emissor inválido. A pilha de
entrega parte de um segundo commit exclusivamente de testes e cartão, filho de `6078aac`,
ainda com a produção idêntica a `f36f644`. Os 86 testes anteriores foram preservados.

- B1 complementar — `focal -k b1_legacy_copy`, rc 1, três falhas `DID NOT RAISE`.
  Foram aceitos lote nulo, emissor inválido e remoção do campo obrigatório por projeção.
  Houve três avisos de depreciação. Com os 89 testes congelados, `focal` devolveu rc 1,
  **50 falhas e 39 aprovações**. As correções foram reaplicadas depois desse registro.

### Decisões sobre os bloqueantes

- **B1 — cópia pública.** Nos dois modelos, `model_copy()` e `model_copy(update={})` criam
  outro registro. A cópia rasa compartilha a evidência imutável e `deep=True` a duplica.
  Uma atualização não vazia reconstrói o registro em modo Python, inclusive a evidência,
  para ambos os valores de `deep`. O construtor e a atualização revalidam inclusive instâncias
  prontas. Política e evidência podem mudar juntas se o novo registro for válido.
  O método legado `copy` delega à mesma validação e indica `model_dump` para projeções.
  O Pydantic confia nos dados de `BaseModel.model_copy(update=...)`. A garantia aqui cobre
  os caminhos públicos descritos com os modelos configurados. `model_construct`, chamadas
  diretas ao método da superclasse e escrita em atributos internos pressupõem um chamador
  confiável. A regra de propósito da Fase 01 sozinha deixaria o lote sem validação.
  [API BaseModel][pyd-base] · [implementação Pydantic 2.13.3][pyd-src].
- **B2 — política e fator.** PROTECTED significa ajuste do preço de exercício pela bolsa por
  proventos nesta fase. O manual de 01/07/2026, §3.2.9, p. 171, descreve a regra para opções
  referenciadas em ações. Sua aplicação a uma série exige comprovar classe e vigência.
  INDOPC 8 indica correção pelo IGP-M (layout rev. 02, p. 10). O rótulo Refer. Protected
  sozinho também é insuficiente. L5 exige identificação, versão e aplicabilidade do documento.
  FATCOT 1 e 1000, documentados na p. 6, são os dois fatores aceitos neste recorte.
  A cobertura de outros arquivos históricos depende do layout de cada época.
  [Layout COTAHIST][layout] · [Manual de negociação][manual].
- **B3 — persistência.** Usar `model_validate_json(t.model_dump_json())` tanto para UNKNOWN
  como para as duas políticas documentadas. Datas civis usam `AAAA-MM-DD`, enums usam seus
  valores textuais, lote/fator usam inteiros JSON e o strike usa texto decimal. A leitura
  preserva a tupla Decimal, inclusive zeros finais. O caminho Python estrito recebe objetos
  `date`, enums e `Decimal`, inclusive o resultado de `model_dump()`. Um dicionário de
  `model_dump(mode="json")` é recusado por `model_validate`. O chamador pode serializá-lo
  para a entrada JSON. [Strict mode][pyd-strict] · [API BaseModel][pyd-base].

### Pontos I1–I6 e condições de integração

| Ponto | Decisão e responsável |
|---|---|
| I1 | PR01 usa a primeira ausência na ordem lote, fator, estilo, moeda. Ver códigos abaixo. |
| I2 | PR01 aceita mapping (incluindo somente leitura) e objeto JSON nas duas fronteiras. |
| I3 | PR01 exige publicação até a vigência, inclusive, e correspondência exata da data. |
| I4 | PR de cadastro/coleta de séries, dono da integração, resolve a identidade longitudinal. |
| I5 | PR01 trava imports estáticos em todo o pacote de produção `backend`, por AST. |
| I6 | PR01 cobre imutabilidade, extras, precedência, fator e strike com testes tipados. |

Em I1/I2, chave ausente ou nula resulta em `missing_contract_size`, `missing_quotation_form`,
`unknown_exercise_style` ou `unknown_currency`. O sentinela de estilo UNKNOWN dá o mesmo
código do estilo ausente. Valor presente fora do tipo ou domínio é erro estrutural, inclusive
lote negativo, fator 100 e USD. Objetos de atributos são recusados mesmo com
`from_attributes=True`. O futuro PR adaptador de linhas deverá preservar a linha e registrar
seu motivo ao capturar a exceção, antes de integrar uma chain.

Em I3, o dono do futuro PR de coleta/replay deverá distinguir publicação, intervalo de vigência
e instante da consulta (`as_of`) antes de usar uma norma histórica que cubra várias datas.
Em I4, ticker pode ser reutilizado entre anos. A chave atual identifica uma observação;
preserva a caixa do ticker e retira espaços nas pontas. Antes de unir históricos, o dono
do cadastro deverá validar ISIN e vencimento e definir a normalização do identificador.
Limites de plausibilidade para lotes e strikes extremos também cabem à homologação.

Em I5, `issuer="B3"` declara o emissor e pode constar de uma fixture sintética. O dono do
primeiro PR consumidor deverá definir e testar a procedência, autenticar a fonte e separar
fixture de observação antes de liberar o import. Em I6, seis mutações em cópias temporárias
de produção fizeram a focal correspondente falhar (rc 1 em cada uma):

| Mutação isolada | Falhas observadas |
|---|---:|
| Permitir atribuição / ignorar extras (duas execuções) | 1 / 1 |
| Trocar precedência entre falta de lote e de fator | 4 |
| Aceitar fator 100 / remover a exigência do tipo inteiro (duas execuções) | 1 / 4 |
| Desligar o validador do strike | 3 |

A guarda de I5 também detectou as quatro linhas de import plantadas em um consumidor
temporário (absolutas, relativas e com alias). A focal sem mutação passa.

### Resultado da candidata no macOS

Congelamento completo em `153ef0a`. Produção e testes validados em `46ddfda`,
árvore `c96334be062e80ff515159c91d1f5a1917760056`. macOS 15.8.1 arm64.
Os comandos usam `u` definido acima, Python 3.12.13 e o interpretador explícito do ambiente.

```sh
u python -m pytest tests/unit/derivatives/test_series_terms.py -q
u python -m pytest tests/ -q --ignore=tests/integration --timeout=120
u python -m mypy backend/ --strict --cache-dir "$tmp/mypy-cache"
u pyright --pythonpath "$UV_PROJECT_ENVIRONMENT/bin/python" backend/
```

| Gate | Resultado | rc |
|---|---|---:|
| Pytest focal | 89 aprovados | 0 |
| Pytest global | 8.214 aprovados, 16 pulados, 261 subtestes aprovados | 0 |
| mypy estrito | 157 arquivos, zero erros | 0 |
| Pyright | Zero erros, avisos e informações de análise | 0 |

`$tmp` é um diretório temporário. Pytest emitiu sete avisos esperados de depreciação de
`copy`. Pyright informou a ausência da subpasta local `.venv` e a disponibilidade de versão
mais recente. A execução usou o interpretador solicitado.

Demo na base do PR `11838cd`, no head revisado `f36f644` e na candidata, no mesmo Mac.
Os dois primeiros diretórios foram extraídos dos respectivos commits com `git archive`.

```sh
u python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
u python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

A primeira chamada gerou 67.097 bytes, rc 0 nas três execuções e `cmp` rc 0 em ambos os pares.
SHA-256 `a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`.
A segunda chamada na candidata devolveu `LIVE_NOT_ACTIVATED`, rc 3.

```sh
git diff --check 11838cd HEAD
git diff --numstat 11838cd HEAD
git diff --exit-code 11838cd HEAD -- backend ':(exclude)backend/derivatives/domain/series_terms.py'
git diff --exit-code 153ef0a HEAD -- tests
```

Rc 0 nos quatro comandos. Produção total do PR: **184 linhas** em `series_terms.py`.
Os outros três arquivos do diff são os testes, este cartão e a memória da Fase 2A.
O digest numérico histórico é objeto de PR separado do Claude. A coordenação replica Linux,
atualiza o mesmo draft #142 e solicita novo parecer independente. Estado A, em revisão.

[layout]:
<https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf>
[manual]:
<https://www.b3.com.br/data/files/CF/D0/64/95/753D0A105BF9020AAC094EA8/MPO de Negociacao da B3.pdf>
[pyd-base]: https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_copy
[pyd-src]: https://github.com/pydantic/pydantic/blob/v2.13.3/pydantic/main.py
[pyd-strict]: https://docs.pydantic.dev/latest/concepts/strict_mode/

## Histórico do primeiro candidato (até f36f644)

### SPEC_PRONTA

Um registro imutável identifica a série e sua vigência civil explícita. Guarda fonte,
strike vigente em Decimal finito positivo, estilo americano ou europeu, moeda BRL
(única coberta neste recorte), lote inteiro positivo e fator inteiro 1 ou 1000.
Igualdade exata em todos os testes. Lote 37 funciona com ambos os fatores.
Cada registro traz seus próprios termos, inclusive quando muda o strike da mesma série.

Lote ou fator ausente/inválido, estilo ou moeda desconhecidos geram exceção de domínio
com os códigos missing_contract_size, missing_quotation_form, unknown_exercise_style e
unknown_currency, respectivamente. Entradas malformadas nos demais campos falham na
validação estrutural. UNKNOWN é válido. Para PROTECTED ou UNPROTECTED, o chamador
identifica o documento B3, versão, data e o fato documentado (série, vigência e política).
O domínio verifica consistência da declaração. A autenticação da fonte cabe à coleta.

### Leitura adversária do ADR aceito

- O exemplo de diretório informado distingue BOVAL63 (179, europeia) de BOVAL65
  (176, americana). Protected YES em ambas não estabelece vigência histórica,
  lote ou fator. Um ticker não determina o strike.
- FATCOT unitário ou por mil (layout COTAHIST rev02, p. 6) descreve a unidade de
  cotação. Copiá-lo para o lote faria duas séries economicamente distintas parecerem iguais.
- UNKNOWN é um termo válido aqui. A recusa missing_carry_assumption pertence ao PR02.
  O PR03 conserva 4.192654 e 5.089632 com tolerância 5e-5. A pendência 200/201 é posterior.

### RED_MOSTRADO

Comando (uv offline, ambiente existente, sem sincronização):

    alvo=tests/unit/derivatives/test_series_terms.py::test_missing_contract_size
    uv run --offline --no-sync python -m pytest "$alvo" -q

Saída: `Failed: DID NOT RAISE <class 'backend.derivatives.domain.series_terms.TermsRefusal'>`.
`1 failed in 0.07s`, rc 1. O teste foi coletado e o construtor aceitou a ausência do lote.

Commit do RED: e0f4664595d7fa4464783b9a7b983f6e045a3ba2.

### GREEN local no macOS

macOS 15.8.1 arm64, Python 3.12.13. Comandos abaixo via
`uv run --offline --no-sync`, com `UV_PROJECT_ENVIRONMENT` apontando para o ambiente
preexistente do repositório principal, cache uv temporário e `PYTHONDONTWRITEBYTECODE=1`.

| Gate | Resultado | rc |
|---|---|---|
| `python -m pytest tests/unit/derivatives/test_series_terms.py -q` | 20 passed | 0 |
| Pytest global sem integração, timeout 120 | 8145 passed, 16 skipped, 261 subtests passed | 0 |
| `python -m mypy backend/ --strict` | 157 arquivos, zero erros | 0 |
| `pyright backend/` | 0 erros, 0 avisos de análise | 0 |

Pyright informou que o checkout não contém a subpasta configurada `.venv`.
A repetição com `--pythonpath /Users/fas/projetos/OPENCLAW/.venv/bin/python` confirmou zero erros.

#### Regressão da Fase 01

Na base limpa, antes da SPEC, e na candidata, no mesmo diretório e plataforma:

    python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture

A comparação dos arquivos de stdout com `cmp` retornou 0. Cada JSON tem 67097 bytes e
SHA-256 `a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`.
Sem a opção de provider, a candidata devolveu `LIVE_NOT_ACTIVATED`, rc 3.

O SDD de correções da Fase 01 registra `840770d25be12b8602c614bd` para preços, gregas
e IVs. O comando original segue pendente com a coordenação. Prova alternativa executada:

    git diff --exit-code 11838cd HEAD -- backend/derivatives \
        ':(exclude)backend/derivatives/domain/series_terms.py'

Diff vazio, rc 0. A subárvore base de produção do Lab tem ID
`9283207aab3bf52bb563571705d6567d3f5d34f8`. O único acréscimo nela é o módulo isolado.
O SHA-256 acima mede a demo inteira.

#### Entrega para coordenação

SPEC_PRONTA, RED_MOSTRADO e GREEN concluídos. Revisão independente e recuperação
do verificador do digest histórico seguem pendentes. Estado A.

A repetição de pytest com `-rs` confirmou os 16 skips: 15 testes de serviços opt-in e
um teste do artefato de benchmark Q18 ignorado pelo Git. Todos os 20 casos novos rodaram.
`git diff --check 11838cd HEAD` sem saída; numstat com quatro arquivos e +100 linhas
de produção. `pyproject.toml`, `uv.lock` e o formato da Fase 01 permanecem na base.

### GREEN no Linux aarch64 do primeiro candidato

Clone limpo, imagem local `openclaw-sandbox`, Python 3.12.13, sem rede.
Código e testes medidos no commit `6ac0b1a`; os commits seguintes só registram evidências.
Base `11838cd` no mesmo ambiente: 8125 passed, 16 skipped, 261 subtests passed.

| Gate | Resultado | rc |
|---|---|---|
| Pytest focal | 20 passed | 0 |
| Pytest global sem integração | 8145 passed, 16 skipped, 261 subtests passed | 0 |
| mypy backend/ --strict | 157 arquivos, zero erros | 0 |
| Pyright backend/ | 0 erros, 0 avisos, 0 informações | 0 |
| CLI demo: comparação de stdout com `cmp` | Idêntico à base no Linux | 0 |
| CLI live padrão | LIVE_NOT_ACTIVATED | 3 |

No contêiner, o `venvPath` do projeto inicialmente não enxergou as dependências.
O gate verde usa `pyright --venvpath /tmp/pyright-env backend/`, com
`/tmp/pyright-env/.venv` apontando para `/opt/openclaw-venv`; sem mudar a configuração.
SHA-256 da demo nas duas execuções Linux:
`f4f8003f2021b2744202c782f6e5245872c09d7f9d1968a3356466a7e85ead08`.

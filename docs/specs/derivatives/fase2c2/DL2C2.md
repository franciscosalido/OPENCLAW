# DL2C2 — Oráculo QuantLib offline (cartão de implementação, versão 2)

- **Autor:** Claude, 2026-11-21 (UTC). **Executa:** Codex. **Revisa e integra:** Claude.
- **Autoridade:** ADR-0028, Accepted por Francisco em 2026-11-20 com as ressalvas S1 a S4.
- **Base:** `main` em `55fe712`. **Branch:** `feat/dl2c2-quantlib-oracle`.
- **Estado:** A, offline. **Um PR**, em rascunho, sem merge. **Zero linha de produção.**
- **Destino deste arquivo:** `docs/specs/derivatives/fase2c2/DL2C2.md`, copiado sem edição.

Esta versão substitui a anterior. As tolerâncias foram conferidas pelo autor rodando o
código de produção da `main` contra a referência gerada em x86-64. Se você seguir o cartão
como está, o esperado é passar de primeira.

## 1. O que você vai entregar, em uma frase

Um arquivo com 69 preços calculados pelo QuantLib, guardado no repositório, e testes que
medem contra ele a árvore CRR e as diferenças finitas do projeto, sem o QuantLib virar
dependência.

## 2. O que já está decidido e não se discute neste PR

| Decisão | Onde |
|---|---|
| QuantLib 1.44 só como arquivo de referência. Nunca em `pyproject.toml`, `uv.lock` ou `import`. | ADR-0028 R1 |
| Referência americana: `QdFpAmericanEngine` com esquema fino; incerteza publicada por caso. | ADR-0028 R2 |
| Prazo em dias corridos sobre 365, igual dos dois lados. | ADR-0028 R3 |
| O gerador é do Claude. Você copia sem editar e roda. | ADR-0028 R4 |
| O limiar de 0,00050 é aviso de diagnóstico. Não muda e não reprova nada. | ADR-0028 S2 |
| A sombra BSM não ganha PR nesta fase. | ADR-0028 S4 |
| Árvore CRR segue principal, 200 passos; malha 400 por 200. Nada disso muda aqui. | ADR-0028 R6 |
| Repetir a conferência com dado real é marco futuro, depois da OpLab. Não é este PR. | ADR-0028 S1 |

## 3. Não objetivos

Mudar qualquer arquivo de `backend/`, `config/` ou `scripts/`. Editar teste ou auxiliar de
teste existente. Importar ou instalar o QuantLib no ambiente do projeto. Rodar o QuantLib em
teste, CI ou produção. Trocar passos, malha, limiar ou motor. Expor a sombra BSM. Dividendo
discreto, gregas, calendário, dias úteis. Dado real, OpLab, token, corretora, ordens. Outra
biblioteca de referência. Serviço ou MCP do QuantLib.

## 4. Perguntas que você faria, já respondidas

| # | Pergunta | Resposta |
|---|---|---|
| P1 | Posso usar rede no contêiner para baixar a imagem e o pacote? | Sim, só isso (decisão E4). O contêiner não monta o repositório. Sem imagem ou sem rede: pare e reporte. |
| P2 | E se o `pip` recusar o hash? | Pare. Não remova `--require-hashes`, não troque versão, não instale do código-fonte. |
| P3 | O gerador é determinístico? | Sim: duas execuções dão o mesmo arquivo, byte a byte (conferido em x86-64). O passo 1 confere isso de novo. |
| P4 | Qual referência vale se a minha diferir da do Claude? | Até 1e-9 relativo, vale a sua, do contêiner no Mac. Acima disso, nenhuma: pare e reporte. |
| P5 | Posso editar o gerador para arrumar estilo ou tipo? | Não. O SHA-256 dele é preso por teste. Ele fica fora de `backend/`, então `mypy` e `pyright` do portão não o leem. |
| P6 | Como monto contrato, termos e prazo para inverter pela árvore? | Como o teste T15 faz: importe `A1_TERMS`, `CALL`, `TTE` e `_carry` de `tests.unit.derivatives.test_american_bridge`. Molde na seção 8. |
| P7 | Como converto o alvo para `Decimal`? | `Decimal(repr(valor))`. Para spot e strike, `Decimal(str(valor))`. |
| P8 | Algum caso é recusado pela inversão de produção? | Não. Nos 69 casos as duas inversões devolvem número. Se alguma recusar, pare e reporte. |
| P9 | `B21` e `C01` devolvem volatilidade absurda. É defeito? | Não é deste PR. O preço de referência ali é o intrínseco mais 2e-7, e as duas inversões devolvem `ok` com erro de cerca de 0,05. Registre na tabela de fechamento; não corrija, não mude tolerância. |
| P10 | Os testes do oráculo entram na suíte padrão? | Sim, sem marcador. Divida para nenhum teste passar de 30 s. Total esperado: cerca de 50 s. |
| P11 | Onde roda a medição com 400 e 800 passos? | Fora da suíte, em script descartável em `reports/fase02/dl2c2/evidencias/`. Só o resultado entra no documento. |
| P12 | Em que máquina meço tempo? | Na mesma das medições anteriores (MacBook Pro M4 Pro, macOS nativo). Registre modelo e versão do Python. |
| P13 | Um teste falhou com o código de produção. Ajusto a tolerância? | Não. Pare e reporte o caso e o número. É o resultado mais útil que a fase pode dar. |
| P14 | Posso aproveitar para melhorar a sondagem de identificabilidade ou o motor? | Não. Zero produção. Anote como achado. |

Fica com Francisco, com padrão já aplicado para você não parar: a máquina de medição (P12).
Se ele indicar outra, vale a dele.

## 5. Arquivos

Todos novos. Nenhum arquivo existente é editado, fora `docs/04_MEM/current_state.md`.

| Arquivo | Conteúdo |
|---|---|
| `tests/fixtures/derivatives/reference/quantlib/generate_quantlib_reference.py` | Cópia sem edição de `reports/fase02/dl2c2/`. SHA-256 `c24ca695116b82823bba5389dd69583c496f44df94ad9585cce3f08892e937db`. |
| `tests/fixtures/derivatives/reference/quantlib/quantlib_reference_v1.json` | Saída do gerador no contêiner. |
| `tests/fixtures/derivatives/reference/quantlib/PROVENANCE.md` | Molde na seção 7. |
| `tests/unit/derivatives/test_quantlib_oracle.py` | Testes O1 a O12. |
| `tests/architecture/test_quantlib_is_not_a_dependency.py` | Guardas G1 a G3. |
| `docs/ADR/ADR-0028-laboratorio-derivativos-fase2c2.md` | Cópia sem edição de `reports/fase02/dl2c2/ADR-0028_FASE2C2.md`. |
| `docs/specs/derivatives/fase2c2/DL2C2.md` | Este cartão, sem edição. |
| `docs/specs/derivatives/fase2c2/DL2C2-PR01.md` | Evidências: critério 11, tabela de fechamento, medições. |
| `docs/04_MEM/current_state.md` | Bloco da seção 10, no topo. |

## 6. Passo 1 — gerar a referência no contêiner

No Mac, numa única sessão de shell (os passos 1 e 2 usam as mesmas variáveis).

```sh
set -euo pipefail
REPO="$HOME/projetos/OPENCLAW"
SRC="$REPO/reports/fase02/dl2c2/generate_quantlib_reference.py"
WANT=c24ca695116b82823bba5389dd69583c496f44df94ad9585cce3f08892e937db
GOT=$(shasum -a 256 "$SRC" | cut -d' ' -f1)
[ "$GOT" = "$WANT" ] || { echo "PARE: gerador com SHA $GOT"; exit 1; }
W=$(mktemp -d)
cp "$SRC" "$W/"
cat > "$W/req.txt" <<'EOF'
QuantLib==1.44 \
  --hash=sha256:fb76eb6695fdc178d7da063274e11b40ee772c9da046827616348d26242fdd02 \
  --hash=sha256:60394d8c7f39a9c84a96da509c099e5f84fee50bf6b660fcf9515703fa4abb9b
EOF
docker run --rm -v "$W":/w -w /w python:3.12-slim sh -euc '
  pip install --no-cache-dir --only-binary=:all: --require-hashes -r req.txt
  python generate_quantlib_reference.py quantlib_reference_v1.json
  python generate_quantlib_reference.py segunda.json
  cmp quantlib_reference_v1.json segunda.json
  pip freeze > freeze.txt
  python -c "import platform; print(platform.machine(), platform.python_version())" > host.txt'
docker image inspect python:3.12-slim --format '{{index .RepoDigests 0}}' > "$W/image.txt"
test -s "$W/quantlib_reference_v1.json" || { echo "PARE: JSON vazio"; exit 1; }
grep -qx 'QuantLib==1.44' "$W/freeze.txt" || { echo "PARE: freeze inesperado"; exit 1; }
echo "OK: saída em $W"; cat "$W/host.txt" "$W/image.txt"
shasum -a 256 "$W/quantlib_reference_v1.json"
```

Os dois hashes são do pacote 1.44 para Linux aarch64 e para Linux x86-64, baixados e
conferidos pelo autor. O `cmp` dentro do contêiner prova que a geração é determinística.

### Passo 2 — conferência cruzada com x86-64

Referência do autor: `reports/fase02/dl2c2/quantlib_reference_x86_conferencia.json`, SHA-256
`8db71f02ecbde1e4de1ba249f75f145e57103b2a5d8f6c77445efd67ae5d256a`.

```sh
python3 - "$W/quantlib_reference_v1.json" \
  "$REPO/reports/fase02/dl2c2/quantlib_reference_x86_conferencia.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
assert a["quantlib"] == b["quantlib"] == "1.44" and len(a["cases"]) == len(b["cases"]) == 69
worst = 0.0
for x, y in zip(a["cases"], b["cases"], strict=True):
    assert x["id"] == y["id"]
    for key in ("american", "european", "american_fixed_point_a",
                "american_high_precision_scheme", "american_finite_differences"):
        worst = max(worst, abs(x[key] - y[key]) / max(1.0, abs(y[key])))
print("maior diferença relativa:", worst)
sys.exit(0 if worst <= 1e-9 else 1)
EOF
```

Saída diferente de zero: pare e reporte o número. Depois copie do `$W` para a pasta de
fixtures só o JSON; `freeze.txt`, `host.txt` e `image.txt` alimentam o `PROVENANCE.md`.

## 7. Formato da referência e molde do PROVENANCE

Cabeçalho do JSON: `schema` (`quimera-quantlib-reference/1`), `quantlib`, `python`, `machine`,
`system`, `evaluation_date`, `day_count`, `compounding`, `american_engine`, `cross_checks`,
`european_engine`. Depois `cases`, 69 entradas, nesta ordem: `A01`…`A18`, `B01`…`B27`,
`C01`…`C18`, `D01`…`D06`.

| Campo | Conteúdo |
|---|---|
| `kind`, `spot`, `strike`, `days`, `time_years`, `rate_cont`, `dividend_yield`, `sigma` | insumos; `time_years == days / 365` |
| `american` | referência |
| `american_uncertainty` | incerteza `u` do caso |
| `american_fixed_point_a`, `american_high_precision_scheme` | conferências do mesmo motor |
| `american_finite_differences` | conferência grosseira |
| `european` | fórmula analítica |

Grupos: **A**, call sem rendimento (o caso listado na B3); **B**, call com rendimento não
compensado; **C**, put americana, que testa os motores e não é instrumento listado em ações,
BDRs ou ETFs; **D**, regimes de borda.

`PROVENANCE.md`, com estes campos preenchidos e nada além:

```
# Proveniência de quantlib_reference_v1.json
- Gerado em: <data e hora UTC>
- Quem rodou: <agente e sessão>
- Máquina: <saída de host.txt>
- Imagem: <saída de image.txt>
- Pacote: QuantLib==1.44, hash <o que o pip usou>
- pip freeze: QuantLib==1.44
- SHA-256 do gerador: c24ca695…e937db
- SHA-256 do JSON: <valor>
- Determinismo: duas execuções idênticas (cmp, rc 0)
- Conferência cruzada com x86-64: maior diferença relativa <valor>, limite 1e-9
- Comando: passo 1 do cartão DL2C2, sem alteração
```

## 8. Testes

### Moldes conferidos contra a `main`

```python
from dataclasses import replace
from decimal import Decimal
from backend.derivatives.domain.models import ExerciseStyle, OptionKind
from backend.derivatives.pricing import bsm
from backend.derivatives.pricing.american_bridge import AmericanIvSolution, american_implied_vol
from backend.derivatives.pricing.binomial import crr_price
from backend.derivatives.pricing.fd_american import FdGrid, fd_implied_vol, fd_price
from config.american_fd_config_model import load_american_fd_config
from config.american_iv_config_model import load_american_iv_config
from tests.unit.derivatives.test_american_bridge import A1_TERMS, CALL, TTE, _carry

# europeia
bsm.price(bsm.BsmInputs(kind, spot, strike, years, rate, sigma, q), theta_basis=252).price

# árvore, par N e N+1
0.5 * (crr_price(kind=kind, style=ExerciseStyle.AMERICAN, spot=spot, strike=strike,
                 time_years=years, rate_cont=rate, sigma=sigma, dividend_yield=q, steps=n)
       + crr_price(..., steps=n + 1))

# volatilidade pela árvore, caminho de produção
terms = A1_TERMS.model_copy(update={"strike": Decimal(str(strike))})
contract = CALL.model_copy(update={"kind": kind, "strike": terms.strike})
american_implied_vol(
    contract, terms=terms, carry=_carry(str(q) if q else None), spot=Decimal(str(spot)),
    rate_cont=rate, tte=replace(TTE, year_fraction=years),
    target_price=Decimal(repr(american)), cfg=load_american_iv_config(), steps=200)

# diferenças finitas: malha e parâmetros vêm de load_american_fd_config()
```

`dx` da malha, igual ao do cartão DL2C1:

```python
half = max(width * sigma * sqrt(T) + abs(rate - q - sigma**2 / 2) * T,
           abs(log(spot / strike)) + sigma * sqrt(T))
dx = 2 * half / space_nodes
```

### `tests/unit/derivatives/test_quantlib_oracle.py`

`u` é o `american_uncertainty` do caso. "Identificáveis" são os 67 casos fora `B21` e `C01`.
A coluna "Esperado" é o que o autor mediu com o código da `main` e a referência em x86-64;
serve para você desconfiar de um número muito diferente.

| # | Teste | Limite | Esperado |
|---|---|---|---|
| O1 | SHA-256 do JSON e do gerador, lidos em bytes | igualdade | — |
| O2 | Cabeçalho, 69 identificadores na ordem, `quantlib == "1.44"`, `time_years == days / 365` | igualdade | — |
| O3 | Coerência da referência: `u <= 5e-5`; `abs(american_finite_differences - american) <= 5e-3`; `american >= european - 1e-9`; no grupo A, `abs(american - european) <= 1e-9` | como escrito | 2,6e-5; 2,4e-3; 2e-14 |
| O4 | BSM europeu, 69 casos | `abs(bsm - european) <= 1e-11 * max(1, european)` | 9,5e-15 |
| O5 | Preço da árvore, par 200/201, 69 casos | `abs(par - american) <= 4.5e-4 * S * sigma * sqrt(T) + u` | 61% do limite (C11) |
| O6 | Volatilidade da árvore, 67 casos | `abs(VI - sigma) <= 5e-4` | 3,7e-4 (D01) |
| O7 | Preço das diferenças finitas, malha padrão, 69 casos | `abs(FD - american) <= 0.8 * S * dx**2 + u` | 64% do limite (D04) |
| O8 | Volatilidade das diferenças finitas | grupos A, B, C: `<= 1e-4`; grupo D: `<= 3.5e-4` | 6,1e-5; 2,3e-4 (D02) |
| O9 | Convergência, nos 23 casos de posição 0, 3, 6, … | soma dos erros do par 2000/2001 sobre a do par 200/201 `<= 0.15`; malha 800 por 400 sobre a padrão `<= 0.35` | 0,083; 0,252 |
| O10 | Diferença entre as duas volatilidades, grupos A, B e C, identificáveis | `<= 5e-4` | 3,6e-4 (A01) |
| O11 | `B21` e `C01` | `abs(american - intrínseco) <= u`; valem os limites de O5 e O7; o estado e o valor de cada inversão entram no relatório, sem asserção | as duas devolvem `ok` |
| O12 | Relatório | o teste escreve em `tmp_path` um JSON com uma linha por caso (erros de preço e de volatilidade dos dois motores) e confere 69 linhas e quatro grupos | — |

Regras dos testes: docstring em toda função; linhas de até 100 colunas; nada de `print`;
`pytest.mark.parametrize` por caso onde couber; nenhum teste acima de 30 s; nenhuma escrita
fora de `tmp_path`.

### `tests/architecture/test_quantlib_is_not_a_dependency.py`

| # | Teste |
|---|---|
| G1 | Por AST, nenhum `.py` de `backend/`, `config/`, `scripts/` ou `tests/` importa `QuantLib` (em `import` ou `from`), com exceção única do gerador. |
| G2 | `pyproject.toml` e `uv.lock` não contêm `quantlib`, em qualquer caixa. |
| G3 | Nenhum arquivo de `backend/`, `config/` ou `scripts/` contém `quantlib_reference` nem `reference/quantlib`. |
| G4 | A guarda pega um intruso: num diretório temporário, um arquivo com `import QuantLib` é acusado. |

## 9. Critério 11 — o oráculo tem dentes

Seis trocas no código de produção, uma por vez, em cópia temporária, rodando **só**
`test_quantlib_oracle.py`. Todas têm de falhar. Registre, para cada uma, o teste que falhou.

| # | Troca |
|---|---|
| D1 | Árvore sem exercício antecipado. |
| D2 | Árvore com `prob_up` calculado com `r` no lugar de `r - q`. |
| D3 | Árvore com `dt = T / (N + 1)`. |
| D4 | Diferenças finitas sem a projeção. |
| D5 | Diferenças finitas com a diagonal sem `- r`. |
| D6 | Diferenças finitas sem a média do payoff. |

Uma troca que sobreviva é achado bloqueante: pare e reporte.

## 10. Bloco para o `current_state.md`

No topo, acima do bloco da Fase 2C1, e atualizando a linha "Última atualização":

```
## Fase 02 — Marco 2C2 (estado A)

[ADR-0028](../ADR/ADR-0028-laboratorio-derivativos-fase2c2.md) aceito por Francisco em
2026-11-20, com as ressalvas S1 a S4. Cartão em
[DL2C2.md](../specs/derivatives/fase2c2/DL2C2.md).

O QuantLib 1.44 entra só como arquivo de referência, gerado fora do repositório; não é
dependência nem motor. O limiar de 0,00050 é aviso de diagnóstico e não muda. A sombra BSM
não ganha PR nesta fase. Repetir a conferência com dado real é marco futuro, depois da OpLab.

PR atual: DL2C2-PR01 — EM_REVISAO. Zero linha de produção.

Próxima ação: Claude revisa o DL2C2-PR01. A fase fecha com a tabela de resultados e duas
decisões de Francisco: passos da árvore e malha das diferenças finitas, pelo pior caso.
```

## 11. Tabela de fechamento (em `DL2C2-PR01.md`)

1. Por grupo: maior erro de preço e de volatilidade de cada motor e maior diferença entre os
   dois, com o caso de cada máximo.
2. Árvore com 200, 400 e 800 passos, 67 casos: erro de volatilidade no **pior caso** e na
   mediana, e mediana de CPU de uma inversão em cada configuração.
3. Diferenças finitas em 200 por 100, 400 por 200 e 800 por 400: o mesmo.
4. Erro de preço de cada motor contra a referência, na mesma volatilidade, quebrado por
   prazo (até 30, 31 a 182, 183 a 365, acima de 365 dias), por distância do strike
   (`S/K` abaixo de 0,97; de 0,97 a 1,03; acima de 1,03) e por rendimento (zero; positivo).
5. Sombra BSM direta: em quantos dos 69 casos ela fica a até 1e-3 da volatilidade verdadeira
   e em quantos não tem solução, separando o grupo A dos demais. Informativo.
6. `B21` e `C01`: o que cada inversão devolveu.
7. As seis trocas do critério 11.

Os itens 2 e 3 com 800 passos e 800 por 400 rodam fora da suíte (P11).

## 12. Sequência de commits

1. `docs`: ADR-0028, este cartão, bloco do `current_state.md`.
2. `test`: gerador, JSON e `PROVENANCE.md` (depois dos passos 1 e 2).
3. `test`: O1 a O12 e G1 a G4.
4. `docs`: `DL2C2-PR01.md` com critério 11, tabela de fechamento e medições.

Não há RED de produção, porque não há produção. O papel do RED é do critério 11.

## 13. Portão

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check 55fe712 HEAD
git diff --exit-code 55fe712 HEAD -- backend config scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

- Pytest em clones limpos, macOS arm64 e Linux aarch64, com a mesma contagem. Base: 10.256
  aprovados, 16 pulados, 261 subtestes. O PR só pode aumentar os aprovados.
- O `git diff --exit-code` sai com rc 0.
- A demo offline é idêntica byte a byte à da base. O CLI padrão devolve `LIVE_NOT_ACTIVATED`,
  rc 3.
- `test_quantlib_oracle.py` em até 60 s de relógio no Mac.

## 14. Fechamento do PR: skill e dois relatórios

Depois do portão verde no head publicado, **em sessão separada da que implementou**, sobre o
SHA publicado:

1. Rodar a skill `quimera-lab-review` com a avaliação de simplificação v0.2 do projeto.
2. Produzir **dois arquivos**, os dois fora do Git, em `reports/fase02/dl2c2/evidencias/`:

| Arquivo | Conteúdo |
|---|---|
| `PARECER_SKILL_<sha7>.md` | O parecer completo, como nos PRs anteriores: requisitos tocados, achados, o que não foi verificado, veredito sugerido. |
| `RELATORIO_SKILL_V02_<sha7>.md` | **Só** os resultados da avaliação de simplificação v0.2. Molde abaixo. |

Molde do segundo relatório, sem acrescentar seção:

```
# Resultados da avaliação de simplificação v0.2 — DL2C2-PR01 (<sha7>)
- Objeto: <SHA completo, copiado do Git> sobre a base 55fe712
- Sessão: separada da autora; somente leitura
- O que foi examinado: <arquivos>
## Simplificações propostas
<para cada uma: o que sai, por que preserva o comportamento, e a prova: suíte verde em
cópia e saídas idênticas. Sem prova, não entra aqui.>
## Simplificações consideradas e descartadas
<o que foi cogitado e por que não se sustenta>
## Guardas, testes e tolerâncias que não podem ser cortados
<lista>
## Resultado
<"nenhuma simplificação qualificada" ou a lista das qualificadas>
```

Neste PR não há código de produção: a avaliação v0.2 recai sobre os testes novos. O gerador
não entra, porque não pode ser editado.

3. Na descrição do PR, os dois SHA-256, **copiados da saída do `shasum`**, não redigitados.
4. O Claude forma o veredito antes de ler os dois arquivos e só integra depois de lê-los.

## 15. Quando parar e perguntar

- Hash do gerador ou do pacote não bate.
- Sem Docker, sem imagem ou sem rede no contêiner.
- As duas execuções do gerador diferem.
- Conferência cruzada acima de 1e-9.
- Qualquer teste O3 a O11 falha com o código de produção.
- Uma inversão recusa um caso identificável.
- Uma troca do critério 11 sobrevive.
- Um critério exigiria editar arquivo existente ou importar o QuantLib.
- O tempo dos testes do oráculo passa de 60 s.

Parar é entregar: o que rodou, o número obtido, o esperado e o comando para reproduzir.

## 16. Pronto quando

- [ ] Quatro commits na ordem da seção 12, no branch `feat/dl2c2-quantlib-oracle`.
- [ ] Passos 1 e 2 sem "PARE", com `PROVENANCE.md` preenchido.
- [ ] O1 a O12 e G1 a G4 verdes; critério 11 com seis trocas mortas.
- [ ] Portão da seção 13 verde em macOS e Linux, com a mesma contagem.
- [ ] `DL2C2-PR01.md` com os sete itens da tabela de fechamento.
- [ ] Dois relatórios da skill fora do Git e os dois SHA-256 na descrição.
- [ ] PR em rascunho, sem merge.

## 17. Mensagem final que você devolve

```
DL2C2-PR01: PR #<n>, rascunho, head <SHA completo>, base 55fe712.
Referência: JSON <SHA-256>; máquina <...>; conferência cruzada <valor>.
Portão: <aprovados>/<pulados>/<subtestes> em macOS e em Linux; mypy e pyright <...>.
Oráculo: O1–O12 e G1–G4 verdes em <segundos> s; critério 11: <n>/6 trocas mortas.
Pior caso: VI da árvore <valor> (<caso>); VI das diferenças finitas <valor> (<caso>).
Parecer da skill: <SHA-256>. Relatório v0.2: <SHA-256>.
Achados ou paradas: <lista, ou "nenhum">.
```

## 18. Riscos

| Risco | Mitigação |
|---|---|
| Tratar o oráculo como verdade absoluta | Incerteza por caso; O3; ADR-0028, "O que esta fase não prova" |
| QuantLib virar dependência "só para teste" | G1 a G4; portão com `git diff --exit-code` |
| Referência regenerada sem ninguém notar | Versão conferida pelo gerador; SHA-256 preso em O1 |
| Diferença de plataforma lida como erro | Passo 2, limite de 1e-9 |
| Tolerância alargada para o teste passar | P13; seção 15 |
| Fase crescer para dias úteis, proventos ou dado real | Seção 3; ADR-0028 R3 e S1 |
| Escolher passos e malha pelo caso médio | Tabela de fechamento com o pior caso |
| Ler o aviso de 0,00050 como alarme | ADR-0028 S2 e S3; nenhum teste falha por ele |
| Parecer e relatório v0.2 escritos pela sessão autora | Seção 14: sessão separada, dita nos dois arquivos |

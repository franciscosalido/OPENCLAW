# DL2B-R1 — Revisão 1 do Marco 2B: dois métodos, 200 passos e integração

Estado: **SPEC_PRONTA** (Claude, 2026-11-20). Autoridade: decisões de Francisco de
2026-11-20, ADR-0026 com a Revisão 1 e `SDD_FASE2B.md` com o Adendo 1. Os dois acompanham
este cartão.
Base de código: candidato local `8a9a391882519dcfeb5b16b3f6ef3a5614e12a80`, revisado por
Claude em `REVISAO_CORRECOES_2B_2026-11-20`. Base de integração: `main` em `2132e10`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidão: A, sem mudança.

Arquivos de `reports/fase02/dl2b-r1/`, com SHA-256:

```text
f89467831e715637f0b3185fe1be7f8ce9d1260aae637156b3ccce80d90c303b  ADR-0026.md
3fce84ce79b709d80f46866931e0091198bf5cf8d51e1ecd5abd61d28f20153a  SDD_FASE2B_ADENDO_1.md
```

## O que Francisco decidiu

1. **Dois métodos convivem.** A árvore CRR é o motor principal: dá o preço e a volatilidade
   implícita da linha. O BSM europeu da Fase 1 roda como sombra, só para medir a
   divergência. Nenhum número mistura os dois.
2. **200 passos por padrão.**
3. **Teto de tempo: 210 ms de CPU por inversão com 200 passos no Mac.**
4. **O ADR-0026 muda e passa a `Accepted`.**

## Este cartão tem duas partes

**Parte A, integração do que já existe.** Quatro PRs, um por vez, na ordem. Sem código novo.

**Parte B, código novo.** Passos padrão, motor de sombra e três testes de cotação. Entra só
no quarto PR.

## Parte A — integração

| Ordem | PR | Conteúdo | Origem local |
|---|---|---|---|
| 1 | DL2B-PR01A | correção de tipos da ponte e testes das lacunas | `f848b19` + `f85e3af` |
| 2 | DL2B-PR02 | volatilidade implícita pela árvore, com YAML próprio | `9ea8fbd` |
| 3 | DL2B-PR03 | registro de termos e carry | domínio de `4c76d14`, sem mudança |
| 4 | DL2B-PR04 | ligação na demo offline, mais a Parte B | resto de `8a9a391` |

Regras:

- **O primeiro commit do PR 1** traz três cópias sem alteração e mais nada: o ADR-0026
  inteiro (substitui o arquivo atual), o Adendo 1 acrescentado ao fim do SDD e este cartão.

  ```sh
  SRC=reports/fase02/dl2b-r1
  cp $SRC/ADR-0026.md docs/ADR/ADR-0026-laboratorio-derivativos-fase2b.md
  printf '\n' >> docs/specs/derivatives/fase2b/SDD_FASE2B.md
  cat $SRC/SDD_FASE2B_ADENDO_1.md >> docs/specs/derivatives/fase2b/SDD_FASE2B.md
  cp $SRC/DL2B-R1_CARD.md docs/specs/derivatives/fase2b/DL2B-R1.md
  ```

- Cada PR parte da `main` já integrada, em rascunho, com portão em macOS e em Linux no head
  publicado. O PR seguinte só é publicado depois de Claude integrar o anterior.
- A árvore final do PR 4, sem a Parte B, tem de ser a de `8a9a391` nos arquivos de
  `backend/`, `config/` e `tests/`. Divergência exige explicação no PR.
- Em cada PR: sessão separada roda `reports/fase02/quimera-lab-review/SKILL.md` sobre o head
  publicado, somente leitura; o parecer fica fora do Git e só o SHA-256 vai na descrição.
  Claude forma o parecer sem ler o da skill e só integra depois de ler.
- O PR 2 registra a medição de tempo (seção "Medição").

## Parte B — código novo, no PR 4

### Escopo

| Arquivo | O que muda |
|---|---|
| `config/american_iv.yaml` | ganha `default_steps: 200` |
| `config/american_iv_config_model.py` | campo `default_steps`, inteiro de 1 a 4999, sem padrão |
| `backend/derivatives/service/demo_chain.py` | passos opcionais com a chave ligada |
| `backend/derivatives/service/american_demo.py` | origem dos passos; motor de sombra |
| `backend/derivatives/cli.py`, `mcp/derivatives_server.py` | só o que a opção de passos exigir |
| `tests/unit/derivatives/test_offline_american_demo.py`, `test_cli.py` | testes B1 a B7 |
| `tests/architecture/` | teste B8 |

Meta: até 60 linhas de produção. `american_bridge.py`, `binomial.py`, o domínio, o
`ChainService` e os dois arquivos de configuração da Fase 1 não mudam.

### Não-objetivos

- Motor de diferenças finitas, Brent ou qualquer terceiro método. O QuantLib é referência
  de disciplina, não dependência nem código a portar.
- Sombra influenciando preço, volatilidade principal ou recusa.
- Chave nova nas linhas do formato `quimera-derivatives-chain-v1`.
- Padrão de passos dentro de `price_american_contract` ou `american_implied_vol`.
- Comparação com preço real, dado da OpLab, NumPy, gregas.

### Contrato

**Passos.** Com a chave ligada (`american_demo` e `series_registry`), `steps` é opcional.
Ausente, vale `default_steps` do YAML. Presente, vale o argumento, de 1 a 4999. Com a chave
desligada, informar `steps` continua sendo `INVALID_ARGUMENTS`. As hipóteses da chain ganham
`american_crr_steps_source`, com `"config"` ou `"argument"`.

**Sombra.** Para cada linha americana suportada, depois de calculados o preço e as
volatilidades principais, a composição da demo chama o `implied_vol` da Fase 1 com: o mid
por unidade, o tipo, o spot, o strike, o prazo, a taxa contínua, o rendimento resolvido
pelo registro e a configuração `iv` do YAML da Fase 1.

Nas hipóteses da linha (`PricingOutcome.assumptions`), entram:

```text
shadow_engine      "bsm_european_v1"
shadow_iv_status   o status da Fase 1 ("ok", "low_vega", ...) ou "error"
shadow_iv_mid      a volatilidade da sombra, só quando existe
shadow_iv_gap      volatilidade principal do mid menos a da sombra, só quando existe
```

Nas hipóteses da chain entram `american_shadow_engine`, `american_shadow_rows` (linhas com
`shadow_iv_gap`) e `american_shadow_max_abs_gap` (ausente se nenhuma linha foi comparada).

Qualquer exceção da sombra vira `shadow_iv_status = "error"`. **A linha principal não muda
em nenhum campo por causa da sombra.** Linha recusada não tem sombra.

### Testes exigidos

**B1. Configuração.** O YAML traz `default_steps: 200`. Campo ausente, `0`, `5000`, `True`,
`200.0` e `"200"` são recusados pelo modelo.

**B2. Passos padrão.** Demo mista sem `steps`: `american_crr_steps == 200` e origem
`"config"`. As linhas são idênticas, campo a campo, às da demo com `steps = 200` explícito.

**B3. Passos por argumento.** Com `steps = 32`: valor 32 e origem `"argument"`. Sem a
chave, `steps = 32` devolve `INVALID_ARGUMENTS`. Chave sem registro, idem.

**B4. Um motor por número.** Em toda linha americana suportada: `model` é
`crr_american_v1`; a mensagem de diagnóstico de cada volatilidade publicada é
`crr_american_v1`; e o preço do modelo reproduz o mid por unidade com diferença de até
1e-7. Rodar com 3, 32 e 200 passos.

**B5. Sombra presente e inofensiva.** Na linha `SYNAC150` com 200 passos: `shadow_engine`
presente, `shadow_iv_status == "ok"`, e `shadow_iv_gap` igual à diferença das duas
volatilidades. Com a função da sombra trocada por uma que levanta exceção
(`monkeypatch`): status `"error"`, e `supported`, `price`, `iv` e `reason` de todas as
linhas idênticos aos da execução normal. As 100 linhas europeias não têm chave `shadow_`.

**B6. Agregado da chain.** `american_shadow_rows` conta as linhas comparadas e
`american_shadow_max_abs_gap` é o maior módulo de `shadow_iv_gap`. Na demo atual: uma linha.

**B7. Cotação que não sustenta volatilidade única.** Três linhas sintéticas em memória,
derivadas de `SYNAC150`: sem oferta de venda, com cotação velha, e com preço no limite
inferior (não identificável). As três saem recusadas, com motivo próprio e sem
volatilidade do meio. A linha com os dois lados publica as três volatilidades.

**B8. A ponte não conhece o segundo motor.** Em `american_bridge.py`, por AST: nenhum
import de `backend.derivatives.pricing.bsm`; de `implied_vol`, só `price_bounds`.

### RED exigido

1. B2: hoje a demo mista sem `steps` devolve `INVALID_ARGUMENTS`.
2. B5: hoje não existe `shadow_engine` nas hipóteses da linha.

### Mutação

Mínimo: 8 mortos, 0 sobrevivente. 1. padrão 200 escrito no código em vez de lido do YAML;
2. origem sempre `"argument"`; 3. `steps` aceito com a chave desligada; 4. sombra recebendo
`q = 0` em vez do rendimento resolvido; 5. sombra recebendo o mid bruto, sem dividir pelo
fator de cotação; 6. exceção da sombra recusando a linha; 7. volatilidade da sombra
gravada no lugar da principal; 8. `shadow_iv_gap` com sinal trocado; 9. agregado contando
linhas recusadas.

## Medição

No Mac, macOS nativo, no head do PR 2 e de novo no do PR 4. Call, `S = K = 100`, `T = 1`,
`r = 0.05`, `q = 0`, alvo igual ao preço da ponte com `sigma = 0.20` e 200 passos. Um
aquecimento e nove inversões, com `time.process_time`. Registrar mínimo, mediana e máximo.
**Teto: 210 ms na mediana.** Referência: 139 ms no candidato `8a9a391`. Estouro não reprova
o PR: é comunicado a Francisco e reabre a decisão sobre NumPy.

## Regressão e portão, em todo PR

```sh
python -m pytest tests/ -q --ignore=tests/integration --timeout=120
python -m mypy backend/ --strict
pyright backend/
git diff --check origin/main HEAD
git diff --exit-code origin/main HEAD -- config/derivatives.yaml \
    config/derivatives_config_model.py scripts pyproject.toml uv.lock \
    CLAUDE.md AGENTS.md .claude
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19
```

Demo padrão idêntica byte a byte à da `main`, por plataforma. CLI padrão com
`LIVE_NOT_ACTIVATED`, rc 3. Contagem de testes igual em macOS e Linux e nunca menor que a
da `main`. Referência do candidato cumulativo, antes da Parte B: 9.522 aprovados, 16
pulados, 261 subtestes.

Regras do repositório: docstring pública, tipos, imports absolutos, até 100 colunas, nunca
`print`. Sem chamada real à OpLab, sem token, sem leitura de `.env`.

## Decisões deste cartão

Francisco pode vetar antes do RED.

1. **O segundo método é o BSM europeu da Fase 1, como sombra.** A mensagem de Francisco
   fala em "duas metodologias" sem nomear a segunda. A leitura adotada é a mais barata que
   cumpre o objetivo declarado, observar a divergência. Diferenças finitas com Brent seria
   um motor novo, escrito à mão e sem dependência: é frente nova, e fica para ADR próprio
   se a divergência observada justificar.
2. **A sombra não aparece nas linhas do formato v1.** Fica nas hipóteses internas da linha
   e no agregado da chain. Expor por linha exige versão nova do formato.
3. **A divergência contra preço real não é medida aqui.** Não há dado real no estado A.
4. **Bisseção continua.** Brent convergiria em menos avaliações; trocar o método de busca é
   otimização e entra junto com a decisão de NumPy, se o teto estourar.
5. **`default_steps` vive só na raiz de composição.** As funções puras seguem sem padrão.

## Fora deste cartão, com dono

| Item | Dono |
|---|---|
| Origem e vigência de termos e carry de série real (D3) | Francisco |
| NumPy ou Brent, se o teto de 210 ms estourar (D4) | Francisco |
| Terceiro motor, por diferenças finitas | Francisco, com ADR próprio |
| Faixa de volatilidade por linha no formato público, com sombra | versão nova do formato |
| Homologação com séries líquidas de BOVA11 (estado B) | depois da assinatura da OpLab |

## Entrega

Quatro PRs em rascunho, um por vez. Em `current_state.md`, o PR atual com `EM_REVISAO`. O
autor não integra. As evidências de cada PR entram abaixo deste cartão, em seção própria.

## Base bibliográfica

- QuantLib, `vanillaoption.cpp` e `impliedvolatility.cpp`. Americana por diferenças
  finitas; volatilidade implícita por Brent, reusando o mesmo motor em toda a busca.
  (código-fonte primário; lido nesta sessão)
- Merton (1973), *Theory of Rational Option Pricing*. Não exercício antecipado da call sem
  dividendo. (artigo original; não relido nesta sessão)
- Hentschel (2003), *Errors in Implied Volatility Estimation*. Cotação ruim domina o erro da
  volatilidade implícita. (indicado por Francisco; não lido pelo revisor)
- Quant Stack Exchange, pergunta 1489, e Reddit r/quant. Resolução calibrada ao erro
  aceitável; não há número universal de passos. (resumo de Francisco; o primeiro site
  segue bloqueado para as ferramentas do revisor, o segundo não foi aberto; evidência de
  prática, não de método)
- Medições do revisor de 2026-11-19 e 2026-11-20: erro do par com 200 passos, 105 idas e
  voltas do atalho misto, 927 idas e voltas pela árvore. (medição própria, cotação
  sintética)

# Lab de Derivativos DL-PR06 - ChainService, fixture sintetica e latencia

Branch: `feat/dl-pr06-chain-service` (empilhada sobre
`feat/dl-pr05b-oplab-transport-client`)
GitHub Issue: pendente (sem card dedicado; segue o prompt v1 §7, as erratas
v1.1 e o handoff do card DL-PR05)
Status: implementado; aguarda PR e revisao

**Adendo local de 2026-11-19.** O cálculo worst-of permanece um diagnóstico de procedência. A autorização para publicar cotações fica fechada em A mesmo quando carimbo e propósito são trocados juntos.
[Conciliação da Fase 01](SDD_conciliacao_fase01.md)

## Objective

`ChainService` compoe o que DL-PR01..05 entregaram: **uma captura** (quatro
leituras: chain, ativo, taxas, status) -> normalizacao -> qualidade -> IV de
bid/ask/mid -> BSM com o sigma do mid, sempre com recusa explicada. Entrega
tambem a fixture sintetica de 100 europeias e o protocolo de latencia (CS10).

Nao-objetivos: servidor MCP e testes de contaminacao da tool (PR07), cache,
persistencia, americanas, superficie de vol, chamadas reais.

## Files

- `backend/derivatives/service/chain_service.py`: `Capture`, `PricedRow`,
  `PricedChain` (`schema_version = quimera-derivatives-priced-chain-v1`) e
  `ChainService` com `acquire`, `normalize`, `price`, `build`.
- `scripts/derivatives_make_synthetic_fixture.py`: gerador deterministico
  (semente registrada) e `tests/fixtures/derivatives/synthetic/` (4 JSON +
  `manifest.json` com hashes + `README.md`).
- `scripts/derivatives_latency_protocol.py`: 30 execucoes, p50/p95/p99 por
  passo, relatorio em `reports/derivatives/` (ignorado pelo Git).
- Testes: `test_chain_service.py` (21), `test_synthetic_fixture.py` (9),
  `test_latency_protocol.py` (4); duas fronteiras novas.

## Decisoes dentro do escopo

- **Tres passos publicos.** `acquire`, `normalize` e `price` sao publicos
  para o protocolo medir cada um sem que o servico tenha relogio proprio.
- **Captura = 4 leituras, ordem fixa, sem paralelismo.** A ordem fixa
  mantem o consumo de orcamento reproduzivel. Falha em qualquer leitura
  (ex.: ativo inexistente) propaga o erro tipado; nao ha chain parcial.
- **Carimbo worst-of da captura.** Procedencia = a da leitura da chain;
  proposito = `inherit_purpose` das quatro leituras. Uma unica leitura de
  teste rebaixa a captura inteira (testado rota a rota).
- **`PricedChain.purpose` e recalculado** (worst-of entre campo, carimbo e
  procedencia) a cada leitura: `model_copy(update=...)` nao valida no
  pydantic e nao pode promover fixture. Validacao a partir de JSON com
  proposito adulterado e rejeitada pelo validador da `Chain`.
- **Data de avaliacao = `now` no fuso `America/Sao_Paulo`.**
- **Recusa de chain inteira, explicada:** `unsupported_day_count:<valor>`,
  `missing_spot`, `missing_rate`, `invalid_rate` (taxa fora do dominio da
  capitalizacao, correcao de 2026-11-19), `calendar_coverage`,
  `expiry_before_valuation`. Cada linha recebe
  `chain_unpriceable:<motivo>` e nenhum numero. `calendar_365` existe no
  contrato YAML mas nao tem contagem implementada: e recusado, nunca
  ignorado em silencio.
- **Sigma do mid.** O preco BSM devolvido usa a IV do mid e portanto
  reproduz o mid: **isto nao e validacao** (ADR-0023); serve para obter as
  gregas na vol implicita. A validacao independente esta abaixo.
- **Vencimento sem series** devolve chain vazia, sem erro.

## Fixture sintetica

Captura coerente em `2026-11-05T17:00:00-03:00`: BOVA11, spot 150,00, Selic
14,9 % a.a., vencimento 2026-11-19 (10 dias uteis), 50 strikes de 137,50 a
162,00. Preco justo = BSM com smile `0.22 - 0.10 k + 0.90 k^2`
(`k = ln(K/F)`); bid arredondado para baixo e ask para cima ao centavo, com
meio-spread aleatorio de semente fixa. Procedencia `synthetic`, proposito
`test`; nunca e mercado. O teste de regeneracao tolera 1 centavo, porque
`erfc` pode diferir no ultimo bit entre plataformas (ver DL-PR04, Adendo 2).

## Validacao independente

O gerador conhece o sigma verdadeiro de cada strike. O teste
`test_true_smile_sigma_lies_inside_the_bid_ask_iv_bracket` exige que ele
caia dentro do intervalo `[IV_bid, IV_ask]` calculado pelo servico. Isso
so acontece se tempo (10/252), taxa (`ln(1.149)`), spot e a inversao
estiverem corretos de ponta a ponta — e nao depende de reproduzir um preco
com a propria IV.

## Latencia (CS10) — medido, nao declarado

Linux aarch64 (VM no Mac de Francisco), Python 3.12.16, 30 execucoes, 100
europeias, 100 precificadas:

| Passo | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| `t_acquire` | 0,39 | 0,44 | 0,52 |
| `t_normalize` | 0,72 | 0,88 | 0,98 |
| `t_price` | 20,81 | 25,52 | 26,10 |
| `t_serialize` | 1,07 | 1,14 | 1,15 |
| **total** | 23,01 | **27,81** | 28,34 |

Carga unica dos calendarios: 22 ms. Meta p95 < 2000 ms **atingida nesta
maquina virtual**. A medicao nativa em macOS ainda nao foi feita.

## Acceptance evidence (Linux aarch64, Python 3.12.16, `uv.lock`)

- `pytest tests/ --ignore=tests/integration`: rc 0, 7.964 passed, 15
  skipped. `pytest tests/unit/derivatives tests/architecture`: 5.827 passed,
  tambem em ordem invertida e embaralhada.
- Contador de leituras por captura: 4, na ordem chain, ativo, taxas, status.
- `mypy backend/ --strict`: 0 erros (151 arquivos); `pyright backend/`: 0.
- Producao: 163 linhas (<= 400); 0 linhas > 100 colunas; protegidos
  intocados; nenhuma dependencia nova.

## O que nao esta demonstrado

- p95 nativo no macOS (rodar `scripts/derivatives_latency_protocol.py`).
- Comportamento com dados reais: campos, horarios e sincronismo de spot
  (estado B).
- Chain com muitos vencimentos e milhares de series (so 100 linhas medidas).

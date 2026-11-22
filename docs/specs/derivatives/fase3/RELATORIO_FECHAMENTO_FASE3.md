# QUIMERA · Laboratório de Derivativos — fechamento da Fase 3 (22/11/2026)

De: Claude (planejador e revisor). Para: Francisco e o implementador (Codex).

**Resultado:** a Fase 3 está fechada no estado A. Existe em `backend/derivatives/ticket/` um
motor de boleta que roda sem rede e de forma determinística, com prévia versionada, gate
humano, travas de mercado, simulador local e recibo verificável. Uma linha de comando roda
uma sessão inteira de replay e publica os recibos. Nenhuma chamada real, nenhum token,
nenhuma conta, nenhuma tela e nenhuma ordem.

Este relatório foi escrito na revisão da cabeça `029a092` do PR #162, antes do squash.

## 1. Critério binário da SDD

A [SDD da Fase 3](SDD_FASE3_BLUEPRINT.md) fixou quatro condições. As quatro estão cumpridas.

| Condição | Situação | Evidência |
|---|---|---|
| Os 22 cenários de aceite passam | cumprida | um teste por cenário em `tests/unit/derivatives/ticket/test_engine.py` (tabela da seção 3); 68 testes do arquivo passam |
| Os testes de arquitetura passam | cumprida | `tests/architecture/test_ticket_boundaries.py`, 10 testes |
| Portão completo verde | cumprida | Linux x86_64, clone limpo: 11.227 aprovados, 16 pulados, 261 subtestes; `mypy --strict` e Pyright sem erro |
| Zero dependência nova | cumprida | `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `AGENTS.md` e `.claude/` sem diferença desde a base da fase (`ea9373f`) |

## 2. O que entrou

| PR | Commit na `main` | Cartão | Conteúdo |
|---|---|---|---|
| #154 | `1b16962` | [DL3-PR00](DL3-PR00.md) | VI americana não identificável na precisão do tick |
| #155 | `937b1cc` | DL3-ADR | ADR-0024 aprovada quanto ao desenho, sem vigência operacional |
| #156 | `19e6463` | [DL3-PR01](DL3-PR01.md) | modelo da boleta, versão, resumo criptográfico, trava de campo |
| #157 | `2e93532` | [DL3-PR02](DL3-PR02.md) | estados, transições e recibo encadeado |
| #158 | `88b7033` | [DL3-PR03](DL3-PR03.md) | sequenciamento de pernas, cobertura e reservas |
| #159 | `0bec461` | [DL3-PR04](DL3-PR04.md) | venue simulada, replay, travas de mercado e dois prazos |
| #160 | `e48e8ac` | [DL3-PR05a](DL3-PR05a.md) | decisão humana e gatilho de aviso |
| #161 | `51fd6d2` | [DL3-PR05b](DL3-PR05b.md), [R1](DL3-PR05b-R1.md), [R2](DL3-PR05b-R2.md) | motor da boleta |
| #162 | squash deste PR | [DL3-PR06](DL3-PR06.md), [DL3-PR06B](DL3-PR06B.md) | sessão de replay, linha de comando e este fechamento |

Tamanho na cabeça `029a092`: 2.222 linhas em `backend/derivatives/ticket/` e no script de
replay, em 15 arquivos. O pacote da boleta, o script e a arquitetura somam 430 testes. Desde
a base da fase entraram 2.237 linhas em `backend/` e `scripts/` e 3.346 em testes e fixtures.

## 3. Os 22 cenários e seus testes

| Cenário | Teste em `test_engine.py` |
|---|---|
| S01, S02 | `test_complete[S01]`, `test_complete[S02]` |
| S03, S22 | `test_expire_uncrossed_sale[S03]`, `test_expire_uncrossed_sale[S22]` |
| S04 | `test_s04_partial` |
| S05 | `test_auction[S05]` |
| S06 | `test_s06_discard` |
| S07 | `test_s07_cancel_buy` |
| S08 | `test_s08_cancel_partial_sale` |
| S09 | `test_s09_shared_coverage` |
| S10 | `test_s10_trigger_only_then_confirm` |
| S11 | `test_s11_reused_arm` |
| S12 | `test_s12_strategy` |
| S13 | `test_s13_expired_trigger` |
| S14 | `test_s14_refresh_and_cancel_blocked_market` |
| S15 | `test_s15_native_expiry` |
| S16 | `test_refused_confirmation_preserves_nonce[S16]` |
| S17 | `test_s17_edit_and_locked_refresh` |
| S18 | `test_s18_duplicate_confirm` |
| S19 | `test_s19_reconcile_and_resume` |
| S20 | `test_s20_pause_fill_resume` |
| S21 | `test_s21_close` |

Os três replays longos do piloto de D0 são as sessões `calmo`, `leilao` e `rapido`, com
quatro âncoras de recibo fixadas em `tests/unit/derivatives/test_ticket_replay_script.py`.

## 4. Como a fase andou

Quatro PRs de código passaram na primeira rodada (#156, #157, #159 e #160). Quatro
precisaram de mais de uma:

| PR | Rodadas | Motivo das rodadas extras |
|---|---|---|
| #154 | 2 | igualdade exata de um tick sem teste; depois, duas correções pedidas por Francisco |
| #158 | 2 | exposição parcial somava só a primeira compra; nove guardas sem teste |
| #161 | 3 | duas boletas na mesma recompra, foto divergente depois do envio, venda rejeitada reenviada; depois, colisão de `order_id` |
| #162 | 2 | ids que só diferem por maiúsculas, `after_seq=0` ambíguo, pasta de saída reaproveitada |

Parte dessas rodadas veio de lacuna dos cartões do planejador, não de erro do implementador.
Cada cartão registra quais pontos foram lacuna dele, na sua seção de revisão.

O que funcionou e fica para a próxima fase:

- Valor esperado de cartão conferido contra código que já existe, antes de publicar.
- Parecer do revisor formado antes de ler os relatórios da skill, lidos depois com SHA-256.
- Mutantes próprios do revisor, um por vez, e sondas contra os componentes reais.
- Portão em Linux x86_64 pelo revisor e em macOS pelo implementador.

## 5. O que a fase não entrega

Fora do escopo por decisão, não por falta:

- Tela, servidor, rede, OpLab real, token, conta, D1 e D2, persistência em banco.
- Margem, custos, histórico por estrutura e conciliação com a corretora.
- Trava de volatilidade. Os parâmetros de `config/ticket_sim.yaml` são sintéticos e não
  homologados.

Limites conhecidos do que foi entregue:

1. **O resultado em papel é teto otimista, não previsão.** O simulador casa pelo livro e
   pela quantidade exibida, sem fila e sem seleção adversa.
2. **Borboleta e venda para zerar uma comprada em perna única são recusadas** pelo plano de
   pernas. Trava e condor funcionam.
3. **A foto de posição não tem strike.** O par de proteção confere ativo-objeto, tipo,
   vencimento e multiplicador.
4. **No instante exato do fechamento** a decisão humana é gasta e a venue rejeita depois.
5. **Bloqueio por divergência não tem liberação** dentro da sessão. Ocupação de compra nunca
   enviada só sai no fim da sessão.
6. **Relatório impossível da venue ainda levanta exceção** no motor. A venue simulada não o
   emite.
7. **O recibo não prova que não foi trocado.** A âncora fica na mesma pasta e sob o mesmo
   usuário.
8. **Publicação inteira só na execução normal.** Queda de energia, morte abrupta do
   processo e Windows não foram ensaiados.
9. **A `main` segue sem proteção de branch.**

## 6. O que vem depois

As decisões de produto de Francisco (DP-01 a DP-19) dão a ordem. O registro vigente é a
Revisão 2, de 22/11/2026, hoje fora do repositório (`reports/fase03/`, SHA-256
`2c0eb6a1d3cc1dbe59fcd5ae28331e06cf8c0c2a9276aa79a54115b0a24300a9`). A Revisão 1 está em
[DECISOES_PRODUTO_DP01-DP19.md](DECISOES_PRODUTO_DP01-DP19.md).

| Cartão | Conteúdo | Resolve os limites |
|---|---|---|
| PR07A | origem da cobertura; bruto assinado, executado e projetado; DP-12, DP-13, DP-14, DP-15 | 4, 5 (em parte) e 6 |
| PR07B | zeragem e borboleta em simulação, com posição sintética | 2 e 3 |
| cartões próprios | margem, custos, histórico, integrações, âncora do recibo, volatilidade | 7 e o que depende de dado real |

Travas que continuam valendo: o DP-01 só vira código depois de adendo à G3 da ADR-0024
assinado por Francisco. A ADR-0024 segue sem vigência operacional. As proibições de
`CLAUDE.md` e do ADR-007 seguem vigentes: nenhuma integração com corretora, nenhuma ordem.

## 7. Para conferir por conta própria

```bash
git fetch origin && git log --first-parent --format='%h %s' ea9373f..origin/main
uv run python -m pytest tests/unit/derivatives/ticket tests/architecture/test_ticket_boundaries.py \
  tests/unit/derivatives/test_ticket_replay_script.py -q
uv run python scripts/derivatives_ticket_replay.py \
  --replay tests/fixtures/derivatives/synthetic/ticket/sessions/calmo.replay.json \
  --roteiro tests/fixtures/derivatives/synthetic/ticket/sessions/calmo.roteiro.json \
  --out /tmp/quimera_calmo && cat /tmp/quimera_calmo/resumo.json
```

O primeiro comando lista os nove commits da tabela da seção 2. O segundo deve dar 430
aprovados. O terceiro deve terminar com a boleta `T1` em `COMPLETED` e a âncora
`050354936eae64e316000a2f1570845a489dfe87f87f2dc5e70a4ceb742642f7`. A pasta `--out` não pode
existir antes.

# SDD — Fase 3 do Laboratório de Derivativos: motor da boleta em simulador (D0)

**Data:** 21/11/2026 · **Autor:** Claude · **Estado:** PUBLICADO para implementação.
**Base:** `main` = `ea9373f` · ADR-0024 aprovada quanto ao desenho (arquivo na worktree,
SHA-256 `fa0c8d7d4075a12808305526558ba6ad0fd79302d068b2f75fbc18aabe4a7748`).
**Cartões:** `DL3_CARDS.md` (DL3-PR00 a DL3-PR06 e o passo documental DL3-ADR).

> Leitura adotada do pedido "sem mais discussões": este SDD fixa as escolhas em aberto.
> Cada escolha minha está marcada **[padrão]** e pode ser trocada por adendo datado do
> Francisco. Nada aqui libera rede, token, conta, tela ou ordem real.

---

## 1. Objetivo verificável

Ao fim da Fase 3 existe, em `backend/derivatives/ticket/`, um motor de boleta que roda
**offline e de forma determinística**: recebe uma estrutura de até 4 pernas, produz prévia
versionada com resumo criptográfico, aceita edição humana, aplica as travas G1–G5 da
ADR-0024 e executa contra um simulador local com replay de cotações.

**Critério binário de fechamento:** os 22 cenários do §6 passam; os testes de arquitetura
do §5 passam; portão completo verde; zero dependência nova.

## 2. Não-objetivos (fechados)

Tela, FastAPI ou qualquer servidor; chamadas de rede; OpLab real, token, conta; D1 e D2;
Touch ID/passkey; persistência em banco; gráfico de payoff; gregas de carteira; Kronos;
agentes de tendência; MCP novo; dependência nova; alteração de `CLAUDE.md`, `AGENTS.md`,
`.claude/`, `pyproject.toml`, `uv.lock`.

## 3. Pesquisa que sustenta as escolhas

Limite de método: Quant StackExchange segue bloqueado para as minhas ferramentas e o Reddit
não retornou resultado utilizável. **Nenhuma afirmação abaixo vem deles.**

| Tema | O que a fonte sustenta | Escolha no projeto |
|---|---|---|
| Preenchimento de ordem limitada em simulador | Preencher "no toque" é otimista; simuladores sérios atribuem posição de fila e só preenchem quando o volume negociado atravessa essa posição (arXiv 2409.12721; material educativo NexusFi, viés comercial) | Modelo **cruzamento do livro**: só executa quando o lado oposto do livro cruza o limite, limitado à quantidade exibida. Nunca pelo último negócio. |
| Seleção adversa em ordem limitada | Execuções de ordem passiva tendem a ser seguidas de movimento contrário (arXiv 2407.16527) | O relatório do simulador declara que o resultado em papel é **teto otimista**, não previsão. |
| VI com vega muito baixa | Em opção muito dentro ou fora do dinheiro o preço quase não responde à volatilidade; erro mínimo de preço vira erro grande de VI (arXiv 1308.6759, 1901.08943, 1610.04760) | Regra de **identificabilidade por faixa de tick** (DL3-PR00). |
| Estratégia × perna na B3 | Negócio de estratégia não dispara stop nem atualiza último negócio das pernas (Manual B3, citado na ADR; **lido pelo Codex, não conferido por mim**) | Evento de replay distingue `SIMPLE` de `STRATEGY`; cenário S12. |

Evidência toda de nível baixo a moderado para o nosso caso: os artigos tratam de futuros e
ações líquidas, não de opções da B3. Por isso o modelo é o mais conservador que continua
determinístico.

## 4. Arquitetura

```
backend/derivatives/ticket/
  models.py       Perna, rascunho, prévia, versão (pydantic, imutáveis, Decimal)
  digest.py       JSON canônico + SHA-256 da parte autorizável
  state.py        TicketState, OrderState, tabela de transições
  receipt.py      Recibo só de acréscimo, encadeado por hash
  sequencing.py   Ordem das pernas, cobertura, reservas exclusivas (G2, G3)
  guards.py       Travas de mercado: Cuidado × Bloqueado (G1)
  venue.py        Protocolo ExecutionVenue
  paper_venue.py  Simulador com replay (modelo cruzamento do livro)
  replay.py       QuoteEvent, TradeEvent, leitor de fixture
  gate.py         HumanDecision: única origem de confirmação e cancelamento
  trigger.py      Engatilhar: só avisa e preenche
  engine.py       Orquestra: propor, editar, atualizar, confirmar, cancelar, pausar
config/ticket_sim.yaml
tests/unit/derivatives/ticket/ · tests/architecture/test_ticket_*.py
tests/fixtures/derivatives/synthetic/ticket/
```

Decisões **[padrão]**:

1. **Dinheiro em `Decimal`, quantidade em `int`.** Preço com passo de 0,01. Nada de `float`
   na boleta. O que vem dos motores de preço (float) entra como informação, nunca como
   limite assinado sem arredondamento explícito ao tick, a favor do usuário.
2. **Resumo criptográfico cobre só a parte autorizável:** ambiente, pernas (símbolo, lado,
   quantidade, limite), débito máximo ou crédito mínimo, teto bruto, exposição parcial,
   prazo de envio, validade da ordem, identificador da foto de cotação. Atualização só
   informativa não muda o resumo.
3. **Ambiente é sempre `SIMULATED`** nesta fase. O valor `REAL` não existe no enum.
4. **Campo editado pelo humano fica travado.** `refresh` de mercado nunca escreve em campo
   travado. Mudança em campo autorizável gera versão nova e mata a confirmação anterior.
5. **Confirmação é um objeto, não um booleano.** `HumanDecision` nasce só em `gate.py`,
   carrega o resumo da versão, a ação e um identificador de uso único. O motor rejeita
   resumo divergente, decisão repetida ou vencida.
6. **Dois prazos distintos:** `send_deadline` (até quando o motor envia pernas) e
   `order_validity` (até quando a ordem vive na venue). A venue declara quais validades
   garante; pedido fora disso é recusado antes do envio. Sem cancelamento automático.
7. **Ordem das pernas:** vai primeiro a perna que aumenta posição comprada ou reduz
   posição vendida. A seguinte só é liberada na quantidade executada e não reservada.
8. **Sem aleatoriedade, sem relógio do sistema.** O tempo vem dos eventos do replay.
9. **Estados.** `TicketState`: `DRAFT, ARMED, TRIGGERED, CONFIRMED, WORKING, COMPLETED,
   STOPPED, DENIED, EXPIRED, UNCERTAIN`. `OrderState`: `PENDING_SEND, LIVE, PARTIAL, FILLED,
   CANCEL_REQUESTED, CANCELLED, EXPIRED, REJECTED, UNCERTAIN`. Rótulos em português da ADR
   ficam em uma tabela de apresentação, fora da lógica.
10. **Modelo de execução do simulador:** compra executa quando `ask <= limite`, venda quando
    `bid >= limite`, pela quantidade exibida naquele evento; saldo fica vivo. Em fase
    `AUCTION` ou `SUSPENDED` nada executa no contínuo; a fixture pode injetar execução de
    leilão e recusa de cancelamento (cenário S05).

## 5. Regras de arquitetura (viram teste)

- `backend.derivatives.ticket` **não importa**: `httpx`, `requests`, `socket`, `litellm`,
  `openai`, `anthropic`, `backend.derivatives.oplab.client`, `...oplab.transport`,
  `backend.derivatives.mcp`, `backend.gateway`.
- `backend.derivatives.mcp` **não importa** `backend.derivatives.ticket`.
- `HumanDecision` só é construído em `ticket/gate.py`; fora dos testes, só `cli.py` importa
  `gate`.
- Nenhum esquema de ferramenta MCP contém campo `approve`, `confirm`, `execute`, `cancel`,
  `arm` ou `send`.
- `oplab/routes.py` continua com `ALLOWED_METHOD = "GET"` e um único host.
- O enum de ambiente não contém `REAL`.

## 6. Cenários de aceite (22)

| # | Cenário | Resultado exigido |
|---|---|---|
| S01 | Trava de alta com calls, compra e venda completas | `COMPLETED`; débito ≤ assinado |
| S02 | Trava de baixa com puts, completa | `COMPLETED` |
| S03 | Compra executa, venda nunca cruza | `STOPPED`; posição só comprada; exposição = prêmio pago |
| S04 | Compra parcial 3 de 10 | Venda liberada em 3, nunca mais |
| S05 | Compra 3 de 10, leilão, cancelamento pendente ou recusado, +1 executa | 4 executadas, 6 de saldo, nenhuma perna nova |
| S06 | Negar proposta | `DENIED`; zero chamadas à venue |
| S07 | Cancelar com ordem viva | `CANCEL_REQUESTED` até a venue confirmar |
| S08 | Execução entre pedido e confirmação de cancelamento | Recibo guarda os dois eventos; saldo correto |
| S09 | Duas boletas disputam a mesma proteção | Reserva exclusiva; a segunda não vende |
| S10 | Gatilho cruza | Um aviso; boleta preenchida; zero ordens até confirmar |
| S11 | Condição já verdadeira ao armar | Recusa armar |
| S12 | Negócio de estratégia cruza, negócio simples não | Só dispara se a fonte declarada for a de estratégia |
| S13 | Gatilho expira | `EXPIRED`; não rearma |
| S14 | Cotação velha, leilão ou livro inválido | Executar bloqueado; cancelar permitido |
| S15 | Prazo de envio vence com compra parcial | Nenhuma perna nova; ordem viva segue a validade nativa |
| S16 | Validade pedida que a venue não garante | Envio recusado antes de qualquer ordem |
| S17 | Edição humana e refresh de mercado | Campo travado intacto; versão nova; resumo antigo rejeitado |
| S18 | Confirmação repetida | Um único envio |
| S19 | Timeout da venue | `UNCERTAIN`; bloqueia novos envios; sem reenvio |
| S20 | Pausa | Não envia nem cancela; retomar exige decisão humana |
| S21 | Desmontagem | Recompra da vendida antes de vender a comprada |
| S22 | Perna restante fora do limite assinado | Para e mostra a posição; limite não se move |

## 7. Plano de PRs

| PR | Entrega | Depende de | Teto |
|---|---|---|---|
| DL3-ADR | ADR-0024 em `main`, só documento | — | docs |
| DL3-PR00 | VI não identificável perto do intrínseco | — | ≤ 200 linhas |
| DL3-PR01 | Modelo, versão, resumo, trava de campo, testes de arquitetura | — | ≤ 350 |
| DL3-PR02 | Estados, transições e recibo | PR01 | ≤ 300 |
| DL3-PR03 | Sequenciamento, cobertura e reservas | PR02 | ≤ 300 |
| DL3-PR04 | Venue, simulador, replay, travas de mercado, dois prazos | PR03 | ≤ 400 |
| DL3-PR05 | Motor, gate, Engatilhar, pausa, 22 cenários | PR04 | ≤ 400 |
| DL3-PR06 | CLI de replay sem tela, relatório e fechamento | PR05 | ≤ 250 |

DL3-ADR e DL3-PR00 podem andar em paralelo com PR01.

**Sobre "duração do piloto":** em D0 sem tela e sem dado real, piloto medido em dias não mede
nada. O piloto de D0 é o roteiro de 22 cenários mais 3 replays longos sintéticos (PR06).
Piloto com calendário só faz sentido em D1.

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Simulador otimista demais | Modelo de cruzamento do livro; relatório declara "teto otimista" |
| Motor virar framework | Teto por PR; sem plugin, sem persistência, sem servidor |
| Vazamento de caminho de ordens para o MCP | Testes de arquitetura desde o PR01, com mutantes |
| Float em dinheiro | `Decimal` obrigatório; teste que rejeita float nos modelos |
| Regra de VI recusar caso bom | PR00 mede as 69 referências e para se houver recusa indevida |
| ADR fora do `main` | DL3-ADR primeiro; `CLAUDE.md` intocado, proibições seguem vigentes |

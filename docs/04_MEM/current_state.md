# current_state.md — OPENCLAW Operational Memory

> Volatile project state for Codex, Claude Code, ChatGPT Thinking, and human
> review. Read after `docs/04_MEM/AGENT_CONTEXT.md`. Update at the end of
> meaningful sessions.

**Última atualização:** 2026-11-25 · **Turno:** Claude (planejador). **Fase 4 em andamento:** DL4-PR00 e DL4-PR01 integrados; DL4-PR02 com cartão escrito.

## Fase 04 — A boleta que Francisco consegue usar — EM ANDAMENTO

Blueprint: `claude/derivativos/FASE4_BLUEPRINT.md` (projeto). Cartões versionados em
`docs/specs/derivatives/fase4/`. Tudo em simulador D0, com dado sintético, sem rede e sem
corretora. A ADR-0024 segue sem vigência operacional; `CLAUDE.md` e a ADR-007 seguem
vigentes.

Fila decidida por Francisco em 24/11/2026:

| PR | Entrega | Situação |
|---|---|---|
| DL4-PR00 | piso e lock do pydantic em 2.14.4 | integrado, PR #186, `128e78d` |
| DL4-PR01 | contrato de visão (`ticket_view`, `formato` 1) | integrado, PR #188, `565136d` |
| DL4-PR02 | três roteiros de trava de BOVA11 e gabarito do M1 | cartão escrito em 25/11/2026 |
| DL4-PR03 | tela HTML estática; prova de uso do M1 (18 de 18) | — |
| DL4-PR04 a PR06 | confirmar uma versão, acompanhar por perna, visor de recibo (M2) | — |
| DL4-PR07 | alvo de spread que só avisa (M3) | — |
| DL4-PR08 e PR09 | leitura OpLab e confiabilidade da VI (M4) | condicionais; exigem liberação assinada do D1 |

Entregue pelo DL4-PR00:
- `pyproject.toml` declara `pydantic>=2.14.4,<3`; o lock trava 2.14.4. O delta foi de
  quatro pacotes (pydantic, pydantic-core, typing-extensions, typing-inspection).
- `tests/architecture/test_pydantic_floor.py` impede o piso de voltar abaixo de 2.14.2 e o
  portão de rodar sobre ambiente que não é o do lock.
- Os avisos GHSA-qpmf-fgh3-ff25 e GHSA-3r8g-cqwr-jr29 não atingiam a configuração do
  QUIMERA. A atualização foi preventiva.

Entregue pelo DL4-PR01:
- `TicketEngine.reading(now)`: consulta sem efeito do que a confirmação conferiria.
  `confirm` usa o mesmo trecho (`_admissible`); ordem e texto das recusas não mudaram.
- `backend/derivatives/ticket/view.py`: `ticket_view(session, ticket, now)` devolve pernas,
  custo, dois riscos, cotação e guarda por perna, guarda do conjunto e situação de avanço
  com o motivo literal do motor. Esquema publicado em
  `docs/specs/derivatives/fase4/schemas/visao.schema.json`.
- Adendo 1 (Codex, autorizado por Francisco): a visão não depende do contexto decimal de
  quem chama.
- Portão da cabeça `af60eee`: 11.685 aprovados, 16 pulados; mypy estrito e Pyright limpos.

Decisões de Francisco que valem para os próximos cartões:
- L3: mercado adverso é só o que `guards.assess` já emite. Condição nova é cartão de motor.
- L4: o risco aparece em dois números, com rótulos distintos: desembolso se só a compra
  executar e pior resultado no vencimento. O rótulo é «pior resultado», não «perda máxima».
- Lembrete para o DL4-PR09 (25/11/2026): VI, gregas e preços teóricos seguem em float64,
  sem arredondar cedo; oráculos com `mpmath` e estudo de convergência das malhas; a
  incerteza da VI vem do spread e da vega, não do número de casas.

Pendências sem cartão:
- `tests/integration` tem 4 falhas conhecidas na `main`, anteriores à Fase 4 e iguais nas
  duas versões do pydantic. São defeitos dos próprios testes. Precisam de cartão de
  correção antes do M4. Até lá, a linha de base de cada cartão é «as mesmas 4, pelos IDs».
- `Literal[1]` do `formato` da visão aceita `true` e `1.0` na leitura. Endurecer quando a
  tela (DL4-PR03) passar a ler a visão.
- A fonte do spread para o gatilho do DL4-PR07 não está decidida: o gatilho atual olha uma
  série só.

### Próximo turno (aviso ao implementador e ao revisor)

- **Implementador (Codex):** o próximo cartão é o **DL4-PR02**
  (`claude/derivativos/cards/DL4-PR02_SUPERCARD.md`, no projeto), com o patch
  `DL4-PR02_PROTOTIPO.patch`. Só fixtures e testes; nenhum arquivo de produção muda. Os
  sete SHA-256 do §2 do cartão decidem os bytes. A base é a `main` com este commit de
  documentação: em relação a `565136d`, só `docs/04_MEM/current_state.md` difere.
- **Revisor:** em chat próprio do PR. Recebe cartão, diff e evidências; roda por conta
  própria o B3, o B5 e os mutantes 1, 9 e 11; não repete o portão nem escreve o próximo
  cartão. Linha de base da integração: as mesmas 4 falhas conhecidas, pelos IDs.
- **Planejador:** escreve o DL4-PR03 (tela HTML e prova de uso do M1) depois do GO.

## Depois da Fase 3 — decisões de produto no simulador (D0) — EM ANDAMENTO

Trabalho sobre o mesmo motor, guiado pelo registro de decisões de Francisco
([Revisão 2](../specs/derivatives/fase3/DECISOES_PRODUTO_DP01-DP19_R2.md), que substitui a
Revisão 1). O PR07A foi cortado em três pelo planejador.

| Cartão | Conteúdo | Situação |
|---|---|---|
| [DL3-PR07A1](../specs/derivatives/fase3/DL3-PR07A1.md) | DP-14, DP-12, DP-15 e higiene | MERGEADO (PR #163) |
| [DL3-PR07A2](../specs/derivatives/fase3/DL3-PR07A2.md) | bruto assinado, executado e projetado; série de proteção | MERGEADO (PR #164) |
| [DL3-PR08A](../specs/derivatives/fase3/DL3-PR08A.md) | resultado da estrutura no vencimento | MERGEADO (PR #165) |
| [DL3-PR08B](../specs/derivatives/fase3/DL3-PR08B.md) | a estrutura montada em parte: posição executada ao lado da planejada | MERGEADO (PR #166) |
| [DL3-PR08C](../specs/derivatives/fase3/DL3-PR08C.md) | borboleta de puts, travas e iron condor conferidos, com quantidades, multiplicador e custos | MERGEADO (PR #167) |
| [DL3-PR08D](../specs/derivatives/fase3/DL3-PR08D.md) | estimativa antes do vencimento, compondo os preços das pontes da Fase 2 | MERGEADO (PR #169) |
| [DL3-PR08E](../specs/derivatives/fase3/DL3-PR08E.md) | calendário oficial da B3 de 2027 (OC 057/2026-VNC) | MERGEADO (PR #170) |
| [DL3-PR07A3](../specs/derivatives/fase3/DL3-PR07A3.md) | cada boleta vende coberta só pelas próprias compras | MERGEADO (PR #171) |
| [DL3-PR07A3B](../specs/derivatives/fase3/DL3-PR07A3B.md) | autorização para usar a sobra de boleta parada: prévia, resumo, plano e livro | MERGEADO (PR #172) |
| [DL3-PR07A3C](../specs/derivatives/fase3/DL3-PR07A3C.md) | o motor usa a sobra autorizada de boleta parada; recibo com origem em cada pedido e execução | MERGEADO (PR #173) |
| [DL3-PR07A3D](../specs/derivatives/fase3/DL3-PR07A3D.md) | uma só ordem para as autorizações (série, origem); testes de cancelamento | MERGEADO (PR #174) |
| [DL3-PR07A4](../specs/derivatives/fase3/DL3-PR07A4.md) | DP-13, 1ª parte: relato contraditório vira divergência registrada | MERGEADO (PR #175) |
| DL3-PR07A4, acompanhamento | conferência dos relatos de ordem incerta; `report_check.py` | MERGEADO (PR #176) |
| [DL3-PR07B1](../specs/derivatives/fase3/DL3-PR07B1.md) | DP-02: zeragem de posição comprada em perna única | MERGEADO (PR #177) |
| [DL3-PR07B2](../specs/derivatives/fase3/DL3-PR07B2.md) | DP-03: montagem da borboleta (strike na foto; vendida com mais de uma proteção) | MERGEADO (PR #178) |
| [DL3-PR07A5](../specs/derivatives/fase3/DL3-PR07A5.md) | DP-13, 2ª parte: fato externo legítimo, reação do livro e do motor | MERGEADO (PR #179) |
| [DL3-PR07A6](../specs/derivatives/fase3/DL3-PR07A6.md) | DP-13, 2ª parte: entrada do fato pela sessão e pelo roteiro; registro sem boleta de origem; aviso a todas as boletas da conta | MERGEADO (PR #180) |
| [DL3-PR07C1](../specs/derivatives/fase3/DL3-PR07C1.md) | cota do plano na proteção disputada entre duas vendas | MERGEADO (PR #181) |
| [DL3-PR07B3](../specs/derivatives/fase3/DL3-PR07B3.md) | DP-03: desmontagem da borboleta com conta exata | MERGEADO (PR #182) |
| [DL3-PR07D1](../specs/derivatives/fase3/DL3-PR07D1.md) | andamento por perna, rótulo da parada e projetado após cancelamento humano | MERGEADO (PR #183) |
| [DL3-PR07E1](../specs/derivatives/fase3/DL3-PR07E1.md) | formato versionado do recibo e do resumo; esquema de saída da prévia | MERGEADO (PR #184) |
| [DL3-PR07F1](../specs/derivatives/fase3/DL3-PR07F1.md) | fecho: guarda da versão do pydantic e recibo da sessão como cópia | MERGEADO (PR #185) |

Entregue pelo DL3-PR07A1 (37 linhas de produção):
- No instante exato da validade o motor recusa antes de gastar a decisão, ocupar o livro
  ou enviar. A janela de envio é uma só: `now <= send_deadline` e `now < order_validity`.
  O instante exato do prazo de envio continua permitido.
- Boleta que entra em `STOPPED` libera a ocupação das compras que nunca tiveram ordem,
  pelos dois caminhos (laço de envio e conciliação). Compra enviada, parcial ou incerta
  não muda. Divergência aberta na própria conta retém a ocupação.
- Rótulos em português separados: `TICKET_LABELS_PT` e `ORDER_LABELS_PT`, com os textos
  decididos por Francisco. `LABELS_PT` deixou de existir. O log da linha de comando
  mostra rótulo e código. O `resumo.json` segue com códigos.
- As três sessões oficiais saem idênticas byte a byte; as quatro âncoras não mudaram.
- Portão da cabeça `101147f`, Linux x86_64 limpo: 11.258 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro. 30 mutantes do revisor, 29 mortos.

Entregue pelo DL3-PR07A2 (62 linhas de produção, só visibilidade):
- `TicketEngine.gross()` devolve bruto assinado (`gross_cap`), executado (preço real ×
  quantidade já aplicada) e projetado. O projetado conta tudo que falta ao preço assinado
  enquanto a boleta ainda pode enviar, e só o saldo das ordens abertas depois que ela
  termina. Ordem incerta só entra no executado depois da conciliação.
- O recibo traz `gross` em toda execução e em todo registro que conclui ou para a
  boleta, e `protection` no registro de pedido de cada venda. O `resumo.json` traz
  `bruto` por boleta. A prévia assinada e os resumos criptográficos não mudaram.
- Três âncoras oficiais mudaram por desenho (`calmo` T1, `leilao` T1, `rapido` T1); a de
  `rapido` T2 ficou igual. Os valores estão no §6 do cartão.
- Portão da cabeça `10076d3`: Linux ARM64 pelo implementador e Linux x86_64 pelo
  revisor, ambos com 11.267 aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright
  sem erro. 30 mutantes do revisor, 28 mortos.

Regra de processo (Francisco, 22/11/2026): o implementador executa o portão Linux via
MCP/Docker na cabeça candidata e entrega cabeça, arquitetura, imagem, comandos, log e
manifesto. O revisor analisa e não repete a suíte. Desde o DL3-PR08B o contêiner do
implementador é Linux x86_64 (emulado em Mac ARM64, conferido pelo cabeçalho ELF).

Frente PR08 — análise de estruturas (autorização de Francisco de 22/11/2026, em
[AUTORIZACAO_ANALISE_ESTRUTURAS_2026-11-22.md](../specs/derivatives/fase3/AUTORIZACAO_ANALISE_ESTRUTURAS_2026-11-22.md)).
Por decisão dele, esta frente passa à frente do PR07A3, do PR07A4 e do PR07B.

Entregue pelo DL3-PR08A (`pricing/expiry_payoff.py`, 140 linhas, só biblioteca padrão):
- Resultado no vencimento de estrutura de 1 a 8 pernas de opções do mesmo ativo e do
  mesmo vencimento: resultado por perna, total depois dos custos, entrada (positivo é
  débito), equilíbrios como fração exata, ganho máximo e perda máxima, com ilimitado
  marcado como ilimitado. Dinheiro em `Decimal` exato; `float` é recusado.
- Primeira prova: a borboleta de calls 95/100/105 com débito 2 dá −2, +3 e −2, com
  equilíbrios em 97 e 103.
- O módulo não se liga ao motor da boleta, não estima valor antes do vencimento e não
  trata vencimentos diferentes.
- Os três testes que faltavam no DL3-PR07A2 entraram.
- Portão da cabeça `6a8cee4`: Linux ARM64 pelo implementador e x86_64 pelo revisor, 11.303
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. 30 mutantes do
  revisor mortos. Sem divergência contra o oráculo do planejador em 20.000 estruturas.

Referências (decisão final de Francisco, 22/11/2026): o QuantLib segue como oráculo
principal de preço. O OptionLab é usado fora da aplicação, só para conferir estratégias.
Nenhum dos dois é dependência do repositório. No DL3-PR08A o OptionLab 1.9.7 coincidiu
com o módulo em 70.007 preços, com diferença máxima de 1,4 × 10⁻¹⁴.

Limite conhecido: expoentes decimais muito distantes entre si custam memória e tempo no
módulo de resultado. O cartão que ligá-lo a dados externos fixa um limite de escala.

Entregue pelo DL3-PR08B (`pricing/partial_position.py`, 89 linhas):
- `partial_view(plan, executions)` devolve o perfil planejado (preços assinados), as
  pernas e o perfil da posição executada (preços efetivos, uma perna por série e preço)
  e o pendente por série. Só execução confirmada entra. Sem execução, `executed` é `None`.
- As três funções de `expiry_payoff` ganharam `max_legs` (1 a 64, padrão 8). O plano
  segue limitado a oito pernas; a posição executada vai até 64 pares de série e preço.
- Exemplo fixado em teste: com só as duas vendas centrais da borboleta executadas, a
  posição tem crédito de 7,00 e perda ilimitada, enquanto o plano perde no máximo 2,00.
- Não há ligação com o motor da boleta nem com o recibo. A regra de cobertura continua
  no livro de reservas (PR07A3 e PR07B).
- Portão da cabeça `9ca6b8e`, pelo implementador: Linux x86_64 e macOS, 11.336
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. Por decisão de
  Francisco o revisor não repetiu a suíte; conferiu as evidências e rodou o oráculo
  próprio em 8.000 planos aleatórios, sem divergência.

Entregue pelo DL3-PR08C (só testes; nenhuma linha de `backend/` mudou):
- 20 casos novos com valores escritos à mão: borboleta de puts, as quatro travas, iron
  condor, condor e borboleta com quantidade, multiplicador e custos ilustrativos, e o
  condor montado em parte.
- Exemplo fixado em teste: com só as duas vendas do condor executadas, a posição tem
  crédito de 5,00 e perda ilimitada, enquanto o plano perde no máximo 2,00.
- Fechadas as duas lacunas do DL3-PR08B: plano com exatamente oito séries e símbolo que
  não é texto.
- Quatro defeitos plantados passavam pelos testes anteriores e agora são detectados:
  resultado por perna em ordem invertida; resultado por perna sem o multiplicador; plano
  de oito séries recusado; símbolo não textual aceito.
- Portão da cabeça `1ceba84`, pelo implementador: Linux x86_64 e macOS, 11.356
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. O revisor não
  repetiu a suíte; conferiu o manifesto de 86 evidências e comparou os 80 valores
  escritos nos testes com o oráculo próprio, sem divergência.
- Os custos dos cenários são ilustrativos. A tabela real segue pendência de Francisco.

Observação de processo, fora do portão do cartão: numa rodada extra de integração no Mac,
`test_pr09_pg_dump_restore_verify_live` encontrou o Postgres do host e gerou um `pg_dump`
em pasta temporária antes de falhar. O implementador relatou ter excluído a cópia sem
abri-la. Conferência posterior de Francisco, no Mac, em 23/11/2026: a busca por arquivos
`quimera_pg18_*.dump` na pasta temporária achou só três arquivos sintéticos de 19 bytes,
criados pelo teste unitário `test_manifest_schema_hash_and_restore_update`; nenhum dump
do teste de integração. Desde o DL3-PR08D o cartão manda rodar `tests/integration` só no
contêiner Linux isolado, e o implementador cumpriu.

Entregue pelo DL3-PR08D (`pricing/pre_expiry.py`, 90 linhas):
- `pre_expiry_estimate(legs, outcomes)` recebe um `PricingOutcome` por perna, vindo das
  pontes da Fase 2 (`price_contract`, BSM; `price_american_contract`, CRR), e devolve
  entrada, valor teórico, resultado depois dos custos, resultado por perna e os mesmos
  `outcomes`. O módulo não calcula preço teórico nem escolhe premissa.
- Recusa preço recusado pela ponte (com a posição da perna e o motivo), preço de outra
  série e preços calculados com preço do ativo ou prazo diferentes. Vencimentos
  diferentes ficam fora da cobertura.
- Fixado em teste: no dia do vencimento, a estimativa é exatamente o resultado no
  vencimento, para as borboletas de calls americanas e de puts europeias.
- Conferência com o QuantLib 1.44, fora do repositório, em 18 combinações de perna e
  preço do ativo: puts europeias até 1,4 × 10⁻¹⁴; calls americanas até R$ 0,0012 por
  unidade, que é o erro de discretização da árvore de 200 passos.
- Portão da cabeça `0266c58`, pelo implementador: Linux x86_64 e macOS, 11.405
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. O revisor não
  repetiu a suíte; conferiu o manifesto de 101 evidências e rodou os 39 testes do seu
  protótipo independente contra o módulo entregue, todos aprovados.
- Limitação conhecida, da mesma classe da do `expiry_payoff`: com expoentes decimais
  muito distantes (prêmio `1E-900000000`), a conta exata esgota a memória em vez de
  recusar. Só alcançável por entrada construída de propósito; não há dado externo
  ligado. O cartão do limite de escala cobre os dois módulos.

ADR-0024, Adendo 1 (PR #168, commit de autoria de Francisco, integrado em 23/11/2026):
G3 ganha a modalidade B, com teto em reais para o pico estimado de garantia adicional
da conta, e a exceção da venda a preço melhor. A modalidade A (teto bruto) não muda. O
adendo é desenho: não autoriza implementação, acesso real nem ordens. Registra duas
condições para a liberação futura do D1 e a prova de saída do piloto em papel. A DP-01
deixa de depender de adendo e passa a depender de cartão próprio, ainda não escrito.

Entregue pelo DL3-PR08E (só dados, evidência e testes; nenhuma linha de `backend/` mudou):
- O pregão da B3 de 2027 passa de `unknown` a oficial, na revisão r4 de
  `config/calendars/b3_calendar_2027.yaml`, com o Ofício Circular 057/2026-VNC, de
  17/11/2026, arquivado como evidência. São 249 pregões e 12 fechamentos em dia de semana,
  iguais, data a data, à projeção que a r3 guardava.
- A cobertura da B3 é 2026 e 2027. 2028 continua recusado: a B3 não publicou.
- A Quarta-feira de Cinzas (10/02/2027) conta como dia útil inteiro. Horário intradiário
  segue fora.
- Fixado em teste: 35 dias úteis de 23/11/2026 ao vencimento de 15/01/2027; contagens que
  atravessam o ano; as doze terceiras sextas de 2027.
- Portão da cabeça `34c132e`, pelo implementador: Linux x86_64 e macOS, 11.416
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. O revisor não
  repetiu a suíte; conferiu o manifesto de 59 evidências, leu o Quadro A no PDF arquivado
  e rodou conferidor próprio da r4 contra a r3 (preservação, quatro hashes internos,
  linhas da B3, hash do PDF).

Pendente para um próximo cartão de testes (o código está certo): o teste sintético da
projeção não fixa o `projection_id` que liga a projeção à versão. Um carregador que
promovesse só projeções ligadas por esse campo passaria pelos testes.

Com o DL3-PR08E, a frente de análise de estruturas aberta pela carta de 22/11/2026 fica
entregue nos itens 1 a 4, com duas pendências registradas: limite de escala
(`expiry_payoff` e `pre_expiry`) e vencimentos diferentes na estimativa.

Entregue pelo DL3-PR07A3 (`ticket/sequencing.py`, só `ReservationBook._capacity`):
- A venda de uma boleta só é liberada por compras executadas dela mesma, na montagem e
  na desmontagem. Antes, o livro somava as compras de todas as boletas da conta.
- Dois comportamentos corrigidos, fixados em teste pelo motor: a sobra de uma boleta
  parada não é mais usada por outra sem autorização; uma boleta pausada conserva a
  própria proteção e vende ao ser retomada.
- Continuam por conta: capacidade de recompra de posição vendida, unicidade das
  execuções, foto de posição e bloqueio por divergência.
- Motor, prévia, recibo e roteiro de replay não mudaram. As âncoras oficiais das sessões
  são as mesmas.
- Portão da cabeça `f0485d0`, pelo implementador: Linux x86_64 e macOS, 11.422
  aprovados, 16 pulados, 261 subtestes; mypy estrito e Pyright sem erro. O revisor não
  repetiu a suíte; conferiu o manifesto de 72 evidências e rodou os dez cenários do seu
  protótipo contra o módulo entregue.
- Enquanto o DL3-PR07A3B não entra, a sobra de uma boleta não é usada por nenhuma outra.

Decisões de Francisco de 23/11/2026 para o DL3-PR07A3B: só vale a sobra de boleta já
parada; a boleta que usa a sobra pode ser só de venda. Ordem confirmada por ele:
PR07A3B, PR07A4, PR07B.

Entregue pelo DL3-PR07A3B (camada pura; 62 linhas líquidas de produção):
- `CoverageGrant` (série, boleta de origem, quantidade máxima) e o campo `coverage` na
  boleta e na prévia, com até quatro autorizações. A lista entra no resumo criptográfico,
  ordenada por série e origem, e no corpo da prévia gravado no recibo, na ordem informada.
  Com a lista vazia, a chave não aparece: recibos e âncoras de hoje ficam idênticos.
- Plano: o autorizado soma à proteção da série; boleta só de venda tem plano quando a
  autorização cobre a venda.
- Livro: `close(conta, boleta)` marca a boleta como parada; `available` e `reserve`
  aceitam `origin`. A sobra de uma origem parada é reservada com exclusividade, até o teto
  autorizado. Boleta parada não vende mais com as próprias compras.
- **O motor ainda recusa boleta com autorização**, antes de gravar a prévia. Nada muda
  para quem opera até o DL3-PR07A3C.
- As duas lacunas de teste do DL3-PR07A3 foram fechadas (W15 e W16).
- Portão da cabeça `361238c`, pelo implementador: Linux x86_64 e macOS, 11.438 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 24 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 102 evidências e rodou os 18
  cenários do seu protótipo e sete sondas contra os módulos entregues.

Entregue pelo DL3-PR07A3C (`engine.py` +13 linhas; `sequencing.py` +1):
- O motor aceita boleta com autorização. Ao entrar em `STOPPED` sem divergência aberta na
  conta, marca a boleta como parada no livro, e a sobra dela passa a existir. Boleta
  concluída não cede sobra; conta com divergência não marca.
- Na venda, o motor usa primeiro as compras próprias e depois cada origem autorizada, na
  ordem da prévia (desde o DL3-PR07A3D, sempre série e depois origem), com uma ordem e uma
  reserva exclusiva por origem.
- O recibo grava `origin` no pedido e em cada execução de ordem coberta por sobra. Ordem
  coberta por compras próprias não tem a chave; recibos e âncoras de hoje ficam idênticos.
- Sobra tomada por outra boleta: a confirmação é recusada antes de gastar a decisão. A
  boleta que depende de sobra indisponível vende o que existe e para.
- Trava no livro: boleta parada não reserva nada, nem a sobra de outra.
- As três lacunas de teste do DL3-PR07A3B foram fechadas (K1, K2 e K3).
- Portão da cabeça `527e070`, pelo implementador: Linux x86_64 e macOS, 11.456 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 22 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 116 evidências e rodou os 16 cenários
  do seu protótipo e quatro sondas contra os módulos entregues.

Decisões de Francisco de 23/11/2026, depois do DL3-PR07A3C (texto completo no projeto, em
`claude/derivativos/DECISOES_POS_PR07A3C_2026-11-23.md`):
- As três lacunas de teste e a trava da boleta parada eram condição do PR07A3C: cumpridas.
- Ordem que já existia antes da parada continua comprometida: execução tardia é
  contabilizada, e só o cancelamento confirmado devolve o saldo à origem. Os dois casos
  devem estar em teste.
- Esquema JSON de saída da prévia: corrigir **antes do primeiro consumidor externo** (tela,
  API ou gerador de cliente), em cartão próprio.
- Só boleta parada cede sobra, por enquanto. A apresentação deve dizer quando a boleta parou
  com montagem parcial e quanto executou em cada perna.
- Para cartão posterior: repetir, completar ou ajustar uma estrutura, sempre com boleta e
  autorização novas; boleta concluída cede só o que o livro comprovar livre; uso no pregão
  seguinte depende de conciliação atualizada; ajuste de delta mostra exposição antes e
  depois e custo estimado.

Entregue pelo DL3-PR07A3D (`models.py` +6 linhas):
- Correção de falha de desenho do planejador: o resumo criptográfico ordenava as
  autorizações e o motor usava a ordem informada, de modo que a prioridade entre origens
  ficava fora da assinatura. Agora a boleta ordena as autorizações por série e origem na
  validação. A ordem informada deixou de existir: prévia, recibo, resumo e motor usam a
  mesma. Nenhum valor de resumo mudou. Vale o critério de Francisco de 23/11/2026: inverter
  a ordem de entrada mantém o mesmo resumo.
- Dois testes pedidos por Francisco entraram (o código já estava certo): a execução que
  chega com o cancelamento pedido conserva a origem; a ordem viva de boleta parada segue
  comprometida até o cancelamento confirmado.
- Recibo emitido entre o PR #173 e o PR #174 com autorizações fora da nova ordem não é mais
  lido pelo leitor atual. Não há recibo real nessa condição. Lição registrada: mudança no
  corpo canônico da prévia pede versão de formato antes de dados reais.
- Portão da cabeça `a2ffa68`, pelo implementador: Linux x86_64 e macOS, 11.459 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 6 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 88 evidências e rodou os cenários do
  seu protótipo contra o módulo entregue.

Entregue pelo DL3-PR07A4 (`engine.py` +36 linhas; `venue.py` +2):
- Antes de aplicar um relato da venue, o motor o confere. O contraditório **não é
  aplicado**: vira registro `divergence` com a mensagem recebida, o motivo e o último
  executado que o livro aceitou, e bloqueia novos envios da conta. Os relatos seguintes do
  lote continuam entrando. Antes, o relato impossível levantava exceção e a execução acima
  da ordem era gravada como execução.
- Motivos: correção oficial; correção sem fato original; fato repetido com conteúdo
  diferente; relato impossível para o estado da ordem; execução malformada; execução acima
  da quantidade da ordem. No simulador, cancelamento não pedido também é relato impossível.
- `VenueReport` ganhou `fact` e `corrects`, opcionais. Duplicata idêntica com `fact` é
  ignorada sem efeito. Sem `fact`, dois relatos iguais são dois fatos. A venue de papel não
  preenche os campos.
- A correção oficial é registrada com a referência ao fato original e bloqueia a conta; não
  altera saldo no simulador.
- Recibos e âncoras das sessões oficiais são os mesmos.
- Portão da cabeça `4f1afcb`, pelo implementador: Linux x86_64 e macOS, 11.478 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 18 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 112 evidências e rodou os 13 casos do
  seu protótipo e três sondas contra os módulos entregues.

Entregue pelo acompanhamento do DL3-PR07A4 (PR #176, autorizado por Francisco sem cartão
novo):
- A conferência do relato virou função pura em `report_check.py` e vale também na
  conciliação da ordem incerta: o motor projeta a fila, compara com a consulta à venue e só
  então grava. Consulta incompatível deixa a fila pendente.
- Evento que não é do tipo `Event` é recusado antes de qualquer lançamento.
- As três lacunas de teste e as quatro linhas largas da revisão do #175 foram resolvidas.

Entregue pelo DL3-PR07B1 (PR #177; `sequencing.py` +24 linhas, `engine.py` +2):
- Zeragem: venda em perna única de uma série com saldo comprado, até o saldo livre (saldo da
  foto, menos o que protege vendidas, menos o que já foi posto à venda por zeragem na
  conta). Antes o plano recusava. Recusas novas: «saldo livre insuficiente» (plano) e «saldo
  livre indisponível» (admissão, sem gastar a decisão).
- A zeragem e a desmontagem presa a recompra não tiram saldo uma da outra. A sobra que uma
  recompra de outra boleta deixou continua exigindo autorização.
- O exemplo de Francisco está em teste pelo motor: recompra de 100 com 40 executadas libera
  40; as outras 60 seguem comprometidas.
- Portões das cabeças `4510616` e `b11d492`, pelo implementador, cada um em Linux x86_64 e
  macOS, com mypy estrito e Pyright sem erro. Os dois PRs saíram da mesma base; o revisor
  rodou a suíte sem integração na árvore combinada (11.497 aprovados, 16 pulados) antes de
  integrar.

Decisões de Francisco de 23/11/2026, em resposta ao planejador:
- o PR07B vem antes do evento externo, que fica desenhado antes da fase com corretora;
- fato externo legítimo numa série que uma boleta em execução usa: a boleta para de enviar,
  mantém as ordens já enviadas e contabiliza as execuções;
- o fato externo legítimo não bloqueia a conta; só afeta as boletas da série atingida.

Entregue pelo DL3-PR07B2 (PR #178; `sequencing.py` +17 linhas, `engine.py` +6):
- A foto de posição tem o strike de cada série; o par só vale com strikes diferentes. Os
  três roteiros oficiais ganharam strike; recibos e âncoras não mudaram.
- Uma vendida pode ter mais de uma proteção. O plano reparte a venda entre as compras da
  boleta, na ordem assinada; cada unidade comprada protege uma só vendida.
- O motor envia uma ordem de venda por proteção e o recibo diz qual série protegeu cada
  ordem. Testes da estrutura completa, de cada asa isolada e de execuções parciais.
- As duas contas da DP-03 estão em teste pela análise de vencimento: borboleta inteira perde
  no máximo o débito (0,20 no exemplo); asa de cima perde largura menos crédito (0,40).
- Só a montagem. Foto com vendida aberta e mais de uma proteção é recusada.
- As duas lacunas de teste dos PRs #176 e #177 foram fechadas (G1 e G2).
- Portão da cabeça `34aff5f`, pelo implementador: Linux x86_64 e macOS, 11.513 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 17 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 114 evidências e rodou os cenários do
  seu protótipo contra os módulos entregues.

Entregue pelo DL3-PR07A5 (PR #179; `sequencing.py` +19 linhas, `engine.py` +15, `state.py` +1):
- O livro registra que uma série de uma conta teve fato externo. A partir daí não reserva
  venda nova que use a série (como vendida ou como proteção), não empresta sobra dela e
  recusa boleta nova com «série com fato externo; foto nova necessária». Ordens que já
  existiam seguem contabilizadas. Vale só para aquela conta.
- O motor avisado grava um registro `external` no recibo, uma vez, com o identificador do
  fato e as séries atingidas, e não envia mais nada, de nenhuma perna. As ordens vivas
  ficam, as execuções entram, a conta não bloqueia e nenhuma ordem é cancelada.
- Limites: nada em produção chama as duas funções novas; a quantidade do fato não compõe a
  posição; não há descongelamento (foto nova é livro novo); o livro não segura compra de
  motor que não foi avisado.
- Portão da cabeça `a6b1f07`, pelo implementador: Linux x86_64 e macOS, 11.529 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 21 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 126 evidências e rodou os cenários do
  seu protótipo e quatro sondas contra os módulos entregues.

Entregue pelo DL3-PR07A6 (PR #180; `session.py` +55 linhas, `engine.py` +1, script +22):
- A sessão tem uma entrada única para o fato externo: confere, grava no registro de fatos,
  congela a série na conta e avisa todas as boletas daquela conta, na ordem de abertura.
- O registro de fatos é uma cadeia própria da sessão, sem boleta de origem, com conta,
  série, tipo (exercício ou enquadramento), quantidade com sinal e instante. Repetição
  idêntica conta uma vez; mesmo identificador com conteúdo diferente é recusado.
- O roteiro ganhou o passo `external`. A saída ganha `fatos_externos.jsonl` e a chave
  `fatos_externos` no resumo só quando há fato; as sessões oficiais não mudaram.
- O bruto projetado de boleta avisada passa a ser o executado mais as ordens vivas.
- Limites: a quantidade do fato fica registrada e não altera saldos; a série segue
  congelada até a foto nova; a conferência da foto seguinte depende de histórico entre
  sessões.
- Portão da cabeça `7588cf1`, pelo implementador: Linux x86_64 e macOS, 11.567 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 31 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 144 evidências e rodou os casos do
  seu protótipo e cinco sondas contra os módulos entregues.

A DP-13 está entregue no simulador, menos a conferência da foto nova.

Entregue pelo DL3-PR07C1 (PR #181; `sequencing.py` +15 linhas):
- O plano guarda a quantidade de cada dependência. Quando outra venda do plano usa a mesma
  proteção, o livro limita a venda à parte que o plano lhe destinou. Proteção de uma venda
  só segue limitada pelo total da perna.
- No exemplo do cartão, a estrutura que parava com 44,00 de 46,00 agora conclui.
- Portão da cabeça `ee572b6`, pelo implementador: Linux x86_64 e macOS, 11.574 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 14 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 108 evidências e rodou os cenários do
  seu protótipo e duas sondas contra o módulo entregue.

Decisão de Francisco em 24/11/2026: a repartição das proteções na foto vem de «só conta
exata». A foto é aceita quando as proteções somam exatamente a vendida e nenhuma protege
outra série.

Entregue pelo DL3-PR07B3 (PR #182; `sequencing.py` +10 linhas):
- Foto com vendida aberta e mais de uma proteção é aceita na conta exata. O saldo livre
  desconta a vendida das proteções uma vez só.
- A desmontagem da borboleta funciona pelas regras existentes: cada unidade recomprada
  libera uma unidade de asa; vender asa sem recomprar segue recusado; parada no meio deixa
  trava coberta.
- Segue recusada a foto em que as proteções não somam a vendida, ou em que uma proteção
  serve a duas séries.
- Portão da cabeça `6ad75c6`, pelo implementador: Linux x86_64 e macOS, 11.588 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 11 mutantes detectados. O
  revisor não repetiu a suíte; conferiu o manifesto de 81 evidências e rodou os casos do
  seu protótipo e três sondas contra o módulo entregue.

Entregue pelo DL3-PR07D1 (PR #183; `engine.py` +38 linhas, `session.py` +5, script −1):
- O motor e o resumo mostram, por perna e na ordem assinada, o assinado, o executado, o
  saldo vivo e o preço médio ponderado. A contagem segue a convenção do FIX: ordem morta
  não tem saldo vivo; ordem com cancelamento solicitado ainda tem.
- Parada com execução vira «Parada · montagem parcial» ou «Parada · desmontagem parcial».
- Depois de um cancelamento humano, o projetado é o executado mais as ordens vivas.
- **A âncora da sessão `leilao` mudou**, de `0e95249a…` para `8592cd74…`: o registro 9 do
  recibo gravava projetado 25,00 e passa a gravar 14,50. As outras três âncoras não mudaram.
- Portão da cabeça `a0c2730`, pelo implementador: Linux x86_64 e macOS, 11.597 aprovados,
  16 pulados, 261 subtestes; mypy estrito e Pyright sem erro; 17 mutantes detectados.

Com isso ficam entregues no simulador os assuntos abertos pela DP-03 e pela DP-13.

Entregue pelo DL3-PR07E1 (PR #184):
- O esquema de saída da prévia enumera os campos e está versionado em
  `docs/specs/derivatives/fase3/schemas/previa.schema.json` (SHA-256 `a1c0bed2…0a2d`),
  preso por teste ao que o código gera.
- Cada linha de recibo e o resumo trazem `formato` 1. **A partir daqui, mudança de formato
  sobe o número e diz o que mudou.**
- `load_rows` lê as linhas gravadas e recusa formato desconhecido, linha alterada, cadeia
  quebrada e recibo vazio; confere a âncora quando informada.
- Nenhuma âncora mudou.
- Dois erros do cartão do planejador foram corrigidos por adendo e ratificados na revisão:
  o esquema fixado recusava dinheiro em notação exponencial, e o texto do truncamento
  ignorava o recibo de um evento só.

Entregue pelo DL3-PR07F1 (PR #185): o módulo da boleta recusa pydantic anterior ao 2.12 na
importação, e `ReplaySession.receipt` devolve cópia.

### Fase 3 estendida: encerrada em 24/11/2026

Não há cartão na fila. O que foi entregue no simulador D0, entre 22 e 24/11/2026:
contabilidade dos três brutos; livro de reservas com sobra autorizada; relatos
contraditórios; fato externo legítimo (DP-13); zeragem, montagem e desmontagem de borboleta
(DP-03); cota na proteção disputada; andamento por perna; formato versionado e esquema de
saída da prévia.

O que **não** foi feito e continua valendo como limite:

- **Tudo é simulador, com dados sintéticos.** A ADR-0024 segue sem vigência operacional; as
  proibições de `CLAUDE.md` e da ADR-007 seguem vigentes; nenhum agente envia ou cancela
  ordem.
- A quantidade de um fato externo fica registrada e não altera saldos; a série fica
  congelada até a foto nova, e a conferência da foto nova não existe.
- Foto em que as proteções não somam a vendida é recusada.
- O `pyproject.toml` ainda declara piso 2.10 para o pydantic. A guarda cobre a falha; subir
  o piso é decisão e commit de Francisco.
- Não há esquema para o resumo nem para os eventos do recibo além da prévia.

Frentes novas, cada uma só abre com decisão de Francisco: repetir, completar e ajustar
estruturas; histórico persistente com conferência da foto nova; foto com quantidade por
par; modalidade B de garantia.

Pendências anteriores a esta fase, que ela não tocou: limite de escala em `expiry_payoff` e
`pre_expiry`; vencimentos diferentes na estimativa; o `projection_id` no teste sintético do
calendário.

Manutenção opcional: duas linhas a menos em `Position.unpledged` (relatório de
simplificação do PR #182).

Próxima ação (uma só): Francisco decide se abre alguma frente nova ou se o laboratório
para aqui.

## Fase 03 — Motor da boleta em simulador (D0) — FECHADA (estado A)

Último PR: DL3-PR06 com a correção DL3-PR06B — MERGEADO (PR #162). Antes dele, DL3-PR05b
(PR #161), DL3-PR00 (PR #154), DL3-ADR
(PR #155), DL3-PR01 (PR #156), DL3-PR02 (PR #157), DL3-PR03 (PR #158), DL3-PR04
(PR #159) e DL3-PR05a (PR #160). O DL3-PR05 foi dividido: 05a (decisão e gatilho) e 05b (motor). SDD em [SDD_FASE3_BLUEPRINT.md](../specs/derivatives/fase3/SDD_FASE3_BLUEPRINT.md);
cartões e revisões em [DL3-PR00.md](../specs/derivatives/fase3/DL3-PR00.md),
[DL3-PR01.md](../specs/derivatives/fase3/DL3-PR01.md),
[DL3-PR02.md](../specs/derivatives/fase3/DL3-PR02.md),
[DL3-PR03.md](../specs/derivatives/fase3/DL3-PR03.md),
[DL3-PR04.md](../specs/derivatives/fase3/DL3-PR04.md),
[DL3-PR05a.md](../specs/derivatives/fase3/DL3-PR05a.md),
[DL3-PR05b.md](../specs/derivatives/fase3/DL3-PR05b.md) e
[DL3-PR06.md](../specs/derivatives/fase3/DL3-PR06.md), com as correções em
[DL3-PR05b-R1.md](../specs/derivatives/fase3/DL3-PR05b-R1.md),
[DL3-PR05b-R2.md](../specs/derivatives/fase3/DL3-PR05b-R2.md) e
[DL3-PR06B.md](../specs/derivatives/fase3/DL3-PR06B.md). Fechamento em
[RELATORIO_FECHAMENTO_FASE3.md](../specs/derivatives/fase3/RELATORIO_FECHAMENTO_FASE3.md).

Critério binário da SDD cumprido: os 22 cenários de aceite passam, os testes de
arquitetura passam, o portão completo está verde e não entrou dependência nova.

Entregue pelo DL3-PR06 e pelo DL3-PR06B (`ticket/session.py` novo e
`scripts/derivatives_ticket_replay.py` novo; 336 linhas de produção, em duas rodadas):
- Sessão de replay: uma fita, um livro, uma venue, um livro de reservas, um livro de
  decisões e um quadro de bloqueios, compartilhados por todas as boletas da sessão.
- A sessão recusa abrir boleta cujo id só difere de outro por maiúsculas (DP-18). O
  motor continua aceitando os dois.
- `after_seq=0` é o instante anterior ao primeiro evento. A sessão recusa fita cujo
  primeiro evento tem sequência zero ou negativa (DP-19). O leitor de replay não mudou.
- Linha de comando `scripts/derivatives_ticket_replay.py --replay --roteiro --out`: roda a
  sessão inteira e só então publica um recibo por boleta e o `resumo.json`, juntos, em
  pasta nova. Destino que já existe é recusado antes de ler as entradas. Código 0 ou 2.
- Só recusa de domínio vira código 2. Erro de programação na abertura sobe com traceback.
- Três sessões sintéticas oficiais (`calmo`, `leilao`, `rapido`) com quatro âncoras de
  recibo fixadas em teste; duas execuções produzem os mesmos bytes.
- Portão da cabeça `029a092`, Linux x86_64 limpo: 11.227 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro. 75 mutantes do revisor, 64 mortos.

Limites do que foi entregue, para quem continuar:
- A publicação é inteira durante a execução normal. Queda de energia e morte abrupta do
  processo não foram ensaiadas. Windows fica sem a renomeação exclusiva e o comando
  recusa publicar.
- O `resumo.json` guarda a âncora de cada recibo na mesma pasta e sob o mesmo usuário.
  Isso não prova que o recibo não foi trocado (DP-11).
- Destino terminado em `..`, pai que é link quebrado e prazo de decisão que estoura a
  data devolvem 2, mas não têm teste. Uma linha de teste tem 105 colunas. O bloco de
  caminhos com `..` é candidato à rodada de simplificação (DP-17).

Decisões de produto de Francisco (DP-01 a DP-19): a Revisão 1 está em
[DECISOES_PRODUTO_DP01-DP19.md](../specs/derivatives/fase3/DECISOES_PRODUTO_DP01-DP19.md).
A Revisão 2, de 22/11/2026, separa o que vale hoje, o que é produto e o que depende de
dado ou homologação. Ela entrou no repositório com o PR #163.
Recorte autorizado: PR07A (origem da cobertura; bruto assinado, executado e projetado;
DP-12 a DP-15) e PR07B (zeragem e borboleta em simulação). O resto tem cartão próprio.

Entregue pelo DL3-PR05b (`ticket/engine.py` novo e admissão em `ticket/sequencing.py`; 435
linhas de produção no PR, em três rodadas de revisão):
- Motor de uma boleta no replay síncrono: propor, editar, atualizar, armar, desarmar,
  descartar, confirmar, cancelar, pausar, retomar e reconciliar; aplica relatórios da venue
  e eventos de mercado. Nunca cancela nem reenvia por conta própria.
- A confirmação confere, nesta ordem: estado, pausa, conta bloqueada, prazos, trava de
  mercado, limites assinados, admissão no livro e, por último, a decisão humana. Recusa em
  qualquer passo não gasta a decisão e não envia nada.
- Livro de reservas com admissão (`admissible`, `admit`) e ocupação de compra
  (`settle_buy`): duas boletas não ocupam a mesma recompra de posição vendida, e foto de
  posição divergente é recusada antes de gastar a decisão.
- O fato da venue vem primeiro: o relatório entra no estado da ordem e no recibo antes da
  contabilidade. Se o livro recusar, o motor grava `DIVERGENCE` e bloqueia a conta até o
  fim da sessão, sem levantar exceção.
- Rejeição da venue é definitiva: a perna rejeitada não recebe novo envio.
- `order_id = "{boleta}:{símbolo}:{n}"`. Id de boleta e símbolo só aceitam letras, dígitos,
  `_`, `.` e `-`; fora disso o motor recusa no construtor ou na proposta.
- Portão da cabeça `9f5db3c`, Linux x86_64 limpo: 11.173 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro. 55 mutantes do revisor mortos; 6.000 sessões
  aleatórias contra a `PaperVenue` real sem violar estado, recibo, prazo ou cobertura.

Notas do motor que o DL3-PR06 recebeu (seguem valendo):
- O condutor entrega cada evento nesta ordem: `book.advance`, `venue.advance`, e para cada
  motor `on_reports` (só com os relatórios das ordens daquele motor) e `on_market`.
- O id da boleta precisa ser único na sessão inteira, em todas as contas. O motor não
  confere isso; o DL3-PR06 recusa id repetido.
- Relatório impossível da venue (transição inválida) ainda levanta exceção. A `PaperVenue`
  não emite isso; o tratamento fica para o degrau D1.
- O bloqueio por divergência não tem liberação: a saída é sessão nova com posição
  conciliada. Ocupação de perna de compra nunca enviada só sai no fim da sessão.

Comportamentos do motor que Francisco pode querer rever (não são defeito):
- A cobertura é por conta, não por boleta (contrato do DL3-PR03, S09). Uma boleta pode
  vender usando proteção comprada por outra boleta da mesma conta que parou sem vender.
- Venda executada a preço melhor que o assinado aumenta o volume bruto e pode parar a
  boleta por `gross_cap` (cenário L1 do DL3-PR05b-R1).

Entregue pelo DL3-PR05a (`ticket/gate.py` e `ticket/trigger.py`, 247 linhas de produção):
- Decisão humana presa à boleta, à ação, ao prazo, ao resumo **e à versão** da prévia, à
  ordem (no cancelamento) e ao gatilho (ao armar). Uso único por `nonce`; recusa não
  consome. Em D0 a emissão é função local, sem autenticação real.
- Gatilho de aviso: não arma com condição já verdadeira nem com dado inválido, dispara uma
  vez, expira, e nunca envia, reserva ou grava recibo.
- Portão, Linux x86_64 limpo: 11.093 aprovados, 16 pulados, 261 subtestes; mypy estrito e
  Pyright sem erro.

Entregue pelo DL3-PR04 (`ticket/replay.py`, `guards.py`, `venue.py`, `paper_venue.py` e
`config/ticket_sim.yaml`, 398 linhas de produção):
- Replay: fixture JSON com cotações, negócios, execução de leilão, recusa de cancelamento
  e timeout; dinheiro só como texto decimal; lacuna de sequência fica marcada no evento.
- Venue simulada: a ordem só casa com cotação posterior ao envio, pelo livro e pela
  quantidade exibida, nunca pelo último negócio. Cancelamento só se confirma em cotação
  posterior do mesmo símbolo, depois do casamento. Validade nativa só "dia".
- Travas de mercado: bloqueio por cotação vencida, leilão, suspensão, livro inválido ou
  incompleto, falta de cotação e perda de sequência; cautela por spread e profundidade.
- Dois prazos: prazo de envio e validade nativa, conferidos antes de enviar.
- Portão com o teste do revisor, Linux x86_64 limpo: 11.012 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro.

Limites do simulador, para o DL3-PR05 saber:
- Depois do fechamento da sessão a venue só expira ordens; qualquer outro evento com
  horário igual ou posterior ao fechamento é ignorado.
- `check_deadlines` aceita o instante exato do fechamento quando prazo e validade
  coincidem com ele; a venue rejeita o envio nesse instante. O motor trata a rejeição.
- Trava de volatilidade não existe: a ADR exige números homologados.
- Parâmetros de `ticket_sim.yaml` são sintéticos e não homologados.

Entregue pelo DL3-PR03 (`ticket/sequencing.py`, 299 linhas de produção):
- Plano de pernas: compras antes das vendas; na desmontagem, recompra da vendida antes de
  vender a comprada. O pareamento vem de evidência explícita na foto de posição.
- Livro de reservas por conta: a venda só é liberada na quantidade comprada e executada,
  descontado o vendido e o reservado, em múltiplos do lote, entre boletas concorrentes.
- Foto de posição divergente bloqueia com motivo próprio.
- `partial_exposure`: desembolso máximo se nenhuma venda executar, somando todas as
  compras. `within_signed_limits`: limites por perna, líquido e bruto, com o executado.
- Portão com os testes do revisor, Linux x86_64 limpo: 10.924 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro.

Limitações conhecidas do sequenciamento, com dono (Francisco decide quando):
- Vender para zerar uma posição comprada própria, sem série vendida pareada, é recusado.
- Borboleta e toda estrutura em que duas compras protegem a mesma venda são recusadas.
  Trava e condor funcionam.
- `gross_cap` é o volume bruto (compras mais vendas ao pior preço assinado, mais custo),
  não o desembolso. O desembolso máximo é `partial_exposure`.

Entregue pelo DL3-PR02 (`ticket/state.py` e `ticket/receipt.py`, 291 linhas de produção):
- Duas máquinas de estados com tabela explícita e imutável, uma da boleta e uma da ordem.
  Estado terminal não reabre. `UNCERTAIN` só sai por `reconcile`, com evidência.
- Pedido de cancelamento não cancela: só o evento da venue confirma. Execução que chega
  durante o pedido fica registrada.
- Recibo só de acréscimo, encadeado por SHA-256. A prévia é gravada inteira e o resumo é
  conferido na leitura. Sem uma ponta externa conhecida, o recibo não prova que não foi
  truncado.
- Portão com os testes do revisor, Linux x86_64 limpo: 10.873 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro.

Entregue pelo DL3-PR01 (`backend/derivatives/ticket/`, 239 linhas de produção):
- Modelo imutável da boleta simulada: 1 a 4 pernas, dinheiro em `Decimal` no passo de
  0,01, quantidade inteira múltipla do lote, ambiente único `SIMULATED`.
- Resumo SHA-256 do conteúdo autorizável, independente da versão e das travas.
- Edição humana trava o campo e avança a versão; atualização de mercado não escreve em
  campo travado; destravar não muda versão nem resumo.
- Testes de arquitetura: o pacote não importa rede, LLM, MCP nem cliente da OpLab; o MCP
  não importa a boleta; a rota de mercado segue só `GET`.
- Portão da cabeça `55b1746`, Linux x86_64 limpo: 10.844 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro.

Para os próximos cartões:
- O resumo não inclui a versão: editar de A para B e voltar a A recupera o mesmo resumo.
  No DL3-PR05 a decisão humana deve prender também a versão, para que uma confirmação
  antiga não volte a valer.
- `LABELS_PT` junta os dois enums num só dicionário. `EXPIRED` e `UNCERTAIN` existem nos
  dois e comparam iguais como texto, então os rótulos coincidem por construção. Se um dia
  precisarem diferir, separar em dois dicionários (DL3-PR06).
- O recibo aceita número em ponto flutuante no conteúdo genérico. No DL3-PR05 o motor
  grava dinheiro como texto decimal.
- A sugestão S1 da simplificação (evitar a segunda decodificação da prévia em `verify`)
  é opcional e não foi aplicada.
- Custo conhecido com fração de centavo gera exposição que a prévia recusa. O motor
  (DL3-PR05) arredonda o custo para cima ao centavo antes de calcular.
- O motor não decide pelo texto da recusa do livro. Se precisar separar "conciliar a
  posição" de "plano inválido", cria tipo próprio de recusa (DL3-PR05).
- A ordem entre prazo de envio e validade da ordem não é validada no modelo; fica para o
  DL3-PR04.

Entregue pelo DL3-PR00:
- A árvore e as diferenças finitas recusam publicar VI quando o preço está até um tick
  (`price_tick: 0.01`, inclusive) acima do piso americano efetivo, o maior entre o limite
  europeu e o exercício imediato. Preço abaixo do piso além da tolerância é
  `below_intrinsic` nos dois motores.
- Nas 69 referências do oráculo só `B21` e `C01` mudam, de `ok` para recusa. Os outros 67
  ficam idênticos bit a bit. A demo mista fica idêntica byte a byte.
- Portão da cabeça `fb5b07f`, Linux x86_64 limpo: 10.797 aprovados, 16 pulados, 261
  subtestes; mypy estrito e Pyright sem erro.

Escopo da fase (decisão de Francisco em 2026-11-21): motor da boleta em simulador local,
sem tela, sem rede, sem conta e sem dependência nova. A interface fica para a Fase 4. Os
cartões DL3-PR02 a DL3-PR06 estão publicados fora do repositório e entram cada um no seu PR.

ADR-0024: Francisco aprovou o desenho reescrito em 2026-11-21 (degraus D0, D1 e D2, gate
humano, ponte isolada). O texto está em `main` desde o PR #155. Não há vigência
operacional: as proibições de `CLAUDE.md` e do ADR-007 seguem valendo, e acesso real
continua dependendo de commit assinado por Francisco.
ADR-0024 aprovada quanto ao desenho em 21/11/2026; sem vigência operacional; proibições de `CLAUDE.md` e ADR-007 seguem vigentes.

Pendências com dono:
- Caminho europeu (BSM): as puts da B3 são europeias e não receberam a regra do tick.
  Cartão próprio; Francisco decide quando.
- Convenção de dias úteis `(D0,Dv]`, ainda hipótese.
- Sugestão S1 da avaliação de simplificação (unir duas recusas idênticas da árvore): não
  aplicada; opcional.

A sequência depois do fechamento está na seção "Depois da Fase 3", no alto deste arquivo.

## Fase 02 — Marco 2C2 — FECHADO (estado A)

PR atual: DL2C2-PR01 — MERGEADO (PR #153, GO na primeira rodada). Zero linha de produção.
[ADR-0028](../ADR/ADR-0028-laboratorio-derivativos-fase2c2.md) aceito por Francisco em
2026-11-20, com as ressalvas S1 a S4. Cartão em
[DL2C2.md](../specs/derivatives/fase2c2/DL2C2.md),
[Adendo 1](../specs/derivatives/fase2c2/DL2C2-ADENDO-1.md) e resultados em
[DL2C2-PR01.md](../specs/derivatives/fase2c2/DL2C2-PR01.md).

Entregue:
- Referência de 69 preços do QuantLib 1.44, gerada fora do repositório em contêiner, com
  incerteza por caso. O QuantLib não é dependência nem motor.
- Testes que medem contra ela o BSM europeu, a árvore CRR e as diferenças finitas, em preço
  e em volatilidade. Portão do head, Linux aarch64 limpo: 10.750 aprovados, 16 pulados, 261
  subtestes.

Resultado, com a configuração mantida por Francisco (árvore com 200 passos, malha
400 por 200), nos 67 casos identificáveis:
- Árvore: erro de volatilidade de até 3,7e-4; inversão em 148 ms no caso mais lento.
- Diferenças finitas: erro de até 2,3e-4; inversão em 405 ms no caso mais lento.
- BSM europeu contra o analítico do QuantLib: 1e-14.

O que o marco não prova:
- Nada sobre o modelo: volatilidade e juros constantes e rendimento contínuo são premissas
  dos três métodos.
- Nada sobre dias úteis, provento discreto ou dado de mercado.

Pendências com dono:
- **Identificação de VI perto do intrínseco**: resolvida para as americanas no DL3-PR00
  (PR #154). O alerta de relevância (ADR-0028, S3) segue pendente.
- Convenção de dias úteis `(D0,Dv]`, ainda hipótese em `config/derivatives.yaml`; o
  `Business/252` do QuantLib conta `[D0,Dv)`.
- Sombra BSM: fica como controle no grupo sem rendimento (acerta 18 de 18) e não vota nos
  demais (11 de 51). Sem PR nesta fase (ADR-0028, S4).

O limiar de 0,00050 é aviso de diagnóstico e não muda. Repetir a conferência com dado real é
marco futuro, depois da ativação da OpLab, que tem rito próprio.

Roteiro (Francisco, revisto em 2026-11-21): 2C1 e 2C2 fechados → Fase 3 (motor da boleta
em simulador) → Fase 4 (interface). Kronos fica sem fase definida. Ver a seção da Fase 03.

## Fase 02 — Marco 2C1 — FECHADO (estado A)

PR atual: DL2C1-PR02 — MERGEADO (PR #152, GO na primeira rodada). PR 1 em #151.
[ADR-0027](../ADR/ADR-0027-laboratorio-derivativos-fase2c1.md) aceito por Francisco em
2026-11-20, com D4 e D5 provisórios. Cartão, Adendo 1 e as duas revisões em
[DL2C1.md](../specs/derivatives/fase2c1/DL2C1.md); provas dos critérios em
[DL2C1-PR02.md](../specs/derivatives/fase2c1/DL2C1-PR02.md).

Entregue, só na demo sintética offline:
- Segundo motor americano por diferenças finitas (`pricing/fd_american.py`,
  `config/american_fd.yaml`), só diagnóstico. A árvore CRR segue dona do preço, da
  volatilidade e de toda recusa da linha.
- Por linha americana suportada da demo mista: diferença de preço na mesma volatilidade,
  volatilidade do segundo motor, diferença entre as duas, marca de baixa sensibilidade e
  alerta acima de 0,0005. Saem na chave pública `diagnostics`. Agregados na chain.
- O alerta não recusa linha nem muda o código de saída.
- Portão do head, Linux aarch64 limpo: 10.256 aprovados, 16 pulados, 261 subtestes.

O que o marco não prova:
- Qual motor está certo quando divergem. Os dois são do projeto; o árbitro é a Fase 2C.
- Nada com rendimento na fixture publicada: a única linha americana suportada é call sem
  rendimento, em que americana e europeia valem o mesmo.
- Precisão uniforme do segundo motor: o erro escala com `S dx^2` (Adendo 1); com
  `sigma * sqrt(T)` acima de 1 ele fica na mesma ordem do erro da árvore com 200 passos.
- Nada com dado real.

Pendências com dono:
- Revisão explícita da sombra BSM no fechamento da Fase 2C, inclusive se ela sai por linha
  na saída pública (Francisco, D3 do ADR-0027).
- Malha, orçamento de 700 ms e limiar de 0,0005 são provisórios (Francisco, D4 e D5).
- Convenção de dias úteis `(D0,Dv]` ainda marcada como hipótese em `config/derivatives.yaml`.

Roteiro (Francisco, 2026-11-20): 2C1 fechado → 2C (QuantLib só como oráculo de teste) →
Fase 3 → Fase 4 (Kronos). Nenhum passo autoriza dado real, OpLab ou token.

ADR-0024 (corretora) segue PROPOSED. Ele só muda de estado com commit assinado por
Francisco alterando `CLAUDE.md`; mensagem em conversa não cumpre essa condição, e nenhum
agente faz essa alteração. A proibição de corretora e de ordens segue em pleno efeito.

Próxima ação (uma só): Francisco aprova o ADR-0028 e o cartão da Fase 2C, escritos pelo
Claude. Nenhum código antes disso. O QuantLib não entra como dependência do repositório.

## Fase 02 — Marco 2B — FECHADO (estado A)

PR atual: DL2B-PR04 — MERGEADO (PR #150, NO-GO na primeira rodada, GO na segunda).
[ADR-0026](../ADR/ADR-0026-laboratorio-derivativos-fase2b.md) aceito, com a Revisão 1.
Revisões independentes dos quatro PRs em
[DL2B-R1.md](../specs/derivatives/fase2b/DL2B-R1.md); contrato e evidências do último em
[DL2B-PR04.md](../specs/derivatives/fase2b/DL2B-PR04.md).

Entregue no marco (#146 a #150), só na demo sintética offline:
- Ponte americana (`pricing/american_bridge.py`): preço pela média do par de árvores CRR e
  volatilidade implícita por bisseção no mesmo par, configurada em `config/american_iv.yaml`.
- Registro versionado de termos e carry por identidade e vigência
  (`domain/series_registry.py`).
- Ligação na demo (`service/american_demo.py`, `service/demo_chain.py`), atrás da chave
  `--american-demo` com `--series-registry synthetic-v1`. 200 passos por padrão; `--steps`
  prevalece quando informado.
- BSM europeu da Fase 1 como sombra: só diagnóstico, não altera preço, volatilidade nem
  recusa da árvore. Primeira divergência observada: 5,0e-6 de volatilidade, uma linha.
- Linha americana só é suportada com volatilidade na compra, na venda e no meio. Lado
  ausente, cotação velha ou lado sem volatilidade: linha recusada com motivo próprio.
- Portão do head, Linux aarch64 limpo: 9.556 aprovados, 16 pulados, 261 subtestes. O autor
  registrou 9.555 em macOS arm64 e em Linux, antes do teste que o revisor somou.
- Inversão com 200 passos no Mac: mediana de 146 ms de CPU, teto de 210 ms.

Decisões da Revisão 1 (Francisco, 2026-11-20): árvore CRR no preço e na volatilidade da
linha; BSM europeu só como sombra; 200 passos por padrão; teto de 210 ms; faixa de
volatilidade entre compra e venda em vez de número único.

O que o marco não prova:
- Nada com dado real. Sem OpLab, sem token; o caminho de mercado não mudou e o CLI padrão
  devolve `LIVE_NOT_ACTIVATED`.
- A árvore contra uma implementação independente. Fica para a Fase 2C.
- Gregas americanas e dividendo discreto, fora do marco.

Pendências com dono:
- D3, origem e vigência dos termos de série real (Francisco).
- D4, NumPy ou outro método de busca; só se o teto de 210 ms for ultrapassado (Francisco).
- `--steps` é ignorado sem aviso quando o provedor é o de mercado.
- A `main` segue sem proteção de branch (Francisco).

Roteiro decidido por Francisco em 2026-11-20, na ordem: Fase 2C, QuantLib como oráculo de
teste, com ADR próprio; Fase 3, como já definida; Fase 4, Kronos. Nenhuma autoriza dado
real ou token por si só.

Regra de memória (Francisco, 2026-11-20): este arquivo é a única fonte de verdade entre
os colaboradores. Decisão que apareça aqui sem registro de quem decidiu deve ser
confirmada com Francisco antes de ser removida ou seguida.

Próxima ação (uma só): Claude escreve o ADR e o cartão da Fase 2C. Nenhum código antes
deles. O QuantLib não entra como dependência do repositório.

## Fase 02 — Marco 2A — FECHADO (estado A)

PR atual: DL2-PR04 — MERGEADO (PR #145, GO na primeira rodada de revisão). Marco fechado.
Os dez critérios do SDD têm a prova apontada em
[DL2-PR04.md](../specs/derivatives/fase2/DL2-PR04.md), na tabela "Provas dos dez critérios".

Entregue no marco, sem nenhum consumidor em produção:
- `domain/series_terms.py` (215 linhas), `domain/carry.py` (131) e `pricing/binomial.py`
  (153). Nenhum arquivo de produção da Fase 01 foi alterado.
- Referência CRR de 42 casos em decimal de 60 dígitos, com gerador versionado e fixado por
  SHA-256, e grade de 2.880 pontos com seis invariantes.
- Portão do head, Linux aarch64 limpo: 9.184 aprovados, 16 pulados, 261 subtestes. O autor
  registrou 9.183 em macOS arm64 e em Linux aarch64, antes do teste que o revisor somou.
- Os 84 preços da referência coincidem bit a bit entre macOS arm64 e Linux.
- Custo no Mac, Python puro: 0,047 s por preço com 1.000 passos e 1,23 s com 5.000.

O que o marco não prova:
- O erro da americana contra o modelo contínuo. A referência é o preço da árvore finita.
- Nada com dado real. Sem OpLab, sem token; a americana segue recusada na chain, no MCP e
  no CLI, e o CLI padrão devolve `LIVE_NOT_ACTIVATED`.

Pendências que passam para o Marco 2B:
- Ponte com a chain, valor de `PricingModel` e pontos cegos da guarda (salto por `config/`
  a partir de `scripts/`; import dinâmico relativo dentro de função).
- Decisão de NumPy (L4 do ADR-0025), com a medição acima.
- Ajuste de strike em ETF segue `UNKNOWN` até haver documento datado da B3 (L5).
- Simplificação de `crr_parameters`, sugerida no piloto da skill de revisão.
- A `main` segue sem proteção de branch (Francisco).

Próxima ação (uma só): Francisco define o recorte do Marco 2B. Antes de qualquer código,
SDD próprio.

## Fase 01 do Lab de Derivativos — CONCLUIDA e integrada na `main` (estado A)

**Estado A (offline verificado) fechado em 2026-11-19.** Tudo abaixo esta na
`main` do GitHub; nao ha branch pendente da Fase 01.

| PR | Conteudo | Gate nativo (macOS, arvore limpa) |
|---|---|---|
| #132 | testes hermeticos para clone limpo | 7.766 passed |
| #133 | DL-PR05a: rotas, erros e orcamento OpLab | 7.875 passed |
| #134 | DL-PR05b: transporte e cliente OpLab | 7.930 passed |
| #135 | DL-PR06: ChainService, fixture sintetica, latencia | 7.966 passed |
| #136 | DL-PR07: servidor MCP `quimera-derivatives` | 8.030 passed |
| #137 | conciliacao Dots + revisao Claude | 8.059 passed |
| #138 | correcoes da revisao independente (REPLAY, `invalid_rate`) | 8.101 passed |

- Apos o #138 a `main` ficou em `b0ca5a5`, arvore `df34e1d`: **a mesma arvore
  aprovada pela revisao independente** (Codex) em macOS e Linux, com 22 de 22
  regressoes plantadas detectadas. Gate final nessa `main`: 8.101 passed,
  16 skipped, 0 failed; `mypy --strict` 0 (155 arquivos); `pyright` 0.
- O DL-PR08 (CLI `quimera chain`, opcional) e este registro entraram em
  seguida, pelos dois PRs seguintes, com o mesmo procedimento.
- Integracao feita por `reports/fase01/integrar_fila.sh` (fora do Git):
  rebase e gate em arvore de trabalho propria, arvore conferida antes do gate
  e depois de cada squash-merge, merge preso ao commit testado.

### O que a Fase 01 entrega

Cliente OpLab offline (rotas em allowlist, orcamento, erros tipados),
`ChainService` (uma captura, IV e BSM por linha, recusa explicada), servidor
MCP em loopback com barreira de procedencia e CLI fino. A tool produtiva
devolve sempre `LIVE_NOT_ACTIVATED`; so a demo sintetica (`purpose=test`)
mostra numeros. Nenhuma chamada real a OpLab e nenhum token real foram usados.

### Proximo turno

1. **Fase 02 offline:** definir o primeiro recorte (SDD antes do codigo).
2. **Estado B** (homologacao com dados reais da OpLab) e **estado C**
   (promocao explicita por Francisco) continuam fora; ver `BACKLOG.md` do Lab
   e as pendencias de homologacao no ADR-0023.
3. Pendencias nao bloqueantes registradas no BACKLOG: guarda do FastMCP
   depende de atributo privado da versao 3.4.0; procedencia da captura herda
   so da leitura de opcoes; limite de plausibilidade da taxa.
4. A `main` nao tem protecao de branch. Vale ligar "exigir branch atualizado"
   antes de varios agentes voltarem a mergear em paralelo.

---

## Historico — turno Claude de 2026-11-19 (revisao, DL-PR08 e correcoes do NO-GO)

> Registro do turno, anterior a integracao. Onde este trecho diz "pendente",
> "fila" ou "NO-GO", leia como historia: tudo foi integrado (secao acima).

**Turno do Claude iniciado e encerrado em 2026-11-19**, a pedido de
Francisco: revisar o delta de conciliacao do Dots, corrigir e iniciar o
DL-PR08. Trabalho feito em clone isolado; nenhum push, PR ou merge.

Estado da origem: `origin/main == aec9b8e` (PR #131 `bcb2188` e PR #130
`aec9b8e` mergeados por Dots). A arvore da `main` foi conferida contra a
simulacao previa: identica (`26fb46c`).

### NO-GO da revisao independente e correcoes (2026-11-19)

A revisao independente (Codex) deu **NO-GO** para fechar A: dois defeitos
de produto, reproduzidos tambem nesta pilha. **Nenhum merge foi feito.**
Corrigidos na branch nova `fix/dl-fase01-procedencia-taxa`, posicionada
entre a conciliacao e o DL-PR08 (o CLI e opcional e nao deve segurar A):

1. Transporte simulado carimbava `observed/production` -> agora
   `REPLAY/test`, com trava de AST contra atribuicao de `OBSERVED` em A.
2. Taxa composta `<= -100% a.a.` chegava a `log(0)` -> recusa
   `invalid_rate`, linhas preservadas.
3. Lacuna de teste na cauda da put -> oraculo `Decimal` em 4 caudas.

Os 3 testes do revisor entraram sem alteracao e passam. 7 mutantes mortos.
Precos inalterados (mesmo digest). O DL-PR08 foi rebaseado sobre a correcao
(range-diff: 5 commits identicos). Detalhes: `SDD_correcoes_fase01.md`.

**Pendente para levantar o NO-GO:** o revisor repetir a suite ampliada
nesta ponta e Francisco repetir a validacao nativa no macOS.

### O que mudou no turno anterior (revisao + DL-PR08)

- **Revisao do delta `6892c82..c1cd172`:** aceito no essencial (guarda de
  `Host`/`Origin`, transporte HTTP so com `MockTransport`, excecoes fora do
  `except`, `Retry-After` robusto). **Sete correcoes** em 3 commits; a
  principal: chamada de tool rejeitada devolvia HTTP 400 e derrubava a
  sessao do cliente MCP; agora devolve `INVALID_TOOL_CALL` em HTTP 200.
  Tambem: o servidor deixou de consultar o PyPI ao subir. Detalhes em
  `SDD_conciliacao_fase01.md` (secao "Revisao Claude").
- **Pilha inteira rebaseada sobre `origin/main` `aec9b8e`**, sem conflito;
  cada branch difere da versao anterior apenas pelos 5 arquivos do PR #130.
  As versoes antigas seguem no reflog do repo.
- **DL-PR08 implementado:** `backend/derivatives/cli.py` + entrada
  `[project.scripts] quimera` no `pyproject.toml` (`SDD_DL-PR08.md`).

### Fila de integracao (push -> PR -> revisao -> squash-merge)

| # | Branch | Ponta | Base antiga para `rebase --onto` |
|---|---|---|---|
| 0 | `chore/tests-hermetic-main-gates` (so testes) | `07bb7ba` | ja sobre `aec9b8e` |
| 1 | `feat/dl-pr05a-oplab-routes-errors-budget` | `e8ea887` | ja sobre `aec9b8e` |
| 2 | `feat/dl-pr05b-oplab-transport-client` | `d3af143` | `e8ea887` |
| 3 | `feat/dl-pr06-chain-service` | `27cf097` | `d3af143` |
| 4 | `feat/dl-pr07-mcp-server` | `cc2d3e1` | `27cf097` |
| 5 | `review/fase01-claude-dots` (conciliacao + revisao) | `334f2e9` | `cc2d3e1` |
| 6 | `fix/dl-fase01-procedencia-taxa` (correcoes do NO-GO) | `daa5bfa` | `334f2e9` |
| 7 | `feat/dl-pr08-cli` (opcional para A) | ponta da branch | `daa5bfa` |

**A fila so anda depois de levantado o NO-GO.** O estado A fecha no item 6;
o item 7 pode ficar para depois. Depois de cada squash-merge:
`git fetch origin && git rebase --onto origin/main <base-antiga> <branch>`.
A ponta anterior do DL-PR08 ficou em `backup/dl-pr08-pre-correcoes`.

**Testes hermeticos.** O patch de portabilidade do Codex nunca chegou ao
repo. Para nao segurar a fila, Claude escreveu a branch
`chore/tests-hermetic-main-gates`: o teste do resumo Qwen3 passa a gerar o
resumo pelo serializador real a partir de runs sinteticos que carregam os
campos proibidos (teste de mutacao: falha se o serializador vazar), e o
teste de ADR usa `docs/ADR`. Com ela, `main` em clone limpo no Linux fica
com **0 falhas** (7.766 passed). Se o patch do Codex aparecer, escolher um
dos dois; eles tocam os mesmos 2 arquivos.

### Evidencia (Linux aarch64, Python 3.12.16, `uv.lock`, clone limpo)

Sem o JSON legado do Qwen3 e sem `docs/adr`; testes hermeticos aplicados.

| Arvore | `pytest tests/ --ignore=tests/integration` | Producao do PR |
|---|---|---|
| `main` + hermeticos | 7.766 passed, 16 skipped, 0 failed | 0 linhas |
| + DL-PR05a | 7.875 passed, 0 failed | 242 |
| + DL-PR05b | 7.930 passed, 0 failed | 203 |
| + DL-PR06 | 7.966 passed, 0 failed | 163 |
| + DL-PR07 | 8.030 passed, 0 failed | 205 |
| + conciliacao e revisao | 8.059 passed, 0 failed | 300 |
| + correcoes do NO-GO | 8.101 passed, 0 failed | 48 |
| + DL-PR08 | 8.125 passed, 0 failed | 70 |

- Ponta final: mesma contagem em ordem natural, invertida e embaralhada;
  `mypy backend/ --strict` 0 (156 arquivos); `pyright backend/` 0; digest
  bit a bit de precos, gregas e IVs inalterado; arvore limpa apos a suite.
- Sonda HTTP real em loopback com cliente FastMCP: sessao sobrevive a
  chamadas rejeitadas; `Host`/`Origin` externos -> 403; sem banner/PyPI.
- macOS nativo: a ponta anterior (`0fb4f6a`) foi validada por Francisco
  (8.081 passed, mypy 0, pyright 0, CLI 0/3). **A ponta nova ainda nao.**

### Proximo turno

1. Revisor: repetir a suite ampliada na ponta nova. Francisco: validacao
   nativa no macOS. So entao o owner (ou Dots com `gh`) segue a fila.
2. Quem pegar o turno: **anotar aqui o inicio antes de mexer em branches**;
   o checkout principal ficou em `feat/dl-pr08-cli`, arvore limpa. O clone
   `OPENCLAW-fase01-dots` ficou intocado em `c1cd172`; para alinhar:
   `git fetch source-mac` e usar as branches de la.
3. Fora da fase: estado B (assinatura OpLab), medicao do CLI/servidor
   nativos no Mac, bundle OKF.

---

## Historico — turno Dots com Codex (2026-11-19 00:13 BRT)


Branch local `review/fase01-claude-dots`, clone `OPENCLAW-fase01-dots`.
Código validado `17bc0c3`, parent `6892c82` (pilha Claude). #131/Adendo 2
`629df7e` é a base comum. A pilha Dots `847eb9c` foi mantida como referência
e **não deve ser integrada em paralelo**. Ela forneceu guardas e testes, sem
substituir o cliente, ChainService ou demo de 100 opções da pilha Claude.
O checkout original permanece em `feat/dl-pr07-mcp-server`, limpo.

### Evidência

- **Mac arm64 + Linux aarch64, Python 3.12.13:** 8.052 passaram, 15 pulados,
  261 subtestes passaram, zero falhas em cada plataforma no gate
  `pytest tests/ --ignore=tests/integration --timeout=120`. Mypy strict
  (155 arquivos) e Pyright retornaram 0 nos dois.
- Composição de gate: `17bc0c3` mais #130 `95a043b` e patch de
  portabilidade `2c2583cd…`, **somente em clones descartáveis**. Não houve
  dependência do JSON legado. Esses dois itens seguem separados da pilha
  do Lab e precisam chegar à main para reproduzir a árvore verificada.
- **Prova HTTP real apenas em loopback**, dentro de contêiner Linux sem
  rede externa: prod não anunciou demo; teste retornou 100 linhas BOVA11
  rotuladas synthetic/test; produtiva retornou LIVE_NOT_ACTIVATED/A nos
  dois contextos, sem cotação. Host externo foi recusado, servidores
  efêmeros foram encerrados.
- **CS10 no Mac nativo:** 30 rodadas, 100 europeias sintéticas e 100
  precificadas; p50 24,25 ms, p95 29,61 ms (meta <2.000 ms). É medição
  offline da candidata, não latência de mercado.
- Segurança: desativação produtiva antes do serviço, sem modo vivo mesmo
  com C injetado nesta implementação; HTTP Market funciona apenas com
  MockTransport; 4 arquivos e manifesto sintéticos verificados por SHA-256;
  Host/Origin verificados; corpo limitado a 64 KiB; erros sem eco de
  parâmetros ou nomes desconhecidos; cliente rejeita ativo divergente e
  números não finitos. Dependências e fixtures documentais intactas.

### Próximo turno

1. Claude revisa **apenas** o delta `6892c82..review/fase01-claude-dots`,
   em especial a guarda do SDK MCP versão fixada. Anotar início do turno
   no ponto de handoff compartilhado **antes** de abrir outro checkout.
2. Owner conduz publicação/revisão/merge: alinhar #131 (incluindo Adendo 2),
   #130 e patch de portabilidade; depois PR05A, PR05B, PR06, PR07 e o delta
   de conciliação em ordem de dependência. Não integrar a segunda
   implementação P05–07. Após os merges, repetir o gate numa main limpa.
3. PR08 CLI é opcional e ficou fora. OKF próprio do Lab não foi localizado;
   SDD, ADR e esta memória são o handoff. O BACKLOG guarda os itens não
   bloqueantes (p. ex., calendário B3 após 2026 e convenção civil).
   B = homologação de dados reais; C = promoção explícita. Ambos fora da fase.

**Status:** implementação e validação técnica offline concluídas localmente.
Revisão do diff conciliado por Claude e integração na main pendentes.
Nenhum push, merge, deploy, token real ou chamada à OpLab.

[SDD da conciliação](../specs/derivatives/SDD_conciliacao_fase01.md)

### Correcoes apos o NO-GO da revisao independente (2026-11-19, turno Claude)

Branch `fix/dl-fase01-procedencia-taxa`, sobre `review/fase01-claude-dots`.
Dois defeitos reproduzidos e corrigidos, com os tres testes do revisor
incorporados sem alteracao:

- Transporte simulado carimbava `observed/production`; agora `REPLAY/test`,
  com trava de AST contra qualquer atribuicao de `OBSERVED` em A.
- Taxa composta `<= -100% a.a.` chegava a `log(0)`; agora a chain e
  recusada com `invalid_rate`, linhas preservadas.
- Cauda da put passa a ser conferida contra oraculo `Decimal`.

Precos inalterados (mesmo digest). Detalhes e evidencia em
[SDD das correcoes](../specs/derivatives/SDD_correcoes_fase01.md).

---

## Histórico de coordenação — turno Claude de 2026-11-18

- **Turno do Claude encerrado em 2026-11-18.** Fase 1 implementada ate o
  DL-PR07 em branches locais empilhadas; nada foi enviado a origem.
- **Proximo turno: humano ou Dots**, pela fila abaixo. Claude **nao tem
  credencial de push nem de merge**; por isso nenhum PR foi aberto.
- Inicio do turno: nenhuma tarefa do Dots em andamento (checkout limpo em
  `feat/dl-pr04-implied-vol` `629df7e`, sem branches novas na origem). O
  `openclaw-main-gates.patch` do Codex (hermeticidade de dois testes) **nao
  esta no repo**; continua pendente de entrega.
- Checkout deixado em `feat/dl-pr07-mcp-server` (ponta da pilha), arvore
  limpa, para que este arquivo reflita o estado mais recente.

Fila de integracao (cada item: push -> PR -> revisao -> squash-merge):

1. PR #131 — `feat/dl-pr04-implied-vol` (`629df7e`): falta so o push dos 3
   commits do Adendo 2. Validado em Linux e macOS.
2. PR #130 — `chore/tests-no-tracked-artifacts` (Codex).
3. Patch de hermeticidade do Codex (2 testes) — precisa chegar ao repo.
4. `feat/dl-pr05a-oplab-routes-errors-budget`
5. `feat/dl-pr05b-oplab-transport-client`
6. `feat/dl-pr06-chain-service`
7. `feat/dl-pr07-mcp-server`

As branches 4-7 estao **empilhadas** sobre a 1. Depois de cada squash-merge,
rebasear a seguinte: `git rebase --onto origin/main <ponta-da-anterior>
<branch>`. Sem conflito esperado: cada PR toca modulos proprios; os pontos
comuns sao `current_state.md`, ADR-0023, `BACKLOG.md` e o teste de
fronteiras, sempre em ordem de pilha.

Pendencias que so um humano resolve: push/PR/merge; assinatura e token da
OpLab (estado B); medicao de latencia nativa em macOS; assinatura do
ADR-0024 (so para a Fase 3).

---

## READY FOR PR — Lab de Derivativos DL-PR07 (servidor MCP + fechamento da Fase 1)

Current branch: `feat/dl-pr07-mcp-server`

Base: `feat/dl-pr06-chain-service` (empilhada).

Scope:

- Added `backend/derivatives/mcp/derivatives_server.py`: servidor
  `quimera-derivatives` (loopback, 8814) com `derivatives_health`,
  `derivatives_chain` (sempre `LIVE_NOT_ACTIVATED` na Fase 1) e
  `derivatives_chain_demo` (so com `QUIMERA_DERIV_CONTEXT=test`);
  `production_view` como barreira unica; `chain_view` compacta.
- `backend/derivatives/config.py`: `fixture_dir`
  (`QUIMERA_DERIV_FIXTURE_DIR`).
- Tests: `test_derivatives_mcp.py` (61) + fronteiras: `backend.mcp` e
  `fastmcp` so em `mcp/`; relogio real so em `system_clock`.
- Docs: `SDD_DL-PR07.md` (com tabela de fechamento CS1-CS11), ADR-0023,
  BACKLOG.

Validation (Linux aarch64, Python 3.12.16, deps do `uv.lock`):

- `pytest tests/ --ignore=tests/integration` rc 0 (8.028 passed, 15
  skipped); Lab + arquitetura 5.891 passed (3 ordens).
- `mypy backend/ --strict` 0 (153 arquivos); `pyright backend/` 0.
- Producao 205 linhas (<= 400); protegidos intocados; sem dependencia nova.
- Fumaca HTTP real em loopback (contextos `test` e `prod`): ok.

Scope intentionally unchanged:

- Sem provedor ao vivo, sem token, sem chamada real, sem escrita, sem
  ordens; DL-PR08 (CLI opcional) nao foi feito.
- Next: integrar a fila acima; depois, homologacao (estado B) quando houver
  assinatura OpLab.

---

## READY FOR PR — Lab de Derivativos DL-PR06 (ChainService + sintetica + latencia)

Current branch: `feat/dl-pr06-chain-service`

Base: `feat/dl-pr05b-oplab-transport-client` (empilhada).

Scope:

- Added `backend/derivatives/service/chain_service.py`: `Capture`,
  `PricedRow`, `PricedChain`, `ChainService` (`acquire`/`normalize`/`price`/
  `build`); captura de 4 leituras em ordem fixa; carimbo worst-of;
  `PricedChain.purpose` recalculado; recusa de chain com motivo nomeado.
- Added `scripts/derivatives_make_synthetic_fixture.py` e
  `tests/fixtures/derivatives/synthetic/` (BOVA11, 100 europeias, manifesto
  com hashes, README).
- Added `scripts/derivatives_latency_protocol.py` (relatorio em
  `reports/derivatives/`, ignorado pelo Git).
- Tests: `test_chain_service.py`, `test_synthetic_fixture.py`,
  `test_latency_protocol.py` (34 testes) + 2 fronteiras.
- Docs: `SDD_DL-PR06.md`, ADR-0023 secao ChainService, BACKLOG.

Validation (Linux aarch64, Python 3.12.16, deps do `uv.lock`):

- `pytest tests/ --ignore=tests/integration` rc 0 (7.964 passed, 15
  skipped); Lab + arquitetura 5.827 passed (3 ordens).
- `mypy backend/ --strict` 0 (151 arquivos); `pyright backend/` 0.
- Producao 163 linhas (<= 400); protegidos intocados.
- Latencia em VM Linux no Mac: p95 total 27,8 ms em 30 execucoes de 100
  europeias (meta 2000 ms). Medicao nativa em macOS pendente.
- Validacao independente: sigma verdadeiro da sintetica dentro de
  `[IV_bid, IV_ask]` nas linhas bem condicionadas.

Scope intentionally unchanged:

- Sem MCP (PR07), sem cache, sem persistencia, sem chamada real.
- Next: DL-PR07 (servidor MCP `quimera-derivatives`, barreira e testes de
  contaminacao).

---

## READY FOR PR — Lab de Derivativos DL-PR05b (transporte e cliente)

Current branch: `feat/dl-pr05b-oplab-transport-client`

Base: `feat/dl-pr05a-oplab-routes-errors-budget` (empilhada).

Scope:

- Added `backend/derivatives/oplab/transport.py`: `VendorResponse`,
  protocolo `Transport`, `FixtureTransport` (nunca `OBSERVED`),
  `HttpTransport` (unico ponto de `httpx` e de `OPLAB_TOKEN`; sem redirect,
  sem retry; causa `httpx` suprimida), `redact`.
- Added `backend/derivatives/oplab/client.py`: `OplabMarketClient` (4
  leituras tipadas + `ProvenanceStamp`; JSON bruto nao sai do pacote).
- Tests: `test_oplab_transport.py`, `test_oplab_client.py` (54 testes);
  fixture autouse `no_network` no `conftest.py` do Lab; fronteiras: `httpx`
  so em `oplab/transport.py`; `OPLAB_TOKEN` em exatamente 1 arquivo.
- Docs: `SDD_DL-PR05.md` (Parte B), ADR-0023.

Validation (Linux aarch64, Python 3.12.16, deps do `uv.lock`):

- `pytest tests/ --ignore=tests/integration` rc 0 (7.928 passed, 15
  skipped); Lab + arquitetura 5.791 passed.
- `mypy backend/ --strict` 0 (149 arquivos); `pyright backend/` 0.
- Producao 203 linhas (<= 400); 0 linhas > 100 col; protegidos intocados.

Scope intentionally unchanged:

- Nenhuma chamada real; nenhum token real; sem `ChainService` (PR06), sem
  MCP (PR07), sem cache, sem retry.
- Next: DL-PR06 (`ChainService` + fixture sintetica + protocolo de latencia).

---

## READY FOR PR — Lab de Derivativos DL-PR05a (rotas, erros, orcamento)

Current branch: `feat/dl-pr05a-oplab-routes-errors-budget`

Base: `feat/dl-pr04-implied-vol` (`629df7e`, ainda nao mergeada).

Scope:

- Errata ao card DL-PR05: a implementacao completa mediu 444 linhas de
  producao (> 400); dividida em Parte A (pura) e Parte B (transporte e
  cliente). Detalhes no `SDD_DL-PR05.md`.
- Added `backend/derivatives/oplab/errors.py`: `OplabError` + 11 subclasses,
  `parse_retry_after`, `classify_status` (429 sem header -> 300 s; 503 -> 1 s).
- Added `backend/derivatives/oplab/routes.py`: `MarketRoute` (4 rotas),
  `render_route` (`symbol` em `[A-Z0-9]{4,12}`), `assert_allowed` (GET,
  HTTPS, host exato, `/v3`, dupla lista enum + YAML, sem query).
- Added `backend/derivatives/oplab/budget.py`: `credential_key`,
  `RequestBudget` (50/s e 100/min deslizantes, `block_until`, `snapshot`).
- Tests: `test_oplab_routes.py`, `test_oplab_errors.py`,
  `test_oplab_budget.py` (106 testes) + 3 fronteiras de arquitetura.
- Docs: `SDD_DL-PR05.md`, ADR-0023 secao "Cliente OpLab", BACKLOG.

Validation (Linux aarch64, Python 3.12.16, deps do `uv.lock`):

- `QUIMERA_DERIV_FORBID_NETWORK=1 pytest tests/ --ignore=tests/integration`
  rc 0 (7.873 passed, 15 skipped); Lab + arquitetura 5.736 passed.
- `mypy backend/ --strict` 0 (147 arquivos); `pyright backend/` 0.
- Producao 242 linhas (<= 400); 0 linhas > 100 col; protegidos intocados.

Scope intentionally unchanged:

- Sem `httpx`, sem `OPLAB_TOKEN`, sem transporte nem cliente (Parte B), sem
  `ChainService` (PR06), sem MCP (PR07), sem chamada real.
- Next: DL-PR05b (`transport.py` + `client.py`).

---

## READY FOR MERGE — Lab de Derivativos DL-PR04 (PR #131; falta push de `629df7e`)

Current branch: `feat/dl-pr04-implied-vol`

Base: DL-PR03 mergeado via PR #128; `main == origin/main == c9c6e68` no
inicio da sessao, arvore limpa.

Scope:

- Added `backend/derivatives/pricing/implied_vol.py` (puro; `Iv` via
  `TYPE_CHECKING`): `IvStatus` (7 estados), `IvDiagnostic`/`IvResult`
  (frozen+slots, invariante `sigma is None <=> status fora de
  {OK, LOW_VEGA}` no `__post_init__`), `price_bounds`, `implied_vol` —
  bissecao pura com dominio validado, limites de nao-arbitragem, expansao
  de bracket dobrada/contada ate `bracket_hi_max`, tolerancia dupla
  (preco E vol), `NO_CONVERGENCE` com `sigma=None` (nunca o meio do
  bracket), `LOW_VEGA` com sigma preenchido e mal condicionado.
- Added `backend/derivatives/pricing/quote_iv.py`: `QuoteIv`/
  `IvResultModel`/`IvDiagnosticModel` (pydantic forbid/frozen, enum como
  str), `iv_for_quote` — bid/ask/mid separados, lado ausente vira `None`,
  cotacao intocada, `price_source_note` ("mid e indicativo").
- `contract_pricing.py`: `PricingOutcome` ganha `iv`/`sigma_source`
  opcionais (PR03 compativel); `price_contract_from_quote` em
  `contract_pricing` (nao em `quote_iv`: evitaria import circular) com
  recusa `iv_unavailable:<status|missing_quote>` e americana recusada
  antes de qualquer IV.
- Tests: `test_implied_vol.py` (round-trip 150 lados, oraculo 184 lados,
  limites, expansao, iteracoes, determinismo, dominio, invariante),
  `test_quote_iv.py`, boundaries (pureza de `implied_vol.py`, grep
  anti-`sigma=0.0`). Coleta do Lab: 891 (>= 650).
- Docs: `SDD_DL-PR04.md`, ADR-0023 secao "IV por bissecao protegida",
  BACKLOG (Jäckel/Brent validados contra esta bissecao; reformat
  calendar.py <= 100 col; casos de IV no oraculo seguem pendentes).

Validation:

- Round-trip: 128/150 lados OK, pior erro 7.3e-9 (tol 1e-6); 22 lados
  degenerados documentados (vega < low_vega_threshold).
- Oraculo: 132/184 lados OK, pior erro 7.3e-9 (tol 1e-7); 52 degenerados
  (44 LOW_VEGA, 8 NO_CONVERGENCE), zero excecoes; desfechos dos 6 `limit`
  pinados (ATM T=1e-9 recupera sigma=0.20 — errata ao card no SDD).
- Iteracoes OK: min 29 / mediana 29 / max 32 (max_iterations=200).
- `pytest tests/ --ignore=tests/integration` rc 0 (3057 passed);
  `mypy backend/ --strict` 0; `pyright backend/` 0.
- Producao 386 linhas (<= 400); 0 linhas > 100 col nos arquivos do PR
  (16 linhas longas pre-existentes de calendar/conventions viram BACKLOG).
- Adendo: gamma por diferencas finitas falhava em Linux por tolerancia;
  passo do teste subiu para h = 1e-4*S (ruido eps/h^2 cai ~100x; residuo
  vira truncatura O(h^2) estavel, pior erro 1.0e-6 vs tol 1e-5 mantida).
  Justificativa numerica no SDD_DL-PR04; bsm.py intocado.
- Adendo 2 (2026-11-18, Codex CLI): em Linux aarch64 `bsm.price` devolvia
  preco negativo (~-6e-15) em put muito OTM por cancelamento em
  `0.5*(1+erf)` e `1-N(d)`. `bsm.py` passa a usar `erfc` e `N(-d)` direto
  na put, com piso zero para residuo subnormal; novo `test_bsm_tails.py`
  (4.704 pontos de nao negatividade/paridade + 3 pinados). Producao do PR:
  399 adicoes (<= 400). Validado em Linux aarch64 (Claude): Lab +
  arquitetura 5.627 passed; mypy/pyright 0; mpmath 40.000 precos sem
  negativos. Detalhes no SDD_DL-PR04.
- Fora deste PR (existem em `main`): em clone limpo no Linux,
  `test_qwen3_summary_does_not_leak_query_payload_vectors` depende de JSON
  ignorado pelo Git e `test_pr10_sdd_and_adr_contracts_exist` abre
  `docs/adr/` em minusculas; no checkout do Mac ambos passam.

Scope intentionally unchanged:

- Sem Newton/Brent/Jäckel, americanas, superficie, HTTP/OpLab,
  ChainService (PR06), MCP (PR07), `/market/options/bs`, campo novo em
  `Iv`, mudanca em `calendar.py`/`conventions.py`.
- Next: DL-PR05 (cliente OpLab: transporte, allowlist, orcamento, erros —
  sem rede nos testes) apos merge.

---

## MERGED — Lab de Derivativos DL-PR03 (PR #128)

Current branch: `feat/dl-pr03-bsm-greeks`

Base: DL-PR02 mergeado via PR #127; `main == origin/main == e8d3719` no
inicio da sessao. Oraculo mpmath do Codex chegou como untracked em
`tests/fixtures/derivatives/reference/` apos o pre-voo (SHA-256 conferido:
`aa15a6de...92d74d`) e foi versionado neste PR.

Scope:

- Added `backend/derivatives/pricing/bsm.py`: `PricingModel`
  (`bsm_european_v1`), `PricingDomainError`, `BsmInputs` (dominio validado
  em `__post_init__`), `Greeks` (unidades no nome: `vega_per_pct_point`,
  `theta_per_day`, `rho_per_pct_point` + `theta_basis`), `BsmResult`
  (`d1`/`d2`/`regime`/`notes`), `norm_cdf`/`norm_pdf` via `math.erf`,
  `price` com regimes `regular`/`expiry`/`zero_vol` (nucleo `_analytic`
  unico; limite `sigma->0` com `N(d)` saturado), `unsupported`.
- Added `backend/derivatives/pricing/contract_pricing.py`:
  `PricingOutcome` (pydantic strict/frozen) + `price_contract` — europeia
  vira `Decimal(str(price))` + assumptions com `pricing_model`; americana/
  desconhecida: `supported=False`, motivo, campos numericos `None`.
- Added `tests/unit/derivatives/test_bsm.py` (Hull, paridade 162 casos,
  diferencas finitas centrais 5 gregas x 8 pontos, unidades, regimes,
  dominio, oraculo 92 casos) e `test_contract_pricing.py`; extensao de
  `tests/architecture/test_derivatives_boundaries.py` (bsm.py sem
  pydantic/decimal; `random` proibido no pacote).
- Versionado `tests/fixtures/derivatives/reference/` (oraculo mpmath:
  JSON 92 casos, README, gerador congelado, sha256, validation_report).
- Docs: `SDD_DL-PR03.md`, ADR-0023 secao "BSM europeu — convencoes e
  regimes", BACKLOG (Jäckel, CRR/BS-1993 Fase 2, `/market/options/bs` so
  reconciliacao, extensao do oraculo).

Validation:

- Hull: call 4.759422, put 0.808599, d1 0.769263, d2 0.627841.
- Paridade: residuo maximo ~2e-14; FD vs analitico pior caso ~5.2e-6
  (gamma, tolerancia 1e-5); oraculo pior erro ~2.8e-14 (tolerancias
  1e-9/1e-8).
- `pytest tests/ -q --ignore=tests/integration --timeout=120` rc 0;
  coleta `tests/unit/derivatives` >= 200 (506).
- `mypy backend/ --strict` 0; `pyright backend/` 0.
- Producao 245 linhas (<= 250), zero linhas > 100 colunas.

Scope intentionally unchanged:

- Sem IV (PR04), americanas (Fase 2), dividendos discretos, HTTP,
  MCP, persistencia, campo novo em `Conventions`.
- Next: DL-PR04 (IV por bissecao protegida, bid/ask/mid, diagnosticos)
  apos merge.

---

## MERGED — Lab de Derivativos DL-PR02 (PR #127)

Current branch: `feat/dl-pr02-calendar-conventions`

Base: DL-PR01 mergeado via PR #126; `main == origin/main == 05592cb` no
inicio da sessao (artefato regenerado de `evaluation/` guardado em stash
`dl-pr02-preflight`, nunca commitado).

Renumeracao (06/11): DL-PR02 = tempo (calendario + convencoes),
DL-PR03 = BSM + gregas, DL-PR04 = IV, DL-PR05 = cliente OpLab,
DL-PR06 = ChainService, DL-PR07 = MCP, DL-PR08 = CLI opcional.

Scope:

- Versionado `config/calendars/` byte a byte (3 bundles 3.0.0 2026-2028,
  PDF OC 041/2026 errata, SHA256SUMS, README); checksums conferem antes e
  depois do commit.
- `Conventions` perdeu `holidays_file` e ganhou `calendars_dir`,
  `trading_calendar_id`, `financial_calendar_id`,
  `day_count_calendar`(+assumed), `interval_convention`(+assumed),
  `year_basis` (252).
- Added `backend/derivatives/pricing/calendar.py`: `CalendarId`,
  `TradingCalendar` congelado, `load_calendar_bundle` (JSON estrito: chave
  duplicada/NaN recusados, schema 3.0.0, ano e SHA-256 conferidos),
  `build_calendar` (ano com `unknown` fica inteiro fora; projecao 2027
  lida e ignorada), `load_calendars`, `business_days_between` (bissecao),
  `is_business_day` (recusa fora da cobertura), `third_friday_preceding`.
- Added `backend/derivatives/pricing/conventions.py`: `year_fraction`,
  `continuous_rate`, `TimeToExpiry`/`time_to_expiry`, `model_assumptions`.
- Added 78 testes novos (`test_calendar.py`, `test_conventions.py`,
  extensao de `test_config.py` e boundaries) + fixture
  `calendars_bad/`; coleta do Lab = 159.
- Errata do card: base de coleta era 81 (nao ~117); alvo >= 150 atingido
  com testes substantivos (registrada no SDD_DL-PR02).

Validation:

- `pytest tests/ -q --ignore=tests/integration --timeout=120`: 2285+ passed
  (v_tests=0); carga dos 3 bundles + 2 calendarios < 1 s (guarda de teste).
- `mypy backend/ --strict` 0; `pyright backend/` 0;
  `mypy config/derivatives_config_model.py --strict` 0.
- 286 linhas de producao adicionadas (<= 300).

Scope intentionally unchanged:

- Sem BSM/gregas (PR03), IV (PR04), HTTP (PR05), persistencia PostgreSQL,
  calendarios EUA, `market_context_day`, hashes canonicos internos
  (`integrity.*_sha256` — backlog), alteracao de formato dos YAMLs.
- Next: DL-PR03 (BSM + gregas, referencias de Hull) apos merge.

---

## MERGED — Lab de Derivativos DL-PR01 (PR #126)

Current branch: `feat/dl-pr01-vendor-domain-quality`

Base: DL-PR00 mergeado via PR #125; `main == origin/main == a3d3fcf` no
inicio da sessao (apos restaurar artefatos regenerados pela suite).

Scope:

- Added `backend/derivatives/oplab/vendor_models.py`: espelho literal da doc
  OpLab v3 (`extra="allow"`, frozen), `unknown_fields`, parsers com
  `VendorPayloadError` sanitizado.
- Added `backend/derivatives/domain/models.py`: dominio imutavel
  (`extra="forbid"`, `Decimal`, `AwareDatetime` anti-naive), `Chain` com
  `purpose` validado contra `inherit_purpose(stamp.purpose)`.
- Added `backend/derivatives/domain/quality.py`: `assess_quality` pura com
  `now` injetado; limiares do modelo `Quality` existente.
- Added `backend/derivatives/adapters/normalize.py`: epoch ms -> UTC,
  `money` via `Decimal(str(...))`, zero-vs-ausente, spot com fallback
  OPTION_LAST_TRADE, SELIC preferida, `normalize_chain` com warning unico
  por campo desconhecido. (Decisao: `normalize` em `adapters/`, nao em
  `domain/`, para fronteira de import uniforme — ver SDD_DL-PR01.)
- Added 53 testes novos em `tests/unit/derivatives/` (total 81) + 2 testes
  de arquitetura (dominio nao importa oplab; sem relogio interno).
- `.gitignore`: +1 linha (`.claude/settings.local.json`).
- Errata do card registrada no SDD: epoch 1620423900000 ms =
  2021-05-07T21:45:00Z (card dizia 22:25:00).

Validation:

- `uv run pytest tests/ -q --ignore=tests/integration --timeout=120`:
  2241 passed, 15 skipped, 261 subtests (v_tests=0); collect do Lab = 81.
- `uv run mypy backend/ --strict` 0 errors; `uv run pyright backend/` 0
  errors.
- 396 linhas de producao adicionadas em `backend/` (< 400).
- Protegidos intocados; nenhum artefato de `docs/rag/`/`evaluation/` no PR.

Scope intentionally unchanged:

- Sem BSM/IV/gregas, HTTP, token, orcamento, ChainService, fixture
  sintetica, MCP, CLI, persistencia, calendario de feriados, dependencia
  nova. `config/b3_holidays_2026.yaml` apareceu no working tree durante a
  sessao e ficou fora do PR (pendencia do ADR-0023, dono: Francisco).
- Next: DL-PR02 (BSM + gregas + convencoes) apos merge.

---

## MERGED — Lab de Derivativos DL-PR00 (PR #125)

Current branch: `feat/dl-pr00-derivatives-foundation`

Base: FL-PR14 mergeado via PR #124; `main == origin/main == 231b500` no
inicio da sessao; Gate 0 (G0-A..G0-F) passou integralmente com o criterio
E3 (`--ignore=tests/integration`).

Scope:

- Added `docs/adr/ADR-0023-laboratorio-derivativos-fase1.md` (Accepted):
  decisoes 1-8, estados A/B/C, convencoes numericas como hipoteses com flag,
  barreira deterministica anti-fixture, seguranca do token OpLab, pendencias
  de homologacao.
- Added `docs/adr/ADR-0024-reversao-proibicao-corretora.md` (PROPOSED, nao
  assinado; nao altera `CLAUDE.md`).
- Added `docs/specs/derivatives/SDD_DL-PR00.md` and
  `docs/specs/derivatives/BACKLOG.md`.
- Added `backend/derivatives/` (`provenance.py`, `config.py`): enums
  Provenance/Purpose/Readiness, heranca worst-of, `ProvenanceStamp`,
  `DerivativesMcpConfig` (porta 8814) com loader env-injetavel e bloqueio
  duro de `live_homologated`.
- Added `config/derivatives.yaml` + `config/derivatives_config_model.py`
  (pydantic `extra="forbid"`, allowlist so `/market/`).
- Added `tests/fixtures/derivatives/documental/` (7 exemplos byte a byte da
  doc OpLab v3 + README + manifest.json com SHA-256 gerados por shasum).
- Added 31 testes: `tests/unit/derivatives/` (provenance, config, fixtures)
  e `tests/architecture/test_derivatives_boundaries.py`.

Validation:

- `uv run pytest tests/ -q --ignore=tests/integration --timeout=120`
  passed: 2186 passed, 15 skipped (v_tests=0).
- Lab collect: 31 testes (v_collect=0).
- `uv run mypy backend/ --strict` 0 errors; `uv run pyright backend/` 0
  errors; `config/derivatives_config_model.py` verificado em separado
  (mypy/pyright 0).
- Manifesto confere nos dois sentidos, 0 hash divergente.
- Diff vazio contra `main` em `CLAUDE.md`/`AGENTS.md`/`.claude/`/
  `pyproject.toml`/`uv.lock`; 306 linhas de producao (< 400).

Scope intentionally unchanged:

- No vendor models, normalizacao, BSM, IV, cliente HTTP, transporte,
  servidor MCP, CLI, fixture sintetica, dependencia nova, chamada de rede,
  token, rota de ordens.
- Next: DL-PR01 (vendor models + normalizacao + qualidade) apos merge.

---

## MERGED — FINLIB-0 FL-PR14 Aggregates Readiness Closeout (PR #124)

Current branch: `feat/finlib-aggregates-readiness-closeout`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/123`.
- Draft PR remote creation deferred because local `main` is ahead of
  `origin/main` and the FINLIB stack is still local-only in this workspace.

Scope:

- Added SDD `docs/specs/finlib-0/pr-14-aggregates-readiness-closeout.md`.
- Added migration `029_create_finlib_aggregates_readiness.sql`.
- Added read-only latest/aggregate views for macro, treasury, funds and
  market bars.
- Added conservative Timescale continuous aggregate readiness for
  `market_bars_1d_cagg`.
- Added `scripts/check_finlib_readiness.py`, a read-only JSON readiness gate
  for PostgreSQL/TimescaleDB extensions, schema groups, repositories, memory
  boundary, aggregate surfaces, non-destructive retention and closeout docs.
- Added data dictionary, FINLIB-0 done criteria and handoff documentation for
  future data agents.
- Added unit, architecture and integration tests for migration registration,
  readiness contract, destructive-retention absence, docs contract and live
  aggregate/readiness behavior.

Scope intentionally unchanged:

- No destructive retention policy, no data drop, no Qdrant mutation, no Kronos
  runtime, no LLM calls, no agent implementation, no ingestion pipeline, no
  portfolio/private data access and no changes to RAG semantic retrieval.

Local validation:

- `uv run pytest tests/unit/test_finlib*.py tests/unit/test_postgres_migrations_static.py tests/architecture/test_finlib_no_destructive_retention.py -q`
  passed: 87 passed.
- `uv run pytest tests/integration/test_finlib_continuous_aggregates_live.py tests/integration/test_check_finlib_readiness_live.py -q`
  skipped safely without DSN: 3 skipped.
- `uvx ruff check ...` passed.
- `uvx ruff format --check ...` passed.
- `uv run mypy ... --strict` passed.
- `uv run pyright ...` passed with only the known cosmetic Pyright update
  notice.
- `uv run sqlfluff lint backend/memory/postgres/migrations/029_create_finlib_aggregates_readiness.sql --dialect postgres`
  passed: All Finished.
- `git diff --check` passed.

---

## READY FOR LOCAL MERGE — FINLIB-0 FL-PR13 Memory Boundary

**Adversarial review verdict:** `APPROVE_WITH_NITS`
**Report:** `docs/04_MEM/FL_PR13_ADVERSARIAL_REVIEW.md`
**Sandbox:** container `f205ddd50d99` (openclaw-sandbox:latest)
**Tests in sandbox:** 23/23 boundary unit + 16/16 architecture + 89/89 FINLIB unit = 128 targeted PASSED
**import-linter:** 6/6 contracts KEPT
**mypy --strict (scope):** 0 errors
**ruff:** all clean

**NITs (non-blocking):**
- FND-01 [MAJOR]: FL-PR12 not merged into main — BLK-02 fix present and
  correct (Caminho B, commit `09a00c8`). Local merge should merge FL-PR12 and
  FL-PR13 together because this branch is intentionally stacked.
- FND-02 [NIT]: policy.py env-read gap was resolved by RC-01 commit `e0b473c`
  (`test: block memory policy environment reads`).
- FND-03 [NIT]: Pre-existing gateway timing test failure (unrelated).
- FND-04 [NIT]: Pre-existing SQLFluff violations in migrations 012-016.
  FL-PR13 adds zero SQL files.
- FND-05 [NIT]: Synthetic CPF "00000000000" in test fixtures (harmless).

**Merge condition:** merge FL-PR12 and FL-PR13 simultaneously via
`feat/finlib-memory-boundary`, preserving the stacked order:
FL-PR12 SDD -> FL-PR12 implementation -> FL-PR12 RC -> FL-PR13 SDD ->
FL-PR13 implementation -> FL-PR13 RC-01.

Current branch: `feat/finlib-memory-boundary`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/122`.
- Draft PR remote creation deferred because the local FINLIB stack is ahead of
  `origin/main` and FL-PR12 has not been published/merged remotely from this
  workspace.

Scope:

- Added SDD `docs/specs/finlib-0/pr-13-memory-boundary.md`.
- Added ADR `docs/ADR/ADR-006-qdrant-postgres-pgvector-boundary.md`.
- Added active policy doc `docs/specs/memory_policy.md`.
- Added LongRAG planning reference
  `docs/references/long-rag-postgres-memory-reference.md`.
- Added pure policy module `backend/memory/policy.py`.
- Added unit and architecture tests that make the boundary executable:
  Qdrant remains primary semantic/hybrid retriever, PostgreSQL/TimescaleDB
  remains structured long-term memory, pgvector remains auxiliary only, and
  FINLIB repositories do not import Qdrant/RAG/LLM/HTTP clients.
- Extended `.importlinter` with FINLIB/RAG/memory-policy boundary contracts.

Scope intentionally unchanged:

- No LongRAG runtime, migrations, tables, retrievers, agents, Qdrant
  collection mutation, pgvector retriever, FINLIB repository mutation, LLM
  calls, HTTP clients, secrets, DSNs, portfolio data or runtime data mutation.

---

## IN PROGRESS — FINLIB-0 FL-PR12 Repositories Assets

Adversarial RC-01 verdict was `REQUEST_CHANGES`; Codex applied the advisory
lock fix locally.

Current branch: `feat/finlib-repositories-assets`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/121`.
- Draft PR remote creation deferred because local `main` is ahead of
  `origin/main` by 35 commits.

RC-01 fix:

- Replaced advisory-lock placeholder casts that coerced Python `datetime`,
  `date` or `UUID` values through PostgreSQL `text` OID.
- Adopted typed SQL casts instead of Python pre-stringification:
  - `fund_repository.py`: `$2::timestamptz::text`
  - `fixed_income_repository.py`: `$1::uuid::text`,
    `$2::timestamptz::text`
  - `fundamentals_repository.py`: `$1::uuid::text`, `$5::date::text`
  - `macro_repository.py`: `$2::timestamptz::text`
- Added unit assertions that lock SQLs use typed casts and do not regress to
  bare temporal `$N::text` casts.

Cowork sandbox before fix (container 8b973cab9fec):

- Unit: 20/20 + 67/67 FINLIB + 123 cross-sprint PASSED
- Architecture: 4/4 PASSED
- Integration FL-PR12: 0/1 FAILED (BLK-02 live)
- Integration cross-sprint: test_finlib_repositories_core_live 1/2 FAILED (BLK-02b)
- mypy strict 0 errors | pyright 0 | ruff clean | bandit clean | BLK-01 fixed ✅

Local RC-01 validation after fix:

- `uv run pytest tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py -q`
  passed: 26 passed.
- `uv run pytest tests/integration/test_finlib_repositories_assets_live.py tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 3 skipped.
- `uv run pytest tests/architecture -q` passed: 4 passed.
- `uv run mypy backend/finlib/repositories tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py --strict`
  passed: no issues in 14 source files.
- `uv run pyright backend/finlib/repositories tests/unit/test_finlib_fund_repository.py tests/unit/test_finlib_fixed_income_repository.py tests/unit/test_finlib_fundamentals_repository.py tests/unit/test_finlib_macro_repository.py`
  passed with only the known cosmetic Pyright update notice.
- `uvx ruff check ...` passed.
- `uvx ruff format --check ...` passed.

Scope:

- Added SDD `docs/specs/finlib-0/pr-12-repositories-assets.md`.
- Added asset DTOs in `backend/finlib/repositories/models_assets.py`.
- Added `FundRepository` for `fund_registry` and `fund_daily_info`.
- Added `FixedIncomeRepository` for `fi_instruments` and `debenture_market_data`.
- Added `FundamentalsRepository` for `company_registry`, `company_listings`,
  `fundamentals_statements` and `fundamentals_indicators`.
- Reused FL-PR11 `BaseRepository`, audited transaction helper, `AuditContext`,
  `BatchWriteResult`, canonical JSON serialization and Level 0 recursive validation.
- Added architecture tests for FINLIB import boundaries and raw SQL placement.

Scope intentionally unchanged:

- No migrations, agents, ingesters, parsers, HTTP clients, ORM, SQLAlchemy,
  FastAPI, MCP, A2A runtime, Qdrant mutation, LLM call, pgvector policy,
  private portfolio data or secrets.

---

## IN PROGRESS — FINLIB-0 FL-PR11 Repositories Core

Current branch: `feat/finlib-repositories-core`

GitHub:

- Issue created: `https://github.com/franciscosalido/OPENCLAW/issues/120`.
- Draft PR remote creation deferred because local `main` is ahead of
  `origin/main` by 31 commits. Opening a Draft PR now would include unrelated
  prior local sprint commits.

Scope:

- Added SDD `docs/specs/finlib-0/pr-11-repositories-core.md`.
- Added asyncpg-only repository package under `backend/finlib/repositories/`.
- Added typed DTOs for audit context, ops, macro and treasury writes.
- Added shared audited transaction helper that writes domain data and exactly
  one `audit_agent_writes` row in one transaction.
- Added `OpsRepository` for sources, runs, watermarks, quality checks and
  outbox polling.
- Added `MacroRepository` for macro catalog and append-only observations with
  advisory-lock revision allocation.
- Added `TreasuryRepository` for treasury bond catalog and idempotent temporal
  prices.
- Added unit boundary tests and live integration test for repository flow,
  audit counts, rollback and outbox concurrency.

Schema reality:

- Migration head at PR start: `028_create_company_fundamentals.sql`.
- Watermark backing table already exists: `ops_ingestion_watermarks`.
- No new migration is planned for FL-PR11.
- `audit_agent_writes.batch_hash` is the audit hash column used by
  `AuditContext.batch_hash`.

Validation so far:

- `uv run pytest tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py -q`
  passed: 25 passed.
- `uv run pytest tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 2 skipped.
- `uvx ruff check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uvx ruff format --check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uv run mypy backend/finlib/repositories --strict` passed.
- `uv run pyright backend/finlib/repositories` passed with only the known
  cosmetic Pyright update notice.

RC-01 adversarial review fix:

- Cowork found a live PostgreSQL BLOCKER: repository SQL used `$N::jsonb` while
  the repositories pass canonical JSON strings produced by
  `_json_dumps_canonical()`.
- The project pool configures asyncpg JSON/JSONB codecs, so `$N::jsonb` caused
  asyncpg to encode the already-serialized string again. PostgreSQL then saw a
  JSONB string instead of a JSONB object, tripping `jsonb_typeof(...) = 'object'`
  checks such as `ops_data_sources_metadata_check`.
- Fixed repository SQL to cast all pre-serialized repository payloads through
  `::text::jsonb`.
- Added a unit boundary test that rejects bare `::jsonb` casts inside
  `backend/finlib/repositories/` and requires the `::text::jsonb` contract.

RC-01 validation:

- `uv run pytest tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py -q`
  passed: 26 passed.
- `uv run pytest tests/integration/test_finlib_repositories_core_live.py -q`
  skipped safely without host DSN: 2 skipped.
- `uvx ruff check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uvx ruff format --check backend/finlib/repositories backend/finlib/__init__.py tests/unit/test_finlib_ops_repository.py tests/unit/test_finlib_macro_repository.py tests/unit/test_finlib_treasury_repository.py tests/unit/test_finlib_repository_boundaries.py tests/integration/test_finlib_repositories_core_live.py`
  passed.
- `uv run mypy backend/finlib/repositories --strict` passed.
- `uv run pyright backend/finlib/repositories` passed with only the known
  cosmetic Pyright update notice.

Scope intentionally unchanged:

- No agents, ingesters, parsers, HTTP clients, ORM, SQLAlchemy, FastAPI, MCP,
  A2A runtime, Qdrant mutation, pgvector policy, private portfolio data or
  secrets.

---

## IN PROGRESS — FINLIB-0 FL-PR10 Company Fundamentals

Current branch: `feat/finlib-fundamentals`

RC-01 adversarial review fixes:

- Fixed `test_fundamentals_statement_constraints` argument ordering so `$9`
  receives `run_id` and `$10` receives `lineage_hash`. Before this fix,
  `asyncpg` raised `DataError` during UUID binding and the live PostgreSQL
  CHECK constraints were not exercised.
- Narrowed migration 028 `ops_data_sources ON CONFLICT` behavior so existing
  `kind`, `base_url`, and `enabled` values are not silently overwritten.
- Added static coverage asserting migration 028 does not overwrite those
  source identity/operational fields while still merging metadata.

RC-02 adversarial review follow-up:

- Cowork RC-01 verdict was `APPROVE` after sandbox confirmed 7/7 live
  `CheckViolationError` cases for `test_fundamentals_statement_constraints`.
- Resolved the remaining source-conflict nit explicitly in the SDD: migration
  028 may refresh documentation fields and merge metadata, but must not
  overwrite source identity or operational fields such as `kind`, `base_url`
  or `enabled`.
- The remaining timing flap in `test_gateway1_proof_of_life.py` is
  pre-existing and outside FL-PR10 scope.

Scope:

- Adds migration `028_create_company_fundamentals.sql`.
- Adds four tables: `company_registry`, `company_listings`,
  `fundamentals_statements`, and `fundamentals_indicators`.
- Seeds public source contracts for CVM company registry, CVM DFP, CVM ITR,
  and B3 listings through `ops_data_sources`.
- Keeps company identity separate from listings, so PETR3/PETR4 may point to
  one canonical `company_id`.
- Stores DFP/ITR restatements as immutable `version + 1` statement rows.
- Stores only statement-derived indicators; market-dependent valuation
  indicators remain out of scope.
- Makes `fundamentals_indicators` a TimescaleDB hypertable partitioned by
  `ts`, with all primary/unique constraints including the partition column.
- Adds `backend/finlib/fundamentals.py` with strict Pydantic indicator model
  and deterministic statement-only derivation/hash helpers.

Validation:

- `uv run pytest tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 28 passed.
- `uv run pytest tests/integration/test_fundamentals_restatement_live.py::test_fundamentals_statement_constraints -q`
  skipped safely without host DSN: 1 skipped. Cowork should rerun this inside
  code-sandbox-mcp with `TEST_POSTGRES_DSN` set to confirm 7 live
  `CheckViolationError` cases.
- `uv run pytest tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py -q`
  collected cleanly and skipped safely without host DSN: 7 skipped.
- `uvx ruff check backend/finlib/fundamentals.py backend/finlib/__init__.py tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py`
  passed.
- `uvx ruff format --check backend/finlib/fundamentals.py backend/finlib/__init__.py tests/unit/test_company_fundamentals_schema_contract.py tests/unit/test_fundamentals_python_indicators.py tests/unit/test_postgres_migrations_static.py tests/integration/test_company_listing_link_live.py tests/integration/test_fundamentals_restatement_live.py`
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/028_create_company_fundamentals.sql --dialect postgres`
  passed.
- `uv run mypy backend/finlib/fundamentals.py --strict` passed.
- `uv run pyright backend/finlib/fundamentals.py` passed with only the known
  cosmetic Pyright update notice.

Scope intentionally unchanged:

- No repository, ingestion agent, downloader, HTTP client, MCP/A2A runtime,
  Qdrant mutation, pgvector policy, user position, portfolio, brokerage or
  secret handling changes.

---

## FIXED LOCALLY — FINLIB-0 FL-PR09 RC-01 Adversarial Nits

Current branch: `feat/finlib-debenture-market-data`

Context:

- Cowork approved FL-PR09 with nits.
- NIT-01: `debenture_market_data` insert/update trigger guarded `fi_id`, but
  `fi_instruments.kind` could still drift from `debenture` to another kind
  after market data rows existed.
- NIT-02: `evaluation/results/` artifacts were dirty in the worktree and could
  be accidentally staged.

Resolution:

- Added migration `027_guard_debenture_kind_drift.sql` instead of editing the
  already reviewed migration `026`, preserving checksum stability.
- Added `prevent_debenture_market_data_kind_drift()`.
- Added trigger `trg_fi_instruments_debenture_market_data_kind_guard` on
  `fi_instruments BEFORE UPDATE OF kind`.
- The trigger rejects changing an instrument away from `debenture` when rows
  already exist in `debenture_market_data`.
- Added static schema assertions for the new bidirectional kind guard.
- Added live integration coverage for attempted `debenture -> cdb` drift after
  inserting temporal market data.
- Added explicit `evaluation/results/*` ignore rule while preserving
  `evaluation/results/.gitkeep`.
- Documented the bidirectional invariant in the FL-PR09 SDD.

Validation:

- `uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 16 passed.
- `uv run pytest tests/integration/test_debenture_market_data_hypertable_live.py -q`
  skipped safely without host DSN: 14 skipped.
- `uvx ruff check tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uvx ruff format --check tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run mypy --strict tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run pyright tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed with only the known cosmetic Pyright update notice.
- `uvx sqlfluff lint backend/memory/postgres/migrations/026_create_debenture_market_data.sql backend/memory/postgres/migrations/027_guard_debenture_kind_drift.sql --dialect postgres`
  passed.
- `git diff --check` passed.

Scope intentionally unchanged:

- No repository, ingestion agent, live downloader, MCP/A2A runtime, Qdrant,
  pgvector, user-position, brokerage, portfolio or secret handling changes.
- Pre-existing dirty tracked result artifacts were not reverted or staged.

---

## CONTEXT UPDATE — Cowork Reviewer Pack

Current branch: `feat/finlib-debenture-market-data`

What changed:

- Added `docs/04_MEM/COWORK_REVIEWER_CONTEXT.md`.
- Added a compact pointer in `CLAUDE.md`.
- Kept `docs/04_MEM/current_state.md` as live state and
  `docs/04_MEM/decisions.md` as durable decision log.

Purpose:

- Give Claude Cowork a token-cheap A2A reviewer pack.
- Keep adversarial review structured, compact and evidence-first.
- Reduce repeated context expansion in reviewer prompts.
- Preserve settled runtime truths such as Qdrant `1.18.x` family parity.

Scope intentionally unchanged:

- No MCP connector, desktop extension or remote connector was added.
- No secrets, `.env`, service runtime state, DB state or generated reports were
  touched for this context update.

---

## CONTEXT UPDATE — Qdrant/UV Lock Integrity

Current branch: `feat/finlib-debenture-market-data`

Decision treated as settled:

- Qdrant server/client parity is by `1.18.x` family, not exact patch parity.
- Active server target remains `qdrant/qdrant:v1.18.2`.
- Accepted Python client target remains `qdrant-client 1.18.0`.
- Do not reopen the Qdrant 1.18 family decision unless a future explicit
  upgrade sprint requests it.

What changed:

- `pyproject.toml` now bounds the Python SDK to `qdrant-client>=1.18,<1.19`.
- `uv.lock` was regenerated and resolves `qdrant-client==1.18.0`.
- `infra/qdrant/version_contract.yaml`, ADR-018, PKD-D2P-00Y and active Qdrant
  result docs now document the bounded `1.18.x` dependency contract.
- `CLAUDE.md` now reports Qdrant v1.18.2 via Docker and a Python SDK bounded to
  the `qdrant-client 1.18.x` family.
- `backend/rag/qdrant_store.py` was inspected and did not require edits; it
  already uses the modern `query_points` API instead of legacy `search`.

Validation:

- Static search confirms no active dependency on `qdrant-client==1.13.2`.
- `uv.lock` contains `qdrant-client` version `1.18.0` under the project
  specifier `>=1.18,<1.19`.
- Runtime `uv run` verification was intentionally not repeated after the human
  decision to accept server `1.18.x` and client `1.18.0` as the project truth.

Scope intentionally unchanged:

- No Qdrant container restart, rebuild, volume reset or collection mutation.
- No dependency family upgrade to `1.19+`.
- No changes to unrelated PR-08/PR-09 generated result artifacts already dirty
  in the worktree.

---

## IN PROGRESS — FINLIB-0 FL-PR09 Debenture Market Data

Current branch: `feat/finlib-debenture-market-data`

GitHub workflow:

- Issue created: https://github.com/franciscosalido/OPENCLAW/issues/119
- Initial SDD committed locally:
  `afc1506 docs: define finlib debenture market data SDD`.
- Draft PR creation was attempted after the SDD commit, but GitHub rejected it
  because the stacked local branch is not published and the remote could not
  resolve a head SHA. No push, force-push or merge to `main` was performed.

Goal:

- Add temporal market data for debentures already represented in
  `fi_instruments`, without repositories, agents, live downloaders, external
  clients, user-position tables, Qdrant or pgvector changes.

Implemented in this branch:

- Added migration `026_create_debenture_market_data.sql`.
- Added exactly one table: `debenture_market_data`.
- Modeled `debenture_market_data` as a TimescaleDB hypertable on `ts` with
  one-month chunks.
- Used `fi_id UUID REFERENCES fi_instruments(instrument_id)` instead of ISIN
  as database identity.
- Enforced that market rows point only to `fi_instruments.kind = 'debenture'`
  with trigger `trg_debenture_market_data_instrument_kind`.
- Added revisioned temporal identity with `PRIMARY KEY (fi_id, ts, revision)`
  and idempotent content lineage via `UNIQUE (lineage_hash, ts)`.
- Required provenance through `source_id`, `run_id`, `lineage_hash`,
  `schema_version`, object-only `quality_flags` and object-only `metadata`.
- Added data-quality checks for at least one measurement, positive PU when
  present, non-negative duration and non-whitespace lineage.
- Narrowly hardened the existing `anbima_debentures` source limitations for
  secondary-market observations without creating a second debenture catalog.
- Added static schema-contract tests and live isolated PostgreSQL tests for
  hypertable, constraints, trigger, revision history and cross-sprint tables.

Validation so far:

- `uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 16 passed.
- `uv run pytest tests/unit -q` passed: 2029 passed, 261 subtests passed.
- `uv run pytest tests/integration/test_debenture_market_data_hypertable_live.py -q`
  skipped safely: 13 skipped because no test DSN was present in the current
  host environment.
- `scripts/vibe_deep_run.sh 'uv run pytest tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py -q'`
  passed in the Python 3.12 Vibe sandbox with live services: 22 passed.
- `uv run mypy --strict tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed.
- `uv run pyright tests/unit/test_debenture_market_data_schema_contract.py tests/integration/test_debenture_market_data_hypertable_live.py`
  passed with the known cosmetic Pyright version notice.
- `uvx ruff check` and `uvx ruff format --check` on changed Python tests
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/026_create_debenture_market_data.sql --dialect postgres`
  passed.
- `git diff --check` passed.

Scope intentionally unchanged:

- No CRI/CRA market data table.
- No `fi_positions`.
- No user holdings, account identifiers, personal identifiers, brokerage or
  portfolio fields.
- No repository, ingestion agent, HTTP client, MCP/A2A runtime, Qdrant or
  pgvector mutation.

---

## FIXED LOCALLY — FINLIB-0 FL-PR08 RC-01 Hardening

Current branch: `feat/finlib-private-fixed-income`

Context:

- Adversarial review approved FL-PR08 with two nits: Python did not expose a
  pre-DB `issuer_cnpj` validator, and `compute_quality_flags()` did not warn
  for uncommon `cdb + igpm` combinations.

Resolution:

- Added `validate_issuer_cnpj()` to `backend.finlib.rate_spec` and exported it
  from `backend.finlib`.
- Extended `validate_rate_spec_for_instrument()` with an optional
  `issuer_cnpj` parameter so future repositories can validate CNPJ shape
  before attempting a database write.
- Added unit coverage for valid, masked, short, long and non-numeric CNPJ
  values.
- Added an advisory `uncommon_cdb_igpm` quality flag while keeping warnings
  non-blocking and outside database constraints.
- Updated FL-PR08 SDD with the Python CNPJ validator and quality-flag behavior.

Scope intentionally unchanged:

- No migration edits after `025`.
- No database checksum churn.
- No repository, live ingestion, external client, user-position table or
  runtime service changes.

---

## IN PROGRESS — FINLIB-0 FL-PR08 Private Fixed Income

Current branch: `feat/finlib-private-fixed-income`

GitHub workflow:

- Issue created: https://github.com/franciscosalido/OPENCLAW/issues/118
- Draft PR creation was attempted before implementation, but GitHub rejected it
  because the branch had no commits and local `main` is ahead of
  `origin/main` by the stacked FINLIB commits. The branch remains local until
  the stacked base is published or coordinated.

Goal:

- Add the minimal private fixed-income reference catalog for CDB, LCA, LCI,
  CRI, CRA and debenture without repositories, agents, ingesters, external
  clients, user positions, valuation, Qdrant or pgvector changes.

Implemented in this branch:

- Added migration `025_create_fi_instruments.sql`.
- Added exactly one table: `fi_instruments`.
- Seeded `local_fixed_income_input` and `anbima_debentures` in
  `ops_data_sources` using existing allowed source kinds.
- Modeled `issuer_cnpj` as 14 canonical digits and optional ISO-like `isin`.
- Constrained `kind`, `indexer`, `rate_spec` JSONB shape, source provenance,
  JSONB object fields, non-whitespace text and unique `lineage_hash`.
- Enforced fail-safe FGC semantics: CRI, CRA and debenture cannot be
  `fgc_covered = true`.
- Enforced `maturity_date` for CRI, CRA and debenture, and `maturity_date >=
  issue_date` when both are present.
- Added `backend.finlib.rate_spec.RateSpec` as a strict Pydantic v2 model with
  semantic validation for prefixado, percent-of-indexer, indexer-plus-spread
  and inflation-plus-coupon contracts.
- Added canonical `compute_fi_lineage_hash()` and explicit rejection of Level
  0 position fields.
- Documented the Level 0 boundary in the FL-PR08 SDD.

Validation:

- `uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py -q`
  passed: 34 passed.
- `uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 41 passed.
- `uv run pytest tests/unit -q` passed: 2013 passed, 261 subtests passed.
- `uv run mypy --strict .` passed: no issues in 441 source files.
- `uv run pyright backend/finlib tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py`
  passed: 0 errors, 0 warnings.
- `uvx ruff check .`, `uvx ruff format --check .`, and `git diff --check`
  passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/025_create_fi_instruments.sql --dialect postgres`
  passed.
- Full SQLFluff over historical migrations still fails on pre-existing
  migrations 000-016; migration 025 is clean.
- `scripts/vibe_deep_run.sh 'uv run pytest tests/unit/test_fi_instruments_schema_contract.py tests/unit/test_fi_rate_spec_validation.py -q'`
  was attempted, but Docker failed before tests with `DeadlineExceeded` while
  resolving `docker/dockerfile:1`.

Scope intentionally unchanged:

- No `fi_positions`.
- No user holdings, accounts, CPF, broker/custodian or portfolio fields.
- No live data access.
- No repository, agent, MCP, A2A runtime, Qdrant or pgvector mutation.

---

## FIXED LOCALLY — FINLIB-0 FL-PR07 RC-02 Fund Whitespace Coverage

Current branch: `codex/fl-pr07-rc02-fund-whitespace-tests`

Context:

- The adversarial V2 review confirmed the FL-PR07 schema was correct, but
  flagged a permanent coverage gap: live whitespace tests covered
  `legal_name` but not nullable registry descriptors `cvm_class` and
  `fund_type`.

Resolution:

- Expanded the live integration parametrization to cover whitespace-only
  `cvm_class` and `fund_type` values.
- Fixed the test statement builder so the parametrized field is actually
  inserted for nullable fields instead of only changing `legal_name`.
- Documented the registry text contract in the FL-PR07 SDD: optional
  descriptors may be absent, but cannot be semantic whitespace when present.

Scope intentionally unchanged:

- No migration edits.
- No schema checksum changes.
- No runtime ingestion, repository or agent code.

---

## IN PROGRESS — FINLIB-0 FL-PR07 Fund Library

Current branch: `feat/finlib-fund-library`

RC-01 migration checksum hardening:

- Fixed pre-existing checksum drift for
  `022_create_macro_catalog_observations.sql`.
- Root cause: a documentation-only SQL comment about `value <> 0` was added
  after migration 022 had already been applied to the local PostgreSQL
  database. The live `schema_migrations` checksum was
  `1b2a45c168d3e6ce0b26f606a3dd437b25e19974db9b2da035959279ff741d76`.
- Resolution: restored migration 022 to the already-applied canonical content
  by removing the post-apply inline comment; the explanation remains in the
  FL-PR05 SDD.
- Added a unit guard pinning the canonical migration 022 checksum so future
  cosmetic edits fail before runtime.
- Fixed two Vibe integration false positives where offline LiteLLM MCP config
  tests inherited `host.docker.internal` from the sandbox environment. The
  tests now pass explicit loopback-only offline env maps and the runtime
  validator remains strict.

RC-01 validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 25 passed.
- `uv run pytest tests/integration/test_pr07_litellm_mcp_registration_smoke.py tests/integration/test_pr08_litellm_mcp_tools_live.py tests/unit/test_macro_series_seed.py -q`
  passed: 20 passed.
- Vibe targeted checksum-regression suite passed:
  `test_postgres_repository.py`, `test_pr01_concurrency_gaps.py`,
  `test_pr02_market_bars_concurrency.py` -> 19 passed.
- Vibe full integration suite passed: 192 passed, 14 skipped,
  3 subtests passed.
- `uv run mypy --strict` on changed test files passed.
- `uvx ruff check` and format check on changed test files passed.

Workflow note:

- `git pull --ff-only` on local `main` reported "Already up to date".
- Branch `feat/finlib-fund-library` was created from local `main`.
- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch had not been pushed. No push or merge
  was performed.

Goal:

- Add the minimal CVM fund registry and Informe Diario library for FINLIB-0
  without implementing repositories, agents, MCP tools, runtime ingestion,
  live CVM clients, Qdrant changes, pgvector changes or FL-PR08+ tables.

Implemented in this branch:

- Added migration `024_create_fund_registry_daily_info.sql`.
- Added exactly two tables: `fund_registry` and `fund_daily_info`.
- Seeded canonical source `cvm_informes_diarios` in `ops_data_sources` with
  `kind='regulator'`.
- Modeled `fund_cnpj` as the canonical 14-digit natural key in
  `fund_registry`.
- Modeled `fund_daily_info` as a TimescaleDB hypertable on `ts` with
  `chunk_time_interval => INTERVAL '1 month'`.
- Enforced revisioned history with
  `PRIMARY KEY (fund_cnpj, ts, revision)` and idempotency with
  `UNIQUE (lineage_hash, ts)`.
- Added data-quality constraints for mandatory positive `quota_value`,
  mandatory `net_worth`, non-negative `shareholders`, non-negative flows when
  present, mandatory provenance, object-only JSONB fields and semantic text
  guards using `~ '\S'`.
- Documented CVM CSV semantics, CNPJ normalization, DT_COMPTC timestamp
  semantics, future reapresentacao by `revision+1`, advisory-lock mitigation
  and future repository/audit transaction contract.
- Added static schema tests, CSV sample normalization/lineage tests and live
  isolated PostgreSQL integration tests for hypertable, idempotency,
  reapresentacao and DQ constraints.

Validation so far:

- `uv run pytest tests/unit/test_fund_schema_contract.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 17 passed.
- Local integration without DSN skipped safely: 27 skipped.
- Vibe sandbox focused unit suite passed: 17 passed.
- Vibe sandbox live integration suite passed: 27 passed.
- `uv run mypy --strict tests/unit/test_fund_schema_contract.py tests/integration/test_fund_daily_info_hypertable_live.py tests/integration/test_fund_daily_info_idempotency_live.py`
  passed.
- `uvx ruff check` on new tests passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/024_create_fund_registry_daily_info.sql --dialect postgres`
  passed.

---

## IN PROGRESS — FINLIB-0 FL-PR06 Treasury Library

Current branch: `feat/finlib-treasury-library`

RC-01 reviewer hardening:

- Documented the explicit price-correction policy in
  `docs/specs/finlib-0/pr-06-treasury-library.md`: FL-PR06 has no
  `revision` column, so a corrected `(bond_id, ts)` observation is rejected by
  the primary key and must become a future repository-level audited policy or a
  future revisioned migration.
- Added live integration coverage proving negative rates are accepted when the
  rate spread remains sane.
- Expanded the test-local Tesouro CSV bond-type normalizer to cover all
  treasury bond labels accepted by the schema.

Goal:

- Add the minimal Tesouro Direto mark-to-market library for FINLIB-0 without
  implementing repositories, agents, MCP tools, runtime ingestion, Qdrant
  changes, pgvector changes or FL-PR07+ financial tables.

Implemented in this branch:

- Added migration `023_create_treasury_bonds_prices.sql`.
- Added exactly two tables: `treasury_bonds` and `treasury_prices`.
- Seeded canonical source `tesouro_transparente` in `ops_data_sources` with
  `kind='treasury'`, matching the enum introduced by FL-PR02.
- Modeled `treasury_prices` as a TimescaleDB hypertable on `ts` with
  `chunk_time_interval => INTERVAL '1 month'`.
- Enforced `PRIMARY KEY (bond_id, ts)` and
  `UNIQUE (lineage_hash, ts)` so all unique constraints on the hypertable
  include the partitioning column.
- Added data-quality constraints for non-negative prices/base value, spread
  sanity, no all-null observation rows, mandatory provenance, object-only JSONB
  fields and no operationally future-dated `ts`.
- Documented the Tesouro CSV contract, normalized reference-date semantics,
  source-kind choice and future repository/audit transaction contract.
- Added static contract tests, CSV sample round-trip tests and live isolated
  PostgreSQL integration tests for hypertable/idempotency/DQ semantics.

Workflow note:

- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch had not been pushed. No push or merge
  was performed.

---

## FIXED LOCALLY — FINLIB-0 FL-PR05 RC-01 PTAX Evidence Notes

Context:

- Adversarial review flagged two minor findings before commit:
  `vw_fx_brlusd` used `value <> 0` without an inline explanation, and
  `ptax_usdbrl_venda` used provider code `1` while the review expected
  `10814`.

Resolution:

- Added an inline SQL comment documenting that `value <> 0` prevents division
  by zero in derived BRL/USD columns.
- Researched BCB Dados Abertos and bounded BCData/SGS API responses.
- Kept `ptax_usdbrl_venda.provider_code = "1"` because BCB Dados Abertos
  identifies SGS `1` as daily USD/BRL venda, while a bounded API sanity check
  for `10814` returned a non-FX value in the checked window.
- Documented the evidence in `docs/specs/finlib-0/pr-05-macro-library.md`.
- Added a unit contract locking the current planning-reference decision:
  compra `10813`, venda `1`, venda not `10814`, still requiring live
  verification before operational ingestion.

Validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 24 passed.
- `uvx sqlfluff lint backend/memory/postgres/migrations/022_create_macro_catalog_observations.sql --dialect postgres`
  passed.
- `uvx ruff check tests/unit/test_macro_series_seed.py` and
  `uvx ruff format --check tests/unit/test_macro_series_seed.py` passed.
- `uv run mypy --strict tests/unit/test_macro_series_seed.py` passed.

---

## IN PROGRESS — FINLIB-0 FL-PR05 Macro Library

Current branch: `feat/finlib-macro-library`

Goal:

- Add the minimal Brazilian macroeconomic and FX library for FINLIB-0 without
  implementing repositories, ingestion agents, MCP tools or FL-PR06+ tables.

Implemented in this branch:

- Added migration `022_create_macro_catalog_observations.sql`.
- Added exactly two tables: `macro_series_catalog` and `macro_observations`.
- Added exactly one view: `vw_fx_brlusd`.
- Seeded canonical source `bcb_sgs` in `ops_data_sources` with explicit
  methodology limitations and live-verification warning.
- Seeded seven catalog series: IPCA, IGP-M, Selic meta, Selic diaria, CDI,
  PTAX USD/BRL compra and PTAX USD/BRL venda.
- Marked all SGS provider codes as `planning_reference` with
  `requires_live_verification = true`; no provider code is treated as ground
  truth in this PR.
- Made `macro_observations` a TimescaleDB hypertable on `ref_ts` with
  `chunk_time_interval => INTERVAL '3 months'`.
- Enforced provenance with mandatory `source_id`, `run_id` and
  `lineage_hash`; `source_id` references `ops_data_sources`, and `run_id`
  references `ops_ingestion_runs`.
- Modeled revisions as append-only rows via
  `PRIMARY KEY (series_code, ref_ts, revision)`.
- Modeled identical reingestion idempotency with
  `UNIQUE (lineage_hash, ref_ts)`, because TimescaleDB unique constraints on
  hypertables must include the partition column.
- Kept BRL/USD out of storage; `vw_fx_brlusd` derives BRL/USD from latest
  PTAX USD/BRL compra/venda revisions.
- Documented the future repository contract: domain writes and exactly one
  `audit_agent_writes` row per logical batch in the same transaction.

Validation:

- `uv run pytest tests/unit/test_macro_series_seed.py tests/unit/test_postgres_migrations_static.py -q`
  passed: 23 passed.
- `uv run pytest tests/unit -q` passed: 1955 passed, 261 subtests passed.
- Local integration without DSN skipped safely: 19 skipped.
- Vibe sandbox focused suite passed: 35 passed.
- Vibe sandbox live hypertable suite passed: 14 passed.
- Vibe sandbox live revision/view suite passed: 5 passed.
- `uv run mypy --strict .` passed: no issues in 431 source files.
- `uv run pyright backend/` passed: 0 errors, 0 warnings.
- `uvx ruff check .`, `uvx ruff format --check .`,
  `uvx sqlfluff lint backend/memory/postgres/migrations/022_create_macro_catalog_observations.sql --dialect postgres`,
  and `git diff --check` passed.

Workflow limitation:

- Draft PR creation was attempted before implementation, but `gh pr create`
  could not proceed because the branch was local/unpushed and the worktree had
  local changes. No push or merge was performed.
- Full SQLFluff over all historical migrations still reports pre-existing
  style violations in migrations 000-016; migration 022 is SQLFluff-clean.

---

## IN PROGRESS — FINLIB-0 FL-PR04 Audit Agent Writes

Current branch: `feat/finlib-audit-agent-writes`

Goal:

- Add append-only audit storage for future FINLIB data-agent/repository writes,
  without implementing repositories, agents, MCP write tools or FL-PR05+
  financial library tables.

Implemented in this branch:

- Added migration `021_create_audit_agent_writes.sql`.
- Added exactly one table: `audit_agent_writes`.
- Added mandatory `trace_id`, optional `run_id` FK to `ops_ingestion_runs`,
  semantic non-whitespace guards for `agent_id`, `repository`, `target_table`
  and `batch_hash`, safe JSONB-object `metadata`, `row_count >= 0`, and
  operation domain `insert/update/upsert/bulk_insert/bulk_upsert`.
- Explicitly excluded `delete` as an audit operation for this PR.
- Added focused indexes on `trace_id`, partial `run_id`, `(agent_id,
  created_at DESC)` and `(repository, target_table, created_at DESC)`.
- Added `prevent_audit_agent_writes_mutation()` and
  `trg_audit_agent_writes_append_only` to reject UPDATE/DELETE with an
  append-only error.
- Added `REVOKE UPDATE, DELETE ... FROM PUBLIC` as defense-in-depth and
  documented that PostgreSQL owner capability means the trigger is the
  authoritative guard in the current single-role setup.
- Added SDD documentation for future repository transaction atomicity: domain
  write and exactly one audit row per logical batch in the same transaction.
- Added static unit tests and live isolated PostgreSQL tests for insert,
  trigger append-only behavior, constraints, FK, metadata safety, ACL catalog
  inspection and optional non-owner role enforcement when CREATE ROLE is
  available.

Workflow limitation:

- GitHub Issue/Draft PR creation was attempted but blocked locally by GitHub
  CLI keyring/API timeout. Branch remains local and unmerged into `main`.

---

## FIXED LOCALLY — FINLIB-0 Migration 020 Checksum Drift

Context:

- Adversarial review for FL-PR04 found a pre-existing checksum drift on
  `020_create_ops_watermarks_quality_outbox.sql`.
- The drift was caused by comments added after the migration had already been
  applied to local PostgreSQL environments.

Resolution:

- Restored migration `020_create_ops_watermarks_quality_outbox.sql` to the
  original applied content with SHA-256
  `bb63d55faede65436f58e4b44c5d0ab6e5d3c352d6b150e81fcbcf03b7cbe99e`.
- Moved the explanatory text about `CREATE OR REPLACE`, `watermark_value` and
  non-concurrent indexes into
  `docs/specs/finlib-0/pr-03-watermarks-quality-outbox.md`.
- Updated unit tests so documentation assertions read the SDD, not the
  immutable migration text.

---

## IN PROGRESS — FINLIB-0 FL-PR03 RC-01 Review Hardening

Current branch: `feat/finlib-watermarks-quality-outbox-rc01`

Goal:

- Close non-blocking reviewer findings for FL-PR03 without expanding scope
  beyond watermarks, data-quality checks and outbox tables.

Implemented in this branch:

- Documented in the SDD that `watermark_ts` is the canonical monotonic
  comparator and `watermark_value` is a descriptive label only.
- Documented in the SDD why FL-PR03 uses `CREATE OR REPLACE` for
  function/trigger idempotency and why indexes deliberately avoid
  `CONCURRENTLY` under the transactional migration runner.
- Added live adversarial PostgreSQL coverage for missing
  `aggregate_type`/`aggregate_id` in outbox events.
- Added live adversarial PostgreSQL coverage for `attempts > max_attempts`.

---

## IN PROGRESS — Qdrant 1.18.x test warning hardening

Current branch: `feat/finlib-watermarks-quality-outbox`

Goal:

- Keep Vibe/pytest output clean without changing the accepted Qdrant 1.18.x
  compatibility policy.

Implemented in this branch:

- Accepted Cowork's root-cause finding: `qdrant-client >=1.17.1` runs
  server-version probing in a daemon thread; in Docker, `localhost:6333` can
  point to the container loopback, so the background probe warns even when
  client `1.18.0` and server `1.18.2` are compatible by major/minor family.
- Added pytest warning filtering in `pyproject.toml` and global Python warning
  filtering in `tests/conftest.py` for only
  `Failed to obtain server version` `UserWarning`.
- Set `asyncio_default_fixture_loop_scope = "function"` to remove the pytest
  asyncio deprecation warning.
- Documented the temporary filter and removal rule in
  `docs/testing/vibe_deep_testing.md`.

Future cleanup:

- When PyPI publishes `qdrant-client >=1.18.2`, run
  `uv lock --upgrade-package qdrant-client`, remove both warning filters, and
  rerun Vibe tests with `-W always`.

---

## IN PROGRESS — FINLIB-0 FL-PR03 Watermarks, Quality and Outbox

Current branch: `feat/finlib-watermarks-quality-outbox`

Goal:

- Add operational idempotency, data-quality recording and a minimal Postgres
  outbox for FINLIB-0 without data agents, repositories, audit tables or MCP
  tools.

Implemented in this branch:

- Added migration `020_create_ops_watermarks_quality_outbox.sql`.
- Added `ops_ingestion_watermarks` with `(source_id, dataset)` primary key,
  JSONB object metadata, source/run FKs and direct-update trigger protection
  against timestamp regression.
- Added `ops_data_quality_checks` with severity limited to `info`, `warning`,
  `error` and `critical`, JSONB object contracts and run FK.
- Added `ops_outbox_events` with explicit status lifecycle, retry counters,
  lock metadata constraints and partial pending poll index.
- Documented and tested the official outbox poll contract using
  `FOR UPDATE SKIP LOCKED`.
- Added static schema tests and live isolated PostgreSQL tests for outbox
  double-dispatch prevention, empty poll latency and watermark concurrency.

Known workflow limitation:

- Draft PR/Issue creation was not completed because `gh auth status` timed out
  in the local keyring and local `main` is ahead of `origin/main`. Branch work
  remains local until the GitHub base is published/ratified.

---

## IN PROGRESS — Vibe pytest report/timeout plugin hardening

Current branch: `feat/vibe-pytest-report-timeout`

Goal:

- Ensure Vibe runners can pass pytest `--json-report` and `--timeout`
  arguments inside the official Python 3.12 venv.

Implemented in this branch:

- Added `pytest-json-report` and `pytest-timeout` to the `dev` dependency
  group and `uv.lock`, which is the dependency source consumed by
  `Dockerfile.openclaw-sandbox`.
- Added `requirements-vibe.txt` for external Vibe runners that install extra
  pytest plugins from a requirements file.
- Added unit contracts proving the Vibe requirements file, `pyproject.toml`
  and `uv.lock` keep both plugins declared.

---

## IN PROGRESS — FINLIB-0 FL-PR02 Whitespace Integrity RC

Current branch: `feat/finlib-ops-whitespace-rc01`

Goal:

- Fix semantic-empty text bypasses in migration `019_create_ops_sources_runs.sql`
  before publishing FL-PR02 remotely.

Implemented in this branch:

- Replaced `length(btrim(...)) > 0` guards with PostgreSQL regex checks using
  `~ '\S'` for `methodology_limitations`, `agent_id`,
  `source_snapshot_hash` and `error_summary`.
- Updated the `execute + completed` compound snapshot rule to require
  `source_snapshot_hash IS NOT NULL AND source_snapshot_hash ~ '\S'`.
- Added an operational maximum of 128 characters for `source_id`.
- Added static and live integration coverage for tab, newline and carriage
  return whitespace-only bypasses.

---

## IN PROGRESS — FINLIB-0 FL-PR02 Ops Sources and Runs

Current branch: `feat/finlib-ops-sources-runs`

Goal:

- Add the first FINLIB operational tables for financial source registry and
  ingestion run bookkeeping, without agents, repositories, watermarks, data
  quality, outbox or audit tables.

Implemented in this branch:

- Added migration `019_create_ops_sources_runs.sql`.
- Added `ops_data_sources` with required methodology limitations, JSONB object
  metadata constraint and B3 historical quotes seed.
- Added `ops_ingestion_runs` with `uuidv7()` run IDs, source FK, explicit
  `dry_run`/`execute` modes, explicit statuses, non-negative counters,
  mandatory trace id and completed execute snapshot-hash rule.
- Added focused indexes on `(source_id, started_at DESC)`, `trace_id`, and
  `(status, started_at DESC)`.
- Added unit schema contract tests and isolated live integration tests.
- Added `docs/specs/finlib-0/pr-02-ops-sources-runs.md`.

Out of scope by design:

- No `ops_ingestion_watermarks`, `ops_data_quality_checks`,
  `ops_outbox_events`, `audit_agent_writes`, repositories or data agents.

---

## IN PROGRESS — FINLIB-0 FL-PR01 PostgreSQL Readiness

Current branch: `feat/finlib-postgres-readiness`

Goal:

- Implement the first FINLIB gate for "PostgreSQL/TimescaleDB readiness +
  migrations + schemas".

Implemented in this branch:

- Added migration `018_enable_library_extensions.sql` for `pg_trgm` and
  `btree_gin`.
- Added `scripts/check_postgres_readiness.py`, a JSON-only readiness gate for
  PostgreSQL, required extensions, migration head, temp write probe and
  read-only role presence.
- Added `infra/postgres/initdb/002_readonly_role.sql` to provision
  `quimera_readonly NOLOGIN` for fresh local volumes and documented the
  one-time bootstrap for existing volumes.
- RC-02 hardened existing-volume operations: documented one-time
  `pg_stat_statements` extension creation, made default privileges explicit for
  `FOR ROLE quimera`, added Bandit `nosec` annotations for intentional safe
  exception/subprocess patterns, and improved the live readiness assertion
  message.
- Integrated safe Postgres readiness summary into `scripts/quimera_status.py`.
- Added unit and live integration tests for the readiness contract.
- Added `docs/specs/finlib-0/pr-01-postgres-readiness.md`.

Gate rule:

- FINLIB data agents remain blocked until the PostgreSQL/FINLIB readiness gate
  exits `0`. The later consolidated `scripts/check_finlib_readiness.py` will
  wrap this gate; FL-PR01 owns only the PostgreSQL readiness layer.

---

## PLANNING — FINLIB-0 Sprint Master Spec (no code changed)

Authored by Claude (Fable) on 2026-06-10 after live repo inspection. This is
the pre-agent phase item 1: "PostgreSQL/TimescaleDB readiness + migrations +
schemas" for Brazilian financial asset libraries.

- New spec: `docs/specs/finlib-0/SPRINT_FINLIB0_MASTER_SPEC.md`.
- PR ladder FL-PR00..FL-PR10 (≤400 production lines each, SDD-first,
  Red/Green/Mutate, Cowork adversarial review, GitHub-only merge per ADR-011).
- Scope: readiness script `check_postgres_readiness.py`; migrations 018–028:
  pg_trgm/btree_gin, ops layer (data_sources, ingestion_runs, watermarks,
  data_quality_checks, outbox_events SKIP LOCKED), audit_agent_writes
  (append-only), macro library (IPCA/IGP-M/Selic/CDI/PTAX USD-BRL),
  Tesouro Direto MtM, CVM fund registry + informe diário, fixed income
  (CDB/LCA/LCI/CRI/CRA) + debêntures, company fundamentals, continuous
  aggregates + compression; `backend/finlib/` repositories with mandatory
  audit append in-transaction.
- Standing decisions to ratify in FL-PR00 (ADR-A..E): keep `public` schema
  prefix convention (no namespaced schemas in V1); runner migrations dir is
  the only schema source of truth vs `infra/postgres/sql`; derived indicators
  (incl. OBV) go to `market_features`, never new tables; BRL/USD is a derived
  view of PTAX, never stored; COE permanently out of scope.
- Data agents (MarketLibrarySeeder, ResearchLibraryCurator, TreasuryMtM) are
  the NEXT sprint and are gated on `check_finlib_readiness.py` exit 0.
- No code, migration, config or runtime state was modified in this session.

---

## codex/code-sandbox-mcp-python312 — code-sandbox-mcp Python 3.12 Runtime

Current branch: `codex/code-sandbox-mcp-python312`
Base branch: local `main` at `4a8141f`.

Implemented:

- Accepted `openclaw-sandbox:latest` as the local truth for the
  code-sandbox-mcp runtime used by Claude Desktop.
- Hardened `Dockerfile.openclaw-sandbox` so the sandbox image is pinned to
  `python:3.12-slim` by digest and fails the build if Python drifts off the
  3.12 series.
- Kept project dependencies resolved from `uv.lock` into `/opt/openclaw-venv`,
  outside `/workspace`, so the runtime survives repository volume mounts.
- Kept PostgreSQL 18 client tools, Node.js/Pyright, `QUIMERA_E2E=true`, and
  `PYTHONPATH=/workspace` in the sandbox runtime.
- Added `docker/docker-compose.sandbox.yml` as the reproducible local build
  recipe for `openclaw-sandbox:latest`.
- Added `docs/04_MEM/CODE_SANDBOX_MCP_RUNBOOK.md` documenting the
  code-sandbox-mcp `-no-update` fix, the stale Python 3.14 regression, and
  post-build verification commands.
- Removed Claude's stray `test_demo.py` scratch file from the local PR scope.

Validation:

- `docker compose -f docker/docker-compose.sandbox.yml config`: passed.
- `docker compose -f docker/docker-compose.sandbox.yml build`: passed,
  produced `openclaw-sandbox:latest`.
- `docker run --rm openclaw-sandbox:latest python --version`:
  `Python 3.12.13`.
- `docker run --rm openclaw-sandbox:latest pg_dump --version`:
  `pg_dump (PostgreSQL) 18.4`.
- `docker run --rm openclaw-sandbox:latest node --version`: `v20.19.2`.
- `docker run --rm openclaw-sandbox:latest pyright --version`: `pyright
  1.1.409` with only the expected upstream notice that 1.1.410 exists.
- `docker run --rm -v "$PWD:/workspace" openclaw-sandbox:latest python -c
  "import backend; print(backend.__file__)"`: `/workspace/backend/__init__.py`.
- `uv run pytest tests/unit/test_vibe_sandbox_operational_contract.py
  tests/unit/test_pr09_backup_scripts_static.py -q`: 11 passed.
- `uvx ruff check tests/unit/test_vibe_sandbox_operational_contract.py`:
  passed.
- `uvx ruff format --check tests/unit/test_vibe_sandbox_operational_contract.py`:
  passed.
- `git diff --check`: clean.

Known residual:

- Per ADR-011, this local merge is not official integration. GitHub remains the
  source of truth after PR, CI, review, and GitHub merge.

---

## codex/tdd-m-real-mutation-hardening — TDD+M Real Mutation Hardening

Current branch: `codex/tdd-m-real-mutation-hardening`
Base branch: local `main` at `901463c`.

Implemented:

- Added real OpenTelemetry span tests for `backend.observability.decorators`
  using `TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter`
  instead of relying only on fake spans.
- Hardened exception telemetry so decorators disable OpenTelemetry automatic
  exception recording and emit a sanitized exception event controlled by
  QUIMERA.
- Expanded DSN redaction so PostgreSQL DSNs are fully redacted in sanitized
  error messages.
- Hardened `backend.rag.collection_guard` so `bool` is not accepted as an
  embedding dimension and metadata completeness checks validate value types,
  not only key presence.
- Hardened gateway health checks so invalid JSON responses from Ollama or
  LiteLLM fail with controlled `SystemExit(1)` rather than uncaught parser
  exceptions.
- Updated `pyproject.toml` mutation config from deprecated
  `paths_to_mutate` to `source_paths` and kept
  `mutate_only_covered_lines = false` as an explicit anti-Goodhart policy.
- Excluded generated `.mutmut-cache/` and `mutants/` directories from mypy and
  pyright so generated mutation artifacts do not poison static analysis.
- Added `docs/testing/tdd_m_professional_methodology.md` documenting the
  QUIMERA Red/Green/Mutate/Refactor loop, survivor triage, and reviewer output.

Validation:

- `uv run pytest tests/unit/test_otel_decorators.py tests/unit/test_collection_guard.py tests/unit/test_gateway_health.py tests/unit/test_otel_safety.py tests/unit/test_vibe_sandbox_operational_contract.py -q`:
  66 passed, 2 subtests passed.
- `uv run pytest tests/unit -q`: 1895 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 417 files already formatted.
- `uv run mypy --strict .`: success, 417 source files checked.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest .venv/bin/pyright <changed python files>`:
  0 errors / 0 warnings.

Known residual:

- A host `uvx mutmut run ...` attempt used an isolated Python 3.14 environment
  and failed during pytest collection. Use `scripts/vibe_deep_run.sh
  'mutmut run'` for authoritative mutation runs because the official Vibe
  sandbox is Python 3.12 and joins the QUIMERA network.

---

## codex/vibe-deep-sandbox-hardening — Vibe Deep Sandbox and Dynamic Test Hardening

Current branch: `codex/vibe-deep-sandbox-hardening`
Base branch: local `main` after local adversarial contract merge
(`351fe5b`).

Implemented:

- Standardized the official Vibe sandbox Dockerfile on Python `3.12.13-slim`
  while keeping `/opt/openclaw-venv` as the image-owned dependency runtime.
- Added `scripts/vibe_deep_run.sh`, which rebuilds `vibe-sandbox:py312`,
  mounts the current checkout at `/workspace`, installs OpenClaw editable, and
  attaches to `QUIMERA_VIBE_DOCKER_NETWORK`, `quimera_network`, or
  `quimera-local_default` so dynamic tests can reach the live QUIMERA stack.
- Added `scripts/quarantine_venv_to_patio.sh`, a reversible virtualenv
  quarantine helper. It moves only `.venv` paths into
  `/Users/fas/projetos/_patio_venvs` and never deletes them.
- Created `/Users/fas/projetos/_patio_venvs` and moved
  `/Users/fas/projetos/vibe_code_sandbox/.venv` to
  `/Users/fas/projetos/_patio_venvs/vibe_code_sandbox.venv.20260609T012125Z`.
- Updated LiteLLM host startup to prefer the project root `.venv` and then
  `uv run litellm`; the old `infra/litellm/.venv` fallback is no longer part
  of the startup path. The directory was intentionally left on disk pending
  operator smoke confirmation.
- Added safe `mutmut` configuration in `pyproject.toml`: mutate `backend/`,
  copy required project context, avoid symlinked `mutants/`, and keep
  `mutate_only_covered_lines = false` so no-test regions remain visible.
- Added `.gitignore` coverage for `.mutmut-cache/` and `mutants/`.
- Updated `uv.lock`: `urllib3 2.6.3 -> 2.7.0` and `idna 3.13 -> 3.18`.
  `PyJWT` was already locked at `2.13.0`.
- Cleaned SQLFluff findings in `infra/postgres/sql/*.sql` while keeping
  non-concurrent index creation explicitly documented for migration/init
  context.
- Added `docs/testing/vibe_deep_testing.md` documenting official sandbox,
  dynamic stack access, mutation testing, venv patio and dependency audit
  policy.
- Added unit contracts for sandbox Python version, Vibe runner network/venv
  behavior, mutmut safe copy config, venv patio behavior and dependency locks.

Validation:

- `uv run pytest tests/unit -q`: 1884 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 417 files already formatted.
- `uvx sqlfluff lint infra/postgres --dialect postgres`: all finished, no
  violations.
- `uv run mypy --strict .`: success, 417 source files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `uvx pip-audit --path .venv/lib/python3.12/site-packages`: no known
  vulnerabilities found; only local `openclaw` is skipped as non-PyPI.
- `docker build -f Dockerfile.openclaw-sandbox -t vibe-sandbox:py312 .`:
  passed; image contains Python 3.12.13, PyJWT 2.13.0, urllib3 2.7.0,
  idna 3.18 and qdrant-client 1.18.0.
- `QUIMERA_VIBE_BUILD_IMAGE=0 scripts/vibe_deep_run.sh 'scripts/vibe_sandbox_bootstrap.sh /workspace && python -m pytest tests/integration/test_agentic0_e2e.py tests/e2e/test_agent0_e2e.py -q'`:
  passed with 1 passed / 2 skipped. The skips are due to live Agent0 gateway
  preconditions, not sandbox Python/venv/network failure.
- `./run_smoke.sh --quick --json --allow-degraded`: completed with services
  online but returned degraded due to existing latency baseline warning and
  LiteLLM model introspection warning.

Known residual:

- Full `mutmut run` was not re-executed in this Codex turn because the previous
  Deep run took about 75 minutes. The runner and config now support a dynamic
  networked rerun without symlinked `mutants/`.
- Direct `python -m infra.litellm.smoke_test` reported readiness/liveliness,
  Ollama and Qdrant OK but `/v1/models` false when no LiteLLM key was exported
  in the current shell. The runner passes `QUIMERA_LLM_API_KEY` and
  `LITELLM_MASTER_KEY` through when the operator has them exported.

Scope intentionally not changed:

- No `.env`, `.env.*`, secrets, real data, Postgres/Qdrant volumes or
  `infra/litellm/.venv` directory content was read, deleted or committed.
- Generated PR-08/PR-09 smoke artifacts were restored and kept out of the diff.

---

## codex/rc-adversarial-report-contract-sync — Adversarial Report Contract Sync

Current branch: `codex/rc-adversarial-report-contract-sync`
Base branch: local `main` at `da758ee`.

Implemented:

- Added a unit contract proving `LocalGenerator(gateway_client=fake)` does not
  read gateway environment settings and does not require
  `QUIMERA_LLM_API_KEY`.
- Updated `LocalGenerator.__post_init__` so an explicitly injected
  `GatewayChatClient` is honored before calling `GatewayRuntimeConfig.from_env`.
  Primitive local validations still run.
- Resolved the current Ruff lint findings across evaluation, infra and scripts.
- Applied the mechanical Ruff formatting required by `ruff format --check .`.
  This touched the non-test files that were already outside the repository-wide
  formatting contract; it did not intentionally refactor behavior.
- Updated active LiteLLM/infra/recovery docs to use the current root wrapper:
  `./start_quimera.sh --start`, `./start_quimera.sh --status` and
  `./start_quimera.sh --stop`.
- Marked historical RAG-01B specs that mention removed `start_quimera.sh`
  subcommands as superseded, without reintroducing those subcommands.

Scope intentionally not changed:

- No `.env`, `.env.*`, secrets, service runtime data, Docker state, Qdrant,
  Postgres or LiteLLM process state touched.
- Generated `evaluation/results` output from the unit run was restored and not
  kept in the diff.
- Historical specs retain their original body for traceability; they only gain
  superseded notes.

Validation:

- `uv run pytest tests/unit -q`: 1877 passed, 259 subtests passed.
- `uvx ruff check .`: all checks passed.
- `uvx ruff format --check .`: 416 files already formatted.
- `uv run mypy --strict .`: success, 416 source files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `git diff --check`: clean.

Known residual:

- `pyright` reports that a newer Pyright release is available. This is an
  environment notice only; the configured gate passed with zero findings.

---

## codex/rc-quality-report-hardening — Standard Quality Report RC

Current branch: `codex/rc-quality-report-hardening`
Base branch: local `main` at `08e524f`.

Implemented:

- Hardened the standard quality report findings from 2026-06-08:
  - `asyncpg` imports now use `# type: ignore[import-untyped, unused-ignore]`
    so mypy passes both when asyncpg is untyped and when an analyzer no longer
    needs the ignore.
  - Replaced Bandit B101 production asserts in
    `backend/rag/hybrid_retriever.py` and
    `backend/rag/ollama_embedding_bakeoff.py` with explicit runtime guards.
  - Made `test_pr09_pg_dump_restore_verify_live` skip only when PostgreSQL is
    genuinely unreachable from a sandbox, while still failing on pg_dump/server
    version mismatch and script bugs.
  - Added Vulture config in `pyproject.toml` for Protocol/API keyword names
    that must remain stable (`vectors_config`, `with_payload`, Qwen3 encoder
    keyword args).
  - Added `.importlinter` with a first kept architecture contract:
    Agent0 must not import Postgres/working-memory/temporal memory backends
    directly.
  - Reduced complexity in `backend/ingestion/report.py`,
    `backend/rag/run_trace.py` and `backend/rag/qdrant_tuning.py`. The prior
    rank-D blocks reported by Xenon/Radon are no longer present.
  - `SnapshotService.create_delta_snapshot` now validates
    `since_checkpoint_id` instead of accepting and ignoring a blank value.

Research notes:

- Mypy `warn-unused-ignores` reports ignores that no longer suppress an error;
  combining `import-untyped` with `unused-ignore` is the portable compromise
  for environments where `asyncpg` typing visibility differs.
- Bandit B101 documents that `assert` statements are removed under optimized
  Python bytecode; production guards now raise explicit exceptions instead.
- Vulture supports `tool.vulture` configuration in `pyproject.toml`; this RC
  keeps the report aligned with `min_confidence = 80`.
- Import Linter forbidden contracts are suitable for enforcing the Agent0
  memory-access boundary without introducing a broad unreviewed layer model.

Validation:

- `uv run pytest tests/unit/test_quality_tool_contracts.py tests/unit/test_pr09_pg_dump_live_contract.py tests/unit/test_wm_snapshot_service.py tests/unit/test_hybrid_retriever.py tests/unit/test_qwen3_4b_embedding_bakeoff.py tests/unit/test_rag_run_trace.py tests/unit/test_qdrant_tuning_profiles.py tests/unit/test_ingestion_pipeline.py -q`:
  172 passed.
- `uv run pytest tests/integration/test_pr09_pg_dump_restore_verify_live.py -q`:
  passed in the local host environment.
- `uv run mypy --strict .`: success, 416 files checked.
- `uv run pyright`: 0 errors / 0 warnings.
- `uvx bandit -q -r backend`: success, no findings.
- `uvx vulture --config pyproject.toml`: success.
- `uvx --from import-linter lint-imports`: Agent0 memory boundary contract
  kept.
- `uvx xenon --max-absolute D --max-modules B --max-average B backend`:
  success, confirming no rank-D blocks remain.
- `git diff --check`: clean.

Known residual:

- `uvx xenon --max-absolute B --max-modules B --max-average B backend` still
  reports rank-C blocks across the historical backend. This RC removes the
  rank-D offenders from the report and reduces targeted complexity, but does
  not convert the entire backend to a strict B threshold in one broad refactor.

---

## codex/rc-vibe-sandbox-bootstrap — Vibe Sandbox Operational Bootstrap RC-02

Current branch: `codex/rc-vibe-sandbox-bootstrap`
Base branch: local `main` at `6823c02`.

Implemented:

- Added `scripts/vibe_sandbox_bootstrap.sh`, an idempotent runtime bootstrap
  for Vibe containers. It runs after the repository is mounted and installs
  OpenClaw editable with `uv pip install --no-deps --editable .`, falling back
  to `python -m pip install --no-deps --editable .`, then verifies
  `backend` imports.
- Added `scripts/vibe_semgrep_scan.sh`, which runs Semgrep outside the project
  virtualenv. Docker `semgrep/semgrep:latest` is preferred; `uvx semgrep` is
  the fallback. This avoids downgrading or constraining the project's
  OpenTelemetry dependencies.
- Added `scripts/vibe_pyright_json.sh`, which warms Pyright with
  `pyright --version >/dev/null` before running `pyright --outputjson`, so
  first-run bootstrap/progress text does not pollute stdout JSON.
- Updated `Dockerfile.openclaw-sandbox` to install `nodejs`, create the
  virtualenv directly at `/opt/openclaw-venv`, and warm Pyright during image
  build with `/opt/openclaw-venv/bin/pyright --version >/dev/null`.
- Added unit contracts covering the editable install bootstrap, isolated
  Semgrep policy, Pyright JSON warmup and sandbox Dockerfile Node/Pyright
  prewarm.

Research notes:

- Current Semgrep documentation recommends the latest Semgrep for current
  features/fixes and supports running Semgrep via Docker, `pipx` or `uv` for
  isolated versions. This RC uses Docker/`uvx` instead of adding Semgrep to the
  project dependency graph.
- Current Semgrep CI examples use the official `semgrep/semgrep` image and
  `semgrep scan --config auto`.
- Pyright JSON output should be produced only by the JSON command; the wrapper
  performs any first-run warmup before `--outputjson`.

Scope intentionally not changed:

- No OpenTelemetry dependency changed.
- No Semgrep dependency added to `pyproject.toml` or `uv.lock`.
- No `.env`, `.env.*`, secrets, service runtime state or data touched.
- Existing generated PR-08/PR-09 artifacts remain unstaged.

Validation:

- `bash -n scripts/vibe_sandbox_bootstrap.sh scripts/vibe_semgrep_scan.sh scripts/vibe_pyright_json.sh`
  passed.
- `uv run pytest tests/unit/test_vibe_sandbox_operational_contract.py tests/unit/test_pr09_backup_scripts_static.py tests/unit/test_gateway_final_baseline.py`
  passed: 16 tests.
- `uv run mypy --strict tests/unit/test_vibe_sandbox_operational_contract.py`
  passed.
- `uv run pyright tests/unit/test_vibe_sandbox_operational_contract.py`
  passed: 0 errors.
- `VIRTUAL_ENV="$PWD/.venv" scripts/vibe_sandbox_bootstrap.sh "$PWD"`
  passed and installed `openclaw` editable from the mounted checkout.
- `QUIMERA_SEMGREP_USE_DOCKER=0 scripts/vibe_semgrep_scan.sh --version`
  passed with isolated Semgrep `1.165.0`.
- `scripts/vibe_pyright_json.sh tests/unit/test_vibe_sandbox_operational_contract.py`
  emitted parseable JSON with zero errors.
- `docker build -f Dockerfile.openclaw-sandbox -t openclaw-sandbox-vibe-bootstrap-check .`
  passed.
- Container smoke passed: `pg_dump` reports PostgreSQL 18.4, Node.js is
  present, `npm` is absent, Pyright runs from `/opt/openclaw-venv`, editable
  bootstrap succeeds after `/workspace` mount, and Pyright JSON output parses
  cleanly.

---

## codex/rc-vibe-test-style-only — Dedicated Test Style and Lint RC

Current branch: `codex/rc-vibe-test-style-only`
Base branch: local `main` at `1f19862`.

Purpose:

- Split the mass `ruff format tests` cleanup out of the mixed Vibe Smoke RC so
  reviewers can inspect the style-only churn independently.
- Keep the required golden baseline gate contract fix in this branch because
  unit tests must pass before local merge.

Implemented:

- Renamed the golden baseline ignore test to
  `test_generated_report_dirs_are_ignored_and_baseline_files_are_tracked`,
  making the behavior under test explicit.
- Reworked that test to validate effective Git ignore behavior via
  `git check-ignore --no-index` instead of asserting stale literal
  `.gitignore` strings. `reports/` is accepted as covering generated
  `reports/golden/`, `reports/gateway2/` and `reports/ci/` outputs, while
  official files under `tests/golden/baseline/` remain tracked.
- Ran `uvx ruff check tests --fix`, removing the 14 unused imports reported by
  Vibe Smoke.
- Replaced the ambiguous variable name `l` in
  `tests/unit/test_litellm_infra_scripts.py`.
- Ran `uvx ruff format tests`, applying the dedicated test-formatting pass.

Research notes:

- Git's current `gitignore` documentation confirms a directory pattern matches
  the directory and paths underneath it, so `reports/` covers generated report
  subdirectories.
- Ruff's current linter documentation distinguishes safe fixes from unsafe
  ones; unused-import cleanup is handled by Ruff's safe fix path in ordinary
  test modules.
- Ruff's formatter documentation defines `ruff format --check` as the
  non-writing verification mode for the same formatting contract.

Validation:

- `uvx ruff check tests`: all checks passed.
- `uvx ruff format --check tests`: 234 files already formatted.
- `uv run pyright tests`: 0 errors / 0 warnings.
- `uv run pytest tests/unit`: 1867 passed.
- `uv run pytest tests/integration`: 34 passed / 48 skipped in this local
  host environment.
- `uv run pytest tests/smoke`: 5 passed / 13 skipped.
- `git diff --check`: clean.

Scope intentionally not changed:

- No backend runtime code.
- No `.env`, `.env.*`, secrets, service runtime state or data.
- Existing generated PR-08/PR-09 artifacts remain unstaged.

---

## codex/rc-vibe-minor-recommendations — Vibe Minor Recommendations RC

Current branch: `codex/rc-vibe-minor-recommendations`
Base branch: local `main` at `14e8491`.

Implemented:

- Added `QUIMERA_E2E=true` to `Dockerfile.openclaw-sandbox` as the Vibe
  sandbox umbrella flag for real e2e collection. The project still does not
  commit `.env.sandbox`; all `.env.*` files remain ignored and untouched.
- Updated `tests/e2e/test_agent0_e2e.py` so Agent0 e2e accepts either the
  legacy explicit flag `RUN_AGENT0_E2E=1` or the sandbox umbrella
  `QUIMERA_E2E=true`.
- Added a unit contract guarding that the sandbox Dockerfile and Agent0 e2e
  test both keep the `QUIMERA_E2E` contract.
- Added explicit `TRUNCATE TABLE qlib_projection_manifests CASCADE` to the
  finance roundtrip fixture after migrations. The truncate is scoped to a
  per-test isolated database, preserving production repository create/insert
  semantics while making repeated live test attempts deterministic.
- Hardened the PR-07 JSON status live-shape test to assert stable service
  shape for Postgres, Qdrant, LiteLLM and Ollama while allowing either
  `overall=ok` or `overall=fail`, depending on host/sandbox reachability.

Research notes:

- PostgreSQL 18 documents `TRUNCATE ... CASCADE` as a fast way to empty tables
  and dependent tables, with explicit caution around unintended data loss.
  This RC uses it only in disposable isolated test databases.
- PostgreSQL 18 `INSERT ... ON CONFLICT DO UPDATE` remains available, but was
  not used because it would change repository semantics from create/insert to
  upsert for `qlib_projection_manifests`.
- Python 3.12 subprocess guidance still favors explicit argument sequences and
  `sys.executable` for relaunching the current interpreter; the status test
  keeps that path instead of reviving removed shell JSON subcommands.

Validation:

- `uv run mypy --strict tests/e2e/test_agent0_e2e.py
  tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/unit/test_gateway_final_baseline.py`: success.
- `uv run pyright` on the same files: 0 errors.
- `uv run pytest tests/unit/test_gateway_final_baseline.py
  tests/e2e/test_agent0_e2e.py
  tests/integration/test_pr07_start_quimera_status_json_live.py`:
  9 passed / 2 skipped.
- `QUIMERA_E2E=true uv run pytest tests/e2e/test_agent0_e2e.py -q`:
  2 skipped through controlled runtime/corpus guards.
- Live Postgres targeted block with temporary superuser test role:
  `tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py`: 2 passed.
- `git diff --check`: clean.

---

## codex/rc-vibe-integration-roundtrip-status — Vibe Integration Residual RC

Current branch: `codex/rc-vibe-integration-roundtrip-status`
Base branch: local `main` at `df37f51`.

Implemented:

- Made `test_finance_repository_full_roundtrip` use a per-test isolated
  PostgreSQL database via the existing `isolated_postgres_client` helper.
  This preserves insert-only repository semantics while eliminating residual
  `qlib_projection_manifests` unique-key collisions between live test runs.
- Updated the PR-07 live JSON status integration test to call
  `scripts/quimera_status.py status --json` through `sys.executable` with an
  explicit `PYTHONPATH`, instead of invoking the removed
  `scripts/start_quimera.sh status --json` contract.
- Updated the local runtime integration checks to use the canonical wrapper
  contract: `./start_quimera.sh --status`.

Research notes:

- PostgreSQL 18 `INSERT ... ON CONFLICT` could handle duplicate unique keys,
  but was intentionally not used here because the failure is test-state
  leakage and the repository method models create/insert semantics.
- Python 3.12 documents `sys.executable` as the recommended way to relaunch
  the current Python interpreter, which is more portable than shelling through
  a wrapper that has no JSON mode.

Validation:

- `uv run mypy --strict tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: success.
- `uv run pyright tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: 0 errors.
- Live targeted integration block with temporary superuser test role:
  `tests/integration/test_finance_repository_roundtrip.py
  tests/integration/test_pr07_start_quimera_status_json_live.py
  tests/integration/test_quimera_local_runtime.py`: 3 passed / 1 skipped.
- `uv run pytest tests/unit/test_start_quimera_status_json.py`: 3 passed.
- `git diff --check`: clean.

Scope intentionally not changed:

- No repository method was converted from insert/create to upsert.
- No Docker, Postgres, Qdrant, LiteLLM or Ollama runtime configuration was
  changed.
- No generated PR-08/PR-09 artifacts were staged.

---

## Testes-01 — Qdrant Client Dependency Contract

Current branch: `Testes-01`
Base branch: `main` at `68f5716d37f6f1c421f73db08d7708f8d4709aa7`.

Implemented:

- Relaxed project dependency from `qdrant-client==1.18.0` to the then-current
  open 1.18 floor; this was superseded on 2026-06-25 by the active
  bounded contract `qdrant-client>=1.18,<1.19`.
- Reconciled `uv.lock` metadata offline; the locked package version remains
  `qdrant-client 1.18.0`.
- Updated Qdrant 1.18 version contract, ADR-018 and active Qdrant handoff docs
  to distinguish dependency boundary (`>=1.18,<1.19`) from current lockfile
  resolution (`1.18.0`).
- Updated Qdrant 1.18 unit contracts to reject legacy `qdrant-client==1.13.2`
  while accepting the new `>=1.18,<1.19` dependency boundary.
- Applied Ruff cleanup to `backend/`: `uvx ruff format backend/` reformatted
  65 files and `uvx ruff check --fix backend/` removed 13 unused imports.
- Updated LiteLLM MCP server identifiers from hyphenated names to
  LiteLLM-safe `snake_case` names:
  `quimera_postgres_memory`, `quimera_qdrant_memory` and
  `quimera_working_memory`.
- Updated the LiteLLM MCP transport contract from `streamable_http` to `http`,
  matching the currently installed LiteLLM gateway runtime.
- Started LiteLLM as a host-only local LaunchAgent
  `com.quimera.litellm.local`, bound to `127.0.0.1:4000`, using the rendered
  runtime config from `infra/litellm/generated/litellm_config.runtime.yaml`
  and explicit development placeholder keys. No `.env` or `.env.*` file was
  read.

Validation:

- `.venv/bin/python -m pytest tests/unit/test_qdrant_118_config.py`:
  43 passed.
- `uv lock --check`: success.
- Host import/version check: installed `qdrant-client` is `1.18.0` and
  satisfies the active `>=1.18,<1.19` boundary.
- `uvx ruff check backend/`: success.
- `uvx ruff format --check backend/`: success.
- `uv run mypy --strict backend`: success.
- `uv run pyright backend`: 0 errors / 0 warnings.
- Full host Python 3.12 regression with `.venv/bin/python -m pytest`:
  1891 passed / 65 skipped.
- `git diff --check`: clean.
- `python -m infra.litellm.config_validator infra/litellm/litellm_config.yaml`:
  success; one expected qdrant-semantic fallback warning.
- `.venv/bin/python -m pytest tests/unit/test_litellm_mcp_config_validator.py
  tests/integration/test_pr07_litellm_mcp_registration_smoke.py
  tests/integration/test_pr08_litellm_mcp_tools_live.py
  tests/unit/test_pr08_litellm_mcp_allowed_tools.py
  tests/unit/test_pr08_healthcheck_contract.py`:
  9 passed.
- `bash infra/litellm/test_models.sh`: success.
- LiteLLM readiness: `http://127.0.0.1:4000/health/readiness` returned
  `status=healthy`, `cache=local`, `litellm_version=1.83.14`.
- Gateway chat smoke through `local_chat`: returned `QUIMERA_OK`.
- Gateway embedding smoke through `quimera_embed`: returned a 768-dimension
  float vector.
- `./scripts/start_quimera.sh status --json`: `overall=ok`; LiteLLM host-only,
  Ollama, Postgres 18.4 and Qdrant reported OK.

Qdrant version finding:

- Official Qdrant server release page shows `v1.18.2` as the newest server
  release.
- Official `qdrant-client` PyPI/GitHub release page shows `1.18.0` as the
  newest Python client release.
- PKD-D2P-00Y now accepts Qdrant server/client parity by `1.18.x` family:
  active server target is `qdrant/qdrant:v1.18.2`, Python dependency boundary is
  `qdrant-client>=1.18,<1.19`, and the current lockfile resolution is
  `qdrant-client 1.18.0`.
- Exact server/client patch parity remains diagnostic only
  (`version_exact_parity_ok=false`) while official PyPI client release remains
  `1.18.0`.
- Local runtime observed before container recreation may still report Qdrant
  server `1.18.1`; compose and version contract now point to `1.18.2`.

Scope intentionally not changed:

- No live Qdrant container restart or volume reset.
- No destructive Qdrant operation.
- No project dependency installation. Ruff was executed through `uvx`, not
  added to `pyproject.toml`.
- No generated PR-09 smoke artifact staged.

---

## vibe_code_sandbox — Postgres Extension Runtime Hardening

Current worktree: `/Users/fas/projetos/vibe_code_sandbox`
Branch: `vibe_code_sandbox`
Base: local `main` at `cb0ba17` after merging `Testes-01` runtime contracts.

Implemented:

- Added `infra/postgres/Dockerfile`, a local runtime image derived from
  `postgres:18.4-trixie`.
- The image installs TimescaleDB `2.23.0` and pgvector `0.8.2` from source so
  RAG-01B integration tests can create `timescaledb` hypertables and
  `vector(768)` checkpoint columns without changing PostgreSQL major/minor.
- Updated `docker/docker-compose.postgres.yml` and
  `infra/docker/compose.quimera.local.yml` to build
  `quimera/postgres-memory:18.4-trixie-timescaledb-pgvector`.
- Updated Postgres startup to preload `timescaledb,pg_stat_statements`.
- Updated initdb extension bootstrap to create `pgcrypto`, `timescaledb`,
  `vector` and `pg_stat_statements`.
- Updated working-memory checkpoint SQL to create `vector` before using the
  `vector(768)` type, so existing databases with the extension package
  available can self-heal on schema application.

Scope intentionally not changed:

- No PostgreSQL version change.
- No switch to PostgreSQL 17/15.
- No `postgres:latest`.
- No live volume reset.
- No pg_dump/restore behavior change yet.

### vibe_code_sandbox RC — start_quimera Postgres rebuild hardening

Implemented:

- Refactored `scripts/start_quimera.sh` as the canonical operational entrypoint
  behind the root `./start_quimera.sh` wrapper.
- The script now accepts exactly `--start`, `--stop` and `--status`.
- Postgres image/config drift is detected before start and requires explicit
  human confirmation before rebuild.
- Rebuild preserves data volumes: it uses compose build-or-pull, stop, rm -f
  and up -d for the Postgres service only; no volume removal, compose down -v
  or Docker prune command is present.
- Ollama warmup uses numeric `keep_alive: -1`, matching the official Ollama API
  preload examples and the existing numeric unload `keep_alive: 0` contract.
- `--status` now degrades to a partial host-only table when Docker is not
  available instead of aborting before rendering any status.
- Postgres rebuild now calls `docker compose build` only when the service has a
  Compose `build:` section; external image services use `docker compose pull`.

Validation:

- `bash -n ./start_quimera.sh scripts/start_quimera.sh scripts/star_quimera.sh`:
  success.
- `uv run pytest tests/unit/test_start_quimera_script.py`:
  19 passed.
- `git diff --check`:
  clean.
- `shellcheck` and `ruff` were not executed in this worktree because the tools
  were unavailable and no dependency installation was requested.

### vibe_code_sandbox RC — Vibe integration residual failures

Implemented:

- Updated `Dockerfile.openclaw-sandbox` to install PostgreSQL 18 client tools
  from the official PGDG apt repository and prepend
  `/usr/lib/postgresql/18/bin` to `PATH`, so sandbox `pg_dump` is not older
  than the canonical PostgreSQL 18.4 server.
- Hardened `infra/postgres/backup.sh` and `restore_verify.sh` to prefer
  PostgreSQL tools from the running `quimera-postgres-memory` container when
  available, avoiding host/sandbox client drift.
- Added TimescaleDB logical restore protocol to `restore_verify.sh`:
  `CREATE EXTENSION IF NOT EXISTS timescaledb`,
  `timescaledb_pre_restore()` before `pg_restore`, and
  `timescaledb_post_restore()` after restore.
- Added migration `017_enable_vector_extension.sql` instead of editing older
  applied migrations, preserving checksum immutability while enabling pgvector
  through the migration runner.
- Added isolated live PostgreSQL test database helper for migration tests.
  `test_postgres_migrations.py` and `test_finance_schema_migrations.py` now run
  against per-test temporary databases and clean them up with a guarded
  `quimera_test_` prefix.
- Fixed the finance checksum assertion to compare only finance migrations when
  querying `schema_migrations WHERE version >= '010'`.

Validation:

- Live reproduction block for the four reported failures:
  4 passed.
- Full affected integration files:
  9 passed.
- Static/unit block:
  39 passed.
- `bash -n infra/postgres/backup.sh infra/postgres/restore_verify.sh
  ./start_quimera.sh scripts/start_quimera.sh scripts/star_quimera.sh`:
  success.
- `uv run mypy --strict` on touched test/helper files:
  success.
- `uv run pyright` on touched test/helper files:
  0 errors.
- `git diff --check`:
  clean.

### main RC — Vibe sandbox contract and pg_dump 18.4 verification

Implemented:

- Updated stale tests that still expected removed `scripts/start_quimera.sh`
  subcommands. The canonical wrapper contract is now exactly
  `./start_quimera.sh --start`, `./start_quimera.sh --status` and
  `./start_quimera.sh --stop`.
- Updated `docs/04_MEM/AGENT_CONTEXT.md` to advertise the new wrapper commands
  instead of obsolete JSON subcommands.
- Hardened unit tests that execute gateway/LiteLLM scripts so sandbox
  integration env such as `host.docker.internal` cannot leak into local-only
  unit contracts.
- Updated `infra/litellm/audit.py` so RC-21/RC-23 audit the actual host
  modules (`infra/litellm/audit.py` and `overhead_benchmark.py`) instead of
  requiring removed `start_quimera.sh` subcommands.
- Rebuilt `Dockerfile.openclaw-sandbox` locally as
  `openclaw-sandbox-pg18-check` and verified the sandbox image has
  `pg_dump (PostgreSQL) 18.4 (Debian 18.4-1.pgdg13+1)` and matching
  `psql 18.4`.

Validation:

- `uv run pytest tests/unit`:
  1866 passed.
- Vibe-reported Postgres integration block:
  9 passed.
- `docker build -f Dockerfile.openclaw-sandbox -t openclaw-sandbox-pg18-check .`:
  success.
- `docker run --rm openclaw-sandbox-pg18-check pg_dump --version`:
  PostgreSQL 18.4.
- `docker run --rm openclaw-sandbox-pg18-check psql --version`:
  PostgreSQL 18.4.
- `bash -n` on touched shell scripts:
  success.
- `uv run mypy --strict` on touched Python files:
  success.
- `uv run pyright` on touched Python files:
  0 errors.

---

## RAG-01B PR-10 — Working Memory Qdrant + pgvector Checkpoints

Current branch: `rag-01b/pr-10-working-memory-qdrant-pgvector`
Base branch: `rag-01b/pr-08-integration-smoke` after PR-09 merge commit
`a0870b14d441de9731c84cb3e027ae76fdbb787c`.

Implemented:

- Added accepted ADR-005 in both ADR trees:
  `docs/adr/ADR-005-qdrant-working-memory-pgvector-checkpoints.md` and
  `docs/ADR/ADR-005-qdrant-working-memory-pgvector-checkpoints.md`.
- Added PR-10 SDD and memory handoff:
  `docs/specs/rag-01b/pr-10-working-memory-qdrant-pgvector.md` and
  `docs/04_MEM/WORKING_MEMORY_QDRANT.md`.
- Added `backend/working_memory/` with settings, immutable models, safety
  gates, Qdrant hot store, pgvector checkpoint repository, snapshot service,
  restore service, cleanup and safe metric names.
- Added pgvector checkpoint SQL:
  `infra/postgres/sql/020_working_memory_checkpoints.sql`.
- Added working-memory MCP tools/server on loopback Streamable HTTP
  `127.0.0.1:8813/mcp`.
- Registered `quimera_working_memory` in host LiteLLM config and allowed only
  safe Agentic0 health/query tools by default. Upsert/snapshot are optional
  write tools; restore/cleanup remain disabled by default.
- Added degraded-safe working-memory smoke report:
  `integration/working_memory_smoke.py` and
  `evaluation/results/rag_01b_pr10_working_memory_smoke.json`.

Scope explicitly not changed:

- No Redis, Dragonfly or Python/RAM backend decision.
- No HybridRAG collection mutation.
- No `quimera_query_cache` or `quimera_llm_cache` mutation.
- No pgvector ANN index as hot path.
- No daemon/scheduler/dashboard/provider remoto/real data.
- No `delete_collection` flow for working memory.

Validation:

- PR-10 unit/integration block: 67 passed / 4 skipped.
- PR-10 + LiteLLM/MCP registration block: 75 passed / 4 skipped.
- `uv run mypy --strict` on PR-10 working-memory, MCP, LiteLLM config and
  tests: success.
- `uv run pyright` on the same scope: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic fallback warning.
- `uv run python -m integration.working_memory_smoke`: generated skipped safe
  smoke artifact because live stack was not requested.
- `git diff --check`: clean.

Operational note:

- Live Qdrant/Postgres restore tests are opt-in and skip cleanly unless the
  human operator exports the explicit `QUIMERA_TEST_WM_*` variables and a
  test DSN.

### RAG-01B PR-10 RC-01 — Restore Integrity and Host Python 3.12 Gate

Implemented:

- Added `abort_on_checksum_fail` to `RestoreService`. Default remains
  availability-first warn-and-restore; strict operators can now abort restore
  before any point is written when checksum validation fails.
- Replaced module-level `count(1)` snapshot epochs in the real snapshot flow
  with PostgreSQL `MAX(snapshot_epoch) + 1` allocation under an advisory lock
  scoped to `(agent_id, session_id)`, avoiding restart-to-1 behavior and
  cross-process epoch races.
- Documented that `integration/hybrid_fixture.py` uses `delete_collection` only
  for synthetic HybridRAG fixture teardown and not in working-memory runtime.

Validation:

- `.venv/bin/python --version`: Python 3.12.13.
- Required host Python 3.12 unit block:
  68 passed.
- PR-10 focused unit/integration block:
  70 passed / 4 skipped.
- Full host Python 3.12 regression with `.venv/bin/python -m pytest`:
  1891 passed / 65 skipped.
- `uv run mypy --strict` on PR-10 working-memory/MCP/tests:
  success.
- `uv run pyright` on PR-10 working-memory/MCP/tests:
  0 errors / 0 warnings.

---

## RAG-01B PR-09 — Operational Hardening + Smoke CLI

Current branch: `rag-01b/pr-09-operational-hardening-smoke`
Base branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added accepted working memory checkpoint ADR:
  `docs/ADR/ADR-004-working-memory-checkpoint-contract.md`.
- Added `docs/04_MEM/WORKING_MEMORY_CONTRACT.md`, explicitly deferring the
  fast working memory backend and accepting pgvector only as durable checkpoint.
- Added PR-09 SDD, recovery runbooks, PostgreSQL backup/restore runbook and
  15-minute agent onboarding doc.
- Added local PostgreSQL backup helpers:
  `infra/postgres/backup.sh`, `restore_verify.sh`, `backup_manifest.py` and
  `backup_config.env.example`.
- Added pg_stat_statements operational config and diagnostics:
  Postgres compose command settings, initdb extension bootstrap,
  `infra/postgres/sql/010_pg_stat_statements_diagnostics.sql` and
  `infra/postgres/pg_stat_report.py`.
- Added working memory checkpoint SQL contract:
  `infra/postgres/sql/011_working_memory_checkpoint_contract.sql`.
- Added PR-09 smoke CLI:
  `./run_smoke.sh` plus `scripts/start_quimera.sh smoke`.
- Added PR-09 smoke summary and manual health report:
  `integration/smoke_summary.py` and `integration/health_report.py`.
- Added conservative latency baseline:
  `baseline/rag01b_latency_baseline.json`.
- Generated PR-09 artifacts:
  `evaluation/results/rag_01b_pr09_smoke_summary.json`,
  `evaluation/results/rag_01b_pr09_health_report.json` and
  `evaluation/results/rag_01b_pr09_pg_stat_report.json`.

Scope explicitly not changed:

- No final fast working memory backend selected.
- No Redis implementation.
- No Qdrant in-memory implementation.
- No Python vector memory implementation.
- No cloud/offsite backup, PITR, replication or dashboard.
- No provider remoto.
- No `down -v`, `docker system prune` or volume deletion.
- No destructive schema migration.

Validation:

- PR-09 unit block: 21 passed.
- PR-09 integration block: 3 passed / 2 skipped.
- PR-08 + PR-09 focused block: 51 passed / 3 skipped.
- Full regression: 1816 passed / 60 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `./run_smoke.sh --quick --json --no-build --timeout 5 --allow-degraded`:
  generated PR-09 smoke summary with `overall=degraded` because LiteLLM was
  unavailable while local Postgres/Qdrant/Ollama healthchecks were OK.

Operational note:

- Live backup/restore and live pg_stat integration tests skipped because no
  Postgres DSN was exported in the shell. The static contract, scripts,
  manifest logic and degraded reports are covered locally.

### RAG-01B PR-09 RC-01 — Integration + Diagnostic Final Closure

Implemented:

- Hardened `integration/smoke_summary.py::render_summary_table` so service
  values can be either strings (`"ok"`, `"fail"`) or dictionaries with
  `status`.
- Added `status` as a compatibility alias for the canonical smoke-summary
  `overall` field, and documented that contract in the PR-09 SDD.
- Refactored PR-09 live subprocess tests to invoke modules with
  `sys.executable` and explicit `PYTHONPATH`, avoiding `uv run` inside
  mounted review sandboxes.
- Added a PR-09 GitHub Actions workflow that runs the required unit contracts
  on Python 3.12 inside `.venv`.
- Added an explicit irreversible-data-loss warning around manual
  `docker volume rm` reset instructions in `infra/README.md`.
- Regenerated PR-09 health and smoke summary artifacts with the new
  `status == overall` contract.

Validation:

- PR-09 focused block: 28 passed / 2 skipped.
- Full regression: 1819 passed / 61 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n run_smoke.sh infra/postgres/backup.sh infra/postgres/restore_verify.sh scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-08 — Agentic0 End-to-End System Integration Smoke

Current branch: `rag-01b/pr-08-integration-smoke`

Implemented:

- Added deterministic PR-08 integration package under `integration/` with:
  Agentic0 smoke contracts, LiteLLM-only Agentic0 client, integration health
  report, synthetic HybridRAG fixture, safe report writer and CLI smoke runner.
- Added PR-08 documentation:
  `docs/specs/rag-01b/pr-08-agentic0-integration-smoke.md`,
  `docs/rag/rag_01b_pr08_integration_report.md`, and
  `docs/references/llm_harness_original_papers.md`.
- Updated `docs/04_MEM/AGENT_CONTEXT.md` with final RAG-01B integration state,
  service responsibility map, Level 0/local-only policy and PR-08 commands.
- Added Agentic0 virtual-key/tool policy to host LiteLLM config and validator.
  Allowed tools are explicit; wildcard and destructive tools are rejected.
- Extended `scripts/start_quimera.sh` with:
  `integration-health`, `mcp-status`, `agentic0-smoke`, `pr08-report`, and
  `rag01b-final-gate`.
- Added PR-08 unit and integration tests for Agentic0 contracts, health,
  HybridRAG, MCP registration, no direct backend shortcuts, safe artifacts,
  OTel trace safety, degraded-service behavior, latency reporting and final
  closeout docs.
- Generated PR-08 artifacts:
  `evaluation/results/rag_01b_pr08_agentic0_smoke_summary.json`,
  `evaluation/results/rag_01b_pr08_integration_health.json`, and
  `evaluation/results/rag_01b_pr08_latency_summary.json`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No remote provider fallback.
- No Agentic0 direct Qdrant/Postgres/Ollama access.
- No destructive Qdrant/Postgres operations outside guarded test-prefix
  cleanup helpers.
- No raw prompt, answer, chunk, document text, vector, embedding, secret or DSN
  stored in PR-08 artifacts.

Validation:

- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- PR-08 focused block: 23 passed / 1 skipped.
- Full regression: 1787 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and LiteLLM validator:
  success.
- `uv run pyright` on PR-08 modules/tests and LiteLLM validator: 0 errors.
- `uv run python -m integration.run_agentic0_smoke_test --json --allow-degraded`:
  generated safe artifacts with status `skipped` because the local stack had
  LiteLLM/Qdrant/Postgres down while Ollama was OK.

Operational note:

- Live end-to-end Agentic0 synthesis should be rerun after starting the full
  local stack with LiteLLM host gateway, Qdrant and Postgres. The degraded
  result is intentional and safe; it verifies no shortcut path bypasses LiteLLM.

### RAG-01B PR-08 RC-01 — Reviewer Risk Closure

Implemented:

- HybridRAG artifacts now explicitly mark Recall@5 as
  `offline_synthetic_fixture`, require live local validation, and distinguish
  deterministic RRF fixture evidence from real `nomic-embed-text` quality.
- `json_has_no_forbidden_fields` now delegates to the AST-aware field scanner,
  so audit flags such as `secrets_seen` do not trigger false positives while
  unsafe field names remain blocked.
- `rag01b-final-gate` no longer interpolates JSON into a Python heredoc. It
  writes status, integration-health and smoke JSON to temporary files and loads
  them by path.
- Latency artifacts now include `measurement_mode`, `sample_count` and
  `p95_warning`. Offline/degraded runs set `p95_ms=null` with
  `not_measured_stack_unavailable`; live p95 over 500ms emits
  `p95_exceeds_500ms`.
- `scripts/quimera_status.py` now captures LiteLLM and Ollama healthcheck
  latency, and integration health includes safe per-service latency metadata.

Validation:

- PR-08 focused RC block: 27 passed / 1 skipped.
- Full regression: 1791 passed / 59 skipped.
- `uv run mypy --strict` on PR-08 modules/tests and status script: success.
- `uv run pyright` on PR-08 modules/tests and status script: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-07 — Benchmark + ADR + MCP Memory Gate

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Added deterministic benchmark harness and artifacts:
  `evaluation/results/rag_01b_session_benchmark_summary.json` and
  `evaluation/results/rag_01b_session_benchmark_rows.csv`.
- Added accepted backend decision ADR:
  `docs/ADR/ADR-003-memory-backend-decision.md`.
- Added PR-07 SDD and benchmark result documentation.
- Added FastMCP-based local memory servers:
  `backend/mcp/postgres_memory_server.py` and
  `backend/mcp/qdrant_memory_server.py`, with loopback-only ports 8811/8812
  and guarded tool inputs.
- Registered MCP servers in host LiteLLM config and hardened the config
  validator for loopback URL, port and transport policy.
- Wired OTel decorators into embedding, retrieval, RRF, cache and selected
  Postgres repository paths, and added benchmark probes for embed, retrieval,
  RRF, rerank, cache, pg_read and pg_write spans.
- Added `scripts/quimera_status.py` plus `start_quimera.sh status --json` and
  `rag01b-acceptance --json`.
- Hardened LiteLLM host-only policy: `start_litellm.sh` refuses to reuse a
  running `quimera-litellm` Docker container, and status JSON reports that
  violation explicitly.
- Closed PR-01/PR-02 reviewer gaps with opt-in integration tests for
  concurrent agent-state/turn writes, market-bar concurrency, and real
  pg_indexes checks.
- Added `fastmcp` dependency for the local MCP memory layer.

Validation:

- PR-07 focused unit block: 35 passed.
- PR-07 focused integration block: 5 passed / 7 skipped.
- Full unit suite: 1739 passed.
- Full regression: 1763 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.
- `git diff --check`: clean.

Operational note:

- Local status currently reports `overall=fail` because Postgres and Qdrant are
  not running and a legacy `quimera-litellm` Docker container is active. This is
  now detected as a host-only violation instead of being silently reused.

---

## RAG-01B PR-07 RC-01 — Review Sandbox and Decision Hardening

Current branch: `rag-01b/pr-07-benchmark-adr-mcp-memory`

Implemented:

- Refactored `test_start_quimera_status_json.py` subprocess checks to invoke
  `scripts/quimera_status.py` with `sys.executable` and explicit `PYTHONPATH`,
  avoiding `uv run` in sandbox-mounted review environments.
- Added `degraded` to MCP `ToolResponse`; Postgres MCP read tools now mark
  responses as degraded when no DSN/backend is configured, and write-enabled
  calls fail explicitly with `postgres backend unavailable`.
- Added `sprint: RAG-01B` to benchmark summary JSON and regenerated benchmark
  JSON/CSV artifacts.
- Clarified `llm_response_cache` decision as `qdrant` in benchmark decisions,
  ADR-003 and benchmark docs. LiteLLM remains gateway/manager, not the
  canonical storage backend.
- Updated PR-07 SDD OTel notes to reflect real retrieval/RRF instrumentation.

Validation:

- RC focused tests: 15 passed.
- Full unit suite: 1740 passed.
- Full regression: 1764 passed / 58 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `./scripts/start_quimera.sh rag01b-acceptance --json`: `overall=ok`.

---

## RAG-01B PR-06 — OpenTelemetry Base Layer

Current branch: `rag-01b/pr-06-otel-base-layer`
Base branch: `rag-01b/pr-05b-litellm-host-audit` while PR-05B remains open.
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- Added `backend/observability/` base package with OTel tracing setup,
  idempotent asyncpg instrumentation, safe attributes, PII/content guards,
  contextvars, events, metrics and async-only decorators.
- Added LiteLLM OTel callback guard and source YAML callback settings:
  `litellm_settings.callbacks: ["otel"]` plus
  `callback_settings.otel.message_logging: false`.
- Added `scripts/start_quimera.sh otel-doctor` and `otel-doctor --json`.
- Added `.env.observability.example` and PR-06 SDD.
- Added OTel dependencies:
  `opentelemetry-api`, `opentelemetry-sdk`,
  `opentelemetry-exporter-otlp-proto-http`,
  `opentelemetry-instrumentation-asyncpg`.

Scope explicitly not changed:

- No full RAG runtime instrumentation.
- No dashboard, collector, Grafana, Tempo, Jaeger or Prometheus service.
- No MCP server, FastAPI, REST API or gRPC.
- No PostgreSQL/Timescale schema change.
- No Qdrant collection change.
- No LiteLLM Docker service.

Validation:

- PR-06 focused OTel tests: 39 passed.
- LiteLLM/start-script compatibility block: 58 passed.
- Full unit suite: 1707 passed.
- Full regression: 1726 passed / 51 skipped.
- Focused post-typing block: 52 passed / 2 skipped.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n scripts/start_quimera.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `./scripts/start_quimera.sh otel-doctor --json`: status `ok`.
- `git diff --check`: clean.

Handoff to PR-07:

- Wire decorators into selected RAG/Gateway execution paths.
- Decide optional collector/profile strategy.
- Keep content capture disabled unless a future ADR explicitly changes the
  privacy boundary.

---

## RAG-01B PR-06 RC-01 — OTel SemConv and Test Marker Cleanup

Current branch: `rag-01b/pr-06-otel-base-layer`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/113>

Implemented:

- `traced_pg` now emits current OTel DB semconv attributes for PostgreSQL:
  `db.system.name=postgresql`, `db.operation.name` and `db.collection.name`,
  while preserving `quimera.pg_table`, `quimera.pg_operation` and
  `latency.pg_ms`.
- Added public metric name constants for the GenAI and retrieval histograms.
- Added `pytest.mark.integration` to all PR-06 OTel integration tests, so
  `pytest -m integration` includes them.
- Hardened `traced_mcp_tool`: validates low-cardinality tool/method names,
  stores tool name as `gen_ai.tool.name`, and keeps span name based on
  `mcp.method.name` rather than raw tool name.

Validation:

- RC focused block: 17 passed.
- `pytest -m integration` on OTel integration tests: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `uv run pytest`: 1730 passed / 51 skipped.
- `git diff --check`: clean.

---

## RAG-01B PR-05B — LiteLLM Host Audit and Hardening

Current branch: `rag-01b/pr-05b-litellm-host-audit`
Issue: <https://github.com/franciscosalido/OPENCLAW/issues/110>

Implemented:

- LiteLLM source config normalized to `os.environ/OLLAMA_BASE_URL`.
- Added canonical aliases `qwen3-local`, `qwen3:14b` and `nomic-embed-text`
  while preserving legacy Gateway/Agentic aliases.
- Embedding aliases now use timeout/stream timeout `5/5`; chat remains
  `120/45`; global request timeout remains `165`.
- Added `infra/litellm/audit.py` for safe JSON/Markdown audit reports.
- Added `infra/litellm/version_fingerprint.py` for best-effort local version
  collection with sanitized DSNs and structured warnings.
- Added `infra/litellm/overhead_benchmark.py`; live benchmark is opt-in via
  `QUIMERA_LITELLM_BENCHMARK=1`.
- Reworked `infra/litellm/start_litellm.sh` to start one host process,
  reuse readiness, write `.runtime/litellm.pid`, use `--num_workers 1`, and
  wait on `/health/readiness`.
- Added `scripts/start_quimera.sh` subcommands: `litellm-audit`,
  `litellm-fingerprint`, `litellm-benchmark`.
- Added PR-05B SDD at
  `docs/specs/rag-01b/pr-05b-litellm-host-audit.md`.

Scope explicitly not changed:

- No LiteLLM Docker service.
- No MCP server, FastAPI or gRPC.
- No HybridRAG mutation.
- No PostgreSQL/Timescale migrations or schema changes.
- No Qdrant collection deletion/recreate.
- No remote providers or model downloads.

Validation so far:

- PR-05B focused unit block: 58 passed.
- LiteLLM/Gateway/Agentic focused block: 160 passed / 95 subtests passed.
- All `tests/unit/test_litellm*.py` + start script tests: 78 passed /
  8 subtests passed.
- Full unit suite: 1669 passed / 256 subtests passed.
- Full regression: 1685 passed / 51 skipped / 259 subtests passed.
- `uv run mypy --strict` on `infra/litellm/*` PR-05B modules: success.
- `uv run pyright` on `infra/litellm/*` PR-05B modules: 0 errors.
- `bash -n` on `scripts/start_quimera.sh` and
  `infra/litellm/start_litellm.sh`: clean.
- `uv run python -m infra.litellm.config_validator`: success with one expected
  qdrant-semantic policy warning.
- `uv run python -m infra.litellm.render_config`: success, fallback local.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` due expected local-service/experimental warnings.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` without
  opt-in.

---

## RAG-01B PR-05B RC-01 — Residual Risk Cleanup

Current branch: `rag-01b/pr-05b-litellm-host-audit`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/111>

Implemented RC-01 fixes:

- RC-09 audit `warn` remains intentional when source YAML declares
  `qdrant-semantic` and the experimental flag is not set; SDD/README now state
  that fallback local is valid runtime behavior.
- `local_json` keeps `timeout=60` and `stream_timeout=45`; SDD/README now
  document the first-chunk tradeoff and recommend concise JSON contexts.
- `version_fingerprint` now exposes `python_version` and `python_executable`
  directly from the running interpreter, independent of command probe failures.
- `overhead_benchmark` keeps `status=SKIPPED_VALID` and now also emits
  `skipped=true` for compatibility with reviewer expectations.

Validation:

- RC-01 focused tests: 19 passed.
- LiteLLM/start-script block: 80 passed / 8 subtests passed.
- Gateway/Agentic focused block: 92 passed / 87 subtests passed.
- PR-05B opt-in integrations without env flags: 5 skipped.
- Full unit suite: 1671 passed / 256 subtests passed.
- `uv run mypy --strict` on RC-01 touched LiteLLM modules: success.
- `uv run pyright` on RC-01 touched LiteLLM modules: 0 errors.
- `uv run python -m infra.litellm.version_fingerprint`: success; includes
  `python_version` and `python_executable`.
- `uv run python -m infra.litellm.overhead_benchmark`: `SKIPPED_VALID` with
  `skipped=true`.
- `uv run python -m infra.litellm.audit`: generated JSON/Markdown, status
  `warn` by design.

---

## RAG-01B PR-05 RC-01 — LiteLLM Host Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/109>

Implemented RC-01 fixes:

- Raised chat alias `stream_timeout` from 15s to 45s for local Qwen slow-start
  safety.
- Raised global `request_timeout` to 165s so it covers 120s model timeout plus
  45s stream slow-start budget.
- Centralized embedding dimension in `CANONICAL_EMBED_DIM = 768` and validates
  the semantic-cache vector size against it.
- `start_quimera.sh` now warns when the local placeholder
  `LITELLM_MASTER_KEY=quimera-dev-key-change-me` is still used.
- `litellm-stop` sends SIGTERM to only the owned PID and escalates to SIGKILL
  only for that same PID after a grace loop.
- Runtime YAML render now uses `allow_unicode=True`.

Validation:

- RC focused tests: 33 passed.
- PR-05/Gateway focused block: 110 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1649 passed / 253 subtests passed.
- Full regression: 1666 passed / 47 skipped / 256 subtests passed.
- `bash -n` on changed shell scripts: clean.
- `./scripts/start_quimera.sh litellm-validate`: success.
- `uv run python -m infra.litellm.render_config`: success with
  `cache_backend=local`.
- Production scan: no LiteLLM Docker image/service, no Qdrant container URL,
  no `pkill litellm`, no `killall litellm`, no `down -v`.
- `git diff --check`: clean.

---

## RAG-01B PR-05 — LiteLLM Host Cache + Timeout Hardening

Current branch: `rag-01b/pr-05-litellm-host-cache-timeout`

Architectural correction:

- LiteLLM is a host Python process, not a Docker Compose service.
- Docker Compose manages only Postgres and Qdrant.
- `scripts/start_quimera.sh` reuses a ready host LiteLLM at
  `http://127.0.0.1:4000` or starts exactly one host process tracked by
  `.runtime/litellm.pid`.
- The PR-04 memory line saying Compose managed `quimera-litellm` is superseded
  by this PR-05 correction.

Implemented:

- Removed `litellm`/`quimera-litellm` from
  `infra/docker/compose.quimera.local.yml`.
- Added host LiteLLM commands to `scripts/start_quimera.sh`:
  `litellm-validate`, `litellm-render`, `litellm-start`, `litellm-stop`,
  `litellm-restart`, `litellm-smoke`.
- Added `infra/litellm/config_validator.py`,
  `infra/litellm/render_config.py` and `infra/litellm/smoke_test.py`.
- Added Qdrant semantic-cache source config with safe local fallback in the
  generated runtime config.
- Added tests guarding against LiteLLM returning to Compose.

Validation:

- Focused PR-05/Gateway block: 103 passed / 3 skipped / 65 subtests passed.
- Full unit suite: 1642 passed / 253 subtests passed.
- Full regression: 1659 passed / 47 skipped / 256 subtests passed.
- `docker compose -f infra/docker/compose.quimera.local.yml config --services`:
  `postgres-memory`, `qdrant`.
- `bash -n` on changed shell scripts: clean.
- `git diff --check`: clean.

---

## RAG-01B PR-04 RC-01 — Compose Env Guard + Volume Reset Docs

Current branch: `rag-01b/pr-04-ollama-tuning`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/108>

Implemented RC-01 fixes:

- `infra/docker/compose.quimera.local.yml` now requires `LITELLM_MASTER_KEY`
  through Docker Compose required interpolation and fails fast when missing.
- Added `.env.local.example` with a local placeholder key and Ollama defaults.
- Added `infra/README.md` documenting the local env contract and manual volume
  reset procedure.
- SDD now states that `restart` preserves volumes and corrupted-volume reset is
  manual/operator-owned via `docker volume rm`.

Validation:

- PR-04 unit tests: 28 passed.
- Compose config with placeholder key: success.
- Compose config without `LITELLM_MASTER_KEY`: fails as expected with an
  actionable message.
- Full unit suite: 1618 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-04 — Ollama Tuning + Keep-Alive Hardening

Current branch: `rag-01b/pr-04-ollama-tuning`
Base: `main` after PR-03 merge.

PR-03 was merged through GitHub:

- PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
- Merge commit: `3fe71d53460e00f68fbeb1df9821f4b8599a9ad6`
- `main...origin/main`: `0 0` after pull/prune.
- Local Git inconsistency fixed: `branch.main.rebase=false` and
  `pull.rebase=false` so `git pull --ff-only` no longer attempts rebase.

PR-04 implemented locally:

- `scripts/start_quimera.sh` controller with start/stop/restart/status/logs/
  doctor/test/warmup/release.
- Root `start_quimera.sh` and `scripts/star_quimera.sh` compatibility wrappers.
- `infra/ollama` config, warmup and shutdown/release hooks.
- `infra/docker/compose.quimera.local.yml` for `quimera-postgres-memory`,
  `quimera-qdrant` and `quimera-litellm`.
- `docs/specs/rag-01b/pr-04-ollama-tuning-keepalive.md`.

Validation:

- PR-04 unit tests: 25 passed.
- Controller self-test: 25 passed.
- Full unit suite: 1615 passed / 253 subtests passed.
- PR-04 optional integration: 1 passed / 2 skipped cleanly.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `bash -n` on shell wrappers: clean.
- YAML parse check: clean.
- `git diff --check`: clean.

Explicitly not implemented: schema SQL, HybridRAG changes, MCP/API/gRPC,
Kronos, Qlib, pgvector logic, model auto-pull or performance tests.

---

## RAG-01B PR-03 RC-02 — Corrupted Cache Payload Handling

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-02 fixes:

- `CacheLayer.lookup` now treats corrupted Qdrant cache payload as a safe cache
  miss, logs `cache_lookup_bad_payload_skipped` at DEBUG, and returns `None`.
- Added unit coverage proving corrupted cache payload does not raise
  `CachePayloadError` to callers.
- `hmac_query_hash` docstring now explicitly warns never to log `query_text`
  alongside the returned hash.

Validation:

- `test_cache_layer.py`: 9 passed.
- `test_cache_fingerprint.py`: 8 passed.
- PR-03 + observability focused tests: 52 passed.
- Full unit suite: 1590 passed / 253 subtests passed.
- Live Qdrant integration with `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.
- Cache module scope scans: no forbidden imports or destructive collection calls.

---

## RAG-01B PR-03 Review Gate

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Status: ready for review, not merged.

Rito status:

- Local branch pulled with `--ff-only`: already up to date.
- Local Qdrant checked healthy at `http://127.0.0.1:6333`.
- Live Qdrant integration now executed with
  `TEST_QDRANT_URL=http://127.0.0.1:6333`: 3 passed.
- PR was converted from draft to ready for review.
- Merge/prune are blocked until COWORK/human approval.

---

## RAG-01B PR-03 RC-01 — Semantic Cache Hardening

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>

Implemented RC-01 fixes:

- `CacheSettings` now rejects `collection_name == source_collection`.
- `invalidate_by_schema_version` rejects empty/blank version values.
- `invalidate_by_corpus_epoch` rejects empty/blank corpus epoch values.
- `test_rag_observability_config` no longer writes to a fixed file under
  `tests/`; it uses an isolated temporary directory, resolving the pre-existing
  PermissionError/carry-over artifact risk.
- `hmac_query_hash` is documented as a caller-side helper whose raw query input
  must never be persisted; only the returned hash may be stored.
- `record_hit` remains best-effort but now emits a safe DEBUG log on failure.

Validation:

- RC focused tests: 37 passed.
- PR-03 + observability focused tests: 51 passed.
- Full unit suite: 1589 passed / 253 subtests passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

---

## RAG-01B PR-03 — HybridRAG Semantic Cache Layer (Qdrant)

Current branch: `rag-01b/pr-03-hybridrag-cache-qdrant`
Draft PR: <https://github.com/franciscosalido/OPENCLAW/pull/106>
Implementation series: `414bf28..HEAD` on the draft PR branch.

Local and remote branch are aligned (`HEAD...origin/rag-01b/pr-03-hybridrag-cache-qdrant`
is `0 0`).

Implemented:

- SDD for PR-03 semantic retrieval cache.
- `backend/rag/cache/*` settings, models, fingerprint helpers, Qdrant collection
  manager, async `CacheLayer`, errors and shared types.
- Unit tests with fake Qdrant clients.
- Optional live Qdrant integration tests guarded by environment configuration.

Validation:

- PR-03 focused unit tests: 44 passed.
- Optional Qdrant integration tests: 3 skipped cleanly when live integration env
  is not set.
- Full unit suite: 1587 passed / 253 subtests passed.
- `uv run mypy --strict .`: success.
- `uv run pyright`: 0 errors.
- `git diff --check`: clean.

Explicitly not implemented in PR-03: response cache, raw query/prompt/final
answer/full chunk storage, LLM calls, embedding generation, MCP/API/gRPC,
PostgreSQL/TimescaleDB changes, Qdrant knowledge collection mutation or ORM.

---

## RAG-01B PR-01 RC-02 — PostgreSQL 18.4 Canonical Memory Base

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 accepts PostgreSQL 18.4 as the canonical relational-temporal memory
  version.
- Docker Compose pins `postgres:18.4-trixie`.
- PostgreSQL local auth uses `POSTGRES_PASSWORD_FILE` with a non-versioned
  password file under `infra/postgres/secrets/`.
- PostgreSQL 18+ storage layout is explicit: volume mount
  `/var/lib/postgresql`, internal `PGDATA=/var/lib/postgresql/18/docker`.
- PKD-00X documents the QUIMERA MCP Memory Fabric over LiteLLM as the future
  memory access architecture. No MCP runtime was implemented in RC-02.
- PostgreSQL 16 was the previous blueprint reference and is superseded by
  ADR-0021.

No benchmark, migration, SQL schema change or version-selection test was added
for this decision.

## RAG-01B PR-01 RC-03 — Janus Temporal Memory Fabric

Current branch: `rag-01b/pr-01-postgres-session-schema`

Local-only review state:

- ADR-0021 now includes a TimescaleDB addendum.
- ADR-0022 accepts PostgreSQL 18.4 + TimescaleDB as the single temporal memory
  source of truth for agentic memory, financial time series, Qlib projections
  and Kronos forecasts.
- Qlib is a derived compatibility projection, not canonical storage.
- Kronos has no separate persistent memory.
- Blueprint V3.0 now includes the QUIMERA Janus Temporal Memory Fabric section.

No TimescaleDB runtime, Docker image change, SQL extension, hypertable, schema,
Qlib adapter, Kronos adapter or MCP tool was implemented in RC-03.

---

## Stack State — 2026-05-27

Stack local completamente verificado e funcional. Ver `docs/04_MEM/QUIMERA_STACK_RUNBOOK.md`.

| Serviço  | Status | Versão / Detalhe                              |
|----------|--------|-----------------------------------------------|
| Qdrant   | ✅ UP  | v1.18.1, 4 collections presentes              |
| Ollama   | ✅ UP  | nomic-embed-text:latest (0.27GB) + qwen3:14b (9.28GB) |
| LiteLLM  | ✅ UP  | 4 aliases chat saudáveis, embedding falso-positivo no health check (ver BUG 1) |

**Fixes aplicados em `start_quimera.sh`:**
1. `/health` → `/health/liveliness` em todas as verificações LiteLLM (3 ocorrências + modo `--status`)
2. Adicionado export de `LITELLM_LOCAL_CHAT_MODEL` e `LITELLM_LOCAL_EMBED_MODEL` no fallback sem iTerm2
3. iTerm2 path: variáveis derivadas incluídas no `LITELLM_TAB_CMD`

**Problema residual conhecido (não-bloqueante):** LiteLLM reporta `unhealthy_count: 2` para `quimera_embed`/`local_embed` porque o health check interno usa `/api/generate` mas `nomic-embed-text` só aceita `/api/embed`. Os embeddings reais funcionam perfeitamente (768d verificado). Ver BUG 1 no runbook.

---

---

## Active Sprint: Agent-0 / CLI and Readiness

**Goal:** expose the first stable public Agent-0 interface,
`OpenClaw.ask(question) -> Answer`, plus a local CLI, readiness checks,
opt-in E2E SLO gates, sanitized reports and rollback docs.

Current branch: `feat/agent0-cli-and-readiness`
Current issue: <https://github.com/franciscosalido/OPENCLAW/issues/82>

A0-PR05 starts after A0-PR04 and closes the Agent-0 MVP sprint surface. It
does not add multi-agent orchestration, FastAPI, MCP, UI, remote providers,
remote fallback, new ingestion, reindexing or Qdrant mutation in readiness.

```text
question
  -> OpenClaw.ask
  -> deterministic domain routing
  -> existing local RAG path when route == local_rag
  -> frozen Answer with metadata-only citations
  -> CLI / sanitized E2E report
```

Current runtime path:

```text
OpenClaw / runtime generation
  -> LiteLLM at http://127.0.0.1:4000/v1
  -> Ollama / Qwen local
```

Current controlled embedding path:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM at http://127.0.0.1:4000/v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text local
```

Rollback embedding path:

```text
RagEmbedder factory
  -> direct_ollama
  -> OllamaEmbedder
  -> Ollama direct at http://127.0.0.1:11434/api/embed
```

GW-07 proves the current RAG E2E path without migrating embeddings:

```text
synthetic docs
  -> chunking
  -> OllamaEmbedder direct at http://127.0.0.1:11434/api/embed
  -> Qdrant temporary collection gw07_synthetic_rag_<short_uuid>
  -> Retriever / ContextPacker / PromptBuilder
  -> LocalGenerator / GatewayChatClient
  -> LiteLLM at http://127.0.0.1:4000/v1/chat/completions
  -> Ollama / Qwen local
```

Hard constraints remain:

- Local only.
- No remote providers.
- No FastAPI.
- No MCP.
- No quant tools.
- No secrets or real portfolio data.
- No `openclaw_knowledge` mutation in verify-only.
- No Qdrant mutation unless `--commit` is explicit and a future writer is wired.
- No arbitrary collection override for dual corpus bootstrap.
- No answer generation in A0-PR03 golden question harness or A0-PR04 routing.
- No LLM-as-judge.
- No Qdrant mutation or live Qdrant requirement in A0-PR03 unit tests.
- No LLM classifier, embeddings, rerankers, remote providers or live Qdrant
  dependency in A0-PR04 classifier/routing unit tests.
- No Qdrant mutation, reindexing or bootstrap in A0-PR05 readiness checks.
- A0-PR05 E2E is opt-in only via `RUN_AGENT0_E2E=1`; unit tests remain offline.
- A0-PR05 reports must not serialize prompt, question text, answer text, chunks,
  vectors, embeddings, payloads, headers, secrets, raw exceptions or tracebacks.
- No final local merge into `main`; GitHub PR approval is the integration path.

## A0-PR05 Current Work

A0-PR05 adds the final Agent-0 MVP public/readiness surface:

- `backend/agent0/openclaw.py` with `OpenClaw.ask(...)` and frozen `Answer`.
- `scripts/openclaw.py` with `ask` command and safe JSON/human output.
- `scripts/check_agent0_readiness.py` with idempotent local readiness checks.
- `backend/agent0/e2e_report.py` with sanitized E2E SLO report builder.
- `tests/e2e/test_agent0_e2e.py`, guarded by `RUN_AGENT0_E2E=1`.
- `docs/AGENT0_RUNBOOK.md` and `docs/AGENT0_ROLLBACK.md`.

Rules:

- `OpenClaw.ask` must reuse existing routing, citation and RAG components; do
  not duplicate the pipeline in the public API wrapper.
- CLI must call `OpenClaw.ask`, support `--json`, avoid tracebacks by default
  and never print prompt/chunks/vectors/payloads/secrets.
- Readiness checks verify Qdrant reachability/collections, local LiteLLM,
  Ollama models, aliases, remote routing disabled, corpus manifests and golden
  questions. They do not mutate Qdrant or bootstrap collections.
- E2E SLO gate is opt-in and expects already-bootstrapped
  `openclaw_internal` / `openclaw_financial`.
- Final SLOs: E2E p95 < 15s and citation hit rate >= 5/6 on the six golden
  questions when local services and corpora are available.
- Rollback deletes only `openclaw_internal` and `openclaw_financial`; never
  delete `openclaw_knowledge`.
- Validation on Python 3.12.13:
  `pytest -v` 561 passed / 9 skipped / 217 subtests passed,
  `mypy --strict .` 0 errors, `pyright` 0 errors, smoke 5 passed / 7 skipped.
- Optional live check status: CLI returns a sanitized local auth failure when
  local gateway credentials are absent; readiness reported 7/9 with only
  Agent-0 Qdrant collections missing in this local environment.

---

## Mandatory GitHub Workflow

For every tracked task:

1. Sync local `main` with GitHub.
2. Open or update a GitHub Issue before implementation.
3. Create a feature branch from updated `main`.
4. Implement locally.
5. Run validation locally.
6. Commit atomic changes.
7. Push the feature branch.
8. Open a GitHub PR to `main`.
9. Link the PR to the issue.
10. Address review on the same branch.
11. Merge only in GitHub after approval.
12. After merge, pull `main` with `--ff-only` and delete branches only when safe.

Do not push directly to `main`. Do not use `git push --force`; if a rebase is
unavoidable, use `git push --force-with-lease`.

---

## Gateway PR Tracking

| PR | Branch | Scope | Status |
|---|---|---|---|
| GW-01 | `feat/gateway-prep-contracts` | ADR, Blueprint V3.0, semantic aliases, config contracts | Done / merged |
| GW-02 | `feat/gateway-install-health` | Local-only LiteLLM operational setup | Done / merged |
| GW-03 | `feat/gateway-route-opencraw-litellm` | Runtime chat/generation through LiteLLM | Done / merged |
| GW-04 | `feat/gateway-runtime-smoke` | Shared message validation, optional smoke, observability | Done / merged |
| GW-05a | `feat/gateway-per-alias-timeouts` | Per-alias timeout configuration | Done / merged |
| GW-05b | `feat/gateway-live-smoke-timeouts` | Live smoke with effective timeout observability | Done / merged |
| GW-06 | `feat/gateway-local-embed-evaluation` | Evaluate embeddings via `local_embed` | Done / merged |
| GW06C | `feat/adr-openai-compatible-embeddings-contract` | OpenAI-compatible embeddings ADR and `quimera_embed` | Done / merged |
| GW-07 | `feat/gateway-rag-e2e-synthetic` | Synthetic RAG E2E through gateway path | Done / merged |
| GW-08 | `feat/rag-controlled-embedding-migration` | Controlled RAG embedding migration to `quimera_embed` | Done / merged |
| GW-09 | `feat/rag-collection-metadata-guard` | Collection metadata drift guard for embedding traceability | Done / merged |
| GW-10 | `feat/rag-run-trace-provenance` | Safe per-query RAG provenance trace | Done / merged |
| GW-11 | `feat/rag-observability-events` | Safe structured RAG lifecycle observability events | Done / merged |
| GW-12 | `feat/gateway-operational-readiness` | Final runbook, readiness checks, ADR boundary, handoff | Done / merged |
| GW-13 | `feat/gateway1-routing-policy-prelude` | Gateway-1 local-first routing policy and token economy prelude | Done / merged |
| GW-14 | `feat/gateway1-routing-audit-token-economy` | Config-driven routing audit and token economy calibration | Done / merged |
| GW-15 | `feat/agent0-local-runner` | Agent-0 local CLI runner MVP | Done / merged |
| GW-16 | `feat/agent0-runner-contract-hardening` | Agent-0 runner contract hardening | Done / merged |
| GW-17 | `feat/agent0-local-failsafe-degradation` | Explicit local fail-safe degradation for Agent-0 | Done / merged |
| GW-18 | `feat/agent0-golden-question-harness` | Golden question benchmark harness for Agent-0 | Done / merged |
| GW-19 | `feat/agent0-observability-signal-contract` | Agent-0 observability signal contract and sanitization tests | Done / merged |
| GW-20 | `feat/gateway1-proof-of-life-smoke` | Gateway-1 operational proof-of-life smoke | Done / merged |
| G2-PR01 | `feat/g2-rag-segment-timing-baseline` | Per-segment RAG latency baseline | Done / merged |
| G2-PR02 | `feat/g2-local-rag-context-budget-cap` | Configurable whole-chunk context budget cap | Done / merged |
| G2-PR03 | `feat/g2-local-rag-generation-budget` | Configurable local_rag generation budget | Done / merged |
| G2-PR04 | `feat/g2-warm-model-cold-start-separation` | Cold/warm/degraded latency separation and model residency measurement | Done / merged |
| G2-PR05 | `feat/g2-keep-alive-model-residency` | Configurable local_rag Ollama keep_alive model residency | Done / merged |
| G2-PR06 | `feat/g2-local-rag-alias-comparison` | Local-only local_rag candidate alias comparison harness | Current |

GW-05a issue: <https://github.com/franciscosalido/OPENCLAW/issues/25>
GW-05b issue: <https://github.com/franciscosalido/OPENCLAW/issues/28>
GW-06 issue: <https://github.com/franciscosalido/OPENCLAW/issues/30>
GW-07 issue: <https://github.com/franciscosalido/OPENCLAW/issues/38>
GW-08 issue: <https://github.com/franciscosalido/OPENCLAW/issues/40>
GW-09 issue: <https://github.com/franciscosalido/OPENCLAW/issues/42>
GW-10 issue: <https://github.com/franciscosalido/OPENCLAW/issues/44>
GW-11 issue: <https://github.com/franciscosalido/OPENCLAW/issues/46>
GW-12 issue: <https://github.com/franciscosalido/OPENCLAW/issues/48>
GW-13 issue: <https://github.com/franciscosalido/OPENCLAW/issues/51>
GW-15 issue: <https://github.com/franciscosalido/OPENCLAW/issues/55>
GW-16 issue: <https://github.com/franciscosalido/OPENCLAW/issues/57>
GW-17 issue: <https://github.com/franciscosalido/OPENCLAW/issues/59>
GW-18 issue: <https://github.com/franciscosalido/OPENCLAW/issues/61>
GW-19 issue: <https://github.com/franciscosalido/OPENCLAW/issues/63>

Gateway-0 sprint complete. GW-01 through GW-12 merged on `main`.
The next sprint must start from a new explicit issue, ADR if architecture
changes, and `git pull --ff-only origin main`.

## G2-PR06 Current Work

G2-PR06 adds an opt-in alias comparison harness for `local_rag` candidates.

Deliverables:

- `scripts/run_rag_alias_comparison.py`.
- `tests/unit/test_rag_alias_comparison.py`.
- `docs/RAG_ALIAS_COMPARISON.md`.

Rules:

- `local_rag` remains the default and comparison baseline.
- Candidate aliases must be semantic local LiteLLM aliases, never concrete
  model names.
- Candidate aliases must resolve to local Ollama config only.
- Remote provider prefixes are rejected.
- The same synthetic golden question fixture is used for baseline and
  candidates.
- Reports store `question_id`, fixture hash, alias metrics and citation flags,
  never question text, answer text, prompt text, chunks, vectors, payloads,
  headers, API keys or tracebacks.
- Warmup runs are discarded and marked only in summary metadata.
- No prompt, retrieval, Qdrant, context budget, generation budget, keep_alive,
  alias default or provider config is changed.
- Candidate promotion requires a separate future PR.

## GW-15 Current Work

GW-15 creates Agent-0, the first local MVP runner:

```text
question
  -> decide_route(...)
  -> local_chat | local_json | explicit local_rag
  -> safe answer metadata
```

Deliverables:

- `scripts/run_local_agent.py`.
- `scripts/test_agent0_local_runner.sh` optional smoke guarded by
  `RUN_AGENT0_LOCAL_SMOKE=1`.
- `docs/AGENT0_LOCAL_RUNNER.md`.
- `tests/unit/test_run_local_agent.py`.

Rules:

- Default execution uses `local_chat`.
- `--json` uses `local_json`.
- `--rag` explicitly opts into the existing local RAG path and `local_rag`.
- `--dry-run` works without live services.
- No remote providers, no remote calls, no API keys, no FastAPI, no MCP.
- No Qdrant mutation, no reindexing, no ingestion, no real data.
- Progressive fallback is handled by GW-17.
- Golden questions harness is handled by GW-18.

## GW-16 Current Work

GW-16 hardens the Agent-0 runner contract without adding new execution
features.

Rules:

- Alias matrix is frozen: default `local_chat`, `--json` `local_json`,
  `--rag` `local_rag`.
- Output schema remains stable across success, dry-run, blocked and failure
  states.
- Blocked and dry-run paths return `latency_ms=0.0`.
- Chat, JSON and RAG failures return safe error categories only.
- No fallback is added. RAG/JSON/chat failures do not silently try another
  alias.
- No remote providers, no remote calls, no Qdrant mutation, no live services
  required for tests.

## GW-17 Current Work

GW-17 adds the first explicit local fail-safe degradation layer.

Rules:

- Fallback reasons are enum-derived, not free-form strings.
- RAG/Qdrant unavailable can fallback once from `local_rag` to `local_chat`.
- Successful RAG fallback returns the chat answer, `alias=local_chat`, and
  `used_rag=false`.
- Policy blocks such as `budget_exceeded` and `unsupported_task` never
  fallback, call no model, and return `error_category=blocked`.
- If the fallback alias also fails, the runner returns a safe failure with no
  second fallback.
- Fallback emits a sanitized local `agent_fallback` loguru event only when
  fallback occurs.
- `local_think` timeout fallback is deferred because Agent-0 has no public
  think path yet.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-18 Current Work

GW-18 adds the reproducible Agent-0 golden question harness.

Deliverables:

- `tests/golden/questions.yaml` with 8 synthetic financial-domain questions.
- `scripts/run_golden_harness.py` opt-in harness guarded by
  `RUN_GOLDEN_HARNESS=1`.
- Offline `--dry-run` mode that emits JSONL and summary JSON without live
  services.
- `scripts/compare_golden_runs.py` for summary-to-summary regression checks.
- `docs/AGENT0_GOLDEN_HARNESS.md` and `tests/golden/README.md`.

Rules:

- No answer text is stored in JSONL by default; only `answer_length_chars`.
- Reports exclude prompt/question/chunks/vectors/payloads/secrets and raw
  exceptions.
- Reports are written under `tests/golden/reports/`, which is ignored by Git.
- Quality scoring is human-readable only; no LLM-as-judge and no external API.
- Optional human scoring helper is deferred to a future issue.
- No remote providers, no remote calls, no Qdrant mutation, no real data, and
  no live services required for unit tests.

## GW-19 Current Work

GW-19 adds the Agent-0 observability signal contract.

Deliverables:

- `backend/gateway/observability_contract.py` with canonical allowlists and
  prohibited signal keys.
- `tests/unit/test_observability_signal_contract.py` for RouterDecision,
  TokenEconomyRecord, RagRunTrace, fallback events, decision logs, Agent-0
  output and golden harness dry-run reports.
- `docs/AGENT0_OBSERVABILITY.md`.
- GW-18 NB fixes:
  - golden harness uses `estimate_prompt_tokens` directly from
    `backend.gateway.routing_policy`;
  - `GoldenResult` rejects `skipped=True` with `error_category`.

Rules:

- Sanitization is enforced with allowlists, not blocklist-only checks.
- Fallback event `decision_id` must correlate with Agent-0 output.
- `estimated_remote_tokens_avoided` is checked across success, dry-run,
  blocked, fallback success and fallback failure paths.
- No prompt, raw user input, chunks, vectors, payloads, headers, API keys, raw
  exceptions or model weight paths may appear in observability keys.
- No runtime routing behavior, fallback behavior or remote provider behavior is
  changed.
- No live LiteLLM/Ollama/Qdrant services are required for tests.

## GW-13 Completed Work

GW-13 opens Gateway-1 with safe routing policy records only.

Deliverables:

- `backend/gateway/routing_policy.py` with frozen decision and token economy
  dataclasses.
- `config/rag_config.yaml` `gateway.routing` defaults with
  `remote_enabled: false` and no allowed remote providers.
- `docs/GATEWAY1_ROUTING_POLICY.md`.
- `docs/ADR/0020-controlled-remote-escalation-policy.md` with status Proposed.
- `docs/sprints/GATEWAY1_SPRINT_HANDOFF.md`.
- `tests/unit/test_gateway_routing_policy.py`.

Rules:

- No remote providers.
- No remote calls.
- No API keys.
- No runtime model routing change.
- No Qdrant mutation, reindexing, ingestion, or `openclaw_knowledge` access.
- Token economy is estimated only, not billed.
- Remote escalation requires future sanitization and an explicit Accepted ADR.

---

## GW-05a Timeout Contract

Runtime gateway calls now reserve different timeout budgets per semantic alias:

| Alias | Timeout | Notes |
|---|---:|---|
| `local_chat` | 30.0s | Default chat calls |
| `local_think` | 120.0s | Longer local reasoning calls |
| `local_rag` | 60.0s | RAG answer synthesis |
| `local_json` | 30.0s | Structured local responses |
| `local_embed` | 30.0s | Placeholder only; embeddings are not routed through LiteLLM in GW-05a |

Unknown aliases and `None` fall back to the global `timeout_seconds`.

---

## GW-12 Completed Work

GW-12 closed Gateway-0 as an operational readiness PR, not a feature PR.

Deliverables:

- `docs/GATEWAY_FINAL_RUNBOOK.md`.
- `scripts/check_gateway_readiness.sh` with static default mode and explicit
  `--live`.
- `tests/unit/test_gateway_readiness_script.py`.
- `tests/unit/test_gateway_final_baseline.py`.
- `docs/ADR/0019-gateway-0-sprint-boundary.md`.
- Final updates to shared context, setup, runtime and handoff docs.

Rules respected:

- No runtime architecture change.
- No remote providers.
- No FastAPI, MCP, quant tools, OpenTelemetry, Prometheus, Grafana,
  dashboards, profiling, or mandatory soak tests.
- No Qdrant mutation, no reindexing, no `openclaw_knowledge` access.
- Live proof remains opt-in and must not become CI.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## Historical Work

GW-05b:

- Add `timeout_s` to gateway call debug logs.
- Run expanded live smoke with LiteLLM and Ollama actually running when
  `RUN_LITELLM_SMOKE=1` is explicitly set.
- Validate `local_chat`, `local_think`, `local_rag`, and `local_json` against
  their effective timeout budgets.
- Keep smoke synthetic-only and local-only.
- Do not introduce remote providers, real data, RAG E2E, or embeddings through
  LiteLLM.

Live smoke status for GW-05b:

- **2026-04-28: PASSED** — Cenário A completo.
- 128/128 unit+integration tests passed. mypy 0. pyright 0.
- `RUN_LITELLM_SMOKE=1 pytest tests/smoke/` — 7/7 passed.
- `RUN_LITELLM_SMOKE=1 RUN_LITELLM_SMOKE_REPEAT=3 pytest tests/smoke/` — 7/7 passed (54s).

Observed latencies (macOS, qwen3:14b Q4_K_M):

| Alias | elapsed_s | timeout_s |
|---|---:|---:|
| `local_chat` | 2.20 | 30.0 |
| `local_think` | 12.44 | 120.0 |
| `local_rag` | 2.23 | 60.0 |
| `local_json` | 1.72 | 30.0 |

GW-06:

- Evaluate whether embeddings should route through `local_embed`.
- Add an experimental `GatewayEmbedClient` for OpenAI-compatible
  `/embeddings` calls through LiteLLM.
- Keep existing direct/local embedding behavior as the default RAG path.
- Do not reindex Qdrant or touch real documents.
- Use only synthetic smoke inputs.
- Live evaluation on 2026-04-28 passed against local LiteLLM + Ollama.
- Decision status: **Approved for future migration**.
- Migration is still not performed in GW-06; a future PR must preserve or
  replace the current Ollama embedder's retry/backoff/concurrency behavior.

Observed local_embed results (2026-04-28):

| Check | Result |
|---|---|
| LiteLLM single embedding | 768 dimensions, 0.08s |
| LiteLLM batch embedding | 2 vectors, 768 dimensions each, 0.05s |
| Direct Ollama parity | 768 dimensions |
| Cosine similarity | 1.000000 |
| Script smoke | 768 dimensions, 0.70s |

GW-07:

- Prove a synthetic RAG end-to-end flow against the gateway path.
- Keep Qdrant data synthetic and local.
- Use a unique temporary collection named `gw07_synthetic_rag_<short_uuid>`.
- Attempt prefix-guarded cleanup and delete only temporary collections with the
  `gw07_synthetic_rag_` prefix.
- Never touch `openclaw_knowledge`.
- Keep embeddings direct through `OllamaEmbedder`; `quimera_embed` appears only
  as embedding contract metadata in this PR.
- Generate the final answer through LiteLLM using `local_rag`.
- Run only when explicitly enabled with `RUN_RAG_E2E_SMOKE=1`.

Manual live command:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

Direct pytest command:

```bash
RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v
```

Cleanup is attempted in teardown. If cleanup is interrupted, manually delete
only Qdrant collections whose names start with `gw07_synthetic_rag_`.

Live status:

- **2026-04-30: PASSED** — Cenário A completo for GW-07.
- Command: `RUN_RAG_E2E_SMOKE=1 uv run pytest tests/smoke/test_rag_e2e_gateway_smoke.py -v -s`.
- Corpus: 3 PT-BR synthetic documents, 14 chunks, 5 chunks retrieved/used.
- Temporary collection: `gw07_synthetic_rag_<short_uuid>` with prefix-guarded
  cleanup for the recorded run; interrupted runs may require manual cleanup by
  prefix.
- Embedding path: direct `OllamaEmbedder` to Ollama `/api/embed`.
- Generation path: `LocalGenerator` / `GatewayChatClient` through LiteLLM
  `local_rag`.

Observed GW-07 latencies (2026-04-30):

| Stage | Latency |
|---|---:|
| embedding/indexing | 178.1 ms |
| retrieval | 18.4 ms |
| generation | 3621.2 ms |
| total pipeline | 3639.6 ms |

---

## Validation Expectations For GW-07

Before opening PR:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run python -m compileall backend tests scripts infra
uv run pytest tests/unit/test_gateway_embed_client.py -v
uv run pytest tests/smoke/ -v
```

## GW-10 Completed Work

GW-10 adds `RagRunTrace`, a safe frozen dataclass for per-query provenance:

```text
LocalRagPipeline.ask(...)
  -> retrieval/prompt/generation timings
  -> RagRunTrace safe metadata only
  -> logger.bind(trace=...).log(...)
```

Trace scope:

- Records collection name, embedding backend/model/alias/dimensions, chunk
  count, gateway alias, and latency metadata.
- Does not record query text, chunk text, prompts, answer text, vectors,
  payloads, real portfolio data, private documents, API keys, Authorization
  headers, or secrets.
- Uses `rag.tracing.enabled` and `rag.tracing.log_level` from
  `config/rag_config.yaml`.
- Raises `EmbeddingDimensionMismatchError` if trace dimensions diverge from
  active expected dimensions.
- Does not mutate Qdrant, reindex collections, or touch `openclaw_knowledge`.

GW-11 current work remains separate from `RagRunTrace`: lifecycle events are
local structured loguru records around embedding, retrieval, and generation.
Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

Live smoke tests should skip by default unless their explicit guards are set.
GW-07 requires `RUN_RAG_E2E_SMOKE=1`.

Optional live validation when local services are already running:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
RUN_LITELLM_EMBED_SMOKE=1 uv run pytest tests/smoke/test_gateway_embed_smoke.py -v
scripts/test_local_embed_litellm.sh
```

Optional GW-07 live validation when Qdrant, Ollama, LiteLLM, and credentials are
already running locally:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_rag_e2e_gateway.sh
```

## GW-08 Completed Work

GW-08 aligns new controlled RAG embedding generation with the accepted
OpenAI-compatible embeddings contract:

```text
RagEmbedder factory
  -> gateway_litellm
  -> GatewayEmbedClient
  -> LiteLLM /v1/embeddings
  -> quimera_embed
  -> Ollama / nomic-embed-text
```

Rollback remains explicit:

```bash
export QUIMERA_RAG_EMBEDDING_BACKEND="direct_ollama"
```

Key rules:

- `OllamaEmbedder` remains available.
- `direct_ollama` remains the rollback backend.
- Existing collections are not reindexed automatically.
- `openclaw_knowledge` is not touched.
- Vectors from different embedding backends, models, providers, or dimensions
  must not be mixed silently in one collection.
- GW-08 smoke uses temporary collections with prefix
  `gw08_embedding_migration_`.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

Optional live validation:

```bash
export QUIMERA_LLM_API_KEY="${LITELLM_MASTER_KEY}"
scripts/test_gw08_embedding_migration.sh
```

Live status:

- **2026-04-30: PASSED** — controlled migration smoke and parity smoke passed.
- Required operational note: restart LiteLLM after adding `quimera_embed`; an
  old LiteLLM process may still expose only `local_embed`.
- Command: `QUIMERA_LLM_API_KEY=<local-placeholder> scripts/test_gw08_embedding_migration.sh`.
- Temporary collection prefix: `gw08_embedding_migration_`.
- Synthetic chunks: 4 indexed, 4 retrieved/used.
- Embedding path: `RagEmbedder factory -> gateway_litellm -> GatewayEmbedClient -> LiteLLM /v1/embeddings -> quimera_embed`.
- Generation path: `LocalGenerator / GatewayChatClient -> LiteLLM local_rag`.
- Rollback path remains: `QUIMERA_RAG_EMBEDDING_BACKEND=direct_ollama`.
- `openclaw_knowledge` was not touched.

Observed GW-08 latencies and parity (2026-04-30):

| Check | Result |
|---|---:|
| embedding/indexing | 314.7 ms |
| retrieval | 27.4 ms |
| generation | 4951.7 ms |
| total pipeline | 4979.1 ms |
| cosine similarity vs direct Ollama | 1.000000 |
| vector dimensions | 768 |

## GW-09 Completed Work

GW-09 adds a traceability guard for Qdrant collection embedding metadata:

```text
Qdrant payload sample
  -> embedding_backend/model/dimensions/contract/alias check
  -> structured warning on drift
  -> hard error only for dimension mismatch by default
```

Key rules:

- The guard samples payloads with `with_payload=True` and `with_vectors=False`.
- It does not mutate, delete, recreate, or reindex collections.
- It does not touch `openclaw_knowledge`.
- Backend, model, contract, alias, and missing metadata drift warn by default.
- Dimension mismatch always raises `EmbeddingDimensionMismatchError`.
- `strict=True` can raise on backend/model/contract/alias mismatch.
- No chunk text, vectors, prompts, secrets, or Authorization headers are logged.
- GW-10 remains the place for `RagRunTrace`.
- GW-11 adds structured RAG observability lifecycle events separately.

Validation expectations:

```bash
git diff --check
uv run pytest -v
uv run mypy --strict .
uv run pyright
uv run pytest tests/smoke/ -v
```

## GW-11 Completed Work

GW-11 adds local structured RAG lifecycle observability events:

```text
embedding/retrieval/generation stage
  -> RagObservabilityEvent safe metadata only
  -> logger.bind(event=...).log(...)
```

Scope:

- `backend/rag/observability.py` defines event kinds, error categories, config,
  safe serialization, emission, and exception categorization.
- `GatewayEmbedClient` emits embedding started/finished/failed events for
  `gateway_litellm`.
- `OllamaEmbedder` emits embedding started/finished/failed events for
  `direct_ollama`.
- `LocalRagPipeline` emits retrieval and generation lifecycle events.
- `config/rag_config.yaml` has `rag.observability` flags and log level.

Safety rules:

- Events contain only safe scalar metadata.
- Events never include query text, prompt text, answer text, chunk text,
  document text, vectors, Qdrant payloads, portfolio data, API keys,
  Authorization headers, tokens, passwords, or secrets.
- No return values change.
- Retry/backoff/concurrency semantics are unchanged.
- Qdrant is not mutated and `openclaw_knowledge` is not touched.

Out of scope:

- OpenTelemetry, Prometheus, Grafana, dashboards, distributed tracing,
  profiling, soak tests, and memory/resource baselines.
- Memory/resource baseline: not implemented in GW-12. Deferred to a future sprint. See ADR-0019 Future Work section.

## GW-20 Completed Work

GW-20 adds the Gateway-1 operational proof-of-life smoke and closes the
Gateway-1 readiness loop before Gateway-2:

```text
dry-run Agent-0
  -> local URL guard
  -> Ollama/Qdrant/LiteLLM probes
  -> live local_chat
  -> live local_rag or explicit fallback
  -> forced Qdrant degradation
  -> policy block no-model-call check
  -> sanitized summary JSON
```

Key files:

- `docs/sprints/GATEWAY1_DONE_CRITERIA.md`
- `scripts/test_gateway1_proof_of_life.py`
- `docs/AGENT0_SMOKE.md`
- `tests/unit/test_gateway1_proof_of_life.py`

Rules:

- The smoke is opt-in with `RUN_GATEWAY1_PROOF_OF_LIFE=1`.
- Live probes refuse non-local service URLs.
- Summary reports do not store answer text, prompts, questions, chunks,
  vectors, payloads, secrets, Authorization headers, raw exceptions or
  tracebacks.
- Forced degradation is injected through Agent-0 hooks; it does not stop Docker,
  mutate Qdrant, reindex, or touch `openclaw_knowledge`.
- Gateway-2 should not begin until GW-20 passes locally.

Live proof result on 2026-05-02:

- Command:
  `QUIMERA_LLM_API_KEY=dev-local-key-change-me RUN_GATEWAY1_PROOF_OF_LIFE=1 uv run python scripts/test_gateway1_proof_of_life.py --output-dir /tmp/openclaw_gateway1_smoke`
- Result: **PASSED** — G1-01 through G1-11 all true.
- Summary: `/tmp/openclaw_gateway1_smoke/gateway1_proof_of_life_9f23ce3df3f2.json`.
- Probes: Ollama OK, Qdrant OK, LiteLLM OK.
- Live runner: `local_chat` OK, `local_rag` OK.
- Forced Qdrant degradation: fallback to `local_chat` with
  `qdrant_unavailable`.
- Policy block: blocked before model call.

Observed live latencies:

| Check | Latency |
|---|---:|
| Ollama probe | 28.6 ms |
| Qdrant probe | 9.4 ms |
| LiteLLM probe | 26.1 ms |
| Agent-0 `local_chat` | 8790.5 ms |
| Agent-0 `local_rag` | 32162.8 ms |
| forced degradation | 0.03 ms |

## G2-01 Current Work

G2-01 starts Gateway-2 with a measurement-only RAG latency baseline:

```text
LocalRagPipeline
  -> RagRunTrace optional segment fields
  -> embed/search/pack/prompt/generation/total timings
  -> safe trace serialization only
```

Scope:

- Extend `RagRunTrace` with optional per-segment fields:
  `routing_ms`, `embedding_ms`, `retrieval_ms`, `context_pack_ms`,
  `prompt_build_ms`, `generation_ms`, `total_ms`, and `run_context`.
- Preserve old trace fields such as `retrieval_latency_ms`,
  `generation_latency_ms`, `prompt_latency_ms`, and `total_latency_ms`.
- Populate pipeline traces from existing `time.perf_counter()` wrappers and
  `Retriever.last_timings`.
- Keep `total_ms` as a directly measured outer timer, not a segment sum.
- Add optional Ollama metric fields, but only when already available in
  metadata. Current LiteLLM path does not expose native Ollama metrics, so
  normal traces record `ollama_metrics_available=false`.

Safety:

- No optimization.
- No prompt/top-k/model/timeout/alias/routing/fallback behavior change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, question, chunks, answer, vectors, payloads, API keys,
  Authorization headers, raw exceptions or tracebacks in trace serialization.

Deferred from G2-01:

- First optimization experiment: configurable local RAG context budget cap.

## G2-02 Current Work

G2-02 adds a rollback-safe, config-controlled context budget cap for
`local_rag`:

```text
retrieved chunks
  -> existing ContextPacker dedup/token-limit/document ordering
  -> optional whole-chunk max_context_chunks cap
  -> PromptBuilder
  -> LocalGenerator/local_rag
```

Scope:

- Add `rag.context_budget` to `config/rag_config.yaml`:
  `enabled: false`, `max_context_chunks: 3`, `mode: whole_chunks`,
  `apply_to_aliases: [local_rag]`.
- Add typed `ContextBudgetConfig` and `ContextBudgetResult`.
- Apply the cap in `ContextPacker` only, after existing packing logic.
- Preserve whole chunks, citation ids, `doc_id`, `chunk_index`, and payload
  metadata.
- Expose safe trace metadata on `RagRunTrace`:
  `context_budget_enabled`, `context_budget_applied`,
  `context_chunks_retrieved`, `context_chunks_used`,
  `context_chunks_dropped`, `context_budget_max_chunks`, and
  `context_estimated_tokens_used`.

Safety:

- Default `enabled: false` preserves existing behavior.
- Rollback is a single config change.
- No retrieval/top-k/Qdrant/model alias/prompt template/timeout change.
- No Qdrant mutation, no reindex, no `openclaw_knowledge` access.
- No prompt, chunks, answer, vectors, payloads, secrets, Authorization headers,
  raw exceptions or tracebacks in trace serialization.

Deferred:

- Token-based context budgeting.
- Full recalibration of `estimated_remote_tokens_avoided` against the final
  capped prompt.
- Mandatory live Golden Harness before/after gate.

## G2-07 Current Work

G2-07 closes Gateway-2 with an offline baseline freeze and regression gate.
This is not an optimization PR.

Delivered scope:

- Official tracked baseline artifacts under `tests/golden/baseline/`:
  `gateway2_baseline_summary.json`, `gateway2_baseline_results.jsonl`,
  `gateway2_baseline_scores.jsonl`, and
  `gateway2_regression_thresholds.yaml`.
- `scripts/compare_golden_runs.py` now supports:
  `--verify-only <summary.json>` and
  `--baseline <summary.json> --candidate <summary.json> --thresholds <yaml>`.
- Regression gate exit codes:
  `0` pass, `2` schema/sanitization, `3` citation/quality,
  `4` latency, `5` fixture/config mismatch, `6` incompatibility.
- Baseline summaries stay grouped by alias and run type:
  `cold_start`, `warm_model`, and `degraded_qdrant`.
- Generated report directories are ignored while official baseline artifacts
  remain explicitly allowed.

Safety:

- No prompt, question text, answer text, chunks, vectors, payloads, headers,
  API keys, raw exceptions, tracebacks, usernames, local paths or model weight
  paths are allowed in baseline artifacts.
- No remote providers, no live services, no Qdrant mutation, no reindexing and
  no `openclaw_knowledge` access are required for the gate.

Gateway-2 handoff:

- See `docs/GATEWAY2_BASELINE.md`.
- See `docs/sprints/GATEWAY2_SPRINT_HANDOFF.md`.
- Gateway-3 should start from the frozen Gateway-2 baseline and use the offline
  gate before accepting performance or quality regressions.

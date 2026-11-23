# DL3-PR08C — Supercartão: borboleta de puts, travas e iron condor conferidos

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `25c4ed3` (DL3-PR08B integrado) · **PR novo**, em rascunho
**Decisão que este cartão implementa:** autorização de Francisco de 22/11/2026 para a análise
de estruturas, item 1, segunda parte: "a borboleta de puts, as travas e o iron condor, com
quantidades, multiplicadores e custos explícitos".

## 0. Escopo

**Este cartão só acrescenta testes.** O módulo de resultado no vencimento (DL3-PR08A) e o da
posição montada em parte (DL3-PR08B) já calculam estas estruturas. O que falta é a prova
versionada, com valores escritos à mão, de que calculam certo. Nenhuma linha de `backend/`
muda.

O cartão também fecha as duas lacunas de teste que ficaram do DL3-PR08B: plano com
exatamente oito séries e símbolo que não é texto.

**Fora deste cartão:** estimativa antes do vencimento; calendário da B3; ligação com o motor
da boleta e com o recibo; limite de escala do `expiry_payoff` (entra no cartão que ligar o
módulo a dado externo); tabela real de custos; tela. Nenhuma dependência nova. Nenhum código
de terceiros.

**Custos.** Os valores de custo abaixo são ilustrativos. A tabela real de custos continua
pendência de Francisco no registro de decisões. A convenção é a do módulo: custo é um total
fixo em reais, descontado uma vez; o resultado por perna vem antes dos custos.

## 1. Arquivos

| Arquivo | O que muda |
|---|---|
| `tests/unit/derivatives/test_expiry_payoff.py` | G1 a G8, só acréscimo |
| `tests/unit/derivatives/test_partial_position.py` | G9, G10, H1 e H2, só acréscimo |
| `docs/specs/derivatives/fase3/DL3-PR08C.md` | cópia deste cartão |

**Não muda:** `backend/` inteiro, os testes que já existem, fixtures, `current_state.md`,
arquivos protegidos. Os testes novos importam só o que os dois arquivos já importam. Linhas
de até 100 colunas, como no resto do repositório.

## 2. Evidência do planejador

Todos os esperados do §3 foram conferidos por três caminhos independentes:

1. conta à mão e oráculo descartável do planejador;
2. o módulo que está na `main` (`25c4ed3`), por roteiro de fatos: 41 verificações, todas
   iguais ao esperado;
3. OptionLab 1.9.7, fora do repositório, na curva de resultado sem custos de G1 a G10:
   100.010 pontos entre 50 e 150, maior diferença 6,8 × 10⁻¹² (ruído de ponto flutuante do
   OptionLab).

O planejador também plantou 27 defeitos no código, um por vez. **Quatro passam pela suíte de
hoje** e caem com os testes deste cartão. São os mutantes 1 a 4 do §4.

## 3. Cenários

Multiplicador 1 e custo zero, salvo indicação. Dinheiro em `Decimal`, equilíbrio em
`Fraction`. Em todos os cenários G1 a G8, ganho e perda são limitados.

### 3.1 Resultado no vencimento (`test_expiry_payoff.py`)

**G1 — borboleta de puts.** Compra 1 put 95 a 2,00; vende 2 puts 100 a 3,50; compra 1 put
105 a 7,00.

- Entrada 2,00; equilíbrios 97 e 103; ganho máximo 3,00; perda máxima −2,00.
- Resultado em 90: −2,00; 95: −2,00; 97: 0; 100: +3,00; 103: 0; 105: −2,00; 110: −2,00.
- Por perna em 100: −2,00; +7,00; −2,00. Por perna em 90: +3,00; −13,00; +8,00.

A borboleta de puts paga no total o mesmo que a de calls. O que prova que as pernas são puts
é o resultado por perna em 90. Esse teste é obrigatório.

**G2 a G5 — as quatro travas.**

| # | Estrutura | Entrada | Equilíbrio | Ganho máx. | Perda máx. | Resultado por preço final |
|---|---|---|---|---|---|---|
| G2 | compra call 100 a 5,00; vende call 105 a 3,00 | 2,00 | 102 | 3,00 | −2,00 | 95: −2; 100: −2; 102: 0; 105: +3; 110: +3 |
| G3 | vende call 100 a 5,00; compra call 105 a 3,00 | −2,00 | 102 | 2,00 | −3,00 | 95: +2; 100: +2; 102: 0; 105: −3; 110: −3 |
| G4 | vende put 100 a 4,00; compra put 95 a 2,50 | −1,50 | `197/2` (98,5) | 1,50 | −3,50 | 90: −3,50; 95: −3,50; 100: +1,50; 105: +1,50 |
| G5 | compra put 100 a 4,00; vende put 95 a 2,50 | 1,50 | `197/2` (98,5) | 3,50 | −1,50 | 90: +3,50; 95: +3,50; 100: −1,50; 105: −1,50 |

Entrada negativa é crédito recebido.

**G6 — iron condor.** Compra 1 put 90 a 1,00; vende 1 put 95 a 2,50; vende 1 call 105 a
2,50; compra 1 call 110 a 1,00.

- Entrada −3,00; equilíbrios 92 e 108; ganho máximo 3,00; perda máxima −2,00.
- Resultado em 85: −2; 90: −2; 92: 0; 95: +3; 100: +3; 105: +3; 108: 0; 110: −2; 115: −2.
- Por perna em 100: −1,00; +2,50; +2,50; −1,00.
- Por perna em 85: +4,00; −7,50; +2,50; −1,00.
- Por perna em 115: −1,00; +2,50; −7,50; +4,00.

**G7 — iron condor com quantidade, multiplicador e custos.** O condor de G6 com 10 em cada
perna, multiplicador 100, custos 37,60.

- Entrada −3.000,00; equilíbrios `115047/1250` (92,0376) e `134953/1250` (107,9624); ganho
  máximo 2.962,40; perda máxima −2.037,60.
- Resultado em 85: −2.037,60; 90: −2.037,60; 100: +2.962,40; 110: −2.037,60; 115: −2.037,60.
- Por perna em 100, com multiplicador 100 e antes dos custos: −1.000,00; +2.500,00;
  +2.500,00; −1.000,00.

**G8 — borboleta de puts com quantidade, multiplicador e custos.** A borboleta de G1 com
3, 6 e 3, multiplicador 100, custos 9,90.

- Entrada 600,00; equilíbrios `97033/1000` (97,033) e `102967/1000` (102,967); ganho máximo
  890,10; perda máxima −609,90.
- Resultado em 95: −609,90; 100: +890,10; 105: −609,90.

### 3.2 Iron condor montado em parte (`test_partial_position.py`)

Plano: o condor de G6, com os símbolos `P90`, `P95`, `C105` e `C110`, nessa ordem. Perfil
planejado em G9 e G10: entrada −3,00; equilíbrios 92 e 108; ganho máximo 3,00; perda máxima
−2,00.

**G9 — só as duas vendas executaram.** Execuções: `P95` 1 a 2,50; `C105` 1 a 2,50.

- Posição executada: entrada −5,00; equilíbrios 90 e 110; ganho máximo 5,00; **perda
  ilimitada** (`max_loss` é `None`, `loss_unlimited` verdadeiro).
- Resultado em 0: −90; 90: 0; 100: +5; 110: 0; 120: −10.
- Pernas executadas: as duas vendas do plano, nessa ordem. Pendente: `P90` 1; `C110` 1.

É o caso que Francisco pediu para ver: o plano tem perda máxima de 2,00, e a posição
formada só pelas vendas tem perda sem limite até as compras executarem.

**G10 — só o lado das puts executou.** Execuções: `P90` 1 a 1,00; `P95` 1 a 2,50.

- Posição executada: entrada −1,50; equilíbrio `187/2` (93,5); ganho máximo 1,50; perda
  máxima −3,50; nada ilimitado.
- Resultado em 85: −3,50; 90: −3,50; 95: +1,50; 100: +1,50.
- Pendente: `C105` 1; `C110` 1.

### 3.3 Lacunas do DL3-PR08B (`test_partial_position.py`)

**H1 — plano com exatamente oito séries é aceito.** Plano: `S1` a `S8`, cada uma compra 1
call a 1,00, com strikes 101 a 108.

- Sem execução: perfil planejado com entrada 8,00; equilíbrio `209/2` (104,5); ganho
  ilimitado; perda máxima −8,00. `executed` é `None`; pendente: as oito séries, 1 cada, na
  ordem do plano.
- Com a execução `S8` 1 a 1,00: posição executada com entrada 1,00; equilíbrio 109; ganho
  ilimitado; perda máxima −1,00. Pendente: `S1` a `S7`, 1 cada.

**H2 — símbolo que não é texto é recusado.** Com `95`, `None` e `b"P90"` no lugar do
símbolo, `PlannedLeg` e `Execution` levantam `PayoffRefusal`. São seis recusas.

## 4. Mutantes obrigatórios

Um por vez. Cada um tem de derrubar ao menos um teste novo. Entre parênteses, o cenário que
derrubou o mutante no protótipo do planejador.

Para os mutantes 1 a 4, relate duas colunas: **sobrevive** aos testes da base `25c4ed3` e
**morre** na cabeça do PR. É a prova de que os testes novos eram necessários.

1. Resultado por perna devolvido em ordem invertida (G1 em 90; G6 em 85 e em 115).
2. Resultado por perna ignorando o multiplicador (G7).
3. `partial_view` recusando plano de oito séries (H1).
4. Símbolo que não é texto aceito (H2).
5. Put calculada como call (G1 por perna, G4, G5, G6).
6. Venda sem inverter a quantidade (G2, G3).
7. Custos cobrados uma vez por perna (G7, G8).
8. Custos multiplicados pelo multiplicador (G7, G8).
9. Custos ignorados no perfil (G7, G8).
10. Puts entrando na inclinação à direita do último strike (G9: a perda deixa de ser
    ilimitada).
11. Tipo da perna executada não herdado do plano (G9, G10).
12. Pendente listando série já completa (G9, G10).

## 5. Critérios de parada

Pare e relate, **sem corrigir**, se:

- algum esperado do §3 não reproduzir. Seria defeito de produção, e defeito de produção
  ganha cartão próprio;
- qualquer arquivo de `backend/` precisar mudar;
- algum teste existente precisar ser alterado ou removido;
- os testes novos precisarem de import fora dos que os dois arquivos já usam;
- algum mutante do §4 sobreviver aos testes novos, ou algum dos mutantes 1 a 4 já morrer na
  base.

## 6. Entrega

1. Um commit de testes. Não há commit vermelho: a produção já passa. A prova de força é a
   tabela de mutantes do §4.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
3. Descrição do PR: cabeça, contagens antes e depois, os 12 mutantes com as duas colunas dos
   quatro primeiros, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Confronta G1 a G10
com o oráculo próprio e com o OptionLab, fora do repositório.

## 7. Depois deste cartão

Próximo da frente: estimativa antes do vencimento conferida com o QuantLib. Depois, o
calendário da B3. PR07A3, PR07A4 e PR07B continuam atrás desta frente.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `1ceba84`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem
mutantes** nesta cabeça: o implementador rodou tudo em Linux x86_64 e em macOS. O revisor
leu o diff, conferiu as evidências pelo SHA-256 e usou o seu oráculo independente, que não
é a suíte.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 (contêiner emulado em Mac ARM64, ELF AMD64) e macOS | 11.356 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| 12 mutantes do §4, nos dois sistemas | todos detectados pelos testes novos | implementador; logs conferidos |
| Mutantes 1 a 4 na base | sobrevivem aos 66 testes dos dois módulos (dois sistemas) e aos 11.336 do portão da base (macOS) | implementador; logs conferidos |
| Manifesto de 86 evidências (`67990ba7…8b60`) e hashes dos dois relatórios | conferem | revisor |
| Diff | três arquivos, só acréscimo; `backend/` intacto; nenhum import novo; nenhuma linha de teste acima de 100 colunas | revisor |
| Cópia do cartão | SHA-256 `6f28b176…464d`, igual ao publicado | revisor |
| 80 valores escritos nos testes de G1 a G8 (perfis, resultados e pernas) contra o oráculo do planejador | sem divergência | revisor |
| G9, G10, H1 e H2 | literais iguais aos do cartão, por leitura | revisor |

Antes de publicar o cartão, o planejador já havia conferido todos os esperados no módulo
da `main` (41 verificações) e no OptionLab 1.9.7, fora do repositório.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça, a força dos testes
repousa nos mutantes do implementador, nos da skill e no protótipo que o planejador rodou
antes de publicar o cartão (27 defeitos, com os mesmos quatro sobreviventes na base).

Observações, nenhuma bloqueante:

1. **Rodada extra de integração no Mac, fora do portão do cartão.** O teste
   `test_pr09_pg_dump_restore_verify_live` encontrou o Postgres do host, gerou um `pg_dump`
   em pasta temporária e falhou no cache do `uv`. O implementador relatou ter excluído a
   cópia sem abri-la. O revisor não tem acesso à pasta temporária e não confirmou a
   exclusão. Recomendação, a decidir por Francisco: integração só no contêiner isolado.
2. **H1 não confere `executed_legs` vazio** no plano sem execução. O cartão não pedia; o
   cenário E1 do DL3-PR08B já cobre.

Nenhum código de terceiros entrou. O OptionLab 1.9.7 serviu de segunda conferência, fora
do repositório, pelo planejador, pelo implementador e pela skill.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`51be492b…e6be` e `9dbf1d16…0583`): GO, sem bloqueante e sem proposta de simplificação.

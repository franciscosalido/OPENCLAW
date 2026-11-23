# DL3-PR07A3D — Supercartão: uma só ordem para as autorizações; testes de cancelamento

**Data:** 23/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `f6a389e` (DL3-PR07A3C integrado) · **PR novo**, em rascunho
**Natureza:** correção de uma falha de desenho do planejador, achada na revisão do PR #173,
e dois testes pedidos por Francisco em 23/11/2026.

## 0. Escopo

**A falha.** O DL3-PR07A3B fez o resumo criptográfico ordenar as autorizações por série e
origem: inverter a ordem informada não muda o resumo. O DL3-PR07A3C fez o motor usar as
origens na ordem informada. Juntos: duas prévias com as mesmas autorizações em ordens
diferentes têm **o mesmo resumo e prioridades diferentes**. A decisão humana é presa ao
resumo; a prioridade que o humano viu fica de fora. Sem efeito operacional hoje (simulador
D0), mas é exatamente o que a assinatura deve impedir.

**A correção.** A ordem informada deixa de existir. A boleta guarda as autorizações
**sempre por série e depois por origem**. É essa a ordem que a prévia mostra, que o recibo
grava, que o resumo assina e que o motor usa. Fica valendo o critério de Francisco:
inverter a ordem de entrada mantém o mesmo resumo — e agora também a mesma prioridade.

**Os dois testes** (o código já está certo; decisão de Francisco de 23/11/2026):

1. A execução que chega com o cancelamento já pedido conserva a origem no recibo.
2. A ordem viva de uma boleta parada segue comprometida: a execução tardia é contabilizada
   e só o cancelamento confirmado devolve o saldo à origem.

**O que este cartão não faz.** Não muda o motor, o livro nem `digest.py`. Não muda nenhum
valor de resumo. Não trata a apresentação da montagem parcial, o esquema JSON de saída nem
boleta concluída cedendo sobra; esses têm cartões próprios.

Nenhuma dependência nova.

## 1. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/models.py` | a boleta ordena as autorizações na validação | 221 (214) |
| `tests/unit/derivatives/ticket/test_models.py` | N1; um teste muda (§3.1) | — |
| `tests/unit/derivatives/ticket/test_engine.py` | N3; dois testes mudam (§3.1) | — |
| `tests/unit/derivatives/ticket/test_sequencing.py` | N4 | — |
| `docs/specs/derivatives/fase3/DL3-PR07A3D.md` | cópia deste cartão | — |

**Não muda:** `digest.py`, `engine.py`, `sequencing.py` e os demais módulos da boleta;
`scripts/derivatives_ticket_replay.py`; `current_state.md`; arquivos protegidos. As âncoras
e os recibos das três sessões oficiais não mudam.

## 2. Regra

O campo `coverage` da versão assinada (boleta e prévia) é ordenado por (série, origem) **na
validação do modelo**, depois da conversão da série para maiúsculas. Duas boletas que
diferem só na ordem em que as autorizações foram informadas são **iguais**.

`digest.py` continua ordenando por conta própria. Fica redundante de propósito: o resumo não
depende de quem montou o objeto.

Consequência no motor, sem mudar o código dele: para cada venda, depois das compras
próprias, as origens são usadas em ordem de nome (as autorizações da série de proteção, por
origem).

## 3. Cenários

Auxiliares: os mesmos do DL3-PR07A3C. **T1 parada com sobra 4**, **boleta só de venda** e
**sobra vista por terceiro** têm o significado daquele cartão.

### 3.1 Testes existentes que mudam

Só estes três. Renomeie quando o nome deixar de dizer a verdade.

| Teste de hoje | O que passa a afirmar |
|---|---|
| `test_w2_signed_coverage_is_sorted_only_in_the_digest` | o corpo da prévia no recibo traz (A, T1, 4) antes de (A, T9, 2), qualquer que seja a ordem informada. Os resumos literais não mudam |
| `test_x6_uses_two_origins_in_preview_order` | com as autorizações informadas como (A, T2, 2) e (A, T1, 3): pedidos `T3:B:1` **3** a 1,50 (`origin` `T1`) e `T3:B:2` **2** a 1,50 (`origin` `T2`). Sobras vistas por terceiro depois: T1 = 1, T2 = 1, como hoje |
| `test_x6_interleaved_grants_follow_priority_within_each_series` | a venda de B sai com `origin` **P** (hoje Q); a de D segue com `origin` P |

### 3.2 Testes novos

**N1 — uma só ordem em todo lugar** (`test_models.py`). Prévias da boleta de referência com
`partial_exposure=Decimal("10")`.

- Autorizações (A, T9, 2) e (A, T1, 4), nas duas ordens de entrada: as duas prévias são
  **iguais**; `coverage` é ((A, T1, 4), (A, T9, 2)); resumo
  `f61d4551b8be2caec9f54774d536acf5fbc2655578555dc4843862de3e86a84e` (o de hoje).
- No recibo, o corpo dessa prévia traz
  `[{"series":"A","origin":"T1","quantity":4},{"series":"A","origin":"T9","quantity":2}]`; a
  leitura do recibo devolve a mesma prévia e o recibo verifica.
- Autorizações (B, T1, 1) e (A, T9, 2): `coverage` é ((A, T9, 2), (B, T1, 1)); resumo
  `364d378948c544bc1afbe75e4f6b7d50b3c9f7e7fd86386f919adfc9971a601e` (o de hoje).
- Séries informadas em minúsculas, `b` e depois `a`: as séries ficam `A`, `B`, nessa ordem.

**N3 — execução durante o cancelamento conserva a origem** (`test_engine.py`). T1 parada com
sobra 4. T2 só de venda de 4 B confirmada em `at(5)`.

1. Cancela `T2:B:1` em 5: T2 em `WORKING`, ordem em `CANCEL_REQUESTED`, sobra vista por
   terceiro = 0.
2. B com demanda a 1,50, tamanho 1, em 6. Há uma só execução no recibo da T2: `origin`
   `T1`, `quantity` 1, estado `CANCEL_REQUESTED`.
3. T2 em `STOPPED`, `T2:B:1` em `CANCELLED`, sobra vista por terceiro = **3**.
4. Sequência do recibo da T2 depois da prévia: `confirm start venue_live request_cancel
   venue_partial venue_cancelled stop`. O registro do cancelamento não tem `origin`.

**N4 — ordem viva de boleta parada segue comprometida** (`test_sequencing.py`). T1 compra
10, vende 6 e é parada. T2 só de venda de 4 B é admitida e reserva 4 com origem T1.

| Passo | Sobra da T1 vista por terceiro | T2 com origem T1 |
|---|---|---|
| `close("sim", "T2")` | 0 | 0 |
| 1 unidade da ordem da T2 executa | 0 | 0 |
| tentativa de liberar 2 (o saldo vivo é 3) | recusa; continua 0 | 0 |
| as 3 restantes são liberadas | 3 | 0 |

## 4. Evidência do planejador

- **Protótipo descartável** sobre o `main` `f6a389e`: `models.py` com 219 linhas (5 a mais).
  Tipagem estrita limpa.
- **Portão completo no protótipo** (sem `tests/integration`): só os três testes do §3.1
  mudam de resultado; os outros 11.453 passam, com 16 pulados. As âncoras seguem passando.
- **Cenários do §3.2:** passam no protótipo. No `main` de hoje, N1 falha; N3 e N4 passam.
- **Mutantes:** cinco defeitos plantados, um por vez, todos detectados (§5).

## 5. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste.

1. A boleta guarda a ordem informada (N1 e o X6 alterado).
2. A ordenação usa só a origem (N1).
3. A ordenação sai invertida (N1 e o X6 alterado).
4. A execução que chega com o cancelamento pedido sai sem `origin` (N3).
5. Parar a boleta libera a ordem viva dela (N4).

## 6. Critérios de parada

Pare e relate se:

- algum esperado do §3 não reproduzir, em especial os dois resumos do N1;
- outro teste, além dos três do §3.1, mudar de resultado;
- alguma âncora de sessão mudar;
- for preciso mudar arquivo de produção além de `models.py`, ou o teto estourar;
- N3 ou N4 falharem no `main` (seria defeito já integrado).

## 7. Entrega

1. Commit vermelho com os testes; depois o verde. N3 e N4 nascem verdes: declare isso.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas de `models.py`, os cinco mutantes, os dois
   resumos do N1, as âncoras e os recibos oficiais comparados byte a byte, desvios.
4. Copie este cartão para o caminho do §1. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 8. Depois deste cartão

DL3-PR07A4 (DP-13: relato contraditório e evento externo) e DL3-PR07B (DP-02 e DP-03:
zeragem e borboleta no motor). Atrás deles, pelas decisões de Francisco de 23/11/2026:
apresentação da montagem parcial; repetir, completar e ajustar estruturas, com boleta
concluída cedendo só o que o livro comprovar livre. O esquema JSON de saída da prévia é
corrigido antes do primeiro consumidor externo.

## Revisão adversarial (Claude) — GO na primeira rodada, cabeça `a2ffa68`

Pela regra de processo de Francisco, o revisor **não executou a suíte, a tipagem nem os
mutantes** desta cabeça. Leu o diff, conferiu as evidências pelo SHA-256 e rodou os cenários
do seu protótipo, escrito antes do cartão.

| Verificação | Resultado | Quem |
|---|---|---|
| Suíte sem integração, Linux x86_64 e macOS | 11.459 aprovados, 16 pulados, 261 subtestes nos dois | implementador; logs conferidos |
| mypy estrito e Pyright, nos dois sistemas | 0 erros | implementador; logs conferidos |
| Commit vermelho | N1 e os três testes alterados falham; N3 e N4 passam na base | implementador; logs conferidos |
| Testes antigos contra a cabeça | só o W2 e os dois X6 mudam de resultado | implementador; log conferido |
| 5 mutantes do §5 e 1 adicional, nos dois sistemas | todos detectados | implementador; logs conferidos |
| Integração | só no contêiner Linux isolado: 31 aprovados, 206 pulados | implementador; evidências conferidas |
| Manifesto de 88 evidências (`6a9a9d78…f91a`) e hashes dos dois relatórios | conferem | revisor (27 arquivos) e Francisco (os 88, no Mac) |
| Diff | cinco arquivos; em produção, só `models.py`, com 220 linhas (teto 221) | revisor |
| Âncoras e recibos das sessões | os quatro recibos e os três resumos iguais byte a byte entre base e cabeça | implementador; log conferido |
| Cópia do cartão | SHA-256 `34609609…7292`, igual ao publicado | revisor |
| 4 cenários do protótipo do planejador e os 15 do DL3-PR07A3C ainda válidos | todos aprovados | revisor |

A mudança de produção é equivalente à do protótipo do planejador. O implementador acrescentou
um teste que o cartão não pediu e que vale: a ordenação também é conferida quando a prévia é
lida direto de JSON, e não só quando nasce de uma boleta.

Limite desta revisão: sem mutantes próprios do revisor nesta cabeça.

Observação, não bloqueante, que o cartão do planejador deixou de prever:

1. **Recibo emitido entre o PR #173 e este, com autorizações fora da nova ordem, não é mais
   lido.** O leitor confere se o corpo gravado é o que o modelo atual produziria; com a
   ordenação na validação, um corpo gravado na ordem informada é recusado («conteúdo da
   prévia incompleto ou não canônico»), mesmo com resumo e âncora corretos. O implementador
   mediu: 49 de 65 entradas sintéticas. Não há recibo real nessa condição: o formato durou
   horas, só em simulador, e as três sessões oficiais não usam autorização. Fica a lição
   para o que vier com dados reais: mudança que altere o corpo canônico da prévia precisa de
   versão de formato ou de leitor da revisão emissora.

Relatórios da skill lidos depois de formado o parecer, com SHA-256 conferidos
(`0cb2047e…4b04` e `791ba81f…5f80`): sem bloqueante.

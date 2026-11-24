# DL3-PR07F1 — Supercartão: fecho da Fase 3 estendida (guarda do pydantic e recibo da sessão como cópia)

**Data:** 24/11/2026 · **Autor:** Claude (planejador e revisor) · **Implementa:** Codex
**Base:** `main` = `899500b` (DL3-PR07E1 integrado)
**PR novo**, em rascunho. Cartão pequeno, de correção.
**Origem:**

- Risco apontado na revisão do DL3-PR07E1 e **reproduzido pelo planejador** (§0).
- Pendência registrada na revisão do DL3-PR07A6: o recibo de cada boleta sai da sessão como
  objeto interno.
- Francisco, 24/11/2026: fechar a Fase 3 estendida.

## 0. Escopo

**O que acontece hoje.** Fatos conferidos no `main`:

- O DL3-PR07E1 passou a omitir a cobertura vazia com `Field(exclude_if=...)`, recurso do
  pydantic 2.12. O `uv.lock` trava 2.13.3. O `pyproject.toml` aceita a partir de 2.10.
- **Com pydantic 2.11.7 o parâmetro é ignorado em silêncio.** O planejador instalou essa
  versão num ambiente à parte e rodou a sessão oficial `calmo` no `main`: a prévia gravada
  ganha `"coverage": []` e a âncora da T1 sai `ddac9c65…` em vez de `1d50bba6…`. Não há
  erro, aviso nem recusa. O resumo criptográfico da autorização não muda, porque não
  depende desse caminho; o que muda é o corpo gravado no recibo e toda a cadeia.
- É defeito introduzido pelo desenho do cartão DL3-PR07E1, do planejador.
- `ReplaySession.receipt(ticket)` devolve o `Receipt` interno, que tem `append` público.
  Quem consulta pode acrescentar evento ao recibo de uma boleta. O registro de fatos já sai
  como cópia desde o DL3-PR07A6.

**O que este cartão entrega.**

1. **Guarda na importação.** O módulo da boleta recusa pydantic anterior ao 2.12, com
   mensagem que diz o porquê. Deixa de existir a falha silenciosa.
2. **Recibo como cópia.** `ReplaySession.receipt` devolve uma foto independente.

**O que este cartão não faz.**

- **Não altera `pyproject.toml` nem `uv.lock`.** São arquivos protegidos. Subir o piso
  declarado para 2.12 é decisão e commit de Francisco; a guarda vale com ou sem isso.
- Não muda formato, âncora, esquema, motor, livro nem regra de negócio.
- Não troca o mecanismo de omissão da cobertura.

Nenhuma dependência nova.

## 1. Referência externa

Este cartão não tem matéria de FIX nem de OIC: é integridade de dependência e de
encapsulamento. A única fonte externa é o comportamento do próprio pydantic, **observado
por execução** nas versões 2.11.7 e 2.13.3, não lido em documentação. **Não foi verificado
em que versão exata o parâmetro `exclude_if` entrou.** O corte em 2.12 é o que o planejador
tinha de memória; o observado é só que 2.11.7 o ignora e 2.13.3 o honra. Se a nota de
versão do pydantic disser outra coisa, pare e relate.

## 2. Arquivos e tetos

| Arquivo | O que muda | Teto (hoje) |
|---|---|---|
| `backend/derivatives/ticket/models.py` | `require_pydantic` e a chamada na importação | 230 (217) |
| `backend/derivatives/ticket/session.py` | `receipt` devolve cópia | 181 (181) |
| `tests/unit/derivatives/ticket/test_models.py` | G1 a G3 | — |
| `tests/unit/derivatives/ticket/test_session.py` | G4; um esperado atualizado | — |
| `docs/specs/derivatives/fase3/DL3-PR07F1.md` | cópia deste cartão | — |

**Não muda:** os demais módulos, o script, roteiros e fitas, o esquema versionado,
`current_state.md`, arquivos protegidos. Linhas novas com até 100 colunas.

**Um teste existente muda, e só ele:** `test_n1_ticket_id_unique_across_accounts` compara
o recibo por identidade (`is`). Passa a comparar os eventos. A intenção do teste fica a
mesma: a segunda abertura não toma o recibo da primeira.

As quatro âncoras e os recibos oficiais não mudam.

## 3. Regra

**`require_pydantic(version: str) -> None`**, pública, em `models.py`:

- compara os dois primeiros componentes da versão **como números**;
- abaixo de (2, 12): `ImportError` com a mensagem
  **«pydantic 2.12 ou mais novo é exigido pela prévia da boleta»**;
- caso contrário, não faz nada.

O módulo chama `require_pydantic(VERSION)` na importação, com o `VERSION` do pydantic,
antes de definir os modelos.

**`ReplaySession.receipt(ticket)`** devolve uma cópia independente do recibo da boleta,
como `facts` já faz. O motor continua escrevendo no recibo interno.

## 4. Cenários

**G1 — versões recusadas.** `require_pydantic` com `2.11.7`, `2.10.0`, `2.9`, `1.10.13` e
`2.11.99`: `ImportError` com a mensagem do §3.

**G2 — versões aceitas.** Com `2.12.0`, `2.13.3`, `2.100.0`, `3.0.0` e `2.12.0b1`: devolve
`None`. O `2.100.0` prova que a comparação é numérica.

**G3 — a guarda roda na importação.** Em processo separado, com `pydantic.VERSION`
trocado antes de importar o módulo:

| `VERSION` | Esperado |
|---|---|
| `2.11.7` | o processo falha; a saída de erro traz `ImportError: pydantic 2.12 ou mais novo é exigido pela prévia da boleta` |
| `2.12.0` | o processo termina com código 0 |

No processo do teste, a boleta do roteiro `calmo` não traz `coverage` em
`model_dump(mode="json")`.

Use processo separado. Recarregar o módulo dentro do processo de teste recria as classes e
quebra os outros testes; o protótipo do planejador caiu nisso.

**G4 — o recibo da sessão é cópia.** Sessão `calmo` até o evento 2, T1 aberta. Acrescentar
um evento à cópia devolvida por `receipt("T1")`:

- a cópia fica com um evento a mais;
- `receipt("T1")` de novo devolve os eventos de antes;
- duas chamadas devolvem objetos diferentes;
- `recibo_eventos` do resumo é a contagem de antes;
- `engine("T1")` continua sendo o mesmo objeto.

## 5. Evidência do planejador

- **Defeito reproduzido.** Ambiente à parte com pydantic 2.11.7, `main` `899500b`: a sessão
  `calmo` conclui sem erro e a âncora da T1 é `ddac9c65…`. Com 2.13.3 é `1d50bba6…`.
- **Com o protótipo**, no mesmo ambiente 2.11.7, a importação falha com a mensagem do §3.
- **Protótipo descartável:** `models.py` com 227 linhas (10 a mais), `session.py` com 181
  (igual). `mypy --strict` limpo em `backend/`; `pyright` limpo no pacote da boleta.
- **Portão completo no protótipo** (sem `tests/integration`): 11.635 aprovados e 2
  reprovados. Um é o teste do §2, antes de atualizado. O outro,
  `test_probes_run_concurrently_not_sequentially`, é de outro módulo e mede tempo; rodado
  sozinho, passa com e sem o protótipo. O planejador o trata como instabilidade do seu
  ambiente, **sem ter provado a causa**.
- **Cenários:** G1 a G4 passam no protótipo. No `main` todos falham.
- **Mutantes:** 6 defeitos plantados, um por vez, todos detectados (§6).

## 6. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. A guarda não roda na importação (G3).
2. A guarda aceita 2.11 (G1, G3).
3. A guarda recusa 2.12 (G2, G3).
4. A guarda compara texto, não número (G1, G2).
5. A guarda só olha a versão maior (G1, G3).
6. O recibo da sessão volta a ser o interno (G4).

## 7. Critérios de parada

Pare e relate se:

- algum esperado do §4 não reproduzir;
- qualquer teste existente mudar de resultado, fora o do §2;
- `test_probes_run_concurrently_not_sequentially` falhar no portão do Mac ou do Linux
  (aí não é instabilidade do ambiente do planejador);
- alguma âncora ou recibo oficial mudar;
- for preciso tocar em arquivo protegido ou em arquivo de produção fora do §2.

## 8. Entrega

1. Commit vermelho com os testes; depois o verde. Envie o vermelho ao GitHub antes do
   verde.
2. Portão completo em clone limpo no Mac e portão Linux x86_64 via MCP/Docker na cabeça
   candidata, com cabeça, arquitetura, imagem, comandos, log e manifesto para o revisor.
   `tests/integration` só no contêiner isolado, nunca no Mac com banco vivo.
3. Descrição do PR: cabeça, contagens, linhas dos dois arquivos, os 6 mutantes, o teste
   atualizado, a versão do pydantic usada, as âncoras comparadas com a base, desvios.
4. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`.
5. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.
6. **Adendo a este cartão só entra na cópia versionada com a autorização de Francisco
   colada na descrição do PR**, com data. Nos dois adendos do DL3-PR07E1 o texto dizia
   «autorizado por Francisco» sem que o revisor tivesse como conferir.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os cenários do
seu protótipo contra os módulos entregues.

## 9. Depois deste cartão

A Fase 3 estendida fica encerrada. Não há cartão seguinte na fila. O que existe são frentes
novas, e cada uma só abre com decisão de Francisco:

- repetir, completar e ajustar estruturas;
- histórico persistente, com a conferência da foto nova;
- foto com quantidade por par;
- limite de escala; modalidade B de garantia;
- esquema do resumo, quando houver consumidor.

Decisão separada, fora de cartão: subir o piso do pydantic para 2.12 no `pyproject.toml`.

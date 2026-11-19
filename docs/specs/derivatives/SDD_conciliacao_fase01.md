# Conciliação local da Fase 01

Candidata sobre a pilha Claude `6892c82`, em `review/fase01-claude-dots`.
A referência Dots é o snapshot local `847eb9c`. Permanecem os critérios
CS1–11 do DL-PR07, o cliente Market com orçamento e Retry-After, o schema
symbol/due_date e a captura sintética BOVA11 de 100 opções do DL-PR06.

## Contrato de aceite definido antes da implementação

- Saúde e tool produtiva declaram A. Uma chamada produtiva com os dois
  campos do schema devolve LIVE_NOT_ACTIVATED antes da validação de domínio
  ou de qualquer leitura. Injeção de C ou troca conjunta de carimbo e
  propósito não habilita projeção.
- Em streamable-http, Host local e Origin correspondente são verificados
  antes do corpo. O preflight limita o POST a 64 KiB, valida envelopes,
  requisições e notificações e impede eco de entradas inválidas pelo SDK.
- A demo aceita apenas a captura sintética versionada. O manifesto tem
  SHA-256 fixado no código. Os bytes consumidos devem corresponder aos
  hashes do manifesto. Caminho externo é recusado antes da leitura.
- HttpTransport só exercita o contrato por MockTransport explícito e
  credencial simulada injetada. Sem mock, a recusa antecede credencial e I/O.
- RED de contrato primeiro. Depois, regressão integral do Lab e arquitetura,
  mypy strict no backend e revisão do diff no clone dedicado. A homologação
  do provedor depende de outra fase.

RED em 6892c82 no Mac: cinco falhas comportamentais (projeção com dois
campos alterados, C injetado, tentativa de leitura externa interceptada,
eco de data e consulta à credencial interceptada). Três casos ASGI
adicionais falharam pela ausência de middleware no entrypoint.

## Resultado local em 2026-11-19

A tool produtiva preserva o envelope e o schema Claude. A projeção direta
recusa inclusive um objeto com propósito efetivo de produção. Para a demo,
o adaptador abre componentes relativos à raiz do repositório sem seguir
links simbólicos, confere o SHA-256 do manifesto e dos quatro arquivos e
serve os mesmos bytes verificados. Os testes substituem cada entrada por
outra da própria fixture e exigem recusa sem dados.

O teste ASGI exercita inicialização MCP nas portas 8814 e 9321, headers
ausentes, externos e duplicados, POST acima de 64 KiB, request e notification
inválidos, leitura de prontidão e chamada da demo. Canários sintéticos cobrem
respostas e logs em DEBUG. No cliente em memória o SDK consulta o cache de
tools antes do middleware FastMCP. A guarda usa o dispatcher da instância
(`_mcp_server.request_handlers`). Esse ponto requer revalidação ao atualizar
o SDK.

O cliente recusa números de mercado não finitos e subjacentes divergentes.
O teste de calendário documental de 2021 usava o spot de PETR4 para PETR3.
Passou a injetar um spot sintético PETR3, com as mesmas asserções de
calendário e de recusa de precificação americana. Para 429 e 503, um
Retry-After maior que o intervalo representável mantém o bloqueio até o
limite de datetime. Uma segunda tentativa durante o cooldown permanece local.

| Validação no Mac arm64, Python 3.12.13 | Resultado |
|---|---|
| `QUIMERA_DERIV_FORBID_NETWORK=1 python -B -m pytest -q -p no:cacheprovider tests/unit/derivatives tests/architecture` | 5.915 aprovados |
| `python -B -m mypy --strict --cache-dir=/private/tmp/quimera-recon-mypy backend` | 155 arquivos, zero erros |
| `git diff --check` e comparação das fixtures com 6892c82 | Limpos |

O executável foi `/Users/fas/projetos/OPENCLAW/.venv/bin/python`. As
evidências históricas CS1–11 permanecem nos SDD originais. Gate global,
pyright e benchmark nativo dedicado não foram repetidos neste clone. O
BACKLOG e a memória do snapshot Dots registram o bundle OKF do Lab como
pendente. A candidata aguarda revisão independente.


## Gate final de Dots — código `17bc0c3`

Em clones descartáveis equivalentes a `17bc0c3` + PR #130 `95a043b` +
patch de portabilidade `2c2583cd…` (sem JSON ignorado):

| Ambiente | Python | Pytest sem integração | Mypy strict | Pyright |
|---|---|---|---|---|
| macOS arm64 | 3.12.13 | 8.052 passaram, 15 pulados, 0 falhas | 0 erros / 155 arquivos | 0 erros |
| Linux aarch64 | 3.12.13 | 8.052 passaram, 15 pulados, 0 falhas | 0 erros / 155 arquivos | 0 erros |

Smoke separado usou o FastMCP por HTTP real em 127.0.0.1:8814 dentro de
um contêiner sem rede externa. Tool produtiva bloqueada em prod e test;
demo não registrada em prod; BOVA11 synthetic/test retornou 100 linhas em
test; Host externo recebeu 403. Os processos foram terminados.

CS10: protocolo PR06 nativo em macOS arm64, 30 execuções, 100 opções
europeias precificadas; p50 24,25 ms, p95 29,61 ms, meta p95 <2.000 ms
atendida. É um cenário sintético, não SLA live. Na base Claude `6892c82`
o mesmo Mac mediu p95 28,22 ms; o gate amplo da base registrou 8.028
aprovados. A comparação não é benchmark controlado de regressão.

A documentação posterior ao código não altera a árvore executável.
A candidata única é `review/fase01-claude-dots`. Revisão Claude e
integração owner continuam pendentes; B/C e CLI opcional ficam fora.


## Revisao Claude do delta `6892c82..c1cd172` (2026-11-19)

Revisado em clone isolado, Linux aarch64, Python 3.12.16, `uv.lock`. O gate
da candidata `c1cd172` foi reproduzido antes de qualquer mudanca: 8.052
aprovados, 15 pulados, 0 falhas; mypy strict 0 (155 arquivos); pyright 0;
digest bit a bit de precos, gregas e IVs inalterado.

**Aceito sem mudanca**

- `LoopbackHeaders`: verificacao de `Host` e `Origin` antes do corpo. Era a
  lacuna real da pilha Claude (DNS rebinding contra servidor local). Sonda
  HTTP real: `Host` externo, de rebinding, sem porta, com ponto final ou em
  outra caixa -> 403; `Origin` externo, `null` ou `https` -> 403; corpo
  acima de 64 KiB (com e sem `Content-Length`) -> 413.
- `HttpTransport` restrito a `MockTransport` + `dict` explicitos e
  `trust_env=False`: no estado A nao existe caminho de rede real.
- Excecoes publicas levantadas **fora** do `except`: o `from None` da pilha
  Claude suprimia a exibicao, mas `__context__` ainda retinha a requisicao
  `httpx` (com o header do token) e o erro do pydantic (com o payload).
- `parse_retry_after`: `isdigit()` sem `isascii()` aceitava digitos Unicode
  que `float()` rejeita, e `Retry-After` enorme estourava `timedelta`. Eram
  dois defeitos da pilha Claude; ambos corrigidos por Dots.
- Tool produtiva constante (`LIVE_NOT_ACTIVATED`) e `production_view` que
  sempre recusa: mais estrito que o caminho "ativavel" da pilha Claude.
- Demo presa a captura versionada com SHA-256 do manifesto fixado.

**Corrigido nesta revisao**

1. **Chamada rejeitada derrubava a sessao do agente.** Uma `tools/call` bem
   formada mas fora do contrato (argumento a mais, tipo errado, tool
   inexistente) recebia HTTP 400. O cliente MCP trata 400 como falha de
   transporte: a sessao morre e as chamadas seguintes falham ("Client is not
   connected"). Reproduzido com cliente FastMCP real. Agora a chamada e
   trocada por uma chamada neutra e o dispatcher guardado responde
   `INVALID_TOOL_CALL` em HTTP 200, sem eco. Protocolo malformado continua
   400. A demo desabilitada ficou indistinguivel de tool inexistente.
2. **Servidor consultava o PyPI ao subir.** O banner do FastMCP verifica
   atualizacoes por HTTP. `show_banner=False` remove a chamada (o conteiner
   sem rede de Dots nao a exibia; num Mac com rede ela acontece).
3. **`except Exception` sem registro na demo.** Passou a capturar excecoes
   nomeadas e a registrar apenas o nome da classe.
4. **Simbolo fora da fixture caia como falha generica.** `DemoFixture`
   levantava `KeyError`, nao `FileNotFoundError`; agora devolve
   `DEMO_SYMBOL_NOT_IN_FIXTURE`, sem ecoar o simbolo.
5. **Falha de configuracao encerrava com codigo 2 em silencio.** Agora
   registra os nomes das variaveis a conferir, nunca os valores.
6. **`id` JSON-RPC refletido sem limite** na resposta 400 (ate 64 KiB).
   Agora so ate 64 caracteres; acima disso, `null`.
7. **Guarda e schema podiam divergir.** `_valid_call` repete os nomes e
   argumentos das tools; um teste novo compara a guarda com as tools
   registradas nos dois contextos.

**Mantido, com ressalva registrada no BACKLOG**

- A guarda usa `server._mcp_server.request_handlers`, atributo privado do
  FastMCP 3.4.0. Falha fechada se o atributo sumir (o servidor nao sobe);
  se o SDK deixar de consultar o dicionario, a validacao propria do FastMCP
  ainda recusa argumentos fora do schema, e os testes de eco acusam.
- `live_service`, `production_view`, `root` e `fixture_dir` viraram
  parametros sem efeito pratico; ficam ate a fase B redesenhar a ativacao.
- `demo_fixture.py` usa `O_NOFOLLOW`/`dir_fd` (POSIX) e mora em `oplab/`.
- `Retry-After` gigante bloqueia o orcamento ate o limite de `datetime`
  (reinicio do processo desfaz). Teto menor e decisao de homologacao.
- Recusa de `parent_symbol` divergente e hipotese ate ver dado real.

Resultado apos as correcoes: `pytest tests/ --ignore=tests/integration`
8.057 aprovados, 15 pulados, 0 falhas; Lab + arquitetura em 3 ordens; mypy
strict 0 (155 arquivos); pyright 0. Producao do delta de conciliacao com a
revisao: 300 adicoes sobre `6892c82` (<= 400). Sonda com cliente FastMCP
real em loopback, contextos `test` e `prod`: tres chamadas rejeitadas
seguidas e a sessao segue viva.

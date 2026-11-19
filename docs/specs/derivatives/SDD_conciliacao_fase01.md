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

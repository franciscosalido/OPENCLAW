# DL2B-PR04 — Ponte americana na chain de demonstração offline

Candidato local a revisão por Claude, estado A. Base do PR03 conferida nas duas
branches em `4c76d146155a2eaccea5f776b1d2f1a56cdf1f05`. O empilhamento é apenas
local e não satisfaz o rito do ADR-0026. Revisão independente permanece pendente.

## Correção após revisão adversarial

A correção candidata mantém o ADR-0026 e o critério 6 do SDD sem alteração.
A demo inverte bid, mid e ask pelo mesmo par CRR N/N+1 usado no preço de modelo.
A raiz de composição lê `config/american_iv.yaml` só no opt-in. Se o arquivo
estiver ausente ou inválido, a demo mista recusa; a padrão não depende dele. O esquema
`quimera-derivatives-chain-v1` conserva os nomes e valores das hipóteses gerais.
Nas linhas americanas, apenas o carry do registro é usado; as duas hipóteses
gerais da Fase 1 não acompanham o resultado da linha.

Os testes preservam as 100 linhas europeias, confrontam cada lado da call
sintética com o preço do mesmo par, cobrem fator 1 versus 1000 com lote 37 e
exigem recusa de carimbo REPLAY/TEST na própria projeção. Os números e gates
abaixo são o registro histórico da versão anterior, não evidência deste delta.

## Autoridade e escopo pré-RED

Leitura dos ADRs 0025 (incluindo Adendo 1) e 0026, SDD_FASE2B e cartões PR01,
01A, 02 e 03. Aplicam-se os critérios 5, 7, 8, 9 e 10 e o contrato de IV por
observação do PR02. Preço CRR médio de N/N+1, carry resolvido exclusivamente pelo
registro da série, D1 somente em CALL com q=0 resolvido e r>0. A cotação de
entrada da inversão é por unidade. Gregas americanas continuam ausentes.

- A CLI requer `--provider offline_fixture --american-demo --steps N
  --series-registry synthetic-v1`. N é inteiro entre 1 e 4999. A demo MCP aceita
  a mesma seleção ao construir o servidor de teste. A chamada v1 continua
  recebendo apenas símbolo e vencimento. Opções parciais ou inconsistentes são
  recusadas. O provedor padrão continua respondendo LIVE_NOT_ACTIVATED, rc 3.
- O registro e os contratos adicionais pertencem a uma fixture identificada como
  sintética, com bytes fixados, sem caminho livre. Só a composição da demo
  verificada chega à ponte. O serviço comum, a tool produtiva, a configuração
  permanente e o binomial original conservam seus contratos.
- Preservar ordem, cardinalidade, preço, IV e payload das europeias. Manter toda
  americana. Resolver a evidência na data civil da captura na B3. Recusar cotação
  desatualizada, fonte temporal ausente, relógios divergentes, spot/taxa ausentes
  ou série incompatível. Usar a IV do mid para o preço. Bid e ask observados são
  invertidos independentemente mesmo se faltar mid. Uma recusa tem motivo e preço
  nulo. Nenhum lado recebe sigma substituto. A demo usa o contrato v1 existente.
- Manter caps da fixture, transporte, despacho e cálculo, propósito test e
  procedência synthetic. Configuração ou entrada adulterada não habilita mercado.
  Autorizar apenas as arestas necessárias entre arquivos exatos. Testar intruso
  direto, transitivo via config e import dinâmico relativo em função.
- D2 (destino e passos padrão), D3 (evidência real e validade) e D4 (NumPy)
  seguem com Francisco. Excluídos produção externa, rede, OpLab real, ordens,
  agentes, dependências, novos modelos/schemas e entregas 5–11.

## Arquivos e validação

Mudanças previstas na composição de demo da CLI/MCP e em um módulo de serviço
offline, na leitura de fixture verificada e na adaptação dos diagnósticos da
ponte. Fixture suplementar em tests/fixtures, testes comportamentais e guardas
em tests/unit/derivatives e tests/architecture. Limite de 400 linhas adicionadas
de produção no diff contra o PR03, contando brancos e comentários.

Primeiro commit só deste cartão. Em seguida, RED comportamental com regressão
mínima independente, GREEN e refactor com justificativa se necessário. Comparar
stdout da demo com ff0c1be por cmp no mesmo SO e verificar o rc do provedor
padrão. Executar pytest tests/ --ignore=tests/integration --timeout=120,
mypy backend/ --strict, Pyright de produção, dos testes alterados e global,
git diff --check e auditoria de arquivos protegidos. Comparar diagnósticos
globais com o PR03. Repetir em Linux arm64 cacheado sem pull ou rede. Provas
locais em reports/dl2b-pr04/, handoff em curren_status.md e memória somente no
bloco Marco 2B de current_state.md.

## Registro do autor para revisão local

A base é `4c76d146155a2eaccea5f776b1d2f1a56cdf1f05`. O cartão pré-RED
permanece em `ff14c64`. O commit `0aad8d2` reproduziu sete falhas de
comportamento e uma aprovação em macOS. Para repeti-lo a partir deste worktree,
`reports/dl2b-pr04/support/reproduce-red` extrai os arquivos daquele commit
em diretório temporário e executa apenas `test_offline_american_demo.py`.
O log da primeira execução e o da reprodução estão em `reports/dl2b-pr04/mac/`.

| Commit | Alteração e prova |
|---|---|
| `7e7c3ff` | GREEN do RED original. Foram aproveitados o despacho da CLI/MCP e a leitura da fixture mista do diff interrompido. Os dois hashes conferiram. A ligação da ponte e as guardas passaram em 96 testes focais. |
| `653ae2c` | A composição abre uma única fixture verificada para opções, spot, taxa, status, relógio e registro. A entrada do serviço de demo exige a seleção completa. O registro reexporta a exceção de carry que seu resolvedor pode levantar. Isso dispensa autorizar a demo a importar o módulo de carry. |
| `aedc1e5` | A chamada Python direta da demo deixava escapar exceção para símbolo nulo e diretório de tipo inválido. Duas falhas reproduzidas em `mac/red-forged.log`; a fronteira agora devolve o erro constante correspondente. |
| `848f030` | A suíte completa expôs uma asserção que enumerava as opções da CLI da Fase 1. A lista exata passou a incluir as três flags deste cartão. Os testes de flags e caminhos proibidos continuam no gate. |

**Procedimento e alcance.** A autorização de imports segue as arestas entre
`cli.py`, `mcp/derivatives_server.py`, `service/demo_chain.py` e
`service/american_demo.py`. A última aresta só é percorrida na seleção mista.
A composição de preço importa a ponte e o registro. A ponte continua sendo o
único importador direto do binomial. Os testes exercitam intrusos, inclusive
um intermediário em `config/` e import relativo dentro de função.
`ChainService`, o binomial e a tool de mercado conservaram sua implementação.

A demo deriva a data civil da captura na B3, verifica idade e sincronismo e
usa o fator de cotação dos termos para inverter o preço por unidade. A IV do
mid alimenta o preço CRR. A falta de bid ou ask preserva o outro lado, com
preço da linha nulo. A projeção continua v1. Internamente, o diagnóstico
registra iterações e expansões informadas pela inversão, o modelo de IV
ou o motivo do PR02. Na demo mista, as duas hipóteses gerais da Fase 1
sobre proventos têm identificação europeia. D2, D3 e D4 seguem com Francisco.

### Evidência de comportamento

A comparação usa a CLI real em cada plataforma e o mesmo Python 3.12.13.

```sh
python -m backend.derivatives.cli chain BOVA11 2026-11-19
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture
python -m backend.derivatives.cli chain BOVA11 2026-11-19 --provider offline_fixture \
  --american-demo --steps 32 --series-registry synthetic-v1
```

A primeira chamada devolveu `LIVE_NOT_ACTIVATED`, rc 3. A segunda teve stdout
idêntico por `cmp` ao de `ff0c1be` no mesmo SO. Na terceira, as 100 europeias
coincidiram em todos os campos e na ordem. As três observações americanas
permaneceram nas 103 linhas, inclusive as duas com o mesmo símbolo.

| Série sintética | Strike | Preço do modelo | IV bid / mid / ask (fração anual) ou motivo |
|---|---:|---:|---|
| SYNAC150 | 150 | 2,999448400484919 | 0,2074413 / 0,2159273 / 0,2244080 |
| SYNABS151 | 151 | nulo | `registry:missing_series_record` |
| SYNAC150 | 152 | nulo | `registry:series_contract_mismatch` |

Os três resultados têm gregas nulas. A CALL admitida usa D1 para a IV e as
árvores 32/33 para o preço. No Mac, as escolhas explícitas de 1 e 4.999
passos também preservaram as 103 linhas e produziram preço para a CALL de strike 150
(`mac/step-limits.log`). O MCP em memória expôs apenas símbolo e vencimento
na assinatura das duas tools de chain. A resposta da demo coincidiu com a CLI.

### Gates do candidato

Código e testes em `848f0309e26980c45f647be704c70654379a2abb`. A auditoria
contra o PR03 contou 223 linhas adicionadas de produção, incluindo brancos e
comentários. Os sete módulos alterados pertencem a `backend/derivatives/`.
Os arquivos protegidos, dependências e lock coincidiram com a base.

| Gate | macOS arm64 | Linux arm64 |
|---|---|---|
| Pytest completo, `--ignore=tests/integration --timeout=120` | 9.492 passaram, 16 pulados, 261 subtestes (43,67 s) | 9.492 passaram, 16 pulados, 261 subtestes (52,45 s) |
| `python -m mypy backend/ --strict` | 0 erros, 163 arquivos | 0 erros, 163 arquivos |
| Pyright de produção e Pyright nos cinco arquivos de testes/guardas alterados | 0 erros e avisos | 0 erros e avisos |
| Pyright global, base e candidato | rc 1 em ambos, 131 erros, logs idênticos | rc 1 em ambos, 131 erros, logs idênticos |
| Stdout da demo padrão contra `ff0c1be` | `cmp` 0, 67.097 bytes | `cmp` 0, 67.101 bytes |
| `git diff --check`, escopo, memória e estado do checkout | rc 0 | rc 0 |

**Pendência de aceite.** O gate de Pyright global continua vermelho nos sete
arquivos de teste herdados. Em cada SO, base e candidato foram verificados no
mesmo caminho temporário. O `cmp` dos diagnósticos completos retornou 0.
Claude deve considerar essa pendência no parecer independente do candidato local.

Os logs, JSONs e hashes desta rodada ficam em
`reports/dl2b-pr04/validated/{mac,linux}/`. Os comandos completos estão em
`reports/dl2b-pr04/support/gates.sh`. O Mac usou o Python 3.12.13 disponível
e bloqueio de conexões IP externas. O Linux usou a imagem arm64 cacheada
`sha256:943825bb4a63ab6e0c7400dbee77cddeeb31ecd457b3366293b7c45d201ca7d8`
com `--network none --pull never`. O handoff local `curren_status.md` aponta
o head documental e os logs da sua verificação.

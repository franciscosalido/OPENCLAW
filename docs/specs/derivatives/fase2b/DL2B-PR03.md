# DL2B-PR03 — Registro versionado de termos e carry por série

Rascunho para Claude, estado A. Parte A, passo 3 do [DL2B-R1](DL2B-R1.md),
sobre a `main` integrada em `eacb172` (#148), com o domínio de `4c76d14` intacto.
O critério 7 do SDD exige recusa com motivo próprio para registro ausente,
vencido ou divergente do contrato. Aplicam-se os critérios 5, 9 e 10.
D3 permanece aberta. Sem a Parte B e sem código de ligação com a chain.

## Escopo do candidato

| Arquivo | Entrega |
|---|---|
| `backend/derivatives/domain/series_registry.py` | Registro imutável em memória e resolução pura na data civil fornecida |
| `tests/unit/derivatives/test_series_registry.py` | Fixture sintética declarada no próprio teste e oráculos por caso |
| `tests/architecture/test_series_terms_imports.py` | Incluir o registro entre os alvos protegidos e testar o alcance indireto |
| `docs/specs/derivatives/fase2b/DL2B-PR03.md` | Contrato pré-RED, resultados e limites |
| `docs/04_MEM/current_state.md` | Atualização apenas no bloco Marco 2B |
| `curren_status.md` | Handoff local ignorado pelo Git deste worktree |

## Contrato proposto à revisão

O chamador fornece uma versão do conjunto e, em cada registro, uma versão da
evidência, subjacente, lado, vencimento contratual, ISIN (também pode declarar
ausência), termos, carry ou ausência explícita, data de disponibilidade e último
dia de vigência conjunta. O primeiro dia vem de `SeriesTerms.effective_on`.
Cada fonte continua no dado de origem. O registro não produz documentos nem
atribui fonte ou política a uma série. O intervalo é uma declaração explícita
para o par. Nenhuma duração, autorização de uso ou lista de fontes vem do código.

1. Igualdade exata de símbolo, subjacente, lado, strike decimal, vencimento e
   ISIN. Um ISIN ausente só corresponde a outro ausente. Ticker ausente no
   conjunto dá `missing_series_record`. Ticker conhecido sem a identidade pedida
   dá `series_contract_mismatch`. Outras identidades com o mesmo ticker coexistem.
2. Uma versão só fica disponível a partir da data declarada pelo chamador. A
   vigência inclui os dois extremos. Datas anteriores à primeira versão disponível
   e iniciada dão `future_series_record`. Uma lacuna depois de um intervalo
   encerrado dá `expired_series_record`. A avaliação nunca consulta o relógio.
3. Uma única versão aplicável é selecionada. Duas vigentes, inclusive cópias
   idênticas, dão `conflicting_series_records`, em qualquer ordem. Reutilizar
   uma versão na mesma identidade também dá conflito a partir do momento em que
   ambas estão disponíveis. Versão é identificador opaco, sem ordenação implícita.
4. Estilo deve coincidir. Lote e fator observados no contrato devem coincidir
   individualmente com os termos. Um campo opcional ausente no contrato continua
   ausente. A API aceita contrato tipado e preserva os tipos do domínio ao
   validar registros e consultas. Dados malformados são erro de validação.
5. Só após a seleção e a conferência dos termos, `resolve_carry` aplica a
   precedência do 2A, inclusive ausência, série/data divergente, política
   desconhecida e dupla contagem. Uma resolução guarda data consultada, versão
   do conjunto, registro selecionado e `ResolvedCarry`. Recusas tipadas não
   entregam termos nem rendimento.
6. O único material de exemplo mora na fixture dos testes, rotulado como sintético.
   A literal de emissor exigida por `AdjustmentEvidence` apenas exercita seu
   esquema com documento fictício. Nenhuma observação real entra neste PR.

## Amostra e critérios antes do RED

- Contrato e fontes fictícios, com dois intervalos sucessivos e uma lacuna.
  Verificar os dias imediatamente fora e os dois extremos inclusivos, registro
  publicado depois do início, consulta histórica, seleção em ordem inversa,
  versões opacas e eco completo dos campos de origem.
- Variar isoladamente strike, vencimento, ISIN (inclusive nulo), lado e
  subjacente com ticker constante. Para termos incompatíveis, variar estilo,
  lote e fator independentemente. Cobrir vizinho homônimo vigente, conjunto
  vazio, ticker diferente e metadado opcional ausente.
- Exercitar sobreposição, duplicata, reutilização da versão e evidência futura.
  Verificar exceção e código literais. Em separado, exigir carry explícito,
  rendimento contínuo declarado, trava de dupla contagem e política desconhecida.
  Rejeitar datas invertidas e coerções implícitas na fronteira.
- RED com API mínima e recusa provisória para executar os casos até as asserções.
  Registrar comando, rc e resumo antes do GREEN. Repetir testes no refactor.
- Portões por SO conforme o PR02: pytest completo offline sem integração e com
  timeout 120, mypy strict e Pyright em `backend/`, Pyright adicional nos testes
  alterados, diff --check, até 400 linhas novas de produção. Executar ainda
  Pyright global e comparar os diagnósticos com a base (131 erros no PR02).
  Comparar stdout da demo offline por `cmp` no mesmo SO e exigir
  `LIVE_NOT_ACTIVATED`, rc 3, na base e no candidato. Linux arm64 com imagem e
  ferramentas cacheadas, sem pull nem rede. Nenhuma porta de serviço publicada.

## Não-objetivos e limites de autoridade

D3 pertence a Francisco, inclusive fonte real, aplicabilidade e prazo. D4 fica
aberta. A Revisão 1 decidiu D2, que só é implementada no PR04. Ficam fora do cartão a autoria de termos B3, inferir
vencimento, preencher volume nominal, inferir q=0, reclassificar proveniência,
persistência, precificação, configuração, IV, consumidores da ponte e PR04.
Não há meta de desempenho. A resolução prova consistência dos dados fornecidos.
Autenticidade da fonte e completude do histórico dependem de evidência externa.

## RED em macOS arm64

Cartão prévio em `4bc1be8`. A API provisória devolve apenas a recusa MISSING.
`python -m pytest -q tests/unit/derivatives/test_series_registry.py tests/architecture/test_series_terms_imports.py --tb=short`
deu rc 1, **43 falhas e 51 aprovações** em 0,82 s. Para 2/abril o teste recebeu
`missing_series_record` e exigia `future_series_record`. Para 4/abril recebeu
a mesma recusa quando já esperava a versão `z-first`. A prova de carga em
processo novo também falhou, assim como as duas provas de import dinâmico
direto e indireto do registro. Log integral local em `reports/dl2b-pr03/mac/red.log`.

## Resultado histórico do candidato local (anterior ao DL2B-R1)

**Estado A, candidato local em revisão. NO-GO local para aceite com Pyright global
verde.** O gate de tipos de produção utilizado no PR02 passou. O Pyright do
repositório inteiro retornou rc 1 nos dois SO. A comparação abaixo registra o
alcance da falha. A decisão de integração cabe à revisão.

| Passo local | Commit | Prova |
|---|---|---|
| Cartão pré-RED | `4bc1be8` | Contrato, escopo, amostra e critérios |
| RED | `e724d7f` | 43 falhas comportamentais e de isolamento, 51 aprovações |
| GREEN | `3cd75bb` | 94 aprovações em testes do registro e guarda |
| Refactor e verificação de fronteira | `1378bf2` | 105 aprovações com a guarda do binomial incluída |

Durante a verificação do GREEN, um objeto genérico com os atributos de
`OptionContract` chegou a produzir uma resolução. A contraprova isolada teve
uma falha e cinco aprovações. O candidato exige a instância de domínio e
revalida os campos observados em modo estrito, inclusive após cópia sem validação.
A seleção temporal foi extraída para uma função privada. Os demais controles
incluem campos extras de autorização e volume, ausência de datas e registro
construído contornando o validador. No Mac, sete mutações isoladas foram detectadas,
com 55 testes de domínio aprovados na cópia de controle. As mutações retiraram
strike, vencimento e ISIN da identidade, ignoraram disponibilidade, excluíram
o último dia ou aceitaram sobreposição e reutilização de versão.

### Interface e isolamento

A entrada pública é `SeriesRegistry.resolve(contract, *, as_of)`. O único
resultado bem-sucedido é `SeriesResolution`. A seleção e a compatibilidade usam
`RegistryRefusal`, e o domínio de carry preserva `CarryRefusal`. Erros de tipo
ou de construção são tratados na fronteira. As versões e fontes são declarações
do chamador. O par termos/carry precisa compartilhar série e data efetiva conforme
o domínio do 2A. O chamador fornece expressamente o fim da vigência conjunta.
O histórico em memória deve conter as versões necessárias à consulta.

A guarda passou a procurar o registro inclusive como alvo de import dinâmico
literal, direto ou por intermediário. A lista de caminhos de produção com
permissão de alcançar a ponte teve zero acréscimos. A única alteração em produção
é o novo módulo do domínio, com 112 linhas de 400 permitidas.

### Portões offline por plataforma

Base `8ec256dfef3564a0b4f34777e7e2aac6bdc97459`,
código `1378bf2da3dc84d68379a4da19777d78ac311cbc`.
Ambos os SO usaram CPython 3.12.13, pytest 9.0.3 e Pyright 1.1.409.
No Mac, o interpretador veio de `/Users/fas/projetos/OPENCLAW/.venv/bin/`.
Linux aarch64 usou o runner cacheado do PR02, com Git e Click locais e a imagem
`sha256:943825bb4a63ab6e0c7400dbee77cddeeb31ecd457b3366293b7c45d201ca7d8`,
`--pull never --network none --cap-drop ALL --security-opt no-new-privileges`.
O runner publicou zero portas e utilizou zero serviços externos. Base e candidato
foram materializados com bundle local em diretórios temporários independentes.

| Comando ou verificação | macOS arm64 | Linux aarch64 | Log em cada SO |
|---|---|---|---|
| `python3.12 -m pytest tests/ -q --ignore=tests/integration --timeout=120` | 9.434 passaram, 16 pulados, 261 subtestes, 42,61 s | 9.434 passaram, 16 pulados, 261 subtestes, 50,44 s | `pytest.log` |
| `python3.12 -m mypy backend/ --strict` | rc 0, 161 arquivos | rc 0, 161 arquivos | `mypy.log` |
| `pyright --venvpath "$envroot" backend/` | 0 erros e avisos | 0 erros e avisos | `pyright-backend.log` |
| Pyright nos dois arquivos de teste do cartão | 0 erros e avisos | 0 erros e avisos | `pyright-tests.log` |
| `pyright --venvpath "$envroot"` global, base e candidato | rc 1, 131 erros em ambos | rc 1, 131 erros em ambos | `{base,head}.pyright-global.log` |
| `cmp` dos diagnósticos globais, normalizado apenas o caminho do checkout | rc 0 | rc 0 | `gates.log`, `{base,head}.pyright-normalized` |
| `git diff --check 8ec256d HEAD`, diff fora da lista permitida e integridade do bloco de memória | rc 0 | rc 0 | `gates.log`, `diff-check.log`, `escopo.log` |
| CLI demo, `cmp` do stdout contra base no mesmo SO | rc 0, 67.097 bytes | rc 0, 67.101 bytes | `{base,head}.demo.json`, `gates.log` |
| CLI padrão em base e candidato | rc 3, `LIVE_NOT_ACTIVATED` | rc 3, `LIVE_NOT_ACTIVATED` | `{base,head}.cli.json`, `gates.log` |
| CLI padrão com relógio fixo, `cmp` do stdout completo | rc 0, 313 bytes | rc 0, 313 bytes | `{base,head}.cli-fixed.json`, `gates.log` |

O CLI real foi chamado com `python3.12 -m backend.derivatives.cli chain BOVA11 2026-11-19`,
adicionando `--provider offline_fixture` para a demo. O CLI padrão publica o
instante da consulta. Para a comparação adicional do JSON completo foi usada a
entrada `cli.main` com o relógio injetável fixado à meia-noite UTC de 19/11/2026.

No Mac, a demo teve SHA-256 `a7d82699b47d31acec31995ccea3cf4149ebcb92311f980fb23390627b1de9c3`.
No Linux, teve SHA-256 `f4f8003f2021b2744202c782f6e5245872c09d7f9d1968a3356466a7e85ead08`.
O CLI com relógio fixo teve o mesmo SHA-256 nos dois SO, `230690465fe972c140d87c662e3b61de934a0b99896a0282e078c31829f16fb7`.

O Pyright global apontou sete arquivos de teste preexistentes. Os diagnósticos
são idênticos aos do PR02 ao substituir somente o caminho absoluto do checkout.
A suíte ganhou 57 testes sobre os 9.377 do PR02. As provas de código ficam em
`reports/dl2b-pr03/code/{mac,linux}/` neste worktree. As contraprovas ficam em
`reports/dl2b-pr03/mac/`, e os comandos completos em `reports/dl2b-pr03/support/`.
O handoff local `curren_status.md` identifica o SHA final e os logs da repetição.
Claude faz o parecer independente. A decisão de fonte e validade reais continua com Francisco.

## Evidências da Parte A — PR 3 (DL2B-R1)

O módulo do registro e os testes de `4c76d14` foram reaplicados sem alteração.
O RED original corresponde a `b094055` nesta base. A descrição do rascunho
vincula a medição dos portões e a evidência da skill ao head publicado.

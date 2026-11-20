# DL2B-PR03 — Registro versionado de termos e carry por série

Cartão candidato para Claude. Estado A. Base local do PR02
`8ec256dfef3564a0b4f34777e7e2aac6bdc97459`, confirmada em ambas as branches.
Francisco autorizou empilhar os commits locais. O critério 7 do SDD exige recusa
com motivo próprio para registro ausente, vencido ou divergente do contrato.
Os critérios 5, 9 e 10 também se aplicam. D3 continua aberta.

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

D3 pertence a Francisco, inclusive fonte real, aplicabilidade e prazo. D2 e D4
permanecem abertas. Ficam fora do cartão a autoria de termos B3, inferir
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

# DL2-PR01 — Termos vigentes da série

Base `11838cdafae0e3de0ed339a2acca736f480967fb`, branch `feat/dl2-pr01-series-terms`.

## SPEC_PRONTA

Um registro imutável identifica a série e sua vigência civil explícita. Guarda fonte,
strike vigente em Decimal finito positivo, estilo americano ou europeu, moeda BRL
(única coberta neste recorte), lote inteiro positivo e fator inteiro 1 ou 1000.
Igualdade exata em todos os testes. Lote 37 funciona com ambos os fatores.
Cada registro traz seus próprios termos, inclusive quando muda o strike da mesma série.

Lote ou fator ausente/inválido, estilo ou moeda desconhecidos geram exceção de domínio
com os códigos missing_contract_size, missing_quotation_form, unknown_exercise_style e
unknown_currency, respectivamente. Entradas malformadas nos demais campos falham na
validação estrutural. UNKNOWN é válido. Para PROTECTED ou UNPROTECTED, o chamador
identifica o documento B3, versão, data e o fato documentado (série, vigência e política).
O domínio verifica consistência da declaração. A autenticação da fonte cabe à coleta.

## Leitura adversária do ADR aceito

- O exemplo de diretório informado distingue BOVAL63 (179, europeia) de BOVAL65
  (176, americana). Protected YES em ambas não estabelece vigência histórica,
  lote ou fator. Um ticker não determina o strike.
- FATCOT unitário ou por mil (layout COTAHIST rev02, p. 6) descreve a unidade de
  cotação. Copiá-lo para o lote faria duas séries economicamente distintas parecerem iguais.
- UNKNOWN é um termo válido aqui. A recusa missing_carry_assumption pertence ao PR02.
  O PR03 conserva 4.192654 e 5.089632 com tolerância 5e-5. A pendência 200/201 é posterior.

## RED_MOSTRADO

Comando (uv offline, ambiente existente, sem sincronização):

    uv run --offline --no-sync python -m pytest tests/unit/derivatives/test_series_terms.py::test_missing_contract_size -q

Saída: `Failed: DID NOT RAISE <class 'backend.derivatives.domain.series_terms.TermsRefusal'>`.
`1 failed in 0.07s`, rc 1. O teste foi coletado e o construtor aceitou a ausência do lote.

Commit do RED: e0f4664595d7fa4464783b9a7b983f6e045a3ba2.

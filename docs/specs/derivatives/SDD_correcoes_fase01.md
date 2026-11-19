# Correcoes da Fase 01 apos a revisao independente (2026-11-19)

A revisao independente da candidata conciliada deu **NO-GO** para fechar o
estado A: a suite existente passava, mas tres testes novos expuseram dois
defeitos de produto e uma lacuna de teste. Este PR corrige os dois defeitos,
fecha a lacuna e incorpora os testes do revisor **sem alterar uma linha
deles** (`tests/unit/derivatives/test_phase_a_independent.py`).

Os dois defeitos foram reproduzidos na pilha desta branch antes de qualquer
mudanca (2 falhas, 1 aprovado, identico ao relatorio do revisor).

## 1. Dado simulado saia carimbado `observed` / `production`

**Causa.** `HttpTransport` carimbava toda resposta de sucesso como
`OBSERVED`. No estado A ele so aceita `httpx.MockTransport`, entao tudo o
que passa por ele e simulado. O teste de sucesso existente exigia
`OBSERVED` para o mock: a suite cristalizava o defeito em vez de acusa-lo.

**Alcance.** Interno. A tool produtiva recusa sempre em A e a demo usa o
adaptador verificado por manifesto; nenhuma cotacao simulada saiu rotulada
como producao. O carimbo errado, porem, era a unica coisa entre um mock e
`purpose=production` dentro do processo.

**Decisao.** Em A, `HttpTransport` carimba `REPLAY` (proposito canonico
`test`). `OBSERVED` fica reservado a aquisicao homologada do estado B.
`REPLAY` e nao `SYNTHETIC` de proposito: a demo so aceita `SYNTHETIC`, e
uma chain alimentada por mock nao deve atravessar **nenhuma** das duas
barreiras.

**Trava estrutural.** `test_phase_a_production_code_never_assigns_observed`
percorre a AST de `backend/derivatives/` e so admite `OBSERVED` como
operando de comparacao (as recusas). Quem implementar a aquisicao real em B
tera de alterar esse teste de proposito, junto com o ADR-0023.

## 2. Taxa composta <= -100% a.a. derrubava a chain

**Causa.** `continuous_rate` calcula `ln(1 + i/100)`. Com `i <= -100%` o
argumento e zero ou negativo e `math.log` levanta `ValueError: math domain
error`, que escapava de `ChainService.build`. O modelo do fornecedor aceita
o valor porque ele e finito.

**Dominio medido** (sonda com 18 taxas x 2 capitalizacoes sobre a fixture
sintetica): o defeito ocorre exatamente em `annual_exp_252` com `i <= -100`.
Taxas nao finitas ja eram recusadas no limite do fornecedor
(`VendorPayloadError`); capitalizacao `continuous` nao tem limite inferior.

**Decisao.**

- `continuous_rate` levanta `RateDomainError` (subclasse de `ValueError`,
  mensagem sem o valor) para taxa nao finita e, na capitalizacao composta,
  para `1 + i/100 <= 0`.
- `ChainService` converte a taxa **uma vez por chain** (antes era por linha)
  e transforma o erro na recusa `invalid_rate`: todas as linhas sao
  preservadas com `chain_unpriceable:invalid_rate` e nenhum numero; a taxa
  recusada continua visivel em `chain.rate`.
- Taxa negativa acima de -100% continua valida e precificada.

Nao ha limite de plausibilidade (ex.: Selic acima de 1.000%): isso e
politica de homologacao, nao dominio matematico. Fica no BACKLOG.

## 3. Lacuna: a cauda da put aceitava um mutante

O teste de cauda existente so exigia preco positivo. Um mutante que trocou
`erfc` por `erf` devolvia 3,9e-16 no lugar de 1,145e-15 e passava em todo o
arquivo. Novo teste: quatro caudas profundas (duas puts, duas calls)
contra um oraculo em `Decimal` com 100 digitos escrito no proprio teste,
tolerancia **so relativa** de 1e-9. O oraculo foi conferido contra duas
referencias independentes: o valor do revisor (Decimal, 80 digitos) e
mpmath com 50 digitos. Erro relativo medido da producao: de 2e-13 a 2e-12.

## Evidencia

- **RED antes:** 2 falhas nos testes do revisor, aplicados sem alteracao.
- **GREEN depois:** os 3 passam; nenhum teste existente foi relaxado. A
  unica expectativa alterada e a que exigia `OBSERVED` do mock.
- **Mutacao:** 7 mutantes (erfc->erf, REPLAY->OBSERVED, sem checagem de
  dominio, fronteira `<=` trocada por `<`, motivo errado, sem checagem de
  finitude, recusa indevida na capitalizacao continua): todos mortos.
- **Precos inalterados:** digest bit a bit de precos, gregas e IVs igual ao
  de antes (`840770d25be12b8602c614bd`).
- Linux aarch64, Python 3.12: gate sem integracao com 0 falhas em ordem
  natural, invertida e embaralhada; `mypy --strict` 0; `pyright` 0.
- Producao do PR: 48 linhas adicionadas em 3 arquivos.

## Fora deste PR

- O carimbo da captura herda a **procedencia** so da leitura de opcoes (o
  proposito e worst-of das quatro). Inalcancavel pela demo, que usa o
  adaptador de manifesto; registrado no BACKLOG para a fase B.
- Homologacao do provedor (B) e promocao (C).

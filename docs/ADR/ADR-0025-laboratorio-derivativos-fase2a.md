# ADR-0025 - Laboratorio de Derivativos - Fase 02, Marco 2A

## Status

Accepted (2026-11-19). Aprovado por Francisco no PR #141 (DL2-PR00), apos a
revisao adversaria registrada em `docs/specs/derivatives/fase2/DL2-PR00.md`.
Os PRs de codigo do Marco 2A ficam liberados a partir do merge desse PR.

## Contexto

A Fase 01 fechou em estado A (offline verificado) na `main` em `1421116`. O
ADR-0023, decisao 4, deixou americanas preservadas e marcadas, nunca
precificadas, e remeteu modelos americanos a uma fase propria, com
referencia numerica propria.

O dominio da Fase 01 guarda `contract_size` e `quotation_form` como
opcionais e a configuracao assume `dividend_yield = 0` com
`strike_adjusted_by_exchange_assumed = true`. Para europeias com BSM isso
foi declarado como hipotese. Para americanas a hipotese pesa mais: o valor
do exercicio antecipado depende do carry, e contar o provento duas vezes
(no strike ajustado e no rendimento) produz preco errado sem nenhum erro
visivel.

Este ADR autoriza o primeiro recorte da Fase 02 e nada alem dele.

## Decisao

Autoriza, e so isto: **modelo binomial americano (CRR) no Lab, como funcao
pura e isolada**, precedido dos termos de serie e da premissa de carry que
o tornam seguro de usar.

Continuam proibidos, sem excecao neste marco:

- NumPy/SciPy ou qualquer dependencia nova;
- snapshots em PostgreSQL;
- chamadas reais a OpLab e token real;
- ordens, em qualquer forma;
- ativacao para Helena ou para qualquer agente consumidor.

O estado de prontidao segue A. O Marco 2A nao aproxima o Lab de B nem de C.

## Marco 2A - entregas 1 e 2 da Fase 02, em 5 PRs

| PR | Entrega | Conteudo |
|---|---|---|
| DL2-PR00 | - | Este ADR e o SDD do marco. So documentacao. |
| DL2-PR01 | 1 | Termos da serie e recusas (dominio puro). |
| DL2-PR02 | 1 | Premissa de carry explicita e trava de dupla contagem. |
| DL2-PR03 | 2 | Nucleo binomial e parametrizacao CRR, isolados. |
| DL2-PR04 | 2 | Referencia independente, invariantes, mutacao, medicao. |

### DL2-PR01 - termos da serie

Modelo novo **ao lado** de `OptionContract`, para nao mudar o formato da
Fase 01 (`quimera-derivatives-chain-v1` e a chain precificada ficam
intactos). Campos: lote, fator de cotacao, moeda, strike vigente, politica
de ajuste de strike (`PROTECTED`, `UNPROTECTED`, `UNKNOWN`), fonte e data de
vigencia.

Recusas tipadas: `missing_contract_size`, `missing_quotation_form`,
`unknown_exercise_style`, `unknown_currency`. Nao existe valor padrao para
lote (ADR-0023: "nunca assumir 100").

### DL2-PR02 - premissa de carry

A premissa de carry e explicita: **nenhum** ou **rendimento continuo**,
sempre com fonte e data. Dado ausente nao e zero: carry nao informado e
recusa, nao `q = 0`.

Carry nao informado tem recusa propria: `missing_carry_assumption`.

Trava de dupla contagem, com recusas tipadas: `dividend_double_count`
(provento contado no strike ajustado e tambem no rendimento),
`strike_adjustment_unknown` (politica `UNKNOWN` com dividendo > 0) e
`discrete_dividends_not_supported`.

### DL2-PR03 - nucleo binomial e CRR

Duas pecas separadas: o nucleo de inducao retroativa, que recebe `u`, `d` e
`p` prontos, e a parametrizacao CRR, que os calcula. O nucleo nao sabe o
que e CRR; isso permite testar a inducao com uma arvore feita a mao.

Nao e ligado a chain, ao MCP nem ao CLI. Nenhum caminho de producao chama o
binomial ao fim do Marco 2A.

### DL2-PR04 - validacao e fechamento

Referencia independente, invariantes em grade, mutacao e medicao de custo.
Fecha o marco.

## Convencoes numericas

- **Parametrizacao CRR:** `u = exp(sigma*sqrt(dt))`, `d = 1/u`,
  `p = (exp((r-q)*dt) - d)/(u - d)`, desconto por passo `exp(-r*dt)`, com
  `dt = T/N`.
- **Taxa e tempo:** `r` continuo vem de `continuous_rate`; tempo em
  `business_252`, como na Fase 01. Nenhuma convencao temporal nova.
- **Exercicio:** elegivel em todo no, inclusive a raiz. `T = 0` devolve o
  intrinseco.
- **Passos:** inteiro em `[1, 5000]`. Toda afirmacao de convergencia usa o
  par `N` e `N+1`, nunca um `N` sozinho.
- **Recusas tipadas, nunca numero:** `p` fora de `(0,1)`, passos fora do
  intervalo, `sigma = 0`, entrada nao finita. Os identificadores das
  recusas sao fixados na SPEC do DL2-PR03.
- **Sem fallback silencioso de americana para BSM.** BSM segue sendo o
  modelo das europeias, sem mudanca.

Duas diferencas deliberadas em relacao ao BSM da Fase 01, registradas para
ninguem "harmonizar" depois:

- `sigma = 0` e regime `zero_vol` no BSM e **recusa** no CRR: com
  `sigma = 0`, `u = d = 1` e `p` nao esta definido.
- `p` em `(0,1)` equivale a `d < exp((r-q)*dt) < u`. Com `sigma` pequeno
  frente a `|r-q|*sqrt(dt)` a condicao falha; a resposta e recusa, nao
  truncamento de `p`.

## Fora do Marco 2A

Dividendo discreto, suavizacao de arvore, Leisen-Reimer, Richardson,
Bjerksund-Stensland, IV americana e gregas americanas. Tambem fora: ligar o
binomial a chain, ao MCP ou ao CLI; mudar o motivo de recusa de americana
ja publicado (`american_not_supported_phase1`).

## Governanca

Padroes adotados; Francisco pode reverter qualquer um na revisao deste PR.

- **L1 - memoria.** A memoria e `docs/04_MEM/current_state.md`. Nao existe
  `curren_status.md`.
- **L2 - integracao.** PR -> squash-merge no GitHub ->
  `git merge --ff-only origin/main` local. ADR-011 preservado.
- **L3 - referencia independente.** A referencia do CRR e gerada por outro
  agente (Codex), nao por quem implementa.
- **L4 - NumPy.** Nao e decidido agora. O 2A mede o custo de um preco CRR e
  a decisao vira ADR proprio no 2B.
- **L5 - ajuste de strike.** A politica so vale com documento da B3 datado
  e versionado. Sem documento, `UNKNOWN`.

## Consequencias

- O Lab ganha um preco americano de referencia, auditavel linha a linha,
  sem que nenhum consumidor o receba.
- Series sem lote, sem fator de cotacao, com estilo desconhecido, ou com
  ajuste desconhecido e dividendo > 0, passam a ser recusadas com motivo
  proprio em vez de carregar hipotese implicita.
- Enquanto nao houver documento datado (L5), toda serie com dividendo > 0
  cai em `strike_adjustment_unknown`. E o comportamento desejado, nao um
  defeito a contornar.
- Python puro pode ser lento para chains inteiras. O marco mede; nao
  otimiza.

## Pendencias

Nada abaixo e afirmado por este ADR. Cada item e **hipotese a confirmar com
documento datado**:

- Regra de ajuste de strike por proventos nas opcoes listadas na B3, por
  tipo de provento e por classe de ativo-objeto.
- Tratamento de proventos do BOVA11 e seu efeito sobre as series de opcoes.
- Lote e fator de cotacao vigentes por serie, e a fonte oficial de cada um.
- Estilo de exercicio por serie conforme a especificacao do contrato.
- Moeda de cotacao e de liquidacao das series cobertas.

Pendencias herdadas do ADR-0023 (base de capitalizacao da taxa, calendario,
sincronismo de spot) seguem abertas e nao sao tocadas aqui.

## Referencias

- ADR-0023 - Laboratorio de Derivativos, Fase 1 (decisao 4 e convencoes).
- ADR-011 - GitHub como fonte de verdade do fluxo de integracao.
- `docs/specs/derivatives/fase2/SDD_FASE2A.md` - criterios de aceite.
- Cox, Ross e Rubinstein (1979), *Option Pricing: A Simplified Approach*.
- Hull, *Options, Futures, and Other Derivatives* - exemplo de put em
  arvore de dois passos, recalculado no SDD.

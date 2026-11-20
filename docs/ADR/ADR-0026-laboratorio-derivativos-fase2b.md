# ADR-0026 - Laboratorio de Derivativos - Fase 02, Marco 2B (ponte americana)

## Status

Accepted (Francisco, 2026-11-20), com a Revisao 1 no fim deste arquivo. A versao original foi
proposta por Claude em 2026-11-19 e entrou na `main` pelo PR #146. Onde o texto abaixo
conflitar com a Revisao 1, vale a Revisao 1.

## Contexto

O Marco 2A fechou em `ff0c1be` com tres pecas isoladas: termos de serie, premissa de carry e
binomial CRR. Nenhuma tem consumidor. A americana segue recusada na chain, no MCP e no CLI
com `american_not_supported_phase1`.

Tres fatos medidos ou documentados no 2A limitam o que o 2B vale:

- Na B3, em acoes, BDRs e ETFs, so a opcao de compra pode ser americana (manual de
  01/07/2026, item 3.3.1; Adendo 1 do ADR-0025).
- Call com `q = 0` e `r >= 0` vale o mesmo que a europeia, no modelo continuo (Merton,
  1973) e na arvore (grade do DL2-PR04, 340 pontos). Para serie com ajuste de strike
  comprovado e sem rendimento, o numero da ponte difere do BSM so pelo erro de discretizacao.
- Com taxa de 13% e rendimento continuo de ate 6%, o premio de exercicio antecipado da call
  ficou em no maximo 0.083 sobre um preco de 34.91 (medicao do revisor, grade pequena).

Logo o ganho do 2B nao e um preco muito diferente. E trocar uma recusa geral por uma
admissao com precondicoes tipadas, e acertar o caso em que o rendimento chega perto da taxa.

## Decisao

Autoriza, e so isto: **uma ponte que leva contrato americano, termos de serie e premissa de
carry ate o binomial, e devolve `PricingOutcome`**. Em quatro PRs:

| PR | Conteudo | Toca chain, MCP ou CLI? |
|---|---|---|
| DL2B-PR01 | Ponte pura, com `sigma` dado pelo chamador | nao |
| DL2B-PR02 | Volatilidade implicita americana pela ponte, com custo medido | nao |
| DL2B-PR03 | Origem versionada dos termos e do carry por serie | nao |
| DL2B-PR04 | Ligacao na chain, atras de chave desligada por padrao; fechamento | sim |

Cada PR tem cartao proprio. Os PRs 02 a 04 so comecam depois do merge do anterior.

Regras da ponte:

1. **Um unico modulo consome os tres isolados**: `backend/derivatives/pricing/american_bridge.py`.
   As duas guardas de arquitetura passam a aceitar esse modulo e continuam recusando
   qualquer outro, inclusive quem importar a ponte antes do DL2B-PR04.
2. **O rendimento vem so da premissa de carry resolvida.** As hipoteses da Fase 01
   `dividend_yield` e `strike_adjusted_by_exchange_assumed` nao acompanham um resultado
   americano: seriam uma segunda fonte para o mesmo dado.
3. **O preco e a media das arvores de `N` e `N + 1` passos.** E a regra do ADR-0025 (toda
   afirmacao no par) transformada em numero. A diferenca entre as duas arvores e publicada
   como diagnostico e **nao** e limite de erro.
4. **Recusa nunca traz numero.** Toda recusa dos tres isolados chega ao chamador com o
   codigo original, prefixado pela origem.
5. **Sem gregas e sem IV no DL2B-PR01.** Resultado suportado com `greeks = None` e valido
   para americana. Nenhum consumidor ve isso antes do DL2B-PR04.
6. **Um motor por numero.** Preco e volatilidade implicita principais de uma serie americana
   saem da arvore CRR, e o resultado diz qual motor gerou cada numero. A ponte nao recua
   para BSM. O BSM roda so como sombra, fora da ponte. Ver Revisao 1, R1.

Continuam proibidos no Marco 2B: dependencia nova, inclusive NumPy, sem ADR proprio; chamada
real a OpLab e token real; ordens; ativacao para Helena ou outro agente; mudar o formato
`quimera-derivatives-chain-v1`; dividendo discreto; trocar a parametrizacao da arvore.

O estado de prontidao segue A.

## Decisoes abertas, com dono

| D | Decisao | Quando |
|---|---|---|
| D1 | Fechada na Revisao 1, R1: arvore como principal, BSM como sombra | fechada |
| D2 | Fechada na Revisao 1, R2: 200 passos, em `config/american_iv.yaml` | fechada |
| D3 | De onde vem termos e carry de cada serie, e por quanto tempo valem | DL2B-PR03 |
| D4 | NumPy, com as medicoes do 2A e do DL2B-PR02 | depois do DL2B-PR02 |

As quatro sao de Francisco. Cada uma e fechada no cartao do PR indicado, antes do codigo.

## Consequencias

- O Lab passa a ter um caminho unico e auditavel para preco americano, ainda sem consumidor.
- As guardas deixam de ser "ninguem importa" e passam a ser "so a ponte importa". Fica mais
  facil errar a lista; por isso a excecao e um caminho de arquivo fixo, testado.
- A ponte herda o erro de discretizacao da arvore. O SDD do 2B fixa quanto se aceita.

## Referencias

- ADR-0025 e seu Adendo 1; `SDD_FASE2A.md` e Adendos 1 e 2; `DL2-PR04.md`.
- `docs/specs/derivatives/fase2b/SDD_FASE2B.md` - criterios de aceite do marco.

## Revisao 1 (2026-11-20)

Decisoes de Francisco, tomadas depois da revisao adversaria dos candidatos locais do marco
(`REVISAO_TURNO_NOTURNO_2B` e `REVISAO_CORRECOES_2B`, 2026-11-20). Fecham D1 e D2.

### R1. D1 fechada: dois metodos, um principal e um de sombra, nunca misturados

**Motor principal: arvore CRR.** Preco e volatilidade implicita de toda serie americana saem
do mesmo par de arvores, com busca por bissecao. E o unico motor que publica preco e
volatilidade da linha.

**Motor de sombra: BSM europeu da Fase 01.** Roda ao lado, sobre a mesma cotacao e o mesmo
rendimento resolvido, e so publica a sua volatilidade e a diferenca para a principal. Serve
para observar a divergencia entre os dois metodos. Nunca substitui, nunca alimenta o preco e
nunca decide recusa: se a sombra falhar, a linha principal sai igual, com o motivo da falha
anotado.

Regra que fica: **dois motores podem conviver; no mesmo numero, nunca.** Todo numero diz
qual motor o gerou, e um teste exige que preco e volatilidade principais venham do mesmo.

Motivo. Um candidato local tirava a volatilidade do BSM e o preco da arvore. Medido: em 105
idas e voltas, todas erraram mais que 1e-6 em sigma, e 34 erraram mais que 0.01. O teorema
de nao exercicio antecipado diz que a call americana vale o mesmo que a europeia no modelo
continuo; nao diz que uma arvore finita vale o mesmo que o BSM.

Referencia externa, nao implementada: o QuantLib precifica americana por diferencas finitas
e busca a volatilidade com Brent, reusando o mesmo motor em toda a busca. E a mesma
disciplina desta regra com outro motor. Um terceiro motor (diferencas finitas) so entra com
ADR proprio, depois de observada a divergencia entre os dois atuais.

O que este marco nao observa: a divergencia contra preco real. So existe cotacao sintetica
(estado A). A comparacao com mercado e da homologacao (estado B).

### R2. D2 fechada: 200 passos por padrao

O numero de passos padrao e **200**, e mora em `config/american_iv.yaml`. As funcoes puras
(`price_american_contract` e `american_implied_vol`) continuam sem padrao: recebem `steps`
do chamador. So a raiz de composicao le o padrao, e o resultado diz de onde veio o numero
usado (configuracao ou argumento).

O que se sabe sobre 200, medido pelo revisor:

- erro do preco contra referencia de alta resolucao, em 12 casos com `S = 100`: ate 0.0077;
- a volatilidade implicita depende do numero de passos: na serie sintetica da demo, 0.2135
  com 3 passos e 0.2159 com 200. Volatilidades obtidas com numeros de passos diferentes nao
  sao comparaveis entre si;
- custo de uma inversao no Mac: mediana de 139 ms de CPU.

Nao existe numero universal de passos. 200 e uma escolha de engenharia, revisavel por ADR
quando houver dado real (estado B).

### R3. Teto de tempo

**210 ms de CPU por inversao com 200 passos no Mac** (arm64, Python puro). E registro de
medicao em cada PR que tocar o solver, nao condicao de teste automatico. Estouro do teto
reabre D4.

### R4. Como o marco foi executado, e o que vale daqui em diante

Os PRs 02, 03 e 04 foram escritos em pilha local, sem cartao do revisor e antes do merge do
anterior, contra a regra original deste ADR. O codigo foi revisto depois. Para o que resta
do marco:

- a integracao e um PR por vez, na ordem 01A, 02, 03, 04, cada um com portao proprio na
  arvore realmente integrada;
- os cartoes escritos pelo implementador ficam como registro; os criterios que valem sao os
  do SDD e de seu Adendo 1;
- a revisao pela skill `quimera-lab-review` e obrigatoria, por sessao que nao seja a do
  autor, sobre o head publicado. Claude forma o parecer sem ler o da skill e so integra
  depois de ler.

### R5. O que segue aberto

| D | Decisao | Dono |
|---|---|---|
| D3 | De onde vem termos e carry de uma serie real, e por quanto tempo valem | Francisco |
| D4 | NumPy, se o teto de R3 estourar ou o uso exigir mais passos | Francisco |

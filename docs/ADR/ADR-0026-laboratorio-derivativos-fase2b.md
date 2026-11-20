# ADR-0026 - Laboratorio de Derivativos - Fase 02, Marco 2B (ponte americana)

## Status

Proposed (Claude, 2026-11-19). Passa a Accepted quando Francisco mandar o Codex iniciar o
DL2B-PR01; o merge desse PR registra a aprovacao. Antes disso, qualquer item pode ser vetado.

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
6. **Sem recuo para BSM dentro da ponte.** A equivalencia com a europeia e informada
   (`early_exercise_premium`), nao usada para trocar de modelo. Ver D1.

Continuam proibidos no Marco 2B: dependencia nova, inclusive NumPy, sem ADR proprio; chamada
real a OpLab e token real; ordens; ativacao para Helena ou outro agente; mudar o formato
`quimera-derivatives-chain-v1`; dividendo discreto; trocar a parametrizacao da arvore.

O estado de prontidao segue A.

## Decisoes abertas, com dono

| D | Decisao | Quando |
|---|---|---|
| D1 | Call com `q = 0` e `r >= 0`: reusar a IV europeia em vez de inverter a arvore | DL2B-PR02 |
| D2 | Numero de passos padrao e onde ele mora na configuracao | DL2B-PR04 |
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

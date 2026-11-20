# DL2C1-PR02 — ligação diagnóstica do FD na demo mista

**Estado:** candidato a revisão, sem integração. Base `7d47d3b` (DL2C1-PR01 integrado).
Autoridade: [ADR-0027](../../../ADR/ADR-0027-laboratorio-derivativos-fase2c1.md) e
[cartão DL2C1 + Adendo 1](DL2C1.md). RED de U1: `44f068a`, por falta de `fd_engine`.

## Contrato da entrega

- A raiz da demo mista carrega o perfil FD validado apenas no opt-in sintético. Arquivo
  ausente ou inválido recusa a demo mista e não afeta o caminho padrão.
- O FD recebe os mesmos insumos e o mesmo prêmio observado por unidade da CRR, em uma
  única malha para preço, VI e sensibilidade. Somente uma linha americana suportada o chama.
  Erro ou recusa do FD não muda os resultados principais nem a sombra BSM.
- A comparação de preço ocorre na VI principal. A comparação de VI usa o alvo observado.
  Alerta só acima do limiar e com sensibilidade de preço suficiente. Alerta não é recusa.
- Adendo de projeção autorizado na revisão: a CLI e o MCP mantêm o esquema v1 e
  acrescentam `diagnostics` ao fim da linha americana suportada, apenas quando há
  chaves `fd_*`. Chaves anteriores e a sombra BSM não entram no objeto novo; linhas
  europeias, recusadas e da demo padrão não ganham a chave. Os agregados continuam
  em `model_assumptions`. A única função de arquivo MCP editada é `_row_view`.
- A fronteira do alerta usa a diferença absoluta entre os decimais nominais dos
  dois floats, sem margem ou arredondamento. O `fd_iv_gap` publicado continua sendo
  a subtração assinada de floats. Assim, 20,00% contra 20,05% não alerta para o limiar
  de 0,0005, mesmo se a diferença binária publicada estiver um pouco acima.
- A mudança escrita autorizada para U11 substitui as três linhas do teste que antes exigia
  zero consumidores. A guarda, o algoritmo de inspeção e os demais testes continuam iguais.

## Provas dos critérios 1 a 19

| Critério | Prova |
|---|---|
| 1 | T2: nove europeias comparadas ao BSM; núcleo PR01 intacto. |
| 2 | T3: três calls sem rendimento contra BSM. |
| 3 | T1: dezoito âncoras; validação do esquema, não oráculo independente. |
| 4 | T4: nove comparações com par CRR 2000/2001. |
| 5 | T5: três malhas em nove casos de convergência. |
| 6 | T6: vinte simetrias call/put, semente fixa. |
| 7 | T7 na malha offline; testes do Adendo 1 na malha padrão, incluindo os 93/1.000 desvios do limite absoluto original, que não vale como garantia nessa malha. |
| 8 | T8–T10, T16–T18: recusas, precedência no vencimento e configuração. |
| 9 | T13: quarenta inversões de ida e volta. |
| 10 | T14: nove alvos da malha de referência mais fina. |
| 11 | T15: comparação das nove VIs; U2: comparação na captura sintética padrão. |
| 12 | T19 protege as dependências do núcleo; U11 exige exatamente o consumidor autorizado. |
| 13 | U3–U6 e U13: ausência de FD em recusadas e europeias; recusa, erro, alerta e baixa sensibilidade preservam todos os resultados legados. |
| 14 | U9, V2 e porta byte a byte por plataforma contra base; CLI padrão `LIVE_NOT_ACTIVATED`, rc 3. |
| 15 | U1, U6–U8, V1–V4; todos os campos legados internos contra `49b12dd` e linhas públicas de `7d47d3b` sem a chave aditiva. |
| 16 | B1 no PR01: 340 ms p95 de relógio e 336 ms mediana CPU. Núcleo intacto; repetição no head final registrada no portão. |
| 17 | Escopo: `american_demo.py`, `demo_chain.py` e, por adendo, só `_row_view` no MCP. Portões Mac/Linux do head na revisão. |
| 18 | U12: fator 1000, carry não nulo, prazo não redondo e mark deslocado provam o mesmo alvo e insumos da árvore. |
| 19 | U15: mesma instância de malha, e diferença de preço na VI principal. |

U10 cobre o perfil FD ausente ou inválido. U14 usa o limiar YAML de 0,0005
nos dois sinais, com igualdade nominal e os valores representáveis imediatamente
abaixo e acima. O RED `c68358e` precede as duas correções da revisão.
V1–V4 cobrem JSON do diagnóstico, omissão em linhas inelegíveis, erro visível sem
mudar campos anteriores e igualdade após retirar somente o objeto aditivo. Decisão de integração e fechamento continuam
pendentes; nenhum teste usa dado real, token ou dependência nova, e nenhum ativa mercado.

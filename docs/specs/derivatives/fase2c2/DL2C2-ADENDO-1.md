# DL2C2 — Adendo 1 (Francisco, 2026-11-20)

Vale sobre o cartão DL2C2 (versão 2) e sobre o ADR-0028 onde houver conflito. Escrito pelo
Claude a partir de decisão de Francisco e de uma sugestão do Codex que Francisco aceitou.
Destino: `docs/specs/derivatives/fase2c2/DL2C2-ADENDO-1.md`, copiado sem edição, no mesmo
commit de documentação.

## A1 — Configuração mantida

Decisão de Francisco: **a árvore continua com 200 passos e as diferenças finitas com malha
400 por 200**, inclusive e principalmente na conferência contra o oráculo.

Consequências:

- As duas decisões que o ADR-0028 (R6) deixava para depois da tabela estão tomadas. A fase
  fecha com a tabela entregue e a revisão do Claude, sem decisão pendente.
- Os itens 2 e 3 da tabela de fechamento (árvore com 400 e 800 passos; malhas 200 por 100 e
  800 por 400) continuam, como informação. Eles não disparam mudança de configuração neste
  PR nem no fechamento.
- Se a configuração mantida falhar em algum limite dos testes O5 a O10, vale a regra do
  cartão: parar e reportar. A decisão não autoriza alargar tolerância.

## A2 — Tempo: p95 de relógio, além da mediana de CPU

Sugestão do Codex, aceita por Francisco. A mediana pode esconder os casos lentos.

Medir no Mac, com uma execução de aquecimento e depois 22 execuções, e registrar em
`DL2C2-PR01.md`, lado a lado, **p95 do tempo de relógio** e **mediana de CPU**, para:

1. uma inversão pela árvore com 200 passos, no caso mais lento dos 67 identificáveis;
2. uma inversão pelas diferenças finitas na malha 400 por 200, no caso mais lento dos 67;
3. o arquivo `test_quantlib_oracle.py` inteiro (aqui bastam 5 execuções).

Dizer qual foi o caso mais lento de cada motor. Os orçamentos em vigor não mudam: 210 ms
para a árvore (ADR-0026) e 700 ms provisórios para as diferenças finitas (ADR-0027).
Passar de um deles é achado a reportar, não motivo para trocar configuração.

Nos itens 2 e 3 da tabela, as configurações alternativas também levam p95 de relógio e
mediana de CPU.

## A3 — `B21` e `C01` em destaque, e uma pendência antes do uso real

Nos dois casos o preço de referência fica a 2e-7 do valor intrínseco. As duas inversões de
produção devolvem `ok`, com erro de volatilidade de 0,055 e 0,053 em `B21` e de 0,028 e
0,026 em `C01` (árvore e diferenças finitas, medido pelo Claude na `main`). Os dois motores
concordam entre si e os dois estão errados em vários pontos percentuais.

- Na tabela de fechamento, esse resultado abre o documento, antes do item 1, com os dois
  casos, o preço, o intrínseco, e a volatilidade que cada inversão devolveu.
- Fica registrada a pendência **"identificação de VI perto do intrínseco"**: nenhuma VI de
  dado real é publicada como identificada antes de essa regra existir. Dono: Francisco decide
  a regra; Claude escreve o cartão. Entra junto do alerta de relevância do ADR-0028, S3.
- Neste PR nada é corrigido: zero produção, como manda o cartão.

## A4 — Texto do `current_state.md`

No bloco da seção 10 do cartão, o último parágrafo passa a ser:

```
Próxima ação: Claude revisa o DL2C2-PR01. Configuração mantida por Francisco: árvore com
200 passos e malha 400 por 200. A fase fecha com a tabela de resultados e a revisão.

Pendência antes de qualquer uso com dado real: identificação de VI perto do intrínseco
(casos B21 e C01 do oráculo). Dono: Francisco decide a regra; Claude escreve o cartão.
```

# DL2-PR00 - ADR-0025 e SDD do Marco 2A

Branch: `docs/dl2-pr00-adr-0025-fase2a`
Base: `main` em `1421116`
Status: EM_REVISAO

## Escopo

So documentacao. Autoriza e especifica o Marco 2A da Fase 02 do Lab de
Derivativos. Nenhuma linha de codigo.

Criados:

- `docs/ADR/ADR-0025-laboratorio-derivativos-fase2a.md`
- `docs/specs/derivatives/fase2/SDD_FASE2A.md`
- `docs/specs/derivatives/fase2/DL2-PR00.md` (este cartao)

Alterados, com o minimo de linhas:

- `docs/04_MEM/current_state.md`: bloco "Fase 02 - Marco 2A" abaixo do
  cabecalho; nada apagado.
- `docs/specs/derivatives/BACKLOG.md`: item de CRR/BS-1993 aponta para o
  ADR-0025.
- `docs/ADR/ADR-0023-laboratorio-derivativos-fase1.md`: uma linha no fim do
  "Escopo negativo".

Fora do escopo: qualquer arquivo em `backend/`, `config/`, `tests/`,
`scripts/`; `pyproject.toml`, `uv.lock`, `CLAUDE.md`, `AGENTS.md`,
`.claude/`; dependencia nova; arquivo de memoria novo.

## Aceite

1. O diff contem apenas arquivos sob `docs/`.
2. `git diff --check origin/main` sem saida.
3. Gate sem integracao com 0 falhas e a mesma contagem de antes.
4. Linhas novas com no maximo 100 colunas.
5. O caso a mao do SDD foi recalculado, no por no.
6. Nenhuma regra da B3, do BOVA11 ou de proventos afirmada de memoria;
   tudo que depende disso esta em "Pendencias".
7. Sem merge: o PR para em revisao.

## Evidencia

Gate: `uv run pytest tests/ -q --ignore=tests/integration --timeout=120`,
macOS, na arvore desta branch.

- Antes (`main` em `1421116`): `8126 passed, 15 skipped, 261 subtests
  passed`.
- Depois: a mesma contagem, 0 falhas (ultima linha no corpo do PR).

Caso a mao (put, 2 passos, `S=50`, `K=52`, `r=5%` continuo, `u=1.2`,
`d=0.8`), recalculado em Python no terminal, sem commitar:

- `p = 0.6281777409`, desconto por passo `0.9512294245`;
- europeia `4.1926542806`; americana `5.0896324742`.

## Divergencia em relacao ao prompt do PR

O prompt pedia europeia 4.1923 e americana 5.0894 com tolerancia 5e-5. O
recalculo nao bateu: esses sao os valores de livro, obtidos com `p`
arredondado para 0.6282. A sessao parou e relatou; Francisco escolheu
registrar os valores exatos (4.192654 e 5.089632) e manter a tolerancia.

## Observacao exploratoria (nao e evidencia de aceite)

Uma arvore CRR europeia ingenua, em Python puro, foi rodada no terminal so
para checar se a tolerancia proposta do criterio 2 e plausivel. Em 216
combinacoes com `S = 100`, o maior erro absoluto contra BSM foi cerca de
0.008 em `N = 1000/1001` e cerca de 0.039 em `N = 200/201` (pior caso com
`sigma = 0.6` e `T = 2`). Um preco com `N = 1000` levou cerca de 21 ms.

Leitura: 0.03 tem folga em `N >= 1000`, mas nao serviria para o par
200/201, cuja tolerancia segue pendente no SDD. Estes numeros nao
substituem a medicao do DL2-PR04 nem a referencia independente.

## Proxima acao

Francisco revisa o PR. Aprovado, o ADR-0025 passa a Accepted e o DL2-PR01
pode ter sua SPEC escrita.

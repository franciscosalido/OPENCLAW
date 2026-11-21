# DL2C2-PR01 — Evidências de fechamento

Base `55fe712`. Testes e documentação; zero linha de produção. Dados sintéticos.

## B21 e C01: VI perto do intrínseco

| Caso | Preço QuantLib | Intrínseco | Excesso | Sigma gerador | VI CRR | VI DF |
|---|---:|---:|---:|---:|---:|---:|
| B21 | 20.0000002384 | 20 | 2.384005e-07 | 0.2 | 0.254844288 (ok) | 0.252967413 (ok) |
| C01 | 10.0000005911 | 10 | 5.911496e-07 | 0.25 | 0.277744113 (ok) | 0.275633679 (ok) |

Os dois motores reportam `ok`, mas erram em pontos percentuais de VI.
A pequena diferença entre motores não demonstra identificabilidade.
Pendência antes de publicar qualquer VI de mercado como identificada:
**identificação de VI perto do intrínseco**. Francisco decide a regra e Claude
escreve o cartão com o alerta de relevância do ADR-0028 (S3). Nada foi corrigido aqui.

## 1. Erros máximos por grupo

Preço por unidade; VI em frações anuais. Primeiro, todos os 69 casos.

| Grupo | Casos | Preço CRR | Preço DF | VI CRR | VI DF | Diferença de VI entre motores |
|---|---:|---:|---:|---:|---:|---:|
| A | 18 | 0.00354137272 (A11) | 0.000349741731 (A06) | 0.000323804231 (A01) | 3.38670657e-05 (A01) | 0.000357671296 (A01) |
| B | 27 | 0.00635720775 (B14) | 0.000936439089 (B18) | 0.0548442877 (B21) | 0.0529674135 (B21) | 0.00187687422 (B21) |
| C | 18 | 0.00967139942 (C11) | 0.00131112018 (C11) | 0.0277441126 (C01) | 0.0256336795 (C01) | 0.00211043307 (C01) |
| D | 6 | 0.0206019991 (D01) | 0.00872274891 (D02) | 0.000372858097 (D01) | 0.00022994287 (D02) | 0.000486357557 (D01) |

Separadamente, VI apenas nos 67 identificáveis (preços ainda nos 69):

| Grupo | Casos | Preço CRR | Preço DF | VI CRR | VI DF | Diferença de VI entre motores |
|---|---:|---:|---:|---:|---:|---:|
| A | 18 | 0.00354137272 (A11) | 0.000349741731 (A06) | 0.000323804231 (A01) | 3.38670657e-05 (A01) | 0.000357671296 (A01) |
| B | 27 | 0.00635720775 (B14) | 0.000936439089 (B18) | 0.000245436517 (B11) | 6.13391645e-05 (B24) | 0.0002464007 (B11) |
| C | 18 | 0.00967139942 (C11) | 0.00131112018 (C11) | 0.00025847518 (C05) | 3.16847282e-05 (C11) | 0.000230704175 (C05) |
| D | 6 | 0.0206019991 (D01) | 0.00872274891 (D02) | 0.000372858097 (D01) | 0.00022994287 (D02) | 0.000486357557 (D01) |

## 2–3. Passos, malhas e latência no Mac

MacBook Pro, Apple M4 Pro, macOS 15.8.1, Python 3.12.13. Para cada configuração:
uma execução por caso identificável para localizar o de maior tempo de relógio;
nesse caso, um aquecimento e 22 inversões completas sem cache.
P95 pelo posto mais próximo (`ceil(0,95 × n)`), sem interpolação.

| Motor/configuração | Máximo de erro VI (caso) | Mediana de erro VI | Caso mais lento | CPU mediana (ms) | Relógio p95 (ms) | Recusas |
|---|---:|---:|---|---:|---:|---|
| tree-200 | 0.000372858097 (D01) | 8.20908929e-05 | A03 | 146.985 | 147.931 | nenhuma |
| tree-400 | 0.00027344998 (C05) | 3.6852224e-05 | A03 | 590.045 | 613.559 | nenhuma |
| tree-800 | 0.000142311336 (C05) | 1.89695544e-05 | C17 | 2480.278 | 2521.201 | nenhuma |
| fd-200x100 | 0.000949643497 (D02) | 3.5363371e-05 | C11 | 95.310 | 96.109 | nenhuma |
| fd-400x200 | 0.00022994287 (D02) | 8.26860496e-06 | C11 | 394.314 | 404.588 | nenhuma |
| fd-800x400 | 5.44959731e-05 (D02) | 2.15732676e-06 | D05 | 1760.094 | 1784.181 | nenhuma |

Arquivo de testes do oráculo, uma execução de aquecimento e cinco medidas:
**45.905 s de CPU mediana / 46.177 s de relógio p95**.

Os orçamentos em vigor continuam 210 ms de CPU mediana para a árvore de 200
passos e 700 ms provisórios de relógio p95 para DF 400 × 200. As alternativas
são medições informativas; nenhuma configuração muda neste PR.

## 4. Erro de preço, usando o mesmo sigma conhecido

| Recorte | Casos | Erro CRR máximo | Erro DF máximo |
|---|---:|---:|---:|
| Prazo ≤ 30 dias | 13 | 0.000972970838 (A01) | 0.000148565069 (C07) |
| Prazo 31–182 dias | 21 | 0.0046916249 (B11) | 0.000339453897 (C09) |
| Prazo 183–365 dias | 17 | 0.00635720775 (B14) | 0.000525161011 (B24) |
| Prazo > 365 dias | 18 | 0.0206019991 (D01) | 0.00872274891 (D02) |
| S/K < 0,97 | 22 | 0.00762046905 (C05) | 0.000866844181 (B09) |
| 0,97 ≤ S/K ≤ 1,03 | 16 | 0.0117501354 (D02) | 0.00872274891 (D02) |
| S/K > 1,03 | 31 | 0.0206019991 (D01) | 0.0062643558 (D01) |
| Rendimento zero | 30 | 0.0206019991 (D01) | 0.0062643558 (D01) |
| Rendimento positivo | 39 | 0.0117501354 (D02) | 0.00872274891 (D02) |

## 5. BSM europeu em sombra (informativo)

Inversão direta do preço americano de referência pelo BSM europeu.

| Grupos | Casos | Erro VI ≤ 0,001 | Sem solução |
|---|---:|---:|---:|
| A | 18 | 18 | 0 |
| B/C/D | 51 | 11 | 0 |

## 6. B21 e C01

Valores e estados completos na abertura.

## 7. Critério 11 — seis mutações

Clones descartáveis separados, uma alteração por clone, e somente
`python -m pytest -q -x tests/unit/derivatives/test_quantlib_oracle.py`.
Todos falharam por uma asserção numérica; nenhum por coleta ou importação.

| Mutação | Primeiro teste que falhou |
|---|---|
| D1 | `test_o5_tree_price[B03]` |
| D2 | `test_o5_tree_price[B01]` |
| D3 | `test_o5_tree_price[A01]` |
| D4 | `test_o7_fd_price[B02]` |
| D5 | `test_o7_fd_price[A01]` |
| D6 | `test_o7_fd_price[A07]` |

Proveniência, comandos de geração e hashes:
[PROVENANCE.md](../../../../tests/fixtures/derivatives/reference/quantlib/PROVENANCE.md).
Os logs brutos estão fora do Git no diretório de evidências do cartão.

## Revisão independente: GO (Claude, 2026-11-21 UTC)

Head do autor: `d0e6974`.

- Zero diferença em `backend`, `config`, `scripts`, `pyproject.toml`, `uv.lock` e arquivos
  protegidos. ADR-0028, cartão e Adendo 1 copiados sem alteração; gerador com o SHA-256 do
  cartão.
- Referência do Mac contra a do revisor em x86-64: maior diferença relativa de 4,5e-13.
  Proveniência com imagem por digest e pacote por hash.
- Portão em clone limpo, Linux aarch64: 10.750 aprovados, 16 pulados, 261 subtestes;
  `mypy --strict` e `pyright` sem erro. Os 490 testes do oráculo em 47 s. macOS não
  reproduzido pelo revisor.
- Antes do PR, o revisor rodou o código da `main` contra a referência de x86-64 e obteve os
  mesmos máximos por grupo desta tabela.
- Mutação do revisor, só com os testes do oráculo, com oito trocas diferentes das seis do
  cartão: sete mortas. A viva tira o desconto do strike na borda distante das diferenças
  finitas, que fica a seis desvios do spot e não alcança o preço; essa linha é presa por
  teste do DL2C1.
- Os testes novos não trazem anotação de tipo nas funções. Não muda comportamento; fica
  como nota de estilo.

Pareceres da skill sobre `d0e6974`, lidos depois do veredito e antes do merge: parecer
completo (SHA-256 `39a40665…127d`), sem bloqueante; relatório de simplificação v0.2
(SHA-256 `9a31a68b…5433`), com uma sugestão não bloqueante, não aplicada. A lacuna de teste
apontada no relatório (O12 não fixava as chaves de cada linha) foi fechada no commit do
parecer.

O que a tabela mostra, em uma linha cada:

- Os dois motores do projeto ficam dentro do erro esperado nos 67 casos identificáveis.
- Com a configuração mantida, a árvore erra no máximo 3,7e-4 de volatilidade e as diferenças
  finitas 2,3e-4; os dois cabem nos orçamentos de tempo.
- Em `B21` e `C01` os dois motores concordam e os dois erram em pontos percentuais. A
  comparação entre motores não detecta esse erro.
- A sombra BSM acerta os 18 casos do grupo A e só 11 dos outros 51.

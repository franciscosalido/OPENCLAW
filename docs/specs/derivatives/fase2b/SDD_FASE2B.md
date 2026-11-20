# SDD - Fase 02, Marco 2B - ponte americana

Autor: Claude (2026-11-19). Autoridade: ADR-0026. Base: `main` em `ff0c1be`.
Implementa: Codex. Revisa e integra: Claude. Estado de prontidao: A, sem mudanca.

## Objetivo

Ao fim do marco, uma linha americana da chain sintetica sai com preco e volatilidade
implicita calculados pela arvore CRR, ou com uma recusa que diz exatamente qual precondicao
faltou. Tudo offline, atras de uma chave desligada por padrao.

## Criterios de aceite

1. **Ancoras da ponte (DL2B-PR01).** Com `steps = 200`, a ponte reproduz a media dos pares
   `crr_06`/`crr_07` e `crr_16`/`crr_17` da referencia do 2A, dentro de
   `1e-11 * max(1, ref)`.
2. **Recusas (DL2B-PR01).** 100% das linhas da tabela de recusas do cartao devolvem o motivo
   exato, com preco, gregas e regime nulos. Nenhuma excecao escapa da ponte para entrada de
   tipo valido.
3. **Fonte unica do rendimento (DL2B-PR01).** Em 100% dos resultados suportados, as chaves
   `dividend_yield` e `strike_adjusted_by_exchange_assumed` nao aparecem nas hipoteses, e
   `carry_dividend_yield` e o valor usado na arvore.
4. **Erro de discretizacao declarado (DL2B-PR01).** Nos 12 casos do cartao, com
   `steps = 400` e `S = 100`, o preco da ponte fica a no maximo 0.01 do valor de referencia
   de alta resolucao. Medido antes do cartao: 0.0030.
5. **Isolamento (DL2B-PR01 a 03).** Um unico modulo de producao importa binomial, termos e
   carry; zero modulo importa a ponte ate o DL2B-PR04.
6. **IV americana (DL2B-PR02).** Ida e volta: preco da ponte com `sigma` conhecido, invertido,
   devolve `sigma` com erro absoluto <= 1e-6, em pelo menos 40 casos. Tempo por inversao
   medido no Mac e registrado. O limite de tempo e fixado no cartao, antes do codigo.
7. **Origem dos termos (DL2B-PR03).** 100% das series sem registro, com registro vencido ou
   com registro divergente do contrato sao recusadas com motivo proprio.
8. **Ligacao (DL2B-PR04).** Chave desligada: saida da demo identica byte a byte a de
   `ff0c1be`, por plataforma. Chave ligada: toda linha americana tem preco ou motivo de
   recusa especifico, e nenhuma linha europeia muda.
9. **Regressao (todos).** Suite verde; nenhum arquivo de producao existente em `ff0c1be` e
   alterado antes do DL2B-PR04; CLI padrao devolve `LIVE_NOT_ACTIVATED`.
10. **Disciplina (todos).** No maximo 400 linhas de producao por PR; zero dependencia nova;
    arquivos protegidos intactos; contagem igual em macOS e Linux.

## Nao-objetivos do marco

Gregas americanas. Dividendo discreto. Richardson, suavizacao, Leisen-Reimer, Tian ou
qualquer troca de arvore. Bjerksund-Stensland. Superficie de volatilidade. Persistencia.
Homologacao com dado real (estado B). Ativacao para agentes (estado C). Ordens.

## Riscos e mitigacao

| Risco | Mitigacao |
|---|---|
| Rendimento contado duas vezes (strike ajustado e `q > 0`) | Trava do DL2-PR02 e criterio 3 |
| Ler a diferenca entre `N` e `N + 1` como limite de erro | ADR-0026, regra 3 |
| IV americana lenta demais em Python puro | Criterio 6 mede antes de ligar; D1 e D4 do ADR |
| Excecao na guarda vira porta aberta | Excecao por caminho fixo; teste com importador intruso |
| Ponte vista como preco de mercado | Estado A; hipoteses e modelo em todo resultado |
| Termos vencidos usados em silencio | Criterio 7; ate la a ponte so recebe termos do chamador |

## Plano

| PR | Entrega testavel |
|---|---|
| DL2B-PR01 | `price_american_contract` pura; criterios 1 a 5 |
| DL2B-PR02 | `american_implied_vol`; criterio 6; medicao para D1 e D4 |
| DL2B-PR03 | registro e resolvedor de termos e carry; criterio 7 |
| DL2B-PR04 | chave, ligacao na chain, MCP e CLI; criterios 8 e 9; fechamento |

## Pendencias

- D1 a D4 do ADR-0026.
- Vigencia dos termos frente a data de avaliacao: a ponte do DL2B-PR01 nao confere data.
  Fica para o DL2B-PR03.

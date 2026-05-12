# Evaluation — Sprint RAG-1A

## Por que este diretório existe

Este diretório existe para medir retrieval antes de introduzir memória, MCP,
LangGraph ou qualquer nova camada de orquestração.

A hipótese do Sprint RAG-1A é:

> Hybrid retrieval (dense + sparse) melhora significativamente o recall de
> queries financeiras brasileiras em comparação a dense-only.

Sem benchmark, essa hipótese não pode ser validada ou refutada com rigor.

## Filosofia

- Medir antes de construir.
- Sem número, não há ciência; há entusiasmo.
- O benchmark deve ser adversarial para dense-only: cada query precisa depender
  de um detalhe do corpus sintético local, não de conhecimento paramétrico do
  modelo.
- Tickers, siglas, jargão BR, cenários sintéticos e termos multilingual são
  exatamente o tipo de consulta que similaridade semântica pura tende a perder.
- Este PR define contrato e goldset placeholder. Ele não executa retrieval,
  embeddings, Qdrant, BM25, reranking ou geração.

## Definição de query adversarial

Uma query adversarial para este benchmark deve cumprir as três condições:

- A resposta correta só deve existir no corpus sintético local.
- Dense-only deve ter chance real de recuperar o documento errado por
  polissemia, proximidade semântica espúria ou perda de exact match.
- O resultado de retrieval deve ser verificável por `expected_doc_ids` e
  `expected_terms`, sem depender da memória do modelo.

Perguntas paramétricas genéricas, como "o que é duration?" ou "como calcular
EBITDA?", não pertencem a este benchmark.

## Categorias de query

| Código | O que testa |
|---|---|
| ticker | Exact match de código B3, como PETR4 e VALE3 |
| fii | Fundos imobiliários: DY, vacância, tipo e segmento |
| renda_fixa | LCI, CRI, CDB, debêntures e crédito privado |
| macro_br | Selic, IPCA, duration, spread e curva de juros |
| estrategia | Rebalanceamento, risco, correlação e alocação |
| siglas | Termos técnicos como PVPA, CDI e VPA |
| multilingual | Termos PT/EN misturados do mercado brasileiro |

## Schema de benchmark_queries.yaml

Cada query deve ter estes campos:

- `id`: identificador estável no formato `CATEGORIA_NNN`.
- `query`: texto sintético da consulta.
- `category`: uma das 7 categorias oficiais.
- `expected_doc_ids`: lista não vazia de documentos relevantes esperados.
- `expected_terms`: lista não vazia de termos que devem aparecer em chunks
  relevantes.
- `notes`: campo opcional para contexto de revisão.

Prefixos válidos:

| Categoria | Prefixo |
|---|---|
| ticker | TICKER |
| fii | FII |
| renda_fixa | RENDA_FIXA |
| macro_br | MACRO_BR |
| estrategia | STRAT |
| siglas | SIGLA |
| multilingual | MULTI |

IDs são imutáveis depois de criados. Se uma query for removida, o ID fica
aposentado e não deve ser reaproveitado.

## expected_results.yaml

`expected_results.yaml` mapeia `query_id -> doc_id -> relevance_grade`.

Graus de relevância:

- `2`: altamente relevante.
- `1`: parcialmente relevante.
- `0`: irrelevante.

Os IDs de documento deste PR são placeholders sintéticos. PRs futuros podem
substituí-los por IDs reais do corpus validado, mas sem renumerar queries.

## Como contribuir com novas queries

1. Escolha uma categoria existente.
2. Crie um ID estável no formato `CATEGORIA_NNN`.
3. Preencha todos os campos obrigatórios.
4. Ancore a pergunta em um documento, corpus, cenário, cláusula, marcador,
   gatilho, proxy, nota ou regra sintética local.
5. Nunca use dados reais de portfólio, conta, corretora, saldos, posições,
   documentos privados ou qualquer conteúdo Level 0.
6. Abra PR com issue vinculada e explique qual lacuna de retrieval a query
   mede.

## O que não vai aqui

- Dados reais de portfólio ou corretora.
- Segredos, credenciais, documentos privados ou dados pessoais.
- Resultados locais de benchmark. `evaluation/results/` é área local e deve
  ficar fora do versionamento, exceto `.gitkeep`.
- Código de retrieval, embeddings, Qdrant, BM25, LiteLLM, MemoryOS, LangGraph,
  MCP, ColBERT ou DBSF.

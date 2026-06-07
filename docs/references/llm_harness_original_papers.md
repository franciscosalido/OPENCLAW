# LLM Harness Original Papers and PR-08 Methodology

## Como isso se aplica ao PR-08

PR-08 usa cenários versionados, fixtures determinísticas, live calls opt-in,
artefatos padronizados e uma política rígida: no prompt/response/chunk/vector/secrets in artifacts.
LLM-as-judge não é hard gate.

## EleutherAI LM Evaluation Harness

Reference: EleutherAI LM Evaluation Harness and the few-shot evaluation
methodology from Gao et al.

Why it matters:

- harness reproduzível;
- tarefas declarativas;
- modelo/teste desacoplados;
- artefatos e logs padronizados.

How PR-08 applies it:

- test scenarios versionados;
- live calls opt-in;
- fixtures determinísticas;
- nenhum segredo em artefatos.

## HELM

Reference: Holistic Evaluation of Language Models.

Why it matters:

- avaliação multidimensional;
- transparência;
- métricas além de acurácia.

How PR-08 applies it:

- health;
- correctness;
- latency;
- safety;
- no-leak;
- robustness;
- degradation.

## RAGAS

Reference: RAGAS evaluation for retrieval-augmented generation.

Why it matters:

- avaliação de RAG por contexto, retrieval e geração.

How PR-08 applies it:

- golden synthetic questions;
- Recall@5;
- groundedness simples;
- retrieval quality separado de LLM synthesis.

## MT-Bench and Chatbot Arena

Reference: MT-Bench, Chatbot Arena and LLM-as-a-judge work.

Why it matters:

- useful comparative signal;
- known biases and instability.

How PR-08 applies it:

- LLM-as-judge não é hard gate;
- any LLM judgment is opt-in diagnostic;
- deterministic smoke remains source of truth.

## Generative Agents

Reference: Generative Agents and memory stream methodology.

Why it matters:

- persistent memory;
- multi-step agent behavior;
- session continuity.

How PR-08 applies it:

- session persistence test;
- agent_state update/readback;
- second execution recovers state.

## Operational Rules

- live calls opt-in;
- no prompt/response/chunk/vector/secrets in artifacts;
- LLM-as-judge não é hard gate;
- local-first services remain the only runtime target.

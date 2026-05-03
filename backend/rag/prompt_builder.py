"""Prompt construction for local RAG answers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.rag._validation import validate_question
from backend.rag.context_packer import RetrievedChunk


DEFAULT_SYSTEM_PROMPT = """Voce e o assistente local do OpenClaw.
Responda somente com base no CONTEXTO recuperado.
Nao use conhecimento externo para fatos especificos.
Se o contexto nao sustentar a resposta, diga:
"Nao ha contexto local suficiente para responder com seguranca."
Cite fontes no formato [doc_id#chunk_index].
Nunca peca nem revele dados reais de carteira, credenciais ou documentos privados.
"""

NO_CONTEXT_MESSAGE = (
    "Nao ha contexto local recuperado. Responda apenas que nao ha contexto local "
    "suficiente para responder com seguranca."
)


@dataclass(frozen=True)
class PromptBuilder:
    """Build chat messages from retrieved local context."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    no_context_message: str = NO_CONTEXT_MESSAGE

    def build(
        self,
        question: str,
        chunks: Sequence[RetrievedChunk],
        thinking_mode: bool = False,
        conciseness_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        """Return chat messages with recovered context and citation rules."""

        clean_question = validate_question(question)
        context = self._format_context(chunks)
        thinking_directive = "/think" if thinking_mode else "/no_think"
        response_instructions = [
            "- Responda em portugues brasileiro.",
            "- Use apenas o contexto recuperado.",
            "- Inclua citacoes no formato [doc_id#chunk_index].",
            "- Se o contexto for insuficiente, diga isso claramente.",
        ]
        if conciseness_instruction is not None:
            instruction = conciseness_instruction.strip()
            if instruction:
                response_instructions.append(f"- {instruction}")
        user_content = (
            f"{thinking_directive}\n\n"
            f"PERGUNTA:\n{clean_question}\n\n"
            f"CONTEXTO RECUPERADO:\n{context}\n\n"
            "INSTRUCOES DE RESPOSTA:\n"
            + "\n".join(response_instructions)
        )

        return [
            {"role": "system", "content": self.system_prompt.strip()},
            {"role": "user", "content": user_content},
        ]

    def _format_context(self, chunks: Sequence[RetrievedChunk]) -> str:
        if not chunks:
            return self.no_context_message

        blocks = []
        for chunk in chunks:
            blocks.append(
                "\n".join(
                    [
                        f"[{chunk.citation_id}] (score: {chunk.score:.3f})",
                        chunk.text.strip(),
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)

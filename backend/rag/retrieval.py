from typing import List
from langchain_core.documents import Document
from rag.vectordb import similarity_search

SYSTEM_PROMPT = """You are a study assistant for college students in India. You answer \
questions using ONLY the context provided below, which comes from documents the institution has \
uploaded. It is about helping students know things about the college Pre Admission.

Rules:
- Answer using only the given context. Do not use outside knowledge to fill gaps.
- If the context does not contain enough information to answer, say so plainly \
  instead of guessing. Do not make up facts, page numbers, or sources.
- When you use information from the context, mention which document it came from \
  (use the filename given in the context, e.g. "According to midterm_notes.pdf...").
- If the context contains conflicting information from different documents, point out \
  the conflict rather than picking one silently.
- Keep answers clear and student-friendly. Use short paragraphs or bullet points for \
  multi-part answers. Don't pad with filler.
- If the retrieved context is unrelated to the question, say you couldn't find relevant \
  material rather than answering from general knowledge.
- Talk in whichever language the user sends message, e.g. "College me kon konse course h?" \
-> "Btech, Mtech, etc.".
Context:
{context}
"""


def retrieve_context(query: str, k: int = 4) -> List[Document]:
    # Semantic search over pgvector. Returns the top-k most relevant chunks.
    return similarity_search(query, k=k)


def format_context(documents: List[Document]) -> str:
    # Turns retrieved chunks into a labeled block the LLM can cite from.
    if not documents:
        return "(No relevant documents were found for this query.)"

    blocks = []
    for doc in documents:
        source = doc.metadata.get("source", "unknown file")
        blocks.append(f"[Source: {source}]\n{doc.page_content}")

    return "\n\n---\n\n".join(blocks)


def build_system_prompt(query: str, k: int = 4) -> tuple[str, List[Document]]:
    """One-shot helper: retrieves + formats + fills the prompt template.
    Returns (system_prompt, retrieved_documents) — keep the documents around
    so you can report sources back to the frontend alongside the answer."""
    documents = retrieve_context(query, k=k)
    context = format_context(documents)
    return SYSTEM_PROMPT.format(context=context), documents
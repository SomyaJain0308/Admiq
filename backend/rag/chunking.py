from typing import List, Dict

from pydantic import BaseModel, Field

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import create_context_cache
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage

# Only used for cache deletion
from google import genai as _raw_genai


HEADERS_TO_SPLIT_ON = [("#", "H1"), ("##", "H2"), ("###", "H3")]
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBEDDING_MODEL = "models/gemini-embedding-001"
VECTOR_SIZE = 768

CONTEXT_MODEL = "gemini-3.5-flash"
BATCH_SIZE = 25
CACHE_TTL = "600s"
MIN_CACHE_TOKENS = 4096
SYSTEM_INSTRUCTION = ("You are helping index a college pre-admission document for retrieval. You will be given chunks extracted from the document and must situate each one within the whole document.")


header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT_ON)
size_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


class ChunkContexts(BaseModel):
    contexts: List[str] = Field(description="1-2 sentence context per chunk, situating it within the document (e.g. which course/programme/section/policy it belongs to).")


def chunk_markdown(markdown_text: str, filename: str, extra_metadata: Dict = None) -> List[Document]:
    # Split markdown by headers first, then by size if a section is too big.
    extra_metadata = extra_metadata or {}
    header_chunks = header_splitter.split_text(markdown_text)

    final_chunks = []
    for i, doc in enumerate(header_chunks):
        sub_chunks = size_splitter.split_text(doc.page_content)
        for j, sub_text in enumerate(sub_chunks):
            if not sub_text.strip():
                continue
            final_chunks.append(Document(
                page_content=sub_text,
                metadata={
                    "source": filename,
                    "section_index": i,
                    "chunk_index": j,
                    **doc.metadata,      # H1/H2/H3 headers if present
                    **extra_metadata,    # e.g. quality_score, method, upload_id
                }
            ))

    return final_chunks



def _build_batch_prompt(chunk_batch: List[Document]) -> str:
    chunks_block = "\n\n".join(
        f'<chunk id="{i}">\n{c.page_content}\n</chunk>'
        for i, c in enumerate(chunk_batch)
    )
    return (f"Below are chunks extracted from the document. For each chunk, write a short 1-2 sentence context that situates it within the overall document, to improve retrieval of this chunk.\n\n{chunks_block}\n\nReturn one context string per chunk, in the same order as the chunk ids.")



def add_context_to_chunks(document_text: str, chunks: List[Document]) -> List[Document]:
    if not chunks:
        return []

    base_llm = ChatGoogleGenerativeAI(model=CONTEXT_MODEL)
    
    batches = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batches.append(batch)

    doc_tokens = base_llm.get_num_tokens(document_text)  # real tokenizer count, LangChain-native
    use_explicit_cache = doc_tokens >= MIN_CACHE_TOKENS and len(batches) > 1

    cache = None
    structured_llm = None

    if use_explicit_cache:
        cache = create_context_cache(base_llm, messages=[SystemMessage(content=SYSTEM_INSTRUCTION), HumanMessage(content=document_text)], ttl=CACHE_TTL)
        cached_llm = ChatGoogleGenerativeAI(model=CONTEXT_MODEL, cached_content=cache.name)
        structured_llm = cached_llm.with_structured_output(ChunkContexts, method="json_schema", include_raw=True)
    else:
        structured_llm = base_llm.with_structured_output(ChunkContexts, method="json_schema", include_raw=True)

    contextualized: List[Document] = []
    try:
        for batch in batches:
            prompt = _build_batch_prompt(batch)
            if cache is not None:
                result = structured_llm.invoke(prompt)
            else:
                result = structured_llm.invoke([SystemMessage(content=SYSTEM_INSTRUCTION), HumanMessage(content=f"{document_text}\n\n{prompt}")])

            parsed: ChunkContexts = result["parsed"]
            raw_msg = result["raw"]

            if len(parsed.contexts) != len(batch):
                raise ValueError(f"Expected {len(batch)} contexts, got {len(parsed.contexts)}")

            # confirm caching is actually hitting
            usage = getattr(raw_msg, "usage_metadata", None) or {}
            cached_tokens = usage.get("input_token_details", {}).get("cache_read", 0) if usage else 0
            if cached_tokens:
                print(f"[cache hit] {cached_tokens} tokens served from cache")

            for chunk, ctx in zip(batch, parsed.contexts):
                contextualized.append(Document(
                    page_content=f"{ctx.strip()}\n\n{chunk.page_content}",
                    metadata={**chunk.metadata, "raw_chunk": chunk.page_content},
                ))
    finally:
        if cache is not None:
            # No LangChain-native delete yet — drop to the raw client just for this.
            _raw_genai.Client().caches.delete(name=cache.name)

    return contextualized


# ---------------------------------------------------------------------------
# Step 3: full pipeline — chunk, contextualize, embed
# ---------------------------------------------------------------------------

def ingest_markdown(markdown_text: str, filename: str, college_id: str, extra_metadata: Dict = None):
    chunks = chunk_markdown(markdown_text, filename, extra_metadata={"college_id": college_id, **(extra_metadata or {})})
    contextualized_chunks = add_context_to_chunks(markdown_text, chunks)

    embedder = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, output_dimensionality=VECTOR_SIZE)
    texts = [c.page_content for c in contextualized_chunks]
    vectors = embedder.embed_documents(texts)

    # Hand these off to your pgvector insert — each row gets:
    #   - embedding: vectors[i]
    #   - content: contextualized_chunks[i].page_content   (embed/display contextualized text if you want the blurb visible)
    #   - raw_chunk: contextualized_chunks[i].metadata["raw_chunk"]  (use THIS when feeding the LLM the final answer context)
    #   - metadata: contextualized_chunks[i].metadata
    return contextualized_chunks, vectors
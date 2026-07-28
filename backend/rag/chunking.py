import logging
from typing import List, Dict
from pydantic import BaseModel, Field
from google import genai as _raw_genai # Only used for cache deletion

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI, create_context_cache
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage

from backend.rag.config import get_settings
from backend.database import models

logger = logging.getLogger(__name__)
settings = get_settings()


HEADERS_TO_SPLIT_ON = [("#", "H1"), ("##", "H2"), ("###", "H3")]
SYSTEM_INSTRUCTION = ("You are helping index a college pre-admission document for retrieval. You will be given chunks extracted from the document and must situate each one within the whole document.")


header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT_ON)
size_splitter = RecursiveCharacterTextSplitter(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)


class ChunkContexts(BaseModel): # Force the llm to answer like this.
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
            final_chunks.append(Document(page_content=sub_text, metadata={"source": filename, "section_index": i, "chunk_index": j, **doc.metadata, **extra_metadata}))
    return final_chunks


def _build_batch_prompt(chunk_batch: List[Document]) -> str: # Prompt the llm to send the context for each chunk in the same order in a list.
    chunks_block = "\n\n".join(
        f'<chunk id="{i}">\n{c.page_content}\n</chunk>'
        for i, c in enumerate(chunk_batch)
        )
    return (f"Below are chunks extracted from the document. For each chunk, write a short 1-2 sentence context that situates it within the overall document, to improve retrieval of this chunk.\n\n{chunks_block}\n\nReturn one context string per chunk, in the same order as the chunk ids.")


def add_context_to_chunks(document_text: str, chunks: List[Document]) -> List[Document]: # Actually invoking the agent also caching documents to optimize for costs
    if not chunks:
        return []
    settings = get_settings()
    base_llm = ChatGoogleGenerativeAI(model=settings.contextual_retrieval_model, api_key=settings.gemini_api_key)
    
    batches = [chunks[i : i + settings.batch_size] for i in range(0, len(chunks), settings.batch_size)] # We can't do all chunks at once because of the 1mill token context window in llms and we can't do one query per chunk since it's way too costly. so batching chunks is perfect

    doc_tokens = base_llm.get_num_tokens(document_text)  # real tokenizer count, LangChain-native
    use_explicit_cache = doc_tokens >= settings.min_cache_tokens and len(batches) > 1 # Gives True or False 
    cache = None
    if use_explicit_cache:
        cache = create_context_cache(base_llm, messages=[SystemMessage(content=SYSTEM_INSTRUCTION), HumanMessage(content=document_text)], ttl=settings.cache_ttl)
        cached_llm = ChatGoogleGenerativeAI(model=settings.contextual_retrieval_model, api_key=settings.gemini_api_key, cached_content=cache.name)
        structured_llm = cached_llm.with_structured_output(ChunkContexts, method="json_schema", include_raw=True)
    else:
        structured_llm = base_llm.with_structured_output(ChunkContexts, method="json_schema", include_raw=True)
    contextualized: List[Document] = []
    try:
        for batch_num, batch in enumerate(batches):
            prompt = _build_batch_prompt(batch)
            try:
                if cache is not None: # DOc is alr cached only send the batch prompt
                    result = structured_llm.invoke(prompt)
                else:
                    result = structured_llm.invoke([SystemMessage(content=SYSTEM_INSTRUCTION), HumanMessage(content=f"{document_text}\n\n{prompt}")])

                parsed: ChunkContexts = result["parsed"]
                raw_msg = result["raw"]

                if len(parsed.contexts) != len(batch):
                    raise ValueError(f"Expected {len(batch)} contexts, got {len(parsed.contexts)}")

                # confirm caching is actually hitting (observability)
                usage = getattr(raw_msg, "usage_metadata", None) or {}
                cached_tokens = usage.get("input_token_details", {}).get("cache_read", 0) if usage else 0
                if cached_tokens:
                    logger.info(f"[cache hit] {cached_tokens} tokens served from cache (batch {batch_num + 1}/{len(batches)})")

                for chunk, ctx in zip(batch, parsed.contexts):
                    contextualized.append(Document(page_content=f"{ctx.strip()}\n\n{chunk.page_content}", metadata={**chunk.metadata, "raw_chunk": chunk.page_content}))
            except Exception as e: # One bad batch shouldn't take down the whole document's ingestion.
                logger.warning(f"Batch {batch_num + 1}/{len(batches)} contextualization failed, using raw chunks for this batch: {e}")
                for chunk in batch:
                    contextualized.append(Document(page_content=chunk.page_content, metadata={**chunk.metadata, "raw_chunk": chunk.page_content, "context_generation_failed": True}))
    finally:
        if cache is not None:
            # No LangChain-native delete yet, drop to the raw client just for this.
            try:
                _raw_genai.Client().caches.delete(name=cache.name)
            except Exception as e:
                logger.warning(f"Failed to delete context cache {cache.name}: {e}")
    return contextualized


def ingest_markdown(markdown_text: str, filename: str, college_id: str, extra_metadata: Dict = None):
    chunks = chunk_markdown(markdown_text, filename, extra_metadata={"college_id": college_id, **(extra_metadata or {})})
    contextualized_chunks = add_context_to_chunks(markdown_text, chunks)
    settings = get_settings()
    embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
    texts = [c.page_content for c in contextualized_chunks]
    vectors = embedder.embed_documents(texts)
    return contextualized_chunks, vectors


def insert_chunks_to_db(db, document_id: int, college_id: int, chunks: list, vectors: list) -> list[models.Chunk]:
    if not chunks:
        return []
    chunk_rows = [
        models.Chunk(document_id=document_id, college_id=college_id, chunk_content=chunk.page_content, embedding=vector, chunk_index=index, source_type="document", source_query_id=None, expires_at=None)
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    db.add_all(chunk_rows)
    db.commit()
    for row in chunk_rows:
        db.refresh(row)
    return chunk_rows

import os
import logging
from typing import List, Optional
from dotenv import load_dotenv
from rag.chunking import get_embeddings

from langchain_core.documents import Document
from langchain_postgres import PGEngine, PGVectorStore

load_dotenv()


logger = logging.getLogger("vector_store")

VECTOR_SIZE = 768
TABLE_NAME = "document_chunks"

CONNECTION_STRING = os.getenv("DATABASE_URL")

_engine: Optional[PGEngine] = None
_vector_store: Optional[PGVectorStore] = None



def get_engine() -> PGEngine:
    global _engine
    if _engine is None:
        _engine = PGEngine.from_connection_string(url=CONNECTION_STRING)
    return _engine


def init_vector_store_table():
    # Run this ONCE (e.g. a setup script) before your app goes live — creates the Postgres table with the right schema for this embedding size. Safe to call again later — if the table already exists, this just logs that and moves on instead of crashing.
    engine = get_engine()
    try:
        engine.init_vectorstore_table(
            table_name=TABLE_NAME,
            vector_size=VECTOR_SIZE,
        )
        logger.info(f"Vector store table '{TABLE_NAME}' created.")
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"Vector store table '{TABLE_NAME}' already exists — skipping.")
        else:
            raise

def get_vector_store() -> PGVectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = PGVectorStore.create_sync(
            engine=get_engine(),
            table_name=TABLE_NAME,
            embedding_service=get_embeddings(),
        )
    return _vector_store


def add_documents(documents: List[Document]) -> List[str]:
    """Embeds and stores chunks. Returns the generated Postgres row IDs."""
    if not documents:
        return []
    store = get_vector_store()
    return store.add_documents(documents)


def similarity_search(query: str, k: int = 5) -> List[Document]:
    """Embeds the query and returns the k most similar chunks, each with
    its original metadata (source filename, etc) attached."""
    store = get_vector_store()
    return store.similarity_search(query, k=k)
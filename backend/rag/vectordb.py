from rag.chunking import get_embeddings
from sqlalchemy import select
from langchain_core.documents import Document as LangChainDocument
from database import models


def add_document_chunks(db, document_id, college_id, chunks: list[LangChainDocument]) -> list[models.Chunk]:
    if not chunks:
        return []
    
    texts = [chunk.page_content for chunk in chunks]
    embeddings = get_embeddings().embed_documents(texts)
    
    chunk_rows = []

    for index, chunk in enumerate(chunks):
        chunk_row = models.Chunk(
            document_id=document_id,
            college_id=college_id,
            chunk_content=chunk.page_content,
            embedding=embeddings[index],
            chunk_index=index,
            source_type="document",
            source_query_id=None,
            expires_at=None,
        )
        chunk_rows.append(chunk_row)
        
    db.add_all(chunk_rows)
    db.commit()

    for chunk_row in chunk_rows:
        db.refresh(chunk_row)

    return chunk_rows




def similarity_search(db, query: str, college_id: int, k: int = 5) -> list[LangChainDocument]:
    query_embedding = get_embeddings().embed_query(query)
    chunks = db.execute(select(models.Chunk).where(models.Chunk.college_id == college_id).order_by(models.Chunk.embedding.cosine_distance(query_embedding)).limit(k)).scalars().all()
    return [LangChainDocument(
        page_content=chunk.chunk_content,
        metadata={
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "college_id": chunk.college_id,
            "source_type": chunk.source_type,
            "source_query_id": chunk.source_query_id,
            "source": f"chunk:{chunk.chunk_id}",
            },
        )
        for chunk in chunks
    ]

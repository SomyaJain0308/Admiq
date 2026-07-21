from typing import List, Dict
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document


HEADERS_TO_SPLIT_ON = [("#", "H1"), ("##", "H2"), ("###", "H3")]
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
EMBEDDING_MODEL = "models/gemini-embedding-001"
VECTOR_SIZE = 768

header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT_ON)
size_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def chunk_markdown(markdown_text: str, filename: str, extra_metadata: Dict = None) -> List[Document]:
    # Split markdown by headers first, then by size if a section is too big. Returns a list of {text, metadata} dicts ready for embedding.
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


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL, output_dimensionality=VECTOR_SIZE)
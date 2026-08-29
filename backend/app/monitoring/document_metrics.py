from prometheus_client import Counter, Histogram


DOCUMENT_EXTRACTION_METHOD = Counter("document_extraction_method_total", "Document extraction tier method used", ["method"])

DOCUMENT_INGESTION_OUTCOME = Counter("document_ingestion_outcome_total", "Total document ingestion task outcomes", ["outcome", "error_type"])

DOCUMENT_INGESTION_LATENCY = Histogram("document_ingestion_latency_seconds", "End to end latency of document ingestion tasks (OCR + chunk + contextualize + embed + insert)")

DOCUMENT_INGESTION_STAGE_LATENCY = Histogram("document_ingestion_stage_latency", "Latency of each stage of document ingestion tasks (OCR + Chunk + Contextualize + Embed + Insert)", ["stage"])

DOCUMENT_QUALITY_SCORE = Histogram("document_quality_score", "Quality score of extracted markdown (0-1, higher is better)", buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

DOCUMENT_CHUNKS_CREATED = Histogram("documents_chunks_created", "Number of chunks created per successfully ingested document", buckets=[1, 2, 3, 4, 5, 10, 20, 40, 80, 160, 320])

DOCUMENTS_PAGES_PROCESSED = Histogram("document_pages_processed", "Number of pages processed per successfully ingested document", buckets=[1, 3, 5, 10, 20, 40, 80])
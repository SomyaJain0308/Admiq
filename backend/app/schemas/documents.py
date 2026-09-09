from pydantic import BaseModel, Field


class BulkDeleteRequest(BaseModel):
    # Capped so one request can't be used to force the server into deleting
    # (and signing storage-delete calls for) an unbounded number of rows.
    document_ids: list[int] = Field(min_length=1, max_length=200)

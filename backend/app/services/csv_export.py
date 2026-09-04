import csv
import io

from fastapi.responses import StreamingResponse


def rows_to_csv_response(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    """Turns a list of dicts into a downloadable CSV response.

    columns controls both which fields are included and their order - rows
    can have extra keys that just get ignored, so callers don't need to
    trim ORM objects down before calling this.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# app/routers/web/assessment/helpers/export_response.py

from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import Response


XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)


def excel_download_response(
    *,
    content: bytes,
    filename: str,
) -> Response:
    """
    HTTP-response для скачивания XLSX.

    filename* нужен для корректных
    кириллических / казахских имён файла.
    """

    encoded_filename = quote(
        filename
    )

    content_disposition = (
        'attachment; '
        'filename="knowledge_quality.xlsx"; '
        f"filename*=UTF-8''{encoded_filename}"
    )

    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                content_disposition
            ),
            "Content-Length": str(
                len(content)
            ),
        },
    )

# app/modules/reports/utils/report_signature.py

from datetime import datetime, timezone, timedelta
from io import BytesIO
import base64

import jwt
import qrcode

from app.core.config import get_settings


JWT_ALGORITHM = "HS256"


class ReportSignatureService:

    @staticmethod
    def create_token(
        *,
        report_type: str,
        report_id: int,
        document_id: int,
        total: int | None = None,
    ) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "type": report_type,
            "report_id": report_id,
            "document_id": document_id,
            "total": total or 0,
            "iat": int(now.timestamp()),
            "exp": int(
                (
                    now + timedelta(days=365 * 5)
                ).timestamp()
            ),
        }

        return jwt.encode(
            payload,
            get_settings().SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )

    @staticmethod
    def decode_token(token: str) -> dict:
        return jwt.decode(
            token,
            get_settings().SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

    @staticmethod
    def generate_qr_bytes(
            *,
            verify_url: str,
    ) -> bytes:
        """
        Сгенерировать QR-код в памяти в формате PNG.
        """

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )

        qr.add_data(verify_url)
        qr.make(fit=True)

        image = qr.make_image(
            fill_color="black",
            back_color="white",
        )

        buffer = BytesIO()
        image.save(buffer, "PNG")

        return buffer.getvalue()

    @classmethod
    def generate_qr_data_uri(
        cls,
        *,
        verify_url: str,
    ) -> str:
        """
        Сгенерировать QR-код и вернуть его как data URI
        для прямой вставки в HTML.
        """

        qr_bytes = cls.generate_qr_bytes(
            verify_url=verify_url,
        )

        encoded = base64.b64encode(
            qr_bytes
        ).decode("ascii")

        return f"data:image/png;base64,{encoded}"

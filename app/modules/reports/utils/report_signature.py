# app/modules/reports/utils/report_signature.py

from pathlib import Path
from datetime import datetime, timezone, timedelta

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
            "type": report_type,  # 👈 универсально
            "report_id": report_id,
            "document_id": document_id,
            "total": total or 0,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=365 * 5)).timestamp()),
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
    def generate_qr_file(
            *,
            report_type: str,
            report_id: int,
            verify_url: str,
    ) -> str:
        base_dir = Path(f"media/reports/{report_type}/qr")
        base_dir.mkdir(parents=True, exist_ok=True)

        qr_path = base_dir / f"{report_type}_{report_id}_qr.png"

        img = qrcode.make(verify_url)
        img.save(qr_path)

        return str(qr_path)

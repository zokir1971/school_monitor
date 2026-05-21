# app/core/storage/s3.py (S3 / MinIO (один код для обоих))

import boto3
from uuid import uuid4
from pathlib import Path

from app.core.storage.base import BaseStorage


class S3Storage(BaseStorage):

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url="http://localhost:9000",  # MinIO
            aws_access_key_id="minio",
            aws_secret_access_key="minio123",
        )
        self.bucket = "school-monitor"

    def save(self, content: bytes, filename: str):
        ext = Path(filename).suffix
        key = f"task_documents/{uuid4().hex}{ext}"

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
        )

        return key, key

    def delete(self, path: str):
        if not path:
            return

        self.client.delete_object(
            Bucket=self.bucket,
            Key=path,
        )

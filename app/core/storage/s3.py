# app/core/storage/s3.py (S3Storage для MinIO и AWS S3 (один код для обоих))

from __future__ import annotations

import asyncio
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.storage.base import BaseStorage


class S3Storage(BaseStorage):
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        public_endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        region: str,
        bucket: str,
        verify_ssl: bool,
    ) -> None:
        common_client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": region,
            "verify": verify_ssl,
            "config": Config(
                signature_version="s3v4",
                retries={
                    "max_attempts": 3,
                    "mode": "standard",
                },
                s3={
                    "addressing_style": "path",
                },
            ),
        }

        internal_client_kwargs = dict(
            common_client_kwargs
        )

        if endpoint_url:
            internal_client_kwargs["endpoint_url"] = (
                endpoint_url
            )

        self._client: BaseClient = boto3.client(
            **internal_client_kwargs
        )

        presign_client_kwargs = dict(
            common_client_kwargs
        )

        if public_endpoint_url:
            presign_client_kwargs["endpoint_url"] = (
                public_endpoint_url
            )
        elif endpoint_url:
            presign_client_kwargs["endpoint_url"] = (
                endpoint_url
            )

        self._presign_client: BaseClient = boto3.client(
            **presign_client_kwargs
        )

        self._bucket = bucket

    async def save(
        self,
        *,
        content: bytes,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        normalized_key = self._normalize_key(
            object_key
        )

        response = await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=normalized_key,
            Body=content,
            ContentType=content_type,
            Metadata=metadata or {},
        )

        return response.get("ETag")

    async def delete(
        self,
        *,
        object_key: str,
    ) -> None:
        normalized_key = self._normalize_key(
            object_key
        )

        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=normalized_key,
        )

    async def exists(
        self,
        *,
        object_key: str,
    ) -> bool:
        normalized_key = self._normalize_key(
            object_key
        )

        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=self._bucket,
                Key=normalized_key,
            )

            return True

        except ClientError as exc:
            error_code = str(
                exc.response
                .get("Error", {})
                .get("Code", "")
            )

            if error_code in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return False

            raise

    async def get_download_url(
        self,
        *,
        object_key: str,
        expires_in: int = 300,
    ) -> str:
        normalized_key = self._normalize_key(
            object_key
        )

        return await asyncio.to_thread(
            self._presign_client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": normalized_key,
            },
            ExpiresIn=expires_in,
        )

    async def ensure_bucket_exists(
        self,
    ) -> None:
        try:
            await asyncio.to_thread(
                self._client.head_bucket,
                Bucket=self._bucket,
            )
            return

        except ClientError as exc:
            error_code = str(
                exc.response
                .get("Error", {})
                .get("Code", "")
            )

            if error_code not in {
                "404",
                "NoSuchBucket",
                "NotFound",
            }:
                raise

        await asyncio.to_thread(
            self._client.create_bucket,
            Bucket=self._bucket,
        )

    @staticmethod
    def _normalize_key(
        object_key: str,
    ) -> str:
        normalized_key = (
            object_key or ""
        ).strip().replace("\\", "/").lstrip("/")

        if not normalized_key:
            raise ValueError(
                "Ключ объекта не указан."
            )

        if ".." in normalized_key.split("/"):
            raise ValueError(
                "Недопустимый ключ объекта."
            )

        return normalized_key

    async def read(self, *, object_key: str, max_bytes: int = 8_000_000) -> bytes:
        def load():
            response = self._client.get_object(Bucket=self._bucket, Key=object_key)
            body = response['Body']
            try:
                data = body.read(max_bytes + 1)
                if len(data) > max_bytes: raise ValueError('Image exceeds export limit')
                return data
            finally: body.close()
        return await asyncio.to_thread(load)

import asyncio
import logging
from functools import partial
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_s3_configured() -> bool:
    return bool(
        settings.aws_access_key_id
        and settings.aws_secret_access_key
        and settings.aws_s3_bucket_name
    )


def _sync_upload(image_bytes: bytes, s3_key: str, content_type: str) -> str:
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    client.put_object(
        Bucket=settings.aws_s3_bucket_name,
        Key=s3_key,
        Body=image_bytes,
        ContentType=content_type,
    )
    return (
        f"https://{settings.aws_s3_bucket_name}"
        f".s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    )


async def upload_handwriting_image(
    image_bytes: bytes,
    session_id: str,
    content_type: str,
) -> Optional[str]:
    """
    원본 손글씨 이미지를 S3에 업로드하고 HTTPS URL을 반환한다.

    버킷이 퍼블릭이 아닌 경우 이 URL은 직접 접근 불가 — 필요 시
    boto3 generate_presigned_url()로 presigned URL 생성 필요.

    AWS 미설정 또는 업로드 실패 시 None을 반환하며, 서비스는 계속 동작한다.
    """
    if not _is_s3_configured():
        logger.warning("S3 미설정 — 이미지 업로드 건너뜀 (session_id=%s)", session_id)
        return None

    ext = content_type.split("/")[-1].replace("jpeg", "jpg")
    s3_key = f"handwriting/{session_id}/original.{ext}"

    try:
        loop = asyncio.get_running_loop()
        url = await loop.run_in_executor(
            None, partial(_sync_upload, image_bytes, s3_key, content_type)
        )
        logger.info("S3 업로드 완료: %s", s3_key)
        return url
    except (BotoCoreError, ClientError) as e:
        logger.error("S3 업로드 실패 (session_id=%s): %s", session_id, e)
        return None

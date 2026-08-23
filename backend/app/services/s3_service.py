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


def _sync_delete_prefix(prefix: str) -> int:
    client = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    paginator = client.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=settings.aws_s3_bucket_name, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not objects:
            continue
        client.delete_objects(
            Bucket=settings.aws_s3_bucket_name,
            Delete={"Objects": objects},
        )
        deleted += len(objects)
    return deleted


async def delete_handwriting_images(session_id: str) -> int:
    """한 세션(session_id)에 업로드된 손글씨 이미지를 전부 삭제한다(계정 삭제, REQ-009-7).

    업로드 키가 handwriting/{session_id}/... 형태이므로 이 프리픽스 아래를 모두 지운다.
    삭제한 오브젝트 개수를 반환하며, AWS 미설정·실패 시 0을 반환하고 서비스는 계속 동작한다.
    """
    if not _is_s3_configured():
        logger.warning("S3 미설정 — 이미지 삭제 건너뜀 (session_id=%s)", session_id)
        return 0

    prefix = f"handwriting/{session_id}/"
    try:
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(
            None, partial(_sync_delete_prefix, prefix)
        )
        logger.info("S3 삭제 완료: %s (%d개)", prefix, count)
        return count
    except (BotoCoreError, ClientError) as e:
        logger.error("S3 삭제 실패 (session_id=%s): %s", session_id, e)
        return 0


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

"""COS 对象存储直传服务"""
import os
import uuid
import logging
from datetime import timedelta
from qcloud_cos import CosConfig, CosS3Client

logger = logging.getLogger("xiugua.cos")
from qcloud_cos.cos_exception import CosServiceError


def _get_client(accelerate: bool = False):
    kwargs = dict(
        Region=os.environ["COS_REGION"],
        SecretId=os.environ["COS_SECRET_ID"],
        SecretKey=os.environ["COS_SECRET_KEY"],
        Scheme="https",
    )
    if accelerate:
        kwargs["Endpoint"] = "cos.accelerate.myqcloud.com"
    config = CosConfig(**kwargs)
    return CosS3Client(config)


def get_presigned_upload(user_id: str, filename: str, file_type: str) -> dict:
    """生成预签名上传URL"""
    client = _get_client(accelerate=True)
    bucket = os.environ["COS_BUCKET"]

    # 用 uuid 作为文件名避免冲突
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "epub"
    key = f"uploads/{user_id}/{uuid.uuid4()}.{ext}"

    url = client.get_presigned_url(
        Method="PUT",
        Bucket=bucket,
        Key=key,
        Expired=1800,  # 30 分钟有效期
        Headers={"Content-Type": "application/octet-stream"},
    )

    return {
        "upload_url": url,
        "key": key,
        "bucket": bucket,
        "expires_in": 1800,
    }


def download_from_cos(key: str, local_path: str) -> bool:
    """从COS下载文件到本地"""
    client = _get_client()
    bucket = os.environ["COS_BUCKET"]
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        resp["Body"].get_stream_to_file(local_path)
        return True
    except CosServiceError as e:
        logger.error("COS download failed: %s", e)
        return False


def delete_from_cos(key: str) -> bool:
    """从COS删除对象"""
    client = _get_client()
    bucket = os.environ["COS_BUCKET"]
    try:
        client.delete_object(Bucket=bucket, Key=key)
        logger.info("COS deleted: %s", key)
        return True
    except CosServiceError as e:
        logger.error("COS delete failed: %s", e)
        return False

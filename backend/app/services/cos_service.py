"""COS 对象存储直传服务"""
import os
import uuid
from datetime import timedelta
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosServiceError


def _get_client():
    config = CosConfig(
        Region=os.environ["COS_REGION"],
        SecretId=os.environ["COS_SECRET_ID"],
        SecretKey=os.environ["COS_SECRET_KEY"],
        Scheme="https",
        UseAccelerate=True,  # 全球加速域名
    )
    return CosS3Client(config)


def _get_client_internal():
    """内网下载用，不走加速（E2E延迟低）"""
    config = CosConfig(
        Region=os.environ["COS_REGION"],
        SecretId=os.environ["COS_SECRET_ID"],
        SecretKey=os.environ["COS_SECRET_KEY"],
        Scheme="https",
    )
    return CosS3Client(config)


def get_presigned_upload(user_id: str, filename: str, file_type: str) -> dict:
    """生成预签名上传URL"""
    client = _get_client()
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

    # 替换为全球加速域名
    base = f"{bucket}.cos.{os.environ['COS_REGION']}.myqcloud.com"
    accel = f"{bucket}.cos.accelerate.myqcloud.com"
    upload_url = url.replace(base, accel)

    return {
        "upload_url": upload_url,
        "key": key,
        "bucket": bucket,
        "expires_in": 1800,
    }


def download_from_cos(key: str, local_path: str) -> bool:
    """从COS下载文件到本地（内网不走加速）"""
    client = _get_client_internal()
    bucket = os.environ["COS_BUCKET"]
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        resp["Body"].get_stream_to_file(local_path)
        return True
    except CosServiceError as e:
        print(f"COS download failed: {e}")
        return False

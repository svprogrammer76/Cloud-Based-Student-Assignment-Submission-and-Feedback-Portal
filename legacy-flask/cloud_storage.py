"""Private local/S3 object storage adapter. Bucket objects are never public."""
import os
from pathlib import Path


def using_s3():
    return bool(os.getenv("S3_BUCKET"))


def save_upload(uploaded_file, key, local_root):
    if using_s3():
        import boto3
        client = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
        client.upload_fileobj(uploaded_file.stream, os.environ["S3_BUCKET"], key,
                              ExtraArgs={"ContentType": uploaded_file.mimetype or "application/octet-stream"})
        return None
    destination = Path(local_root) / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    uploaded_file.save(destination)
    return destination


def open_download(key, local_root):
    if using_s3():
        import boto3
        client = boto3.client("s3", region_name=os.getenv("AWS_REGION"))
        return client.get_object(Bucket=os.environ["S3_BUCKET"], Key=key)["Body"]
    return Path(local_root) / key


def delete_object(key, local_root):
    if using_s3():
        import boto3
        boto3.client("s3", region_name=os.getenv("AWS_REGION")).delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
    else:
        (Path(local_root) / key).unlink(missing_ok=True)

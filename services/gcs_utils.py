# Google Cloud Storage Helpers (empty placeholder)
# services/gcs_utils.py
from google.cloud import storage
import os

BUCKET = os.environ.get("PARSER_BUCKET")

def upload_file(local_path: str, dest_path: str) -> str:
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(local_path)
    return f"gs://{BUCKET}/{dest_path}"

def upload_text(text: str, dest_path: str) -> str:
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    blob = bucket.blob(dest_path)
    blob.upload_from_string(text)
    return f"gs://{BUCKET}/{dest_path}"

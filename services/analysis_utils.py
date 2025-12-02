import os, json
from google.cloud import storage

BUCKET = os.environ.get("PARSER_BUCKET")
try:
    GCS_CLIENT = storage.Client() if BUCKET else None
except Exception:
    GCS_CLIENT = None

def upload_json_to_gcs(data: dict, dest_path: str):
    if BUCKET and GCS_CLIENT:
        try:
            bucket = GCS_CLIENT.bucket(BUCKET)
            blob = bucket.blob(dest_path)
            blob.upload_from_string(json.dumps(data, indent=2), content_type="application/json")
            return f"gs://{BUCKET}/{dest_path}"
        except Exception as e:
            print("[upload_json_to_gcs] GCS upload failed:", e)
    # fallback local save
    local_dir = os.path.join("artifacts", os.path.dirname(dest_path))
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, dest_path.replace("/", "_"))
    with open(local_path, "w") as f:
        json.dump(data, f, indent=2)
    return local_path

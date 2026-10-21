"""Small shared helpers; the counting algorithms live in separate programs."""
from pathlib import Path
import hashlib
import json
import os

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]


def config():
    return json.loads((ROOT / "config.json").read_text())


def require_variant():
    cfg = config()
    if not cfg["variant"] or not cfg["name_regex"]:
        raise RuntimeError("Укажите свой вариант и name_regex в config.json")
    return cfg


def client():
    return boto3.client(
        "s3", endpoint_url=config()["endpoint"],
        aws_access_key_id=os.getenv("LAB_ACCESS_KEY", "labadmin"),
        aws_secret_access_key=os.getenv("LAB_SECRET_KEY", "local-lab-secret-2026"),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, max_pool_connections=12,
                      retries={"total_max_attempts": 1},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required"),
    )


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def canonical(counter):
    rows = [{"skills": list(key), "count": n} for key, n in sorted(counter.items())]
    raw = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    return rows, hashlib.sha256(raw).hexdigest()


def put_json(key, obj):
    body = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()
    r = client().put_object(Bucket=config()["bucket"], Key=key, Body=body,
                            ContentType="application/json")
    assert r["ResponseMetadata"]["HTTPStatusCode"] == 200
    return len(body)

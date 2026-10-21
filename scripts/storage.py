"""Upload the unchanged source and verify its complete S3 body."""
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import ROOT, client, config, save


def main():
    cfg = config()
    s3 = client()
    for _ in range(60):
        try:
            s3.list_buckets()
            break
        except Exception:
            time.sleep(1)
    s3.create_bucket(Bucket=cfg["bucket"])
    src = (ROOT / cfg["source_path"]).resolve()
    with src.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    with src.open("rb") as f:
        r = s3.put_object(Bucket=cfg["bucket"], Key=cfg["source_key"], Body=f,
                          ContentLength=src.stat().st_size, ContentType="text/csv")
    print("PUT", cfg["bucket"] + "/" + cfg["source_key"],
          "HTTP", r["ResponseMetadata"]["HTTPStatusCode"], flush=True)
    response = s3.get_object(Bucket=cfg["bucket"], Key=cfg["source_key"])
    h, count = hashlib.sha256(), 0
    with response["Body"] as body:
        for chunk in iter(lambda: body.read(1024 * 1024), b""):
            h.update(chunk)
            count += len(chunk)
    assert count == src.stat().st_size and h.hexdigest() == digest
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "source": src.name, "bucket": cfg["bucket"], "key": cfg["source_key"],
              "bytes": count, "sha256": digest, "get_sha256": h.hexdigest(),
              "match": True, "put_http": r["ResponseMetadata"]["HTTPStatusCode"],
              "get_http": response["ResponseMetadata"]["HTTPStatusCode"],
              "host": platform.platform(), "python": sys.version,
              "docker": subprocess.check_output(["docker", "version", "--format", "{{.Server.Version}}"], text=True).strip()}
    save(ROOT / "logs/storage.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

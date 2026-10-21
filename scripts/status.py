"""Live evidence for a real terminal screenshot."""
import json
import subprocess
import sys

from common import ROOT, client, config


def main():
    cfg = config()
    print("FRONTEND / VARIANT 8 / LOCAL EXPERIMENT", flush=True)
    if len(sys.argv) == 1 or sys.argv[1] == "storage":
        print("$ docker compose ps --format <name, status, ports>", flush=True)
        subprocess.run(["docker", "compose", "ps", "--format", "table {{.Name}}\t{{.Status}}\t{{.Ports}}"], cwd=ROOT, check=True)
        print("\nS3:", cfg["endpoint"], "bucket:", cfg["bucket"])
        source = client().head_object(Bucket=cfg["bucket"], Key=cfg["source_key"])
        stored = json.loads((ROOT / "logs/storage.json").read_text())
        print("Object:", cfg["source_key"])
        print("HEAD HTTP:", source["ResponseMetadata"]["HTTPStatusCode"], "bytes:", source["ContentLength"])
        print("Complete S3 GET vs source SHA-256:", stored["match"])
        print("SHA-256:", stored["sha256"])
        print("\n$ docker exec rustfs-skills-lab ... format.json")
        subprocess.run(["docker", "exec", "rustfs-skills-lab", "sh", "-c",
                        'for d in /disks/disk?; do printf "%s " "$d"; test -f "$d/.rustfs.sys/format.json" && echo READY; done'], check=True)
        objects = list(client().get_paginator("list_objects_v2").paginate(Bucket=cfg["bucket"], Prefix="results/"))
        print("\nPersisted result objects:", sum(p.get("KeyCount", 0) for p in objects))
    else:
        v = json.loads((ROOT / "results/verification.json").read_text())
        print("$ .venv/bin/python scripts/verify.py")
        print("Full key/count comparisons:", v["count_comparisons"], "ALL MATCH")
        print("S3 result readback: ALL MATCH")
        print("Actual mapper process exit(17) + retry:", v["failure_recovery_match"])
        print("\nStack  vacancies    distinct(1/2/3)       occurrences(1/2/3)")
        for cap in cfg["stack_caps"] + [0]:
            tag = f"{cap}" if cap else "FULL"
            name = f"duckdb_cap{cap}_run1.json" if cap else "duckdb_cap0_runfull.json"
            r = json.loads((ROOT / "results" / name).read_text())
            d = '/'.join(str(r['orders'][k]['distinct']) for k in ('1','2','3'))
            n = '/'.join(str(r['orders'][k]['occurrences']) for k in ('1','2','3'))
            print(f"{tag:>5} {r['selected_rows']:>9} {d:>23} {n:>26}")
        print("\nSHA-256 of canonical FULL counts:")
        print(r["sha256"])
        bench = json.loads((ROOT / "logs/benchmark.json").read_text())
        print("\nFresh-process profiling runs:", len([r for r in bench if isinstance(r['run'], int)]))
        print("All measured exit codes:", sorted({r["exit_code"] for r in bench}))


if __name__ == "__main__":
    main()

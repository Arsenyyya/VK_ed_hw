"""Independent SQL calculation reading the same unchanged CSV directly from S3."""
import argparse
import json
import os
import time

import duckdb

from common import ROOT, canonical, put_json, require_variant, save


def connection(cfg):
    con = duckdb.connect()
    con.execute("SET threads = 4")
    con.execute("SET memory_limit = '2GB'")
    con.execute("SET extension_directory = ?", [str(ROOT / ".cache/extensions")])
    con.execute("LOAD httpfs")
    # These are dedicated, local teaching credentials, also overrideable by env.
    def literal(value):
        return "'" + value.replace("'", "''") + "'"
    con.execute("CREATE SECRET lab_s3 (TYPE s3, KEY_ID "
                + literal(os.getenv("LAB_ACCESS_KEY", "labadmin")) + ", SECRET "
                + literal(os.getenv("LAB_SECRET_KEY", "local-lab-secret-2026"))
                + ", REGION 'us-east-1', ENDPOINT "
                + literal(cfg["endpoint"].removeprefix("http://"))
                + ", URL_STYLE 'path', USE_SSL false)")
    return con


def prepare(con, cfg):
    query = (ROOT / "sql/prepare.sql").read_text()
    con.execute(query, {"source": f"s3://{cfg['bucket']}/{cfg['source_key']}",
                        "pattern": cfg["name_regex"], "role": cfg["role"]})


def count(con, cap):
    statements = (ROOT / "sql/count.sql").read_text().split(";")
    for statement in statements:
        if statement.strip():
            con.execute(statement, {"cap": cap} if "$cap" in statement else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, required=True)
    ap.add_argument("--run", default="1")
    args = ap.parse_args()
    cfg, start = require_variant(), time.perf_counter()
    con = connection(cfg)
    prepare(con, cfg)
    n, m = con.execute("SELECT count(*), count(*) FILTER (WHERE len(skills)>0) FROM vacancies").fetchone()
    count(con, args.cap)
    totals = {tuple(s): n for s, n in con.execute("SELECT skills, count FROM counts").fetchall()}
    rows, digest = canonical(totals)
    result = {"engine": "duckdb", "version": duckdb.__version__, "cap": args.cap,
              "run": args.run, "variant": cfg["variant"], "sha256": digest,
              "selected_rows": n, "with_skills": m,
              "orders": {str(k): {"distinct": sum(len(x) == k for x in totals),
                                   "occurrences": sum(v for x, v in totals.items() if len(x) == k)}
                          for k in (1, 2, 3)}, "counts": rows}
    key = f"results/duckdb_cap{args.cap}_run{args.run}.json"
    put_json(key, result)
    save(ROOT / f"results/duckdb_cap{args.cap}_run{args.run}.json", result)
    summary = {k: v for k, v in result.items() if k != "counts"}
    summary.update(seconds=round(time.perf_counter() - start, 6), s3_output=key)
    save(ROOT / f"logs/duckdb_cap{args.cap}_run{args.run}.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

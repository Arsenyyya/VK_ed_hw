"""S3 -> CSV row chunks -> worker maps -> shuffle/reduce -> S3 JSON.

The baseline keeps emitted keys until reduce. The optimized version combines
inside each mapper and reduces completed chunks immediately. Both are exact.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from concurrent.futures.process import BrokenProcessPool
from contextlib import closing
import csv
import io
from itertools import combinations, islice
import json
import multiprocessing
import os
import re
import time

from common import ROOT, canonical, client, put_json, require_variant, save


def mapper(rows, pattern, role, cap, optimized, fail=False):
    if fail:
        os._exit(17)  # A real worker-process failure, only in the recovery test.
    match = re.compile(pattern, re.IGNORECASE)
    out = Counter() if optimized else []
    selected, nonempty = 0, 0
    for name, raw, vacancy_role in rows:
        if vacancy_role != role or not match.search(name):
            continue
        selected += 1
        skills = sorted({x.strip().lower() for x in raw.split(";") if x.strip()})
        if cap:
            skills = skills[:cap]
        nonempty += bool(skills)
        for size in (1, 2, 3):
            keys = combinations(skills, size)
            if optimized:
                out.update(keys)
            else:
                out.extend(keys)
    return out, selected, nonempty


def calculate(cfg, cap, optimized, fail):
    totals, selected, nonempty, chunks, input_rows = Counter(), 0, 0, 0, 0
    shuffle = []
    response = client().get_object(Bucket=cfg["bucket"], Key=cfg["source_key"])
    # csv.DictReader preserves quoted fields with embedded newlines. A byte
    # boundary is never treated as a CSV record boundary.
    with closing(response["Body"]) as body, io.TextIOWrapper(
        io.BufferedReader(body, buffer_size=1024 * 1024), encoding="utf-8", newline=""
    ) as text, ProcessPoolExecutor(
        max_workers=cfg["workers"], mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        reader = csv.DictReader(text)
        pending = set()

        def consume(done):
            nonlocal selected, nonempty
            for future in done:
                out, n, m = future.result()
                selected += n
                nonempty += m
                if optimized:
                    totals.update(out)
                else:
                    shuffle.extend(out)

        while True:
            rows = [(r["name"], r["key_skills"], r["role"]) for r in islice(reader, cfg["chunk_rows"])]
            if not rows:
                break
            pending.add(pool.submit(mapper, rows, cfg["name_regex"], cfg["role"], cap, optimized,
                                    fail and chunks == 0))
            input_rows += len(rows)
            chunks += 1
            if len(pending) >= 2 * cfg["workers"]:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                consume(done)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            consume(done)
    if not optimized:
        totals.update(shuffle)
    return totals, {"input_rows": input_rows, "selected_rows": selected,
                    "with_skills": nonempty, "chunks": chunks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=int, required=True, help="0 = full skill stack")
    ap.add_argument("--mode", choices=["baseline", "optimized"], default="optimized")
    ap.add_argument("--run", default="1")
    ap.add_argument("--fail-worker", action="store_true")
    args = ap.parse_args()
    cfg = require_variant()
    start, recovery = time.perf_counter(), []
    for attempt in range(2):
        try:
            totals, stats = calculate(cfg, args.cap, args.mode == "optimized",
                                      args.fail_worker and attempt == 0)
            break
        except BrokenProcessPool as exc:
            if not args.fail_worker or attempt:
                raise
            recovery.append({"attempt": attempt + 1, "error": type(exc).__name__,
                             "action": "discard partial counts and retry full S3 job"})
            print("Worker exited with code 17; discarding partial counts; retry from S3", flush=True)
    rows, digest = canonical(totals)
    result = {"engine": "mapreduce", "mode": args.mode, "cap": args.cap,
              "run": args.run, "variant": cfg["variant"], "sha256": digest,
              **stats, "orders": {str(k): {"distinct": sum(len(x) == k for x in totals),
                                          "occurrences": sum(v for x, v in totals.items() if len(x) == k)}
                                    for k in (1, 2, 3)},
              "recovery": recovery, "counts": rows}
    label = f"mr_{args.mode}_cap{args.cap}_run{args.run}"
    key = f"results/{label}.json"
    put_json(key, result)
    save(ROOT / f"results/{label}.json", result)
    summary = {k: v for k, v in result.items() if k != "counts"}
    summary.update(seconds=round(time.perf_counter() - start, 6), s3_output=key)
    save(ROOT / f"logs/{label}.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

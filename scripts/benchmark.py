"""Separate fresh processes; poll concurrent process-tree RSS every 10 ms."""
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

import psutil

from common import ROOT, require_variant, save


def measure(command, label):
    log = ROOT / "logs" / f"{label}.log"
    print("$", " ".join(command), flush=True)
    started = datetime.now(timezone.utc).isoformat()
    peak, samples = 0, 0
    cpu_by_pid = {}
    start = time.perf_counter()
    with log.open("w") as out:
        out.write("$ " + " ".join(command) + "\n")
        out.flush()
        process = subprocess.Popen(command, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
        root = psutil.Process(process.pid)
        while True:
            try:
                processes = [root] + root.children(recursive=True)
            except psutil.NoSuchProcess:
                processes = []
            current = 0
            for p in processes:
                try:
                    current += p.memory_info().rss
                    t = p.cpu_times()
                    cpu_by_pid[p.pid] = t.user + t.system
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            peak = max(peak, current)
            samples += 1
            if process.poll() is not None:
                break
            time.sleep(0.01)
    result = {"label": label, "command": command, "started_utc": started,
              "seconds": round(time.perf_counter() - start, 6),
              "peak_tree_rss_bytes": peak, "peak_tree_rss_mib": round(peak / 2**20, 3),
              "sample_interval_ms": 10, "samples": samples,
              "cpu_seconds": round(sum(cpu_by_pid.values()), 6),
              "exit_code": process.returncode, "output_log": str(log.relative_to(ROOT))}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if process.returncode:
        raise RuntimeError(log.read_text()[-5000:])
    return result


def main():
    cfg = require_variant()
    records = []
    env = {"platform": platform.platform(), "python": sys.version,
           "logical_cpus": psutil.cpu_count(), "physical_cpus": psutil.cpu_count(False),
           "ram_bytes": psutil.virtual_memory().total,
           "workers": cfg["workers"], "duckdb_threads": 4,
           "chunk_rows": cfg["chunk_rows"], "measurement": "10ms process-tree summed RSS",
           "scope": "fresh Python process including S3 read, computation, serialization and S3 result PUT; excludes RustFS/Docker; shared pages can be counted more than once",
           "cache": "warm OS/server caches; not explicitly cleared; rotating engine order"}
    save(ROOT / "logs/environment.json", env)
    engines = ["baseline", "optimized", "duckdb"]
    for run in range(1, cfg["attempts"] + 1):
        for cap in cfg["stack_caps"]:
            order = engines[run-1:] + engines[:run-1]
            for engine in order:
                if engine == "duckdb":
                    command = [sys.executable, "scripts/duckdb_counts.py", "--cap", str(cap), "--run", str(run)]
                    label = f"duckdb_cap{cap}_run{run}"
                else:
                    command = [sys.executable, "scripts/mapreduce.py", "--cap", str(cap), "--mode", engine, "--run", str(run)]
                    label = f"mr_{engine}_cap{cap}_run{run}"
                result = measure(command, label)
                records.append({**result, "engine": engine, "cap": cap, "run": run})
                save(ROOT / "logs/benchmark.json", records)
    # The analytic results use every skill, independent of the scaling caps.
    for engine in ("mapreduce", "duckdb"):
        script = "mapreduce.py" if engine == "mapreduce" else "duckdb_counts.py"
        records.append({**measure([sys.executable, "scripts/" + script, "--cap", "0", "--run", "full"],
                                   engine + "_full"), "engine": engine, "cap": 0, "run": "full"})
        save(ROOT / "logs/benchmark.json", records)
    records.append({**measure([sys.executable, "scripts/mapreduce.py", "--cap", "0", "--run", "recovery", "--fail-worker"], "recovery"),
                    "engine": "mapreduce_recovery", "cap": 0, "run": "recovery"})
    save(ROOT / "logs/benchmark.json", records)


if __name__ == "__main__":
    main()

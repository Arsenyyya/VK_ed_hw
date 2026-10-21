"""Compare every key/count, not just a few top rows or totals."""
import csv
import json
from math import comb

from common import ROOT, client, put_json, require_variant, save


def load(name):
    return json.loads((ROOT / "results" / name).read_text())


def main():
    cfg, checks = require_variant(), []
    for cap in cfg["stack_caps"]:
        reference = load(f"duckdb_cap{cap}_run1.json")
        expected = reference["counts"]
        for run in range(1, cfg["attempts"] + 1):
            for engine in ("mr_baseline", "mr_optimized", "duckdb"):
                name = f"{engine}_cap{cap}_run{run}.json"
                actual = load(name)
                assert actual["counts"] == expected, f"Mismatch: {name}"
                assert actual["selected_rows"] == reference["selected_rows"]
                assert actual["with_skills"] == reference["with_skills"]
                checks.append({"file": name, "keys": len(expected), "sha256": actual["sha256"], "match": True})
    reference = load("duckdb_cap0_runfull.json")
    with (ROOT / "results/skill_frequencies.csv").open() as f:
        analytic_counts = {tuple(r["skills"].split("; ")): int(r["vacancies"])
                           for r in csv.DictReader(f)}
    assert analytic_counts == {tuple(r["skills"]): r["count"] for r in reference["counts"]}
    for name in ("mr_optimized_cap0_runfull.json", "mr_optimized_cap0_runrecovery.json"):
        actual = load(name)
        assert actual["counts"] == reference["counts"], name
        checks.append({"file": name, "keys": len(actual["counts"]), "sha256": actual["sha256"], "match": True})
    assert load("mr_optimized_cap0_runrecovery.json")["recovery"], "Failure was not exercised"
    # S3 readback verifies that the persisted three-size results are the same
    # files that were compared locally, rather than just names in a listing.
    s3 = client()
    for check in checks:
        key = "results/" + check["file"]
        body = s3.get_object(Bucket=cfg["bucket"], Key=key)["Body"]
        with body:
            remote = json.loads(body.read())
        local = load(check["file"])
        assert remote == local
        check["s3_readback_match"] = True
    result = {"all_match": True, "checks": checks,
              "count_comparisons": len(checks), "failure_recovery_match": True,
              "analytic_frequency_table_match": True,
              "full_orders": reference["orders"],
              "theoretical_per_vacancy": [{"stack": s, "singles": s,
                                            "pairs": comb(s, 2), "triples": comb(s, 3)}
                                           for s in cfg["stack_caps"]]}
    save(ROOT / "results/verification.json", result)
    put_json("results/verification.json", result)
    print("Full key/count comparisons:", len(checks), "ALL MATCH; S3 readback ALL MATCH")
    print("Actual mapper process exit(17) + retry: MATCH")
    print(json.dumps(result["full_orders"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

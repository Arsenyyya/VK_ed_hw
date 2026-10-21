"""Salary and regional tables calculated from full stacks via independent SQL."""
import csv
import hashlib
import json

from common import ROOT, client, put_json, require_variant, save
from duckdb_counts import connection, prepare


def records(con, query, args=None):
    cur = con.execute(query, args)
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def export_csv(name, rows):
    if not rows:
        return
    with (ROOT / "results" / name).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        for row in rows:
            w.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in row.items()})


def main():
    cfg = require_variant()
    con = connection(cfg)
    prepare(con, cfg)
    for statement in (ROOT / "sql/analysis.sql").read_text().split(";"):
        if statement.strip():
            parameters = {}
            if "$support" in statement:
                parameters["support"] = cfg["minimum_salary_support"]
            if "$regions" in statement:
                parameters["regions"] = cfg["regions"]
            con.execute(statement, parameters or None)
    source = f"s3://{cfg['bucket']}/{cfg['source_key']}"
    source_audit = records(con, """
        SELECT count(*) AS rows, count(DISTINCT vacancy_id) AS unique_ids,
               min(published_at) AS published_min, max(published_at) AS published_max,
               min(snapshot_date) AS snapshot_min, max(snapshot_date) AS snapshot_max
        FROM read_csv(?, all_varchar=true, max_line_size=16777216, parallel=false)
    """, [source])[0]
    assert source_audit["rows"] == source_audit["unique_ids"], "Repeated IDs require explicit handling"
    stats = records(con, """
        SELECT count(*) AS vacancies,
               count(*) FILTER (WHERE len(skills)>0) AS with_skills,
               count(*) FILTER (WHERE len(skills)=0) AS without_skills,
               count(salary) AS salary_n, median(salary) AS median_salary,
               min(salary) AS salary_min, max(salary) AS salary_max,
               count(*) FILTER (WHERE salary < 10000) AS salary_below_10000,
               median(len(skills)) AS median_stack, max(len(skills)) AS max_stack,
               count(*) FILTER (WHERE salary_from IS NULL AND salary_to IS NULL) AS no_salary_bounds,
               count(*) FILTER (WHERE currency IN ('RUR','RUB') AND gross='true') AS rub_gross,
               count(*) FILTER (WHERE currency NOT IN ('RUR','RUB') AND currency IS NOT NULL) AS foreign_currency
        FROM vacancies
    """)[0]
    selected = records(con, """SELECT vacancy_id, name, area, experience, currency,
        gross, salary_from, salary_to, skills, salary FROM vacancies ORDER BY vacancy_id""")
    export_csv("selected_vacancies.csv", selected)
    ids = "\n".join(row["vacancy_id"] for row in selected).encode()
    stats["selected_ids_sha256"] = hashlib.sha256(ids).hexdigest()
    top = records(con, "SELECT * FROM combination_stats ORDER BY size, vacancies DESC, skills")
    effects = records(con, "SELECT * FROM effects ORDER BY size, delta_rub DESC, skills")
    regions = records(con, "SELECT * FROM regions_summary ORDER BY region")
    regional_skills = records(con, "SELECT * FROM regions_skills ORDER BY region, size, rank")
    assert len(regions) == 3, "One of the three regions has no selected vacancies"
    # Explain possible salary differences using experience composition.
    targets = set()
    for size in (2, 3):
        for group in ([r for r in effects if r["size"] == size and r["delta_rub"] > 0][:3],
                      sorted([r for r in effects if r["size"] == size and r["delta_rub"] < 0], key=lambda r: (r["delta_rub"], r["skills"]))[:3]):
            for r in group:
                targets.add(tuple(r["skills"]))
                targets.add(tuple(r["base_skills"]))
    composition = records(con, """
        SELECT c.skills, v.experience, count(*) AS n, median(v.salary) AS median_salary
        FROM combinations c JOIN vacancies v USING (vacancy_id)
        WHERE v.salary IS NOT NULL AND c.skills IN (SELECT unnest($targets))
        GROUP BY c.skills, v.experience
    """, {"targets": [list(t) for t in sorted(targets)]})
    result = {"variant": cfg["variant"], "name_regex": cfg["name_regex"],
              "source_audit": source_audit, "stats": stats, "support": cfg["minimum_salary_support"],
              "top": [r for k in (1, 2, 3) for r in [x for x in top if x["size"] == k][:10]],
              "effects": effects, "regions": regions,
              "regional_skills": [r for r in regional_skills if r["rank"] <= 3],
              "experience_composition": composition}
    save(ROOT / "results/analysis.json", result)
    for name, rows in [("skill_frequencies.csv", top), ("salary_effects.csv", effects),
                       ("regions_summary.csv", regions), ("regions_skills.csv", regional_skills)]:
        export_csv(name, rows)
    put_json("results/analysis.json", result)
    print(json.dumps({"source_audit": source_audit, "stats": stats, "regions": regions,
                      "eligible_pairs": sum(r["size"] == 2 for r in effects),
                      "eligible_triples": sum(r["size"] == 3 for r in effects)},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

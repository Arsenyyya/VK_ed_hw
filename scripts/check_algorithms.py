"""Small independent fixture for filtering, duplicates and unordered combinations."""
import csv
from collections import Counter
from pathlib import Path
import tempfile

import duckdb

from common import ROOT, require_variant
from duckdb_counts import count
from mapreduce import mapper


def main():
    cfg = require_variant()
    fixture = [
        ("1", "Frontend developer", "JavaScript; CSS; css; HTML", cfg["role"]),
        ("2", "Фронтенд-разработчик", "JavaScript; HTML", cfg["role"]),
        ("3", "Back-end developer", "Python", cfg["role"]),
        ("4", "Frontend analyst", "SQL", "Аналитик"),
        ("5", "Front-end developer", "", cfg["role"]),
    ]
    expected = Counter({("css",): 1, ("html",): 2, ("javascript",): 2,
                        ("css", "html"): 1, ("css", "javascript"): 1,
                        ("html", "javascript"): 2, ("css", "html", "javascript"): 1})
    for optimized in (False, True):
        result, selected, nonempty = mapper([(name, skills, role) for _, name, skills, role in fixture],
                                            cfg["name_regex"], cfg["role"], 0, optimized)
        assert Counter(result) == expected
        assert (selected, nonempty) == (3, 2)
    with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as folder:
        path = Path(folder) / "fixture.csv"
        with path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["vacancy_id", "name", "key_skills", "role", "area", "experience", "gross", "currency", "salary_from", "salary_to", "description"])
            for i, name, skills, role in fixture:
                w.writerow([i, name, skills, role, "Москва", "Нет опыта", "false", "RUR", "50000", "70000", "строка 1\nстрока 2"])
        con = duckdb.connect()
        con.execute((ROOT / "sql/prepare.sql").read_text(),
                    {"source": str(path), "pattern": cfg["name_regex"], "role": cfg["role"]})
        count(con, 0)
        actual = {tuple(s): n for s, n in con.execute("SELECT skills, count FROM counts").fetchall()}
        assert actual == expected
        assert con.execute("SELECT count(*), count(salary), median(salary) FROM vacancies").fetchone() == (3, 3, 60000.0)
    print("PASS: expected counts for singles/pairs/triples; both MR modes and SQL; role/title filter; deduplication; empty skills; multiline CSV; salary midpoint")


if __name__ == "__main__":
    main()

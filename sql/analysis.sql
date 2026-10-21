-- Full stacks, without the artificial benchmark caps.
CREATE TABLE skill_rows AS
SELECT vacancy_id, unnest(skills) AS skill FROM vacancies;

CREATE TABLE combinations AS
SELECT vacancy_id, [skill] AS skills FROM skill_rows
UNION ALL
SELECT a.vacancy_id, [a.skill, b.skill]
FROM skill_rows a JOIN skill_rows b
  ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
UNION ALL
SELECT a.vacancy_id, [a.skill, b.skill, c.skill]
FROM skill_rows a JOIN skill_rows b
  ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
JOIN skill_rows c
  ON a.vacancy_id = c.vacancy_id AND b.skill < c.skill;

CREATE TABLE combination_stats AS
SELECT c.skills, len(c.skills) AS size, count(*) AS vacancies,
       count(v.salary) AS salary_n, median(v.salary) AS median_salary
FROM combinations c JOIN vacancies v USING (vacancy_id)
GROUP BY c.skills;

-- For a pair, the baseline is its more frequent single skill.
-- For a triple, the baseline is its more frequent pair.
-- Frequency is measured among ALL selected vacancies, not only salary rows.
CREATE TABLE effects AS
WITH candidates AS (
    SELECT c.skills, c.size, c.vacancies, c.salary_n, c.median_salary,
           b.skills AS base_skills, b.vacancies AS base_vacancies,
           b.salary_n AS base_salary_n, b.median_salary AS base_median,
           row_number() OVER (
               PARTITION BY c.skills ORDER BY b.vacancies DESC, b.skills ASC
           ) AS rank
    FROM combination_stats c
    CROSS JOIN unnest(CASE WHEN c.size = 2
        THEN [[c.skills[1]], [c.skills[2]]]
        ELSE [[c.skills[1], c.skills[2]], [c.skills[1], c.skills[3]],
              [c.skills[2], c.skills[3]]] END) AS subsets(base)
    JOIN combination_stats b ON b.skills = subsets.base
    WHERE c.size IN (2, 3)
)
SELECT * EXCLUDE (rank),
       median_salary - base_median AS delta_rub,
       100.0 * (median_salary / base_median - 1) AS delta_pct
FROM candidates
WHERE rank = 1 AND salary_n >= $support AND base_salary_n >= $support
  AND base_median > 0;

CREATE TABLE regions_summary AS
SELECT area AS region, count(*) AS vacancies,
       count(*) FILTER (WHERE len(skills) > 0) AS with_skills,
       count(salary) AS salary_n, median(salary) AS median_salary,
       quantile_cont(salary, 0.25) AS q25, quantile_cont(salary, 0.75) AS q75,
       round(100.0 * count(salary) / count(*), 2) AS salary_share_pct
FROM vacancies WHERE list_contains($regions, area)
GROUP BY area;

CREATE TABLE regions_skills AS
WITH regional AS (
    SELECT v.area AS region, c.skills, len(c.skills) AS size,
           count(*) AS vacancies, count(v.salary) AS salary_n,
           median(v.salary) AS median_salary
    FROM combinations c JOIN vacancies v USING (vacancy_id)
    WHERE list_contains($regions, v.area)
    GROUP BY v.area, c.skills
)
SELECT r.*, 100.0 * r.vacancies / s.vacancies AS share_pct,
       row_number() OVER (
           PARTITION BY r.region, r.size ORDER BY r.vacancies DESC, r.skills
       ) AS rank
FROM regional r JOIN regions_summary s ON r.region = s.region;

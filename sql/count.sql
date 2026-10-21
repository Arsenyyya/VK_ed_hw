-- The ordered stack is capped only for the three scaling experiments.
CREATE TABLE stack AS
SELECT vacancy_id,
       CASE WHEN $cap = 0 THEN skills ELSE list_slice(skills, 1, $cap) END AS skills
FROM vacancies;

CREATE TABLE skill_rows AS
SELECT vacancy_id, unnest(skills) AS skill FROM stack;

-- Strict ordering gives each unordered combination exactly once per vacancy.
CREATE TABLE counts AS
SELECT [skill] AS skills, count(*)::BIGINT AS count
FROM skill_rows GROUP BY skill
UNION ALL
SELECT [a.skill, b.skill], count(*)::BIGINT
FROM skill_rows a JOIN skill_rows b
  ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
GROUP BY a.skill, b.skill
UNION ALL
SELECT [a.skill, b.skill, c.skill], count(*)::BIGINT
FROM skill_rows a JOIN skill_rows b
  ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
JOIN skill_rows c
  ON a.vacancy_id = c.vacancy_id AND b.skill < c.skill
GROUP BY a.skill, b.skill, c.skill;

-- The filter is supplied as a bound parameter from the confirmed variant.
CREATE TABLE vacancies AS
WITH cleaned AS (
    SELECT vacancy_id, name, area, experience, gross, currency,
           try_cast(salary_from AS DOUBLE) AS salary_from,
           try_cast(salary_to AS DOUBLE) AS salary_to,
           list_sort(list_distinct(
               [lower(trim(x)) FOR x IN string_split(coalesce(key_skills, ''), ';')
                IF length(trim(x)) > 0]
           )) AS skills
    FROM read_csv($source, header = true, all_varchar = true,
                  delim = ',', quote = '"', escape = '"',
                  max_line_size = 16777216, parallel = false)
    WHERE role = $role
      AND regexp_matches(coalesce(name, ''), $pattern, 'i')
)
SELECT *,
       CASE WHEN currency IN ('RUR', 'RUB') AND gross = 'false'
                 AND (salary_from > 0 OR salary_to > 0)
                 AND (salary_from IS NULL OR salary_from > 0)
                 AND (salary_to IS NULL OR salary_to > 0)
                 AND (salary_from IS NULL OR salary_to IS NULL
                      OR salary_from <= salary_to)
            THEN CASE WHEN salary_from IS NULL THEN salary_to
                      WHEN salary_to IS NULL THEN salary_from
                      ELSE (salary_from + salary_to) / 2 END
       END AS salary
FROM cleaned;

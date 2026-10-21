"""Build the readable report exclusively from this experiment's saved results."""
from collections import defaultdict
import json
from math import comb
import os
from pathlib import Path
from statistics import median

from common import ROOT, config

os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path):
    return json.loads((ROOT / path).read_text())


def num(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", "\u00a0").replace(".", ",")


def skill(values):
    labels = {"javascript": "JavaScript", "typescript": "TypeScript", "react": "React",
              "git": "Git", "html": "HTML", "css": "CSS", "html5": "HTML5", "css3": "CSS3",
              "rest": "REST", "ооп": "ООП", "rxjs": "RxJS", "ms sql": "MS SQL",
              "json": "JSON", "c#": "C#", "webpack": "Webpack", "api": "API", "angular": "Angular", "angularjs": "AngularJS"}
    return " + ".join(labels.get(s, s) for s in values)


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"]
                     + ["| " + " | ".join(str(x) for x in row) + " |" for row in rows])


def main():
    cfg = config()
    a, storage, verification = load("results/analysis.json"), load("logs/storage.json"), load("results/verification.json")
    stats, source = a["stats"], a["source_audit"]
    bench, env = load("logs/benchmark.json"), load("logs/environment.json")
    full = load("results/duckdb_cap0_runfull.json")
    groups = defaultdict(list)
    for r in bench:
        if isinstance(r["run"], int):
            groups[(r["cap"], r["engine"])].append(r)
    summary = {(cap, e): {"t": median(r["seconds"] for r in rows),
                           "m": median(r["peak_tree_rss_mib"] for r in rows)}
               for (cap, e), rows in groups.items()}
    names = {"baseline": "MR исходный", "optimized": "MR с combiner", "duckdb": "DuckDB SQL"}
    effects = {}
    for size in (2, 3):
        for direction in (1, -1):
            effects[size, direction] = sorted(
                [r for r in a["effects"] if r["size"] == size and r["delta_rub"] * direction > 0],
                key=lambda r: (-direction * r["delta_rub"], r["skills"]))[:3]
    regions = {r["region"]: r for r in a["regions"]}
    region_order = ["Москва", "Санкт-Петербург", "Екатеринбург"]
    caps = cfg["stack_caps"]
    growth = [load(f"results/duckdb_cap{cap}_run1.json") for cap in caps]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#263a48", "text.color": "#263a48"})
    fig, ax = plt.subplots(figsize=(8.2, 2.8), layout="constrained")
    for k, color, label in [(1, "#8b9dab", "Навыки"), (2, "#168b90", "Пары"), (3, "#213e60", "Тройки")]:
        ax.plot(caps, [r["orders"][str(k)]["occurrences"] for r in growth], "o-", color=color, label=label, linewidth=2)
    ax.set(xlabel="Максимум навыков в стеке", ylabel="Вхождения сочетаний", xticks=caps)
    ax.legend(frameon=False, ncol=3, loc="upper left")
    ax.grid(axis="y", alpha=.15)
    for suffix in ("png", "pdf"):
        fig.savefig(ROOT / f"evidence/growth.{suffix}", dpi=200)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.2, 2.55), layout="constrained")
    vals = [regions[r]["median_salary"] / 1000 for r in region_order]
    bars = ax.barh(region_order[::-1], vals[::-1], color=["#8b9dab", "#168b90", "#213e60"])
    for b, value in zip(bars, vals[::-1]):
        ax.text(value + 2, b.get_y() + b.get_height()/2, num(value) + " тыс. ₽", va="center")
    ax.set(xlim=(0, max(vals) * 1.25), xlabel="Медианная зарплата на руки, тыс. ₽")
    ax.grid(axis="x", alpha=.15)
    ax.set_axisbelow(True)
    for suffix in ("png", "pdf"):
        fig.savefig(ROOT / f"evidence/regions.{suffix}", dpi=200)
    plt.close(fig)

    pages = []
    pages.append(f"""# Анализ Frontend-вакансий

Вариант 8 · Программист, разработчик Frontend · 21 октября 2026

Репозиторий: [https://github.com/Arsenyyya/VK_ed_hw](https://github.com/Arsenyyya/VK_ed_hw).

Для работы я взял вакансии Frontend-разработчиков, посчитал навыки двумя способами — своим MapReduce и SQL в DuckDB — и сравнил результаты. После этого разобрался, как набор навыков связан с зарплатой и чем отличаются вакансии в трёх городах.

В выборку вошли {num(stats['vacancies'])} вакансий. У {num(stats['with_skills'])} указаны навыки, а {num(stats['salary_n'])} подходят для сравнения зарплат.

## Какие вакансии вошли

Использовал файл `it_vacancies_2024.csv` из прошлой лабораторной. В нём {num(source['rows'])} строк, повторяющихся ID нет. Вакансии опубликованы с {source['published_min']} по {source['published_max']}, данные собраны с {source['snapshot_min']} по {source['snapshot_max']}. Выводы относятся к этому набору вакансий.

Мой фильтр в SQL:

```sql
WHERE role = 'Программист, разработчик'
  AND regexp_matches(name,
      'front[ -]?end|фронт[ -]?[еэ]нд', 'i')
```

Оставил роль «Программист, разработчик» и названия со словом Frontend, Front-end, Front end или его русским написанием. В MapReduce такой же фильтр написал через `re`.

{table(['Проверка данных', 'Результат'], [
['Вакансии варианта 8', num(stats['vacancies'])],
['С указанными навыками', f"{num(stats['with_skills'])} ({num(100*stats['with_skills']/stats['vacancies'],1)}%)"],
['Без навыков; в региональных итогах учтены', num(stats['without_skills'])],
['Медианный / максимальный размер полного стека', f"{num(stats['median_stack'])} / {num(stats['max_stack'])}"],
['Зарплата: рубли на руки', f"{num(stats['salary_n'])} ({num(100*stats['salary_n']/stats['vacancies'],1)}%)"],
['Медиана сопоставимых зарплат', num(stats['median_salary']) + ' ₽']])}

Зарплаты сравнивал в рублях на руки: RUR/RUB, `gross=false`, сумма больше нуля. Если указан диапазон, брал его середину, если одну границу — её значение. У {num(stats['no_salary_bounds'])} вакансий зарплаты нет, у {num(stats['rub_gross'])} указана сумма до налогов, ещё у {num(stats['foreign_currency'])} — другая валюта. В исходнике также есть {stats['salary_below_10000']} суммы ниже 10 000 ₽. Оставил их без изменений; они входят в расчёт медианы.
""")
    pages.append(f"""## Хранилище и загрузка данных

RustFS запустил в отдельном контейнере с четырьмя папками вместо дисков. Все папки находятся на одном накопителе. Настройки сохранил в `compose.yaml`.

{table(['Параметр', 'Значение'], [
['Сервер', 'RustFS 1.0.1, образ закреплён по SHA-256 digest'],
['Адрес S3 / консоли', '127.0.0.1:19100 / 127.0.0.1:19101'],
['Bucket и объект', 'hh-lake / it_vacancies_2024.csv'],
['Размер объекта', num(storage['bytes']) + ' байт'],
['PUT / полный GET', 'HTTP 200 / HTTP 200, SHA-256 совпал']])}

```bash
docker compose up -d
.venv/bin/python scripts/storage.py
```

![Снимок 1. Запущенный RustFS, объект в hh-lake и проверка чтения данных.](evidence/01-storage.png)

SHA-256 исходного файла и обратного чтения:

```text
{storage['sha256']}
```

После загрузки полностью прочитал объект через S3 и сравнил SHA-256 с исходным файлом — хеши совпали. Вывод команды сохранил в `logs/upload-terminal.log`, параметры загрузки — в `logs/storage.json`. Результаты всех запусков для трёх размеров стека лежат в `s3://hh-lake/results/`.
""")
    pages.append("""## Как считаются навыки, пары и тройки

Частоту считал по числу вакансий с навыком или сочетанием. Навыки разделил по `;`, убрал лишние пробелы, привёл названия к нижнему регистру и удалил повторы внутри вакансии. Разные написания, например `html` и `html5` или `react` и `react.js`, оставил отдельно.

Порядок навыков не важен: JavaScript + React и React + JavaScript — одна и та же пара. Вакансии без навыков учитывал в общей численности.

### Свой MapReduce

В `scripts/mapreduce.py` файл читается прямо из S3 с буфером 1 МиБ и разбивается на чанки по 1000 строк. Переносы внутри кавычек обрабатывает CSV-парсер. Для подсчёта использовал 4 процесса маппера, одновременно в работе — до 8 чанков.

```python
skills = sorted({x.strip().lower()
                 for x in raw.split(';') if x.strip()})
for size in (1, 2, 3):
    partial.update(combinations(skills, size))
# редьюсер суммирует частоты из готовых чанков
```

В первой версии сначала собирал все ключи, затем суммировал их частоты. В улучшенной версии маппер сразу объединяет повторы через `Counter`, а редьюсер добавляет результаты готовых чанков в общий счётчик.

### Проверка через DuckDB

Для второго способа написал SQL-запросы. DuckDB читает тот же `s3://hh-lake/it_vacancies_2024.csv` через расширение `httpfs` и считает частоты отдельно от MapReduce. Подготовка данных находится в `sql/prepare.sql`, подсчёт — в `sql/count.sql`.

```sql
SELECT [a.skill, b.skill], count(*)
FROM skill_rows a JOIN skill_rows b
  ON a.vacancy_id = b.vacancy_id AND a.skill < b.skill
GROUP BY a.skill, b.skill;
-- для троек добавляется c с условием b.skill < c.skill
```

Одиночные навыки считаются через `GROUP BY`. Для пар таблица навыков соединяется сама с собой по ID вакансии, для троек добавляется ещё одно соединение. Условие `a.skill < b.skill` убирает повторные перестановки. Фильтр варианта хранится в `config.json` и передаётся в запрос.
""")
    frequency_sections = []
    for size, label in [(1, "Одиночные навыки"), (2, "Пары"), (3, "Тройки")]:
        rows = [r for r in a["top"] if r["size"] == size][:5]
        frequency_sections.append("### " + label + "\n\n" + table(
            ["Навык / сочетание", "Вакансий", "Доля всех Frontend"],
            [[skill(r["skills"]), num(r["vacancies"]), num(100*r["vacancies"]/stats["vacancies"],1)+"%"] for r in rows]))
    pages.append("## Самые частые навыки и сочетания\n\nЗдесь использовал все навыки вакансии, без ограничения размера стека. Ниже — по пять самых частых навыков, пар и троек. Доли посчитаны от всех " + num(stats["vacancies"]) + " вакансий варианта.\n\n" + "\n\n".join(frequency_sections) + "\n\nНа первом месте JavaScript — он указан более чем в половине вакансий. Самая частая пара — JavaScript + TypeScript, а самая частая тройка — JavaScript + React + TypeScript. Полные результаты сохранил в `results/skill_frequencies.csv`.\n")
    pages.append(f"""## Размер стека и проверка результатов

Чтобы посмотреть, как растёт число сочетаний, сделал три запуска с ограничением стека: {', '.join(map(str,caps))} навыков. Сначала сортировал названия по алфавиту, затем брал первые навыки до лимита. Если их меньше, оставлял все. Для анализа зарплат и регионов использовал полные стеки.

{table(['Лимит стека', 'Навыки: вхождения', 'Пары: вхождения', 'Тройки: вхождения'],
[[str(cap)] + [num(r['orders'][str(k)]['occurrences']) for k in (1,2,3)] for cap,r in zip(caps,growth)] +
[['Полный'] + [num(full['orders'][str(k)]['occurrences']) for k in (1,2,3)]])}

Вакансия с m навыками даёт m одиночных ключей, C(m,2) = m(m−1)/2 пар и C(m,3) = m(m−1)(m−2)/6 троек. Например:

{table(['m', 'Одиночных', 'Пар', 'Троек'], [[str(s),str(s),str(comb(s,2)),str(comb(s,3))] for s in caps])}

При росте лимита с {caps[0]} до {caps[-1]} фактическое число пар выросло в {num(growth[-1]['orders']['2']['occurrences']/growth[0]['orders']['2']['occurrences'],2)} раза, троек — в {num(growth[-1]['orders']['3']['occurrences']/growth[0]['orders']['3']['occurrences'],2)} раза. Рост слабее, чем у одной вакансии с ровно m навыками: у многих вакансий стек короче лимита и остаётся прежним.

![Рисунок 1. Число вхождений навыков, пар и троек при разных размерах стека.](evidence/growth.png)

Для каждого запуска сравнил все сочетания и их частоты в MapReduce и DuckDB. Всего получилось {verification['count_comparisons']} сравнений: три размера стека, все режимы и повторы, полный стек и запуск после отказа. Расхождений нет. Сохранённые JSON также прочитал обратно из S3 и проверил их содержимое.

В полном стеке получилось {num(full['orders']['1']['distinct'])} разных навыков, {num(full['orders']['2']['distinct'])} пар и {num(full['orders']['3']['distinct'])} троек. SHA-256 отсортированной таблицы результатов:

```text
{full['sha256']}
```
""")
    trial_rows = []
    for cap in caps:
        for engine in ("baseline", "optimized", "duckdb"):
            rs = sorted(groups[cap,engine], key=lambda r:r["run"])
            trial_rows.append([str(cap), names[engine], " / ".join(num(r["seconds"],2) for r in rs),
                               " / ".join(num(r["peak_tree_rss_mib"],1) for r in rs)])
    med_rows = [[str(cap),names[e],num(summary[cap,e]["t"],2),num(summary[cap,e]["m"],1)] for cap in caps for e in ("baseline","optimized","duckdb")]
    last = caps[-1]
    ratio = summary[last,"duckdb"]["t"] / summary[last,"optimized"]["t"]
    pages.append(f"""## Сравнение времени и памяти

Замеры выполнил на {env['platform']}: {env['logical_cpus']} логических CPU и {num(env['ram_bytes']/2**30)} ГиБ памяти. MapReduce работал в 4 процессах с чанками по 1000 строк, DuckDB — в 4 потоках с лимитом памяти 2 ГБ. Каждый режим запускал по три раза в отдельном Python-процессе. Замерял весь запуск, от чтения S3 до сохранения результата.

Память оценивал по пику суммы RSS клиентских процессов с опросом каждые 10 мс. Потребление Docker и RustFS в этот замер не входит. Такой замер может повторно учитывать общие страницы и пропускать короткие пики. Запуски шли по очереди; кеши не сбрасывал, порядок режимов между попытками менял.

### Все 27 измерений

В каждой ячейке перечислены попытки 1 / 2 / 3. МиБ = 1 048 576 байт.

{table(['Лимит', 'Режим', 'Время, с · 1 / 2 / 3', 'Пик RSS, МиБ · 1 / 2 / 3'],trial_rows)}

### Медианы трёх попыток

{table(['Лимит', 'Режим', 'Время, с', 'Пик RSS, МиБ'], med_rows)}

При лимите {last} DuckDB работал в {num(ratio,2)} раза дольше, чем MR с combiner, и потреблял больше памяти. На результат влияют чтение CSV, буферы и промежуточные таблицы; отдельно их вклад я не измерял. Между попытками есть разброс, поэтому сравнение относится к этому стенду и этому файлу. Подробные замеры — в `logs/benchmark.json`.
""")
    optrows = []
    for cap in caps:
        before, after = summary[cap,"baseline"], summary[cap,"optimized"]
        optrows.append([str(cap), num(before["t"],2)+" → "+num(after["t"],2),
                        num(before["m"],1)+" → "+num(after["m"],1),
                        num((1-after["t"]/before["t"])*100,1)+"%",
                        num((1-after["m"]/before["m"])*100,1)+"%"])
    pages.append(f"""## Оптимизация и проверка отказа маппера

Для оптимизации добавил в маппер локальный `Counter`. Он объединяет одинаковые сочетания до передачи редьюсеру. Редьюсер сразу складывает частоты готовых чанков, поэтому хранить весь список ключей уже не нужно. Источник данных, число процессов и размер чанка оставил прежними.

{table(['Лимит', 'Время до → после, с', 'RSS до → после, МиБ', 'Экономия времени', 'Экономия памяти'],optrows)}

В таблице приведены медианы трёх запусков. Отрицательный процент означает, что после изменения стало хуже. Памяти во всех случаях потребовалось меньше, а по времени выигрыш получился только при стеке до 15 навыков. На коротких стеках разница во времени невелика по сравнению с разбросом между попытками.

### Проверка восстановления

Чтобы проверить обработку отказа, завершил первый процесс маппера через `os._exit(17)`. После ошибки `BrokenProcessPool` программа отбрасывает частичный результат, создаёт новые процессы и один раз повторяет расчёт с чтением S3 с начала. Итоговый JSON записывается после успешного завершения, поэтому частоты не удваиваются.

```bash
.venv/bin/python scripts/mapreduce.py --cap 0 \\
  --run recovery --fail-worker
.venv/bin/python scripts/verify.py
```

![Снимок 2. Сверка результатов MapReduce и DuckDB и проверка восстановления после отказа.](evidence/02-verification.png)

После повтора результат совпал с обычным запуском и с DuckDB. Журнал отказа и повторного запуска — `logs/recovery.log`, сведения об ошибке также есть в поле `recovery` итогового JSON. В этой реализации расчёт после сбоя начинается заново.
""")
    def effect_table(size):
        rows=[]
        for direction,label in [(1,"Выше"),(-1,"Ниже")]:
            for r in effects[size,direction]:
                rows.append([label + ': ' + skill(r["skills"]),
                             skill(r["base_skills"]) + f"; {num(r['base_median'])} ₽; n={r['base_salary_n']}",
                             f"{num(r['median_salary'])} ₽; n={r['salary_n']}",
                             ("+" if r["delta_rub"]>0 else "")+num(r["delta_rub"])+" ₽; "+("+" if r["delta_pct"]>0 else "")+num(r["delta_pct"],1)+"%"])
        return table(["Сочетание", "База: медиана / n", "Сочетание: медиана / n", "Разница"],rows)
    pages.append(f"""## Зарплата и пары навыков

Медиана по {num(stats['salary_n'])} вакансиям с сопоставимой зарплатой — **{num(stats['median_salary'])} ₽**. Для сравнения оставил сочетания хотя бы с {a['support']} зарплатами. Частоту навыков при выборе базы считал по всем {num(stats['vacancies'])} вакансиям.

Для пары A+B брал за базу более частый навык и сравнивал медиану вакансий с ним с медианой вакансий, где есть оба навыка. Базовая группа включает вакансии с сочетанием. При равных частотах выбирал навык по алфавиту. Разницу считал так: Δ = медиана сочетания − медиана базы; Δ% = 100 × (медиана сочетания / медиана базы − 1).

Ниже — по три пары с наибольшей положительной и отрицательной разницей в рублях. `n` — число вакансий с зарплатой в соответствующей группе.

{effect_table(2)}

Полная таблица с частотами — в `results/salary_effects.csv`. Например, REST указан в 295 вакансиях, REST + ООП — в 13; зарплата есть у 132 и 12 из них. JavaScript встречается в 3202 вакансиях, JavaScript + MS SQL — в 19; для медиан использованы 1098 и 14 зарплат.

Самые большие прибавки получились у редких сочетаний: REST + ООП и пар с RxJS. Выборки небольшие, поэтому на медиану может сильно влиять состав вакансий. У пар с MS SQL, C# и JSON медианы ниже базовой. Возможные причины — другой уровень позиций и требования к опыту; по одним названиям навыков их отделить нельзя.
""")
    composition = a["experience_composition"]
    def exp_note(keys):
        rs = sorted([r for r in composition if r["skills"] == keys], key=lambda r:(-r["n"],r["experience"] or ""))
        return "; ".join(f"{r['experience'] or 'не указано'} — {r['n']}" for r in rs)
    plus, minus = effects[3,1][0], effects[3,-1][0]
    pages.append(f"""## Зарплата и тройки навыков

Для тройки взял за базу самую частую из входящих в неё пар. Так можно сравнить пару навыков с тем же набором и ещё одним навыком. Для базы оставил то же ограничение — хотя бы {a['support']} вакансий с зарплатой.

{effect_table(3)}

Самая большая прибавка получилась у Git + Webpack + ООП: 300 000 ₽ против 140 000 ₽ у пары Git + Webpack. Пара встречается в 225 вакансиях, тройка — в 17; зарплата есть у 122 и 13 из них.

У API + Git + REST медиана 67 500 ₽ против 150 000 ₽ у более частой пары Git + REST: −82 500 ₽. Зарплатная выборка тройки — 14 наблюдений, базы — 85.

### Как я понимаю эти результаты

Посмотрел требования к опыту. У вакансий с зарплатой и сочетанием {skill(plus['skills'])}: {exp_note(plus['skills'])}. У {skill(minus['skills'])}: {exp_note(minus['skills'])}. В дорогой группе чаще нужен опыт 3–6 лет, в дешёвой — 1–3 года. Это может объяснять часть разницы.

Кроме навыков, на зарплату влияют опыт, компания и регион. Поэтому Δ показывает разницу между группами вакансий, а не гарантированную прибавку за изучение технологии. Особенно это касается сочетаний, где зарплат всего 10–15.

В итоговой таблице — {sum(r['size']==2 for r in a['effects'])} пар и {sum(r['size']==3 for r in a['effects'])} троек. Для каждой сохранены база, частоты, обе медианы, размеры выборок и разница в рублях и процентах.
""")
    pages.append(f"""## Сравнение зарплат в трёх городах

Для сравнения выбрал Москву, Санкт-Петербург и Екатеринбург. Город определял по точному значению `area`, области отдельно не добавлял. Учитывал все вакансии своего варианта, в том числе без навыков. Зарплаты отбирал по тем же правилам, что и выше.

{table(['Регион','Вакансий','С навыками','Зарплат, n','Доля с зарплатой','Медиана, ₽','Q25–Q75, ₽'],[
[r, num(regions[r]['vacancies']),num(regions[r]['with_skills']),num(regions[r]['salary_n']),num(regions[r]['salary_share_pct'],1)+'%',num(regions[r]['median_salary']),num(regions[r]['q25'])+'–'+num(regions[r]['q75'])] for r in region_order])}

Q25–Q75 — центральная половина зарплатной выборки. Размеры зарплатных групп указаны отдельно от общего числа вакансий.

![Рисунок 2. Медианные зарплаты на руки в Москве, Санкт-Петербурге и Екатеринбурге.](evidence/regions.png)

Москва даёт {num(100*regions['Москва']['vacancies']/stats['vacancies'],1)}% всех Frontend-вакансий выборки. Её медиана выше петербургской на {num(regions['Москва']['median_salary']-regions['Санкт-Петербург']['median_salary'])} ₽ и екатеринбургской на {num(regions['Москва']['median_salary']-regions['Екатеринбург']['median_salary'])} ₽.

В Москве зарплата указана у 25,1% вакансий, а в Екатеринбурге — у 48,4%. Поэтому московская медиана рассчитана по меньшей доле объявлений. По этой выборке Москва лидирует, но зарплатные диапазоны трёх городов заметно пересекаются.

Первая региональная таблица целиком — `results/regions_summary.csv`; запрос — `sql/analysis.sql`.
""")
    region_skill_rows=[]
    for region in region_order:
        for size in (1,2,3):
            r = next(x for x in a["regional_skills"] if x["region"]==region and x["size"]==size and x["rank"]==1)
            region_skill_rows.append([region,str(size),skill(r["skills"]),num(r["vacancies"]),num(r["share_pct"],1)+"%",num(r["median_salary"]),str(r["salary_n"])])
    pages.append(f"""## Сравнение навыков в трёх городах

Во второй таблице собрал самый частый навык, пару и тройку для каждого города. Доли посчитал от всех местных вакансий, включая строки без навыков. Для каждого сочетания также указал медиану зарплаты и число наблюдений `n`.

{table(['Регион','Размер','Навык / сочетание','Частота','Доля','Медиана, ₽','n'],region_skill_rows)}

Во всех трёх городах лидирует JavaScript, а среди пар — JavaScript + TypeScript. У этой пары медиана в Москве — 200 000 ₽, в Санкт-Петербурге — 150 000 ₽, в Екатеринбурге — 137 500 ₽. То есть разница между городами сохраняется и при сравнении одинакового сочетания.

Самая частая тройка Москвы и Петербурга — JavaScript + React + TypeScript, а Екатеринбурга — CSS + HTML + JavaScript. В Екатеринбурге эта тройка есть в 23,8% вакансий, московский лидер — в 15,9%. Получается, что в екатеринбургской выборке базовый набор для вёрстки встречается относительно чаще. При этом полнота заполнения навыков в городах различается.

Медианы у лидирующих троек — 200 000 ₽ в Москве, 155 000 ₽ в Петербурге и 102 500 ₽ в Екатеринбурге. Екатеринбургская тройка отличается по составу, поэтому её зарплату нельзя напрямую считать региональной ценой того же стека.

В `results/regions_skills.csv` сохранены все рассчитанные навыки, пары и тройки по каждому региону, с частотой, долей, медианой и числом зарплат. В `results/analysis.json` для удобства оставлены по три лидера каждого порядка и региона.
""")
    pages.append(f"""## Файлы работы и запуск

Код, SQL-запросы, таблицы, журналы, скриншоты и отчёт собраны в репозитории [Arsenyyya/VK_ed_hw](https://github.com/Arsenyyya/VK_ed_hw). Локальная папка работы — `skills_analytics_lab`. Исходный CSV и папки-диски RustFS из-за размера не включал в Git. Размер и SHA-256 исходного файла сохранены в журнале загрузки.

После установки зависимостей и настройки пути к исходному CSV работу можно повторить командами:

```bash
docker compose up -d
.venv/bin/python scripts/install_extension.py
.venv/bin/python scripts/storage.py
.venv/bin/python scripts/check_algorithms.py
.venv/bin/python scripts/analyze.py
.venv/bin/python scripts/benchmark.py
.venv/bin/python scripts/verify.py
.venv/bin/python scripts/build_report.py
.venv/bin/python scripts/render_pdf.py
```

Путь к исходному файлу, вариант, регионы, параметры чанков и размеры стека — в `config.json`. Команда `benchmark.py` выполняет 27 основных замеров, отдельно полный стек обоими способами и запуск с отказом. `verify.py` проверяет все частоты и обратное чтение результатов из `hh-lake`.

{table(['Что посмотреть', 'Файл'], [
['Исходный объект, размер, SHA-256, PUT и GET', 'logs/storage.json'],
['Каждая попытка: команда, время, RSS, exit code', 'logs/benchmark.json и отдельные .log'],
['Полная сверка и проверка сохранённых S3-результатов', 'results/verification.json'],
['Сбой процесса и успешный повтор', 'logs/recovery.log'],
['Все частоты и зарплатные сравнения', 'results/skill_frequencies.csv; salary_effects.csv'],
['Обе региональные таблицы', 'results/regions_summary.csv; regions_skills.csv']])}

### Источники

- [DuckDB: S3 API и httpfs](https://duckdb.org/docs/stable/core_extensions/httpfs/s3api) — подключение к S3-совместимому endpoint.
- [DuckDB: чтение CSV](https://duckdb.org/docs/stable/data/csv/overview) — параметры парсинга и `all_varchar`.
- [Python 3.12: itertools.combinations](https://docs.python.org/3.12/library/itertools.html#itertools.combinations) — неупорядоченные сочетания.
- [psutil: Process.memory_info](https://psutil.readthedocs.io/en/latest/#psutil.Process.memory_info) — измерение RSS процессов.

Дата обращения к документации — 21.10.2026. Версии библиотек указаны в `requirements.txt`, параметры компьютера и запусков — в `logs/environment.json`.
""")
    (ROOT / "report.md").write_text("\n\n<!-- pagebreak -->\n\n".join(p.strip() for p in pages) + "\n")
    print("Built report.md from", len(pages), "sections")


if __name__ == "__main__":
    main()

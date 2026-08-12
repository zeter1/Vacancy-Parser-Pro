# AGENTS.md

## Project goal

Maintain a reliable Windows desktop vacancy aggregator with high recall, transparent filtering and diagnostic logs that make broken sources easy to identify.

## Important files

- `vacancy_parser.py` — canonical entry point.
- `vacancy_gui.py` — Tkinter UI and local persistence/export.
- `job_scraper.py` — search backend, filters and source adapters.
- `problem_logging.py` — per-search diagnostic sessions under `Логи проблем/`.
- `tests/test_parser_core.py` — network-free backend regression tests.
- `tests/test_problem_logging.py` — diagnostic-session tests.
- `requirements.txt` — runtime dependencies.
- `.github/workflows/ci.yml` — Windows compile/import/test CI.

## Source-adapter rules

- One broken source must never stop the others.
- Every network operation needs bounded timeouts and retries.
- Prefer official APIs where practical, but if an official anonymous endpoint returns CAPTCHA/403, a normal public website fallback may be used without attempting to bypass CAPTCHA.
- HTML adapters must use tolerant selectors and record `fetched`, `accepted` and rejection counters.
- Pagination must be bounded (`MAX_HTML_PAGES` / `MAX_HH_PAGES`) and cancellable.
- Never silently return zero because markup changed: record a source error.
- Do not add a checkbox until the source has real search code and diagnostics.

## Salary rules

Three user modes are supported:

- `Не фильтровать`
- `Мягкий`
- `Строгий`

Soft mode intentionally preserves vacancies with missing salary. Do not push a salary threshold down to an upstream API if doing so would remove vacancies that soft mode is supposed to keep.

## TLS and secrets

- Never disable TLS verification globally.
- A source-specific read-only compatibility fallback may exist only when its failure is explicit in logs and it does not affect other domains.
- Never commit OAuth/API tokens, cookies, personal profiles or user-generated logs.
- `HH_API_TOKEN` is environment-only.

## Problem logs

Every search must create one separate folder in `Логи проблем/`.

The final JSON must include every selected source, even when its count is zero, and preserve source errors plus structured diagnostics.

## Threading and reliability

- Do not update Tk widgets from worker threads; use `root.after`.
- Keep long searches cancellable.
- Do not redirect global `sys.stdout`.
- Config/profile writes must remain atomic.
- Keep runtime logs and exports out of Git.

## Before commit

Run:

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
python -c "import job_scraper, vacancy_gui, vacancy_parser, problem_logging"
```

For source-adapter changes, manually test at least one Belarus query and one Russian query. For a failed or suspicious search, inspect the newest session in this order:

1. `Логи проблем/<session>/00_прочитать_нейросети_сначала.txt`
2. `Логи проблем/<session>/04_диагностика_источников.json`
3. `Логи проблем/<session>/03_итог.json`
4. `Логи проблем/<session>/01_лог_поиска.log`
5. `Логи проблем/<session>/02_параметры_поиска.json`

Use `samples`, `pages_detail`, `reported_total`, `warnings` and `ai_diagnosis` before guessing at a parser failure.

Before push:

```powershell
git status
git branch --show-current
git remote -v
```

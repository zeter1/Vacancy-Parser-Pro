# Vacancy Parser Pro

Windows desktop vacancy aggregator built with Python and Tkinter. It searches multiple job sources, applies local filters, removes duplicates, exports results to Excel and writes structured diagnostics for troubleshooting source and parsing problems.

## Features

- Multi-source vacancy search from one desktop interface.
- Search profiles for frequently used queries.
- Filters by profession, city, minimum salary, experience, work format and publication period.
- Three salary modes: no filtering, soft filtering and strict filtering.
- Vacancy deduplication across sources.
- Open vacancies directly in the browser.
- Excel export.
- Per-source statistics and fault isolation: one broken source does not stop the entire search.
- Structured problem logs designed to make parser regressions and source changes easy to diagnose.
- Network-free regression tests for parser logic.
- Windows EXE build helper.

## Supported sources

The application currently includes adapters for:

- Rabota.by
- HH.ru
- Praca.by
- Belmeta
- GSZ.gov.by

External job sites can change markup, rate-limit requests or temporarily return server errors. Each adapter is therefore isolated and records its own diagnostics.

## Project structure

- `vacancy_parser.py` — application entry point.
- `vacancy_gui.py` — Tkinter UI, profiles, status, statistics and Excel export.
- `job_scraper.py` — networking, parsing, filtering, deduplication and source adapters.
- `problem_logging.py` — structured per-search diagnostics.
- `tests/` — network-free regression tests.
- `parser_config.example.json` — example local configuration.
- `build_exe.bat` — Windows EXE build helper.

## Installation

Requires a current Python 3 installation on Windows.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
python vacancy_parser.py
```

or double-click `run.bat`.

## Salary filtering

`Мин. доход` works together with `Фильтр зарплаты`:

- **Не фильтровать** — vacancies are not rejected by salary.
- **Мягкий** — vacancies without salary remain visible; salary ranges may reach the requested minimum.
- **Строгий** — the salary must be known and its guaranteed lower bound must be at least the requested minimum.

Soft mode is useful when recall is more important than strict salary verification.

## Problem diagnostics

Every search creates its own session directory inside `Логи проблем/`.

```text
Логи проблем/
└── 2026-08-12_15-18-47/
    ├── 00_прочитать_нейросети_сначала.txt
    ├── 01_лог_поиска.log
    ├── 02_параметры_поиска.json
    ├── 03_итог.json
    ├── 04_диагностика_источников.json
    ├── 05_проверка_ссылок.jsonl
    └── 06_итог_проверки_ссылок.txt
```

The diagnostics include per-source page counts, fetched and accepted vacancy counts, filter reasons, warnings, HTTP/network failures, bounded accepted/rejected examples and link-opening information. Secrets such as OAuth tokens are not written to the logs.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The regression suite is designed to run without live network access.

## Build EXE

Run:

```text
build_exe.bat
```

The executable is created in `dist/`.

## Notes about external sources

Rabota.by / HH may restrict anonymous API traffic, so the project includes bounded public-page fallback logic. GSZ.gov.by has also shown certificate-chain and server-side failures in real sessions; compatibility handling is scoped to that source instead of disabling TLS globally.

## Changelog

Detailed release history and parser fixes are kept in [CHANGELOG.md](CHANGELOG.md).

## License

No license has been selected yet. Unless a license is added later, the repository remains source-available under the default copyright rules.

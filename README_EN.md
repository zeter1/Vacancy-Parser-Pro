**Язык / Language:** [Русский](README.md) · **English**

# Vacancy Parser Pro

**Vacancy Parser Pro** is a Python/Tkinter desktop application that searches for vacancies across several sources at once. It collects results, applies local filters, removes duplicates, shows per-source statistics, and exports vacancies to Excel.

The project is built around independent source adapters: a failure or markup change on one site should not stop the entire search. Structured diagnostic sessions are created for network failures and parser changes.

## What the project demonstrates

- independent adapters for external sources;
- fault isolation: one failing site does not stop the aggregator;
- network parsing, normalization, and aggregation of heterogeneous data;
- local filtering, deduplication, and Excel export;
- source-specific diagnostics tied to a concrete search session;
- parser regression tests that do not require real websites;
- careful TLS/network error handling without globally weakening security.

## Features

- simultaneous search across several vacancy sources;
- reusable search profiles;
- filters for profession, city, salary, experience, work format, and publication period;
- soft and strict salary-filter modes;
- cross-source duplicate removal;
- opening vacancies in a browser;
- Excel export;
- statistics for each source;
- parser failure isolation;
- structured diagnostic sessions;
- offline parser regression tests;
- Windows EXE build support.

## Supported sources

- Rabota.by
- HH.ru
- Praca.by
- Belmeta
- GSZ.gov.by

External sites can change their HTML, APIs, and access restrictions, so individual adapters may require maintenance over time.

## Installation

1. Install a current Python 3 version for Windows.
2. Download the project with **Code → Download ZIP** or Git:

```bash
git clone https://github.com/zeter1/Vacancy-Parser-Pro.git
cd Vacancy-Parser-Pro
```

3. Create a virtual environment and install dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Launch

```powershell
python vacancy_parser.py
```

or double-click:

```text
run.bat
```

## Usage

1. Start the application.
2. Enter a profession or keywords.
3. Optionally choose a city, minimum income, experience, work format, and publication period.
4. Select the salary-filter mode.
5. Start the search.
6. Wait for the sources to finish; statistics show which sites completed successfully and how many vacancies were found.
7. Open an interesting vacancy in the browser or export the results to Excel.
8. Save a search profile for frequently reused parameters.

If one source stops working, inspect `Логи проблем` first. It contains diagnostics for the corresponding search session.

## Salary filtering

`Minimum income` works together with the salary-filter mode:

- **No filtering** — vacancies are not excluded by salary.
- **Soft** — vacancies without salary remain; a salary range may reach the requested minimum.
- **Strict** — salary must be present and the guaranteed lower bound must be at least the selected minimum.

## Project structure

- `vacancy_parser.py` — entrypoint.
- `vacancy_gui.py` — GUI, profiles, state, statistics, and Excel export.
- `job_scraper.py` — network requests, parsing, filtering, and deduplication.
- `problem_logging.py` — structured diagnostics.
- `tests/` — regression tests.
- `parser_config.example.json` — configuration example.
- `build_exe.bat` — EXE build script.

## Diagnostics

Every search creates a separate session under `Логи проблем/`. It records query parameters, statistics, HTTP failures, warnings, filtering reasons, and bounded result samples.

Secret values, including OAuth tokens, are intentionally excluded from diagnostic files.

## Verification and tests

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

CI also imports the application's main modules on Windows. Core parser tests are designed to run offline; actual website availability remains an external runtime dependency.

## Support and security

- [`SUPPORT.md`](SUPPORT.md) — useful information for bug reports;
- [GitHub Issues](https://github.com/zeter1/Vacancy-Parser-Pro/issues) — regular bugs;
- [`SECURITY.md`](SECURITY.md) — reporting potential vulnerabilities.

## Building the EXE

```text
build_exe.bat
```

The resulting build is created under `dist/`.

## License

No open-source license has been selected yet. The source code is available for portfolio review and implementation study.
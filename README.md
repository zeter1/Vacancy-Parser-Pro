# Vacancy Parser Pro 4.9

Desktop vacancy aggregator for Windows written in Python/Tkinter.

## What changed in 4.9

This pass is based on the successful 4.8 session with 162 unique vacancies and
targets the remaining data-quality and recall issues visible in the per-source
diagnostics.

- **Belmeta search context is preserved across pagination.** When the HTML exposes
  both a generic `/vacansii` link and a query-preserving
  `/vacansii?q=<profession>&page=N` link, the parser now ranks and follows the
  query-preserving route. Generic whole-site navigation is deliberately
  deprioritized so a profession search cannot silently turn into the global feed.
- Belmeta fallback probes now start from a query-preserving `/vacansii?q=...`
  URL instead of probing the SEO profession path with page parameters that the
  site may ignore.
- **Rabota employer extraction is more tolerant.** The parser now checks current
  employer/company selectors and employer links, then uses a bounded card-text
  fallback when `data-qa` names change.
- **Rabota secondary SEO fallback is guarded.** If
  `/vacancies/<profession>` redirects to generic `/vacancies`, the parser stops
  that fallback immediately instead of downloading unrelated cards and
  inflating duplicate/filter statistics.
- **GSZ location discovery is more tolerant of form changes.** Region/district/
  village controls are discovered by their current `name` or `id` hints, and
  only numeric values actually exposed by the live HTML are submitted. No city
  or region IDs are hardcoded.
- GSZ diagnostics now record the inspected location controls when available,
  making future portal-form changes visible in `04_диагностика_источников.json`.
- Added five regression tests for Belmeta pagination ranking, Rabota employer
  fallback, Rabota generic-SEO redirect protection and GSZ changed-control
  discovery.

## Previous 4.8 changes


This pass is based on the successful 4.7 session that returned 162 unique
vacancies and showed three remaining quality/recall issues rather than critical
application failures.

- **GSZ employer extraction:** when the search table does not expose a usable
  employer header, the parser now recovers the employer from the compact card
  text between the parsed salary and GSZ metadata such as `Ставка:`. This
  handles real rows such as `ООО "Экокор групп"` and compound legal names like
  `Филиал "Вендорож" РУП "Могилевэнерго"` without opening every vacancy page.
- **Belmeta pagination:** the adapter now reads more navigation shapes from the
  HTML itself — `rel=next`, next/arrow labels, numeric pagination links and
  `data-url`/`data-href` buttons — before falling back to guessed `page/p/offset`
  probes. `pages_detail` also records the discovered pagination candidates so
  the next diagnostic session shows exactly what navigation the site exposed.
- **Rabota recall:** if `/search/vacancy` initially works but later stops exposing
  recognizable vacancy cards while the site still reports more results, the
  parser continues through the ordinary public `/vacancies/<profession>` listing.
  The same local title/city/salary filters and vacancy-link deduplication remain
  active, so the second public listing can add unseen vacancies without
  duplicating those already collected.
- **Problem-log quality:** AI diagnosis now flags a source when most saved
  accepted examples still have no employer, making data-quality regressions
  visible even when the source technically returns many vacancies.
- Direct execution of both test files now reaches every regression-test class;
  the previous intermediate `unittest.main()` placement was moved to the end.

## Previous 4.7 changes


- GSZ vacancies now open **immediately** in the browser. The old requests-based
  preflight is removed from the opening path because real session logs showed
  four 4-second connect timeouts before the already-correct browser URL was opened.
- The exact `?source=search` GSZ detail URL from the search results remains the
  first browser URL; link preparation is now a local string operation with no
  network I/O.
- Link logs record `open_direct_detail`, `preflight_skipped=true`,
  `prepared` URL and `open_call_ms`, so browser-dispatch latency is measurable.
- The GSZ landing TLS probe now uses a no-retry HTTP session. A certificate-chain
  failure falls back immediately instead of being retried by the general network
  retry policy, which previously cost about 18 seconds in a real search session.
- GSZ diagnostics now keep a compact `table_structure` sample (headers, first row
  cells and recognized fields) to diagnose missing company/date columns without
  storing full HTML pages.
- `reported_total` AI diagnosis is now deliberately cautious: generic site-wide
  counters are not automatically treated as proof that pagination lost vacancies.

## Previous 4.6 changes

- Fixed multiline salary text from GSZ and other HTML sources: table cells are now always rendered on one line.
- GSZ result links are normalized to public vacancy-detail routes instead of exposing internal/service links.
- When opening a GSZ vacancy, the app validates the link and tries the alternate public route family if the portal returns its own error page.
- If both GSZ detail routes fail, the app opens the GSZ vacancy search instead of knowingly sending the user to a broken detail page.
- GSZ table parsing now prefers named columns for salary, employer, city and publication date.
- Problem logs now include `05_проверка_ссылок.jsonl` with post-search link validation evidence.

This release is driven by the real Minsk `кладовщик`, strict `2000 BYN` session that returned 48 vacancies. The logs showed that Rabota public HTML actually fetched 98 cards but rejected 76 by salary, Belmeta repeated its first page, and GSZ failed before producing result cards.

- Rabota/HH public fallback can traverse up to 10 bounded HTML pages and now extracts salary even when current HTML no longer exposes a recognized salary `data-qa`; a currency-anchored text fallback handles strings such as `2 325 – 2 560 Br за месяц`.
- Salary parsing no longer treats the `до` in phrases like `до вычета налогов` as a max-only salary marker, and strict mode now requires a genuine lower/guaranteed bound.
- Anonymous HH API `403` is now stored as a **warning** when the public HTML fallback works. A successful fallback is no longer reported to the GUI as a completely broken source, even when strict local filters accept zero rows.
- Per-source diagnostics now retain up to five compact examples of rejected salary/city/title/invalid rows and up to five accepted examples. This makes parser mistakes visible without saving full HTML pages.
- `pages_detail` records page URL, HTTP status, HTML size, recognized card count, accepted count and the strategy used by fallback adapters.
- When a source exposes a result total, diagnostics store it as `reported_total`, making a “site says hundreds, parser fetched only one page” failure obvious.
- Belmeta detects a repeated page and probes several bounded pagination shapes (`page`, zero-based page, `p`, `offset`, `start`, path page) before giving up. The first candidate containing unseen vacancy IDs becomes the pagination strategy.
- GSZ no longer sends blank optional form fields. It tries: profession + known location, profession-only, and finally a bounded latest-vacancies request with local profession/city filtering. This specifically addresses real sessions where blank `region/district/...` fields led to HTTP 500.
- GSZ keeps each failed strategy as a warning and only marks the source failed when all strategies fail.
- Successful searches can now show non-fatal source warnings separately from true source errors in the GUI.
- Every session now also creates `04_диагностика_источников.json` with warnings, rejected/accepted samples, page details and automatic AI-oriented diagnosis.
- HTTP/network failures now keep a bounded `samples.request_error` record with stage, exception type, HTTP status, final URL, content type and a short server-response excerpt. Request headers, OAuth tokens and proxy values are not written.
- `00_прочитать_нейросети_сначала.txt` automatically highlights suspicious patterns such as >=60% salary rejection, >=50% city rejection, repeated pagination and request failure before the first result page.
- `02_параметры_поиска.json` now includes Python/OpenSSL and dependency versions plus only boolean presence flags for HH token/proxy environment variables; secret/token/proxy values are never written.

All 4.3 deduplication, Praca, company extraction, salary-mode and per-session logging fixes remain in place.

## Architecture

- `vacancy_parser.py` — minimal entry point;
- `vacancy_gui.py` — Tkinter UI, profiles, status, statistics and Excel export;
- `job_scraper.py` — networking, filtering, deduplication and source adapters;
- `problem_logging.py` — one diagnostic folder per search session;
- `tests/` — network-free regression tests.

## Sources

The UI exposes only sources with an implementation:

- Rabota.by
- HH.ru
- Praca.by
- Belmeta
- GSZ.gov.by

### Rabota.by / HH note

The official HH API can require CAPTCHA for anonymous vacancy-search traffic. `HH_API_TOKEN` remains the most stable way to use API pagination. Version 4.7 also has a bounded public-web fallback so a single API 403 does not automatically make the source return zero.

Optional token:

```powershell
$env:HH_API_TOKEN = "..."
python vacancy_parser.py
```

Do not store OAuth tokens in source files, JSON configuration or Git.

## Salary modes

`Мин. доход` works together with `Фильтр зарплаты`.

- **Не фильтровать** — do not reject vacancies by salary.
- **Мягкий** — unspecified salary is allowed; for ranges, the upper bound may reach the minimum.
- **Строгий** — salary must be verifiable and its lower/guaranteed bound must be at least the minimum.

Soft mode is the best default when the priority is to **see more vacancies**.

## Problem logs

Every search creates a separate directory:

```text
Логи проблем/
└── 2026-08-12_15-18-47/
    ├── 00_прочитать_нейросети_сначала.txt
    ├── 01_лог_поиска.log
    ├── 02_параметры_поиска.json
    ├── 03_итог.json
    └── 04_диагностика_источников.json
```

`03_итог.json` contains:

- overall status (`success`, `partial_success`, `no_results`, `error`, `cancelled`);
- counts for every selected source, including zero;
- source errors;
- per-source fetched/page/filter statistics.

`04_диагностика_источников.json` additionally contains bounded rejected/accepted examples, warnings, page-by-page metadata and `ai_diagnosis`.

For the problem “too few vacancies”, compare `fetched`, `accepted`, `filtered`, `samples` and `pages_detail` for each source.

## Install

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

## Tests

```powershell
python -m unittest discover -s tests -v
```

The regression suite is network-free.

## Build EXE

Run:

```text
build_exe.bat
```

The executable is created in `dist/`.

## Important limitations

HTML job sites can change markup or block automated requests. Each adapter therefore fails independently, writes diagnostics and allows the remaining sources to continue.

GSZ has had certificate-chain and server-side 5xx problems in real sessions. Version 4.6 narrows any TLS compatibility fallback to this read-only public source and records it explicitly in the log rather than disabling TLS globally.


### GSZ link handling in 4.6

Search-result vacancy URLs preserve the portal-provided `?source=search` marker. Only one vacancy-link worker can run at a time, so a double-click cannot open extra delayed GSZ tabs. The generic GSZ search page is used only when no vacancy ID can be determined.

- `06_итог_проверки_ссылок.txt` — компактная сводка по открытиям вакансий, fallback и повторным кликам.

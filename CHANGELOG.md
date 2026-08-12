# Changelog

## 4.9

- Preserved the active Belmeta profession query when choosing next-page links.
- Ranked query-preserving Belmeta pagination above generic whole-site `/vacansii`
  navigation and changed bounded probes to keep `q=<profession>`.
- Added tolerant Rabota employer extraction using semantic selectors, employer
  links and a bounded card-text fallback.
- Stopped the secondary Rabota SEO pass when `/vacancies/<profession>` redirects
  to generic `/vacancies`, preventing unrelated cards and duplicate inflation.
- Broadened GSZ location-control discovery to tolerate changed select names/IDs
  while submitting only numeric values actually exposed by the portal.
- Added diagnostic notes for GSZ location controls.
- Added five regression tests for the new 4.9 behavior.

## 4.8

- Recovered GSZ employer names from listing-card text when table headers do not
  identify the employer column.
- Added HTML-driven pagination discovery for Belmeta (`rel=next`, arrows,
  labels, numeric links and data-url/data-href navigation) before generic probes.
- Added Belmeta `pagination_candidates` to per-page diagnostics.
- Added a secondary public Rabota SEO-listing pass when normal public-search
  pagination stalls after already returning vacancy cards.
- Kept source-local filters and link deduplication active across Rabota public
  search and SEO-listing phases.
- Added AI diagnostic warning when most accepted samples have a missing employer.
- Added six new regression tests covering GSZ employer recovery, Belmeta
  navigation discovery and Rabota secondary-listing recovery.
- Moved direct `unittest.main()` calls to the end of the test modules so direct
  test execution does not skip later regression classes.

## 4.7

- Removed GSZ HTTP link preflight from the vacancy-opening path. Search-result
  detail URLs open immediately in the user's browser.
- Preserved `?source=search` and normalized GSZ links locally without network I/O.
- Added direct-opening diagnostics: `prepared`, `preflight_skipped`,
  `browser_open_result` and `open_call_ms`.
- Updated `06_итог_проверки_ссылок.txt` to summarize direct-browser dispatch
  latency and distinguish normal direct opens from old fallback behavior.
- Added a no-retry session for the GSZ landing TLS probe. Certificate errors now
  reach the existing verify=False fallback without the general retry delay.
- Added bounded GSZ `table_structure` diagnostic samples for missing employer/date
  fields.
- Softened `reported_total` AI conclusions because some sites expose global
  vacancy counters unrelated to the active filtered listing.
- Added regression tests for local/direct GSZ URL preparation, no-retry landing
  probe behavior and direct-open logging.


## 4.6

- GSZ vacancy links now preserve the portal-provided `?source=search` marker instead of stripping it.
- GSZ opening no longer launches the generic search page before a vacancy detail route.
- Added a re-entry guard so button clicks and Treeview double-clicks cannot start parallel link-opening workers.
- Link diagnostics now distinguish a failed background preflight from the browser route actually opened.

## 4.5

- Fixed GSZ vacancy links that could open the portal's “Что-то пошло не так” page.
- Normalized internal GSZ vacancy routes to public `detail-public` URLs.
- Added lazy GSZ link validation with normal/create-future route fallback.
- Added safe fallback to GSZ search when both detail routes are unavailable.
- Added `05_проверка_ссылок.jsonl` to each problem-log session.
- Collapsed newlines/tabs in salary and other Treeview cells.
- Improved GSZ structured table parsing for salary, employer, city and date.
- Added regression tests for GSZ public-link normalization, alternate-route validation and multiline salary rendering.


## 4.4

### Vacancy recall / source recovery
- Increased bounded Rabota/HH public fallback traversal from 5 to 10 pages for better recall after anonymous API 403.
- Fixed Rabota HTML salary extraction when current public cards do not expose a known salary selector; a currency-anchored card-text fallback is used.
- Fixed salary parsing for phrases such as `2 000 Br за месяц, до вычета налогов`: the word `до` in tax text is no longer mistaken for a max-only salary.
- Strict salary mode now requires a real lower/guaranteed bound; `до 3000 BYN` no longer incorrectly satisfies a strict minimum of 2000.
- HH API 403 is now a warning when Rabota/HH public HTML fallback succeeds, instead of leaving the source in a false error state.
- Belmeta repeated-page handling now probes multiple bounded pagination conventions and continues only when unseen vacancy IDs are found.
- GSZ omits blank optional query fields and retries progressively simpler public GET strategies before declaring the source unavailable.
- GSZ can fall back to a bounded latest-vacancies page and apply profession/city filters locally.

### Diagnostics
- Added compact accepted and rejected samples per source/reason.
- Added bounded `request_error` samples with HTTP status, final URL, content type and short server-response excerpts, without logging authorization headers or token/proxy values.
- Added per-page diagnostics with URL/status/HTML size/card/accepted counts and source strategy.
- Added `reported_total` extraction when a source advertises a total such as `1-20 из 489 вакансий`, so diagnostics can detect missing pagination/recall.
- Added `04_диагностика_источников.json` with AI-oriented automatic hypotheses.
- `00_прочитать_нейросети_сначала.txt` now surfaces dominant rejection reasons, pagination duplication and request-stage failures.
- Runtime diagnostics include Python, OpenSSL and key dependency versions plus secret-safe environment-presence flags.
- GUI distinguishes non-fatal warnings/fallbacks from true source errors.

### Verification
- Added regression tests for Rabota salary-from-card fallback, warning-only API 403 recovery, Belmeta alternative pagination probing and GSZ progressive request strategies.

## 4.3

### Fixes driven by real search logs
- Fixed a critical Belmeta deduplication bug: `?id=...` was stripped from `/viewjob` and `/jobdesc` URLs, collapsing many distinct vacancies into one or two rows.
- Namespaced numeric vacancy IDs by source so Praca/GSZ IDs cannot collide with HH/Rabota IDs.
- Rabota.by HTML fallback now uses browser-style headers and tries a public profession SEO page after `/search/vacancy` returns 403/406.
- GSZ now uses its public GET vacancy-search contract and official `detail-public` vacancy links instead of relying on an arbitrary discovered form submission.
- GSZ resolves numeric location values from `<select>` controls when possible and otherwise uses local city filtering.
- Praca no longer counts helper layout columns as invalid vacancy cards.
- Praca employer extraction now tolerates changed employer/company selectors.
- Belmeta company extraction no longer captures a large wrapper containing salary and city text.

### More vacancy recall
- Increased bounded Praca and Belmeta traversal from 5 to 10 pages.
- Added Belmeta `page=N` fallback when a full result page has no discoverable next link.
- Added repeated-page detection to stop safely if a site ignores pagination.

### Diagnostics and verification
- Added response URL/title/HTML-size notes when public markup cannot be recognized.
- Added regression tests for Rabota 406 -> SEO fallback, GSZ public GET contract, Praca helper-column filtering, Belmeta query-ID deduplication and cross-site numeric-ID collisions.


## 4.2

### More vacancies / source recovery
- Added Rabota.by / HH public-web fallback after anonymous HH API 403/CAPTCHA.
- Soft salary mode no longer sends the minimum salary to HH API, avoiding premature removal of vacancies with unspecified salary.
- Belmeta now parses both `/viewjob` and `/jobdesc` vacancy links and follows discovered pagination links.
- Praca.by now follows pagination when available.
- GSZ search now discovers the actual search form action, method and query field before submitting instead of assuming `GET ?query=...`.

### Salary filtering
- Replaced the single strict checkbox with three explicit modes: `Не фильтровать`, `Мягкий`, `Строгий`.
- Kept backward migration from old `strict_salary` settings and profiles.

### Diagnostics
- Added per-source attempts, pages, fetched cards, accepted results and rejection counters.
- `03_итог.json` now keeps zero-result selected sources.
- Added `source_errors`, `source_stats` and `requested_sources`.
- Added `partial_success` for searches that found vacancies while some sources failed.
- GUI status now warns about failed sources instead of showing a misleading full success.

### Verification
- Expanded network-free regression coverage for HH 403 fallback, soft HH salary behavior, Belmeta `/jobdesc` + pagination, Praca filter statistics, GSZ form discovery, partial success and zero-count source logging.

## 4.1

- Reworked problem logging: every search creates its own folder inside `Логи проблем/`.
- Session logs are written incrementally, so diagnostics survive a crash or forced close.
- Added per-session AI summary, exact search parameters/environment JSON and machine-readable final summary.
- Added result counts by source to make low-result searches easier to diagnose.
- Retention now removes old session folders as units instead of loose `.log` files.
- Known cities (including Minsk) are resolved locally first, avoiding an unnecessary HH `/areas` call before vacancy search.
- Anonymous HH/Rabota mode deliberately fetches one 100-item page to reduce CAPTCHA-triggering extra API requests.
- Belmeta adapter now uses the current profession URL and tolerant `viewjob` parsing instead of relying only on obsolete `article.job` markup.
- GSZ.gov.by gets a narrowly-scoped public-GET TLS fallback when Windows/Python cannot validate the site's certificate chain.

## 4.0

### Correctness
- Fixed the country-classification bug where Russian HH area IDs above 1000 could be treated as Belarusian.
- Added dynamic HH area lookup and safer fallback aliases.
- GSZ results are now filtered by the requested city.
- Praca.by is not used outside Minsk until a reliable city filter is available.
- HTML sources no longer fabricate today's date when publication date is unknown.
- Added duplicate removal and more defensive handling of missing vacancy fields.

### HH API
- Added required `HH-User-Agent`.
- Added optional OAuth token through `HH_API_TOKEN`.
- Added `host` selection for `hh.ru` / `rabota.by`.
- Added pagination, bounded retries and request timeouts.
- Added `work_format` for remote/on-site/hybrid filters.
- Updated strict salary search to `label=with_salary`.
- Added monthly salary mode/frequency and correct HH currency codes (`BYR`/`RUR` for API queries).

### Salary and currency
- Replaced hard-coded exchange rates with the official NBRB daily API.
- Added soft vs strict salary semantics.
- Added parsing for ranges, "from"/"to", thousands notation and multiple currencies.
- Hourly/daily/weekly/shift pay is no longer compared as if it were monthly salary.

### Reliability
- Restored normal TLS certificate verification.
- Bounded retry strategy respects `Retry-After`.
- Added cooperative cancellation.
- Removed global `sys.stdout` replacement from the worker thread.
- Added bounded per-search diagnostic logs with retention of the 10 latest sessions.
- Config and saved profiles are written atomically.

### UI / export
- Removed source checkboxes that had no implementation.
- Added Stop button.
- Added clearer salary-filter wording and modern HH work-format choices.
- Improved Excel export with table filters, hyperlinks, summary sheet and formula-injection protection.

### Project structure
- Split GUI and search backend into `vacancy_gui.py` and `job_scraper.py`.
- Added tests, requirements, build/run scripts, README, AGENTS.md and Windows GitHub Actions CI.

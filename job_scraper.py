import json
import os
import re
import time
import urllib.parse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class JobScraper:
    """Backend vacancy search engine.

    The class deliberately keeps GUI concerns out of network/search code. All
    diagnostic messages go through ``log_callback`` and long searches can be
    cancelled with ``cancel_event``.
    """

    HH_API_URL = "https://api.hh.ru/vacancies"
    HH_AREAS_URL = "https://api.hh.ru/areas"
    NBRB_RATES_URL = "https://api.nbrb.by/exrates/rates"
    REQUEST_TIMEOUT = (5, 20)
    MAX_HH_PAGES = 5
    MAX_HH_HTML_PAGES = 10
    MAX_PRACA_PAGES = 10
    MAX_BELMETA_PAGES = 10
    MAX_GSZ_PAGES = 5
    MAX_RESULTS_PER_SOURCE = 500

    BELARUS_SITES = ("Rabota.by", "Praca.by", "Belmeta", "GSZ.gov.by")
    RUSSIA_SITES = ("HH.ru",)

    FALLBACK_AREAS = {
        # Belarus
        "минск": {"id": 1002, "country": "BY", "name": "Минск"},
        "minsk": {"id": 1002, "country": "BY", "name": "Минск"},
        "брест": {"id": 1007, "country": "BY", "name": "Брест"},
        "витебск": {"id": 1006, "country": "BY", "name": "Витебск"},
        "гомель": {"id": 1009, "country": "BY", "name": "Гомель"},
        "гродно": {"id": 1004, "country": "BY", "name": "Гродно"},
        "могилев": {"id": 1005, "country": "BY", "name": "Могилёв"},
        "борисов": {"id": 2013, "country": "BY", "name": "Борисов"},
        "солигорск": {"id": 2026, "country": "BY", "name": "Солигорск"},
        "молодечно": {"id": 2020, "country": "BY", "name": "Молодечно"},
        "полоцк": {"id": 2036, "country": "BY", "name": "Полоцк"},
        "барановичи": {"id": 2010, "country": "BY", "name": "Барановичи"},
        "лида": {"id": 2017, "country": "BY", "name": "Лида"},
        "новополоцк": {"id": 2037, "country": "BY", "name": "Новополоцк"},
        "пинск": {"id": 2023, "country": "BY", "name": "Пинск"},
        "бобруйск": {"id": 2012, "country": "BY", "name": "Бобруйск"},
        "орша": {"id": 2022, "country": "BY", "name": "Орша"},
        # Russia
        "россия": {"id": 113, "country": "RU", "name": "Россия"},
        "москва": {"id": 1, "country": "RU", "name": "Москва"},
        "moscow": {"id": 1, "country": "RU", "name": "Москва"},
        "санкт-петербург": {"id": 2, "country": "RU", "name": "Санкт-Петербург"},
        "saint petersburg": {"id": 2, "country": "RU", "name": "Санкт-Петербург"},
        "st petersburg": {"id": 2, "country": "RU", "name": "Санкт-Петербург"},
        "спб": {"id": 2, "country": "RU", "name": "Санкт-Петербург"},
        "питер": {"id": 2, "country": "RU", "name": "Санкт-Петербург"},
        "новосибирск": {"id": 4, "country": "RU", "name": "Новосибирск"},
        "екатеринбург": {"id": 3, "country": "RU", "name": "Екатеринбург"},
        "нижний новгород": {"id": 66, "country": "RU", "name": "Нижний Новгород"},
        "казань": {"id": 88, "country": "RU", "name": "Казань"},
        "самара": {"id": 78, "country": "RU", "name": "Самара"},
        "омск": {"id": 68, "country": "RU", "name": "Омск"},
        "челябинск": {"id": 104, "country": "RU", "name": "Челябинск"},
        "ростов-на-дону": {"id": 76, "country": "RU", "name": "Ростов-на-Дону"},
        "уфа": {"id": 99, "country": "RU", "name": "Уфа"},
        "красноярск": {"id": 54, "country": "RU", "name": "Красноярск"},
        "пермь": {"id": 72, "country": "RU", "name": "Пермь"},
        "воронеж": {"id": 26, "country": "RU", "name": "Воронеж"},
        "волгоград": {"id": 24, "country": "RU", "name": "Волгоград"},
        "краснодар": {"id": 53, "country": "RU", "name": "Краснодар"},
        "тюмень": {"id": 95, "country": "RU", "name": "Тюмень"},
        "иркутск": {"id": 63, "country": "RU", "name": "Иркутск"},
        "хабаровск": {"id": 75, "country": "RU", "name": "Хабаровск"},
        "владивосток": {"id": 22, "country": "RU", "name": "Владивосток"},
        "томск": {"id": 94, "country": "RU", "name": "Томск"},
        "калининград": {"id": 44, "country": "RU", "name": "Калининград"},
        "сочи": {"id": 237, "country": "RU", "name": "Сочи"},
    }

    EXPERIENCE_MAP = {
        "Не имеет значения": None,
        "Нет опыта": "noExperience",
        "От 1 года до 3 лет": "between1And3",
        "От 3 до 6 лет": "between3And6",
        "Более 6 лет": "moreThan6",
    }

    LEGACY_SCHEDULE_MAP = {
        "Полный день": "fullDay",
        "Сменный график": "shift",
        "Гибкий график": "flexible",
        "Вахтовый метод": "flyInFlyOut",
    }

    WORK_FORMAT_MAP = {
        "Удаленная работа": "REMOTE",
        "На месте работодателя": "ON_SITE",
        "Гибрид": "HYBRID",
    }

    PERIOD_MAP = {
        "За 30 дней": 30,
        "За все время": 30,  # migration from old config; API limit is 30 days
        "За месяц": 30,
        "За неделю": 7,
        "За 3 дня": 3,
        "За сутки": 1,
    }

    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.session = requests.Session()

        retry_strategy = Retry(
            total=4,
            connect=3,
            read=3,
            status=3,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"HEAD", "GET", "OPTIONS"}),
            backoff_factor=0.8,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # A second session is used for bounded probes where retrying the same
        # TLS/connect failure only adds latency (notably the GSZ landing page).
        self.no_retry_session = requests.Session()
        no_retry_adapter = HTTPAdapter(
            max_retries=Retry(
                total=0,
                connect=0,
                read=0,
                status=0,
                redirect=0,
                raise_on_status=False,
            ),
            pool_connections=4,
            pool_maxsize=4,
        )
        self.no_retry_session.mount("http://", no_retry_adapter)
        self.no_retry_session.mount("https://", no_retry_adapter)

        self.session.headers.update({
            "User-Agent": "VacancyParserPro/4.7 (Windows; Python requests)",
            "HH-User-Agent": os.environ.get(
                "HH_USER_AGENT",
                "VacancyParserPro/4.7 (zeter11@gmail.com)",
            ),
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
        })
        hh_token = os.environ.get("HH_API_TOKEN", "").strip()
        self.hh_authorized = bool(hh_token)
        if hh_token:
            self.session.headers["Authorization"] = f"Bearer {hh_token}"
        self.no_retry_session.headers.update(self.session.headers)

        # BYN cost of one unit of currency. Filled from the National Bank API.
        self.currency_rates = {"BYN": 1.0}
        self.currency_rates_updated_at = None
        self._area_index = None
        # Per-search structured diagnostics. GUI stores this in 03_итог.json.
        self.source_diagnostics = {}
        self.requested_sources = []

    def close(self):
        self.session.close()
        self.no_retry_session.close()

    def _log(self, message):
        if self.log_callback:
            self.log_callback(str(message))

    @staticmethod
    def canonical_source_name(source):
        text = str(source or "")
        for known in ("Rabota.by", "HH.ru", "Praca.by", "Belmeta", "GSZ.gov.by"):
            if text.startswith(known):
                return known
        return text or "Неизвестный источник"

    @staticmethod
    def _empty_source_diag():
        return {
            "status": "not_run",
            "error": None,
            "warnings": [],
            "attempts": 0,
            "pages": 0,
            "fetched": 0,
            "accepted": 0,
            "reported_total": None,
            "filtered": {
                "city": 0,
                "position": 0,
                "salary": 0,
                "excluded": 0,
                "schedule": 0,
                "invalid": 0,
                "duplicate_on_source": 0,
            },
            # Короткие диагностические примеры. Они специально ограничены,
            # чтобы папка «Логи проблем» не разрасталась на мегабайты.
            "samples": {
                "city": [],
                "position": [],
                "salary": [],
                "excluded": [],
                "schedule": [],
                "invalid": [],
                "duplicate_on_source": [],
                "request_error": [],
                "accepted": [],
            },
            # Краткое состояние каждой реально загруженной страницы: URL,
            # HTTP, размер HTML, число карточек и число принятых результатов.
            "pages_detail": [],
            "notes": [],
        }

    def _reset_source_diagnostics(self, requested_sources):
        self.requested_sources = list(dict.fromkeys(requested_sources or []))
        self.source_diagnostics = {
            source: self._empty_source_diag()
            for source in self.requested_sources
        }

    def _diag(self, source):
        source = self.canonical_source_name(source)
        if source not in self.source_diagnostics:
            self.source_diagnostics[source] = self._empty_source_diag()
        return self.source_diagnostics[source]

    def _diag_note(self, source, message):
        diag = self._diag(source)
        text = str(message)
        if text not in diag["notes"]:
            diag["notes"].append(text)

    def _diag_warning(self, source, message):
        diag = self._diag(source)
        text = str(message)
        if text not in diag["warnings"]:
            diag["warnings"].append(text)

    @staticmethod
    def _diag_trim(value, limit=320):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) > limit:
            return text[: max(0, limit - 1)] + "…"
        return text

    def _diag_sample(self, source, reason, **fields):
        """Store at most five compact examples for one rejection reason."""
        diag = self._diag(source)
        bucket = diag.setdefault("samples", {}).setdefault(str(reason), [])
        if len(bucket) >= 5:
            return
        safe = {}
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, (int, float, bool)):
                safe[str(key)] = value
            else:
                safe[str(key)] = self._diag_trim(value)
        if safe and safe not in bucket:
            bucket.append(safe)

    def _diag_page(self, source, **fields):
        """Store compact per-page metadata, capped to avoid oversized logs."""
        diag = self._diag(source)
        pages = diag.setdefault("pages_detail", [])
        if len(pages) >= 15:
            return
        item = {}
        for key, value in fields.items():
            if isinstance(value, str):
                item[str(key)] = self._diag_trim(value, 260)
            elif value is None or isinstance(value, (int, float, bool, dict, list)):
                item[str(key)] = value
            else:
                item[str(key)] = str(value)
        pages.append(item)

    def _diag_request_failure(self, source, stage, exc, *, requested_url=None, params=None):
        """Record a bounded HTTP/network failure sample without headers or secrets."""
        response = getattr(exc, "response", None)
        final_url = getattr(response, "url", None) or requested_url
        status = getattr(response, "status_code", None)
        content_type = ""
        body = ""
        if response is not None:
            try:
                content_type = str(response.headers.get("Content-Type") or "")
            except Exception:
                content_type = ""
            try:
                body = self._diag_trim(getattr(response, "text", ""), 700)
            except Exception:
                body = ""
        safe_params = None
        if isinstance(params, dict):
            safe_params = {
                str(key): self._diag_trim(value, 120)
                for key, value in params.items()
                if value not in (None, "", [], {})
            }
        self._diag_sample(
            source,
            "request_error",
            stage=stage,
            error_type=type(exc).__name__,
            error=str(exc),
            http_status=status,
            url=final_url,
            content_type=content_type,
            response_excerpt=body,
            params=safe_params,
        )

    def _diag_error(self, source, message):
        diag = self._diag(source)
        diag["status"] = "error"
        diag["error"] = str(message)

    def _diag_filter(self, source, key, amount=1):
        diag = self._diag(source)
        diag["filtered"][key] = int(diag["filtered"].get(key, 0)) + int(amount)

    def _diag_finish(self, source, accepted, *, status=None):
        diag = self._diag(source)
        diag["accepted"] = int(diag.get("accepted", 0) or 0) + int(accepted or 0)
        if status:
            diag["status"] = status
        elif diag["status"] == "error":
            return
        else:
            diag["status"] = "success" if diag["accepted"] else "no_results"

    def get_source_diagnostics(self):
        # JSON round-trip gives the GUI an independent JSON-safe snapshot.
        import json
        return json.loads(json.dumps(self.source_diagnostics, ensure_ascii=False))

    def source_counts(self, results):
        counts = {source: 0 for source in self.requested_sources}
        for item in results or []:
            source = self.canonical_source_name(item.get("source"))
            counts[source] = counts.get(source, 0) + 1
        return counts

    def source_errors(self):
        return {
            source: str(diag.get("error"))
            for source, diag in self.source_diagnostics.items()
            if diag.get("status") == "error" and diag.get("error")
        }

    def source_warnings(self):
        return {
            source: [str(item) for item in (diag.get("warnings") or [])]
            for source, diag in self.source_diagnostics.items()
            if diag.get("warnings")
        }

    def search_status(self, results, *, cancelled=False, fatal_error=None):
        if fatal_error:
            return "error"
        if cancelled:
            return "cancelled"
        failed = [d for d in self.source_diagnostics.values() if d.get("status") == "error"]
        ran = [d for d in self.source_diagnostics.values() if d.get("status") != "not_run"]
        if failed and results:
            return "partial_success"
        if failed and ran and len(failed) == len(ran):
            return "error"
        if results:
            return "success"
        return "no_results"

    @staticmethod
    def _salary_mode(params):
        mode = str(params.get("salary_mode") or "").strip()
        aliases = {
            "none": "Не фильтровать",
            "off": "Не фильтровать",
            "soft": "Мягкий",
            "strict": "Строгий",
        }
        mode = aliases.get(mode.lower(), mode)
        if mode in {"Не фильтровать", "Мягкий", "Строгий"}:
            return mode
        # Backward compatibility with 4.0/4.1/4.2 configs.
        return "Строгий" if params.get("strict_salary") else "Мягкий"

    @staticmethod
    def _discover_next_page_url(soup, current_url, next_page_number):
        # Prefer semantic rel=next, then a visible numeric pagination link.
        tag = soup.find("a", attrs={"rel": lambda value: value and "next" in value})
        if tag and tag.get("href"):
            return urllib.parse.urljoin(current_url, str(tag.get("href")))
        wanted = str(next_page_number)
        for tag in soup.find_all("a", href=True):
            if tag.get_text(" ", strip=True) == wanted:
                href = str(tag.get("href") or "")
                if href and not href.lower().startswith(("javascript:", "#")):
                    return urllib.parse.urljoin(current_url, href)
        return None

    @staticmethod
    def _browser_headers(host=None):
        """Browser-like headers for public HTML vacancy pages.

        API headers are intentionally not reused here: some public vacancy
        pages reject the application's JSON-oriented Accept header with 406.
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.6,en;q=0.5",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }
        if host:
            headers["Referer"] = f"https://{host}/"
        return headers

    @classmethod
    def _slugify_ru(cls, value):
        """Small deterministic transliterator for SEO vacancy category URLs."""
        mapping = {
            "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
            "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
            "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
            "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
            "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
            "э": "e", "ю": "yu", "я": "ya",
        }
        raw = cls._normalize_text(value)
        chars = []
        for ch in raw:
            chars.append(mapping.get(ch, ch if ch.isalnum() else "-"))
        slug = "".join(chars)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug

    @classmethod
    def _select_option_value(cls, select_tag, wanted_text):
        """Return a <select> option value whose visible label best matches text."""
        if select_tag is None:
            return None
        wanted = cls._normalize_city_key(wanted_text)
        if not wanted:
            return None

        exact = None
        partial = None
        for option in select_tag.find_all("option"):
            label = cls._normalize_city_key(option.get_text(" ", strip=True))
            value = str(option.get("value") or "").strip()
            if not value:
                continue
            if label == wanted:
                exact = value
                break
            if wanted in label or label in wanted:
                partial = partial or value
        return exact or partial

    @classmethod
    def _discover_gsz_location_fields(cls, soup, city_name):
        """Discover numeric GSZ location values from current search-form controls.

        The portal has changed ``name``/``id`` attributes between deployments.
        Do not hardcode Minsk IDs: inspect region/district/village selects and
        return only numeric values actually exposed by the current HTML.
        """
        fields = {}
        diagnostics = []
        wanted = cls._normalize_city_key(city_name)
        if not wanted or soup is None:
            return fields, diagnostics

        for select in soup.find_all("select"):
            raw_name = str(select.get("name") or "").strip()
            raw_id = str(select.get("id") or "").strip()
            hint = f"{raw_name} {raw_id}".lower().replace("-", "_")

            field = None
            if "region" in hint or "oblast" in hint:
                field = "region"
            elif "district" in hint or "raion" in hint:
                field = "district"
            elif "village" in hint or "council" in hint or "selsovet" in hint:
                field = "village_council"

            if not field:
                continue

            options_preview = []
            for option in select.find_all("option")[:12]:
                label = cls._inline_text(option.get_text(" ", strip=True))
                value = str(option.get("value") or "").strip()
                if label or value:
                    options_preview.append({"label": label[:80], "value": value[:40]})

            value = cls._select_option_value(select, city_name)
            matched = bool(value and re.fullmatch(r"\d+", str(value)))
            diagnostics.append({
                "field": field,
                "name": raw_name,
                "id": raw_id,
                "matched_value": str(value or ""),
                "numeric_match": matched,
                "options_preview": options_preview,
            })
            if matched and field not in fields:
                fields[field] = str(value)

        return fields, diagnostics

    @staticmethod
    def _url_with_query(url, **updates):
        parts = urllib.parse.urlsplit(str(url))
        query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        for key, value in updates.items():
            if value is None:
                query.pop(key, None)
            else:
                query[key] = str(value)
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
        )

    @staticmethod
    def _response_debug_note(response):
        try:
            soup = BeautifulSoup(response.text or "", "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
        except Exception:
            title = ""
        return (
            f"HTTP={getattr(response, 'status_code', '?')}; "
            f"url={getattr(response, 'url', '')}; "
            f"title={title[:160]!r}; html_chars={len(getattr(response, 'text', '') or '')}"
        )

    @staticmethod
    def _extract_reported_total(text):
        """Best-effort advertised vacancy count from a listing page."""
        raw = str(text or "").replace("\u00a0", " ").replace("\u202f", " ")
        patterns = (
            r"(?i)\bиз\s+(\d[\d ]{0,8})\s+ваканс",
            r"(?i)показать\s+вакансии\s+(\d[\d ]{0,8})",
            r"(?i)(\d[\d ]{0,8})\s+ваканс(?:ия|ии|ий)",
        )
        values = []
        for pattern in patterns:
            for match in re.finditer(pattern, raw):
                try:
                    values.append(int(match.group(1).replace(" ", "")))
                except (ValueError, IndexError):
                    continue
        return max(values) if values else None

    @staticmethod
    def _inline_text(value):
        """Collapse whitespace for values rendered in one-line table cells/log samples."""
        return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ").replace("\u202f", " ")).strip()

    @classmethod
    def _gsz_public_link_candidates(cls, href):
        """Return bounded candidate public URLs for one GSZ vacancy link.

        IMPORTANT: links emitted by the GSZ search page include ``?source=search``.
        The portal can behave differently when that query parameter is removed,
        so the exact public search-result URL is preserved as the first candidate.
        Only the harmless ``source=search`` query marker is retained.
        """
        raw_absolute = urllib.parse.urljoin("https://gsz.gov.by/", str(href or "").strip())
        parts = urllib.parse.urlsplit(raw_absolute)
        absolute_path = urllib.parse.urlunsplit((parts.scheme or "https", parts.netloc or "gsz.gov.by", parts.path, "", ""))
        query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        from_search = str(query.get("source", "")).casefold() == "search"
        candidates = []

        def add(url):
            url = str(url or "").strip()
            if url and url not in candidates:
                candidates.append(url)

        def with_search(url):
            parts2 = urllib.parse.urlsplit(url)
            return urllib.parse.urlunsplit((parts2.scheme, parts2.netloc, parts2.path, "source=search", ""))

        future = re.search(r"/registration/employer/vacancy/create-future/(\d+)(?:/[^?#]*)?", absolute_path)
        normal = re.search(r"/registration/employer/vacancy/(\d+)(?:/[^?#]*)?", absolute_path)

        if future:
            vacancy_id = future.group(1)
            canonical_future = f"https://gsz.gov.by/registration/employer/vacancy/create-future/{vacancy_id}/detail-public/"
            canonical_normal = f"https://gsz.gov.by/registration/employer/vacancy/{vacancy_id}/detail-public/"
            if from_search:
                add(with_search(canonical_future))
                add(canonical_future)
            else:
                add(canonical_future)
                add(with_search(canonical_future))
            add(with_search(canonical_normal))
            add(canonical_normal)
            return candidates

        if normal:
            vacancy_id = normal.group(1)
            canonical_normal = f"https://gsz.gov.by/registration/employer/vacancy/{vacancy_id}/detail-public/"
            canonical_future = f"https://gsz.gov.by/registration/employer/vacancy/create-future/{vacancy_id}/detail-public/"
            if from_search:
                add(with_search(canonical_normal))
                add(canonical_normal)
            else:
                add(canonical_normal)
                add(with_search(canonical_normal))
            add(with_search(canonical_future))
            add(canonical_future)
            return candidates

        return candidates

    @classmethod
    def prepare_vacancy_link_for_browser(cls, link, source=None):
        """Prepare a vacancy URL for immediate browser opening without network I/O.

        GSZ search-result links are already usable in a normal browser and may
        contain the important ``?source=search`` marker. Opening must never wait
        for a requests-based preflight, because the portal can time out for
        Python while the same URL opens normally in the user's browser.
        """
        raw = str(link or "").strip()
        if not raw:
            return ""
        if cls.canonical_source_name(source) != "GSZ.gov.by":
            return raw

        candidates = cls._gsz_public_link_candidates(raw)
        if not candidates:
            return raw

        # Preserve the exact route family and ?source=search whenever possible.
        return candidates[0]

    @staticmethod
    def _gsz_response_is_error_page(response):
        if response is None:
            return True
        status = int(getattr(response, "status_code", 0) or 0)
        if status >= 400:
            return True
        text = str(getattr(response, "text", "") or "")
        normalized = re.sub(r"\s+", " ", text).casefold()
        markers = (
            "что-то пошло не так",
            "что то пошло не так",
            "something went wrong",
            "внутренняя ошибка сервера",
            "internal server error",
        )
        return any(marker in normalized for marker in markers)

    def resolve_gsz_vacancy_link(self, link, timeout=(4, 10)):
        """Validate/correct a GSZ public vacancy URL before opening it.

        Returns ``(resolved_url, details)``. If both known public route families
        fail, ``resolved_url`` is ``None`` so the GUI can open the GSZ search
        page instead of sending the user to a known error page.
        """
        candidates = self._gsz_public_link_candidates(link)
        details = {
            "original": str(link or ""),
            "candidates": candidates,
            "attempts": [],
            "search_marker_preserved": "source=search" in str(link or ""),
        }
        if not candidates:
            details["reason"] = "vacancy id not recognized in GSZ URL"
            return None, details

        for candidate in candidates:
            response = None
            try:
                response = self._request(
                    candidate,
                    timeout=timeout,
                    headers=self._browser_headers("gsz.gov.by"),
                )
            except requests.exceptions.SSLError:
                try:
                    import warnings
                    from urllib3.exceptions import InsecureRequestWarning
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", InsecureRequestWarning)
                        response = self._request(
                            candidate,
                            timeout=timeout,
                            verify=False,
                            headers=self._browser_headers("gsz.gov.by"),
                        )
                except requests.RequestException as exc:
                    details["attempts"].append({"url": candidate, "ok": False, "error": str(exc)})
                    continue
            except requests.RequestException as exc:
                resp = getattr(exc, "response", None)
                details["attempts"].append({
                    "url": candidate,
                    "ok": False,
                    "http": getattr(resp, "status_code", None),
                    "error": str(exc),
                })
                continue

            broken = self._gsz_response_is_error_page(response)
            details["attempts"].append({
                "url": candidate,
                "ok": not broken,
                "http": getattr(response, "status_code", None),
                "final_url": str(getattr(response, "url", candidate)),
                "error_page": bool(broken),
            })
            if not broken:
                resolved = str(getattr(response, "url", candidate) or candidate)
                details["resolved"] = resolved
                details["corrected"] = resolved.rstrip("/") != str(link or "").rstrip("/")
                return resolved, details

        details["reason"] = "all known public GSZ detail routes returned an error or failed"
        return None, details

    @classmethod
    def _extract_salary_from_text(cls, text, *, default="Не указана"):
        """Extract a salary fragment from a public vacancy card.

        Public HH/Rabota layouts change data-qa names fairly often. When an
        explicit salary node is unavailable, keep the parser conservative and
        look only for amount fragments that are followed by a recognizable
        currency marker. That avoids accidentally treating experience years or
        dates as salary.
        """
        raw = cls._inline_text(text)
        if not raw:
            return default
        amount = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+(?:[.,]\d+)?)"
        currency = (
            r"(?:BYN|Br|бел(?:орусск(?:их|ие)?)?\.?\s*руб(?:\.|ля|лей)?|"
            r"RUB|RUR|₽|рос\.?\s*руб\.?|руб\.?|USD|EUR|\$|€)"
        )
        pattern = re.compile(
            rf"(?i)(?:от\s+|до\s+)?{amount}"
            rf"(?:\s*(?:-|–|—|до)\s*{amount})?\s*{currency}"
            rf"(?:\s*(?:за\s+месяц|в\s+месяц|/мес\.?))?"
        )
        match = pattern.search(raw)
        return cls._inline_text(match.group(0)) if match else default

    @staticmethod
    def _pagination_probe_urls(base_url, logical_page, page_size=20):
        """Return bounded alternative pagination URL shapes for HTML sites.

        Several vacancy boards silently ignore an unknown page parameter and
        return page 1 again. Probing a few common shapes is safer than assuming
        one convention, while duplicate-set detection prevents loops.
        """
        n = max(2, int(logical_page))
        zero_based = n - 1
        candidates = []
        for key, value in (
            ("page", n),
            ("page", zero_based),
            ("p", n),
            ("p", zero_based),
            ("offset", (n - 1) * page_size),
            ("start", (n - 1) * page_size),
        ):
            parts = urllib.parse.urlsplit(str(base_url))
            query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
            query[key] = str(value)
            candidate = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment)
            )
            if candidate not in candidates:
                candidates.append(candidate)
        path_candidate = str(base_url).rstrip("/") + f"/{n}"
        if path_candidate not in candidates:
            candidates.append(path_candidate)
        return candidates


    @classmethod
    def _discover_pagination_urls(
        cls,
        soup,
        current_url,
        next_page_number,
        *,
        base_url=None,
        page_size=20,
    ):
        """Collect plausible next-page URLs exposed by the current HTML.

        Prefer URLs that the site itself renders (rel=next, aria/title labels,
        numeric links and pagination containers). Generic page/p/offset/start
        probes are intentionally left to the caller as a last resort.
        """
        logical_page = max(2, int(next_page_number))
        current_url = str(current_url or "")
        base_url = str(base_url or current_url)
        current_parts = urllib.parse.urlsplit(current_url or base_url)
        allowed_host = (current_parts.netloc or urllib.parse.urlsplit(base_url).netloc).lower()
        candidates = []

        def add(raw_url):
            raw_url = str(raw_url or "").strip()
            if not raw_url or raw_url.lower().startswith(("javascript:", "#")):
                return
            absolute = urllib.parse.urljoin(current_url or base_url, raw_url)
            parts = urllib.parse.urlsplit(absolute)
            if allowed_host and parts.netloc.lower() != allowed_host:
                return
            if absolute == current_url or absolute in candidates:
                return
            candidates.append(absolute)

        semantic = cls._discover_next_page_url(soup, current_url or base_url, logical_page)
        if semantic:
            add(semantic)

        next_words = (
            "следующая",
            "след",
            "next",
            "вперед",
            "вперёд",
            "далее",
        )
        page_keys = {
            "page",
            "p",
            "pg",
            "page_num",
            "page-number",
            "pagenum",
            "offset",
            "start",
        }
        expected_values = {
            str(logical_page),
            str(logical_page - 1),
            str((logical_page - 1) * max(1, int(page_size))),
        }

        for tag in soup.find_all(["a", "button"], href=True):
            href = str(tag.get("href") or "")
            text = cls._normalize_text(tag.get_text(" ", strip=True))
            label = cls._normalize_text(
                " ".join(
                    str(tag.get(name) or "")
                    for name in ("aria-label", "title", "rel")
                )
            )
            combined = f"{text} {label}".strip()
            parent = tag.parent
            parent_hint = ""
            if parent is not None:
                parent_hint = cls._normalize_text(
                    " ".join(
                        [
                            str(parent.get("class") or ""),
                            str(parent.get("id") or ""),
                            str(getattr(parent.parent, "get", lambda *_: "")("class") or "")
                            if getattr(parent, "parent", None) is not None
                            else "",
                        ]
                    )
                )

            explicit_next = (
                text == str(logical_page)
                or text in {">", "›", "»", "→"}
                or any(word in combined for word in next_words)
            )

            parts = urllib.parse.urlsplit(
                urllib.parse.urljoin(current_url or base_url, href)
            )
            query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
            pageish_query = any(
                key.lower() in page_keys and str(value).strip() in expected_values
                for key, value in query.items()
            )
            path_tail = parts.path.rstrip("/").rsplit("/", 1)[-1]
            pageish_path = (
                path_tail == str(logical_page)
                or path_tail in {f"page-{logical_page}", f"page{logical_page}"}
            )
            in_pagination = any(
                token in parent_hint
                for token in ("pagin", "pager", "pages", "page-list", "pagination")
            )

            if explicit_next or pageish_query or (in_pagination and pageish_path):
                add(href)

        # Some frontends render navigation buttons with data-url/data-href.
        for tag in soup.find_all(["a", "button"]):
            raw = tag.get("data-url") or tag.get("data-href")
            if not raw:
                continue
            text = cls._normalize_text(
                " ".join(
                    [
                        tag.get_text(" ", strip=True),
                        str(tag.get("aria-label") or ""),
                        str(tag.get("title") or ""),
                    ]
                )
            )
            if (
                str(logical_page) in text
                or any(word in text for word in next_words)
                or text in {">", "›", "»", "→"}
            ):
                add(raw)

        return candidates

    @classmethod
    def _rank_pagination_candidates(
        cls,
        candidates,
        *,
        query_text="",
        current_url="",
        base_url="",
    ):
        """Rank pagination links without dropping the active search context.

        Some Belmeta pages expose both a generic ``/vacansii`` link and a
        query-preserving ``/vacansii?q=...&page=N`` link. Following the generic
        link switches to the whole-site feed and makes later statistics look
        like relevant vacancies were lost. Prefer links that preserve the
        current query and a page-like parameter.
        """
        query_norm = cls._normalize_text(urllib.parse.unquote_plus(str(query_text or "")))
        current_parts = urllib.parse.urlsplit(str(current_url or ""))
        current_query = dict(
            urllib.parse.parse_qsl(current_parts.query, keep_blank_values=True)
        )
        current_q = cls._normalize_text(
            urllib.parse.unquote_plus(
                str(current_query.get("q") or current_query.get("query") or "")
            )
        )
        base_parts = urllib.parse.urlsplit(str(base_url or current_url or ""))
        base_path = urllib.parse.unquote(base_parts.path).rstrip("/").lower()
        generic_paths = {"/vacansii", "/вакансии"}

        def score(url):
            parts = urllib.parse.urlsplit(str(url))
            path = urllib.parse.unquote(parts.path).rstrip("/").lower()
            query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
            candidate_q = cls._normalize_text(
                urllib.parse.unquote_plus(
                    str(query.get("q") or query.get("query") or "")
                )
            )
            value = 0

            if query_norm:
                if candidate_q == query_norm:
                    value += 300
                elif candidate_q and (
                    query_norm in candidate_q or candidate_q in query_norm
                ):
                    value += 180
                elif path in generic_paths:
                    value -= 180

            if current_q:
                if candidate_q == current_q:
                    value += 120
                elif not candidate_q and path in generic_paths:
                    value -= 80

            if any(
                key.lower() in {
                    "page", "p", "pg", "page_num", "page-number",
                    "pagenum", "offset", "start",
                }
                for key in query
            ):
                value += 45

            if "df" in query and not any(
                key.lower() in {"page", "p", "pg", "offset", "start"}
                for key in query
            ):
                value -= 20

            if base_path and path == base_path:
                value += 30
            elif base_path and base_path not in generic_paths and path in generic_paths:
                value -= 40

            # Keep original order as the final tie-breaker.
            return value

        indexed = list(enumerate(candidates))
        indexed.sort(key=lambda item: (-score(item[1]), item[0]))
        return [url for _, url in indexed]


    def _extract_gsz_company_from_card_text(self, raw_text, *, title="", salary=""):
        """Extract employer from the compact GSZ listing-card text.

        Current GSZ search cards commonly render as:
        ``Должность 2000 – 2500 руб. ООО ... Ставка: 1,0 ...``.
        When the HTML headers are missing/changed, the employer is therefore
        recoverable from the bounded text segment between salary and metadata.
        """
        text = self._inline_text(raw_text)
        if not text:
            return ""

        tail = text
        salary_text = self._inline_text(salary)
        title_text = self._inline_text(title)

        if salary_text:
            index = tail.find(salary_text)
            if index >= 0:
                tail = tail[index + len(salary_text):].strip()
        elif title_text and tail.startswith(title_text):
            tail = tail[len(title_text):].strip()

        markers = (
            " Ставка:",
            " Образование:",
            " Опыт работы:",
            " Режим работы:",
            " Характер работы:",
            " График работы:",
            " Количество мест:",
            " Требования:",
            " Дополнительная информация:",
            " обл. ",
            " р-н ",
            " г. ",
            " гп. ",
            " аг. ",
            " д. ",
        )
        stop = len(tail)
        lower_tail = tail.lower()
        for marker in markers:
            pos = lower_tail.find(marker.lower())
            if 0 <= pos < stop:
                stop = pos
        candidate = self._inline_text(tail[:stop]).strip(" -–—,;:")

        if not candidate:
            return ""
        if len(candidate) > 180:
            return ""
        if title_text and self._normalize_text(candidate) == self._normalize_text(title_text):
            return ""
        if salary_text and self._normalize_text(candidate) == self._normalize_text(salary_text):
            return ""
        if re.fullmatch(r"[\d\s.,+\-–—]+", candidate):
            return ""
        return candidate

    def _extract_hh_company_from_card(self, card, *, title="", salary="", city=""):
        """Best-effort employer extraction for public HH/Rabota vacancy cards.

        Public layouts change data-qa names fairly often. Prefer semantic links
        and attributes first, then use a bounded text fallback between the
        salary/experience metadata and the city label. The fallback is only used
        when no explicit employer element is available.
        """
        if card is None:
            return "Не указана"

        selectors = (
            "[data-qa='vacancy-serp__vacancy-employer']",
            "[data-qa='vacancy-serp__vacancy-employer-text']",
            "[data-qa*='employer']",
            "[data-qa*='company']",
            "a[href*='/employer/']",
            "a[href*='/company/']",
            "[class*='employer'] a",
            "[class*='company'] a",
        )
        title_norm = self._normalize_text(title)
        salary_norm = self._normalize_text(salary)
        city_norm = self._normalize_city_key(city)

        def acceptable(value):
            value = self._inline_text(value)
            if not value or len(value) > 180:
                return ""
            norm = self._normalize_text(value)
            if not norm or norm == title_norm or norm == salary_norm:
                return ""
            if city_norm and self._normalize_city_key(value) == city_norm:
                return ""
            if any(
                token in norm
                for token in (
                    "откликнуться",
                    "откликнитесь",
                    "можно без резюме",
                    "сейчас смотр",
                    "выплаты:",
                    "без опыта",
                )
            ):
                return ""
            return value

        for selector in selectors:
            for node in card.select(selector):
                value = acceptable(node.get_text(" ", strip=True))
                if value:
                    return value

        # Employer names are usually links even when data-qa changes.
        for node in card.find_all("a", href=True):
            href = str(node.get("href") or "").lower()
            if "/employer/" not in href and "/company/" not in href:
                continue
            value = acceptable(node.get_text(" ", strip=True))
            if value:
                return value

        raw_text = self._inline_text(card.get_text(" ", strip=True))
        if not raw_text:
            return "Не указана"

        # Work only with the part before the city/address when it is present.
        left = raw_text
        city_text = self._inline_text(city)
        if city_text:
            pos = self._normalize_text(left).find(self._normalize_text(city_text))
            if pos > 0:
                left = left[:pos].strip()

        # Drop the "Сейчас смотрят ..." prefix by cutting through the title.
        if title:
            pos = self._normalize_text(left).find(title_norm)
            if pos >= 0:
                # Use the real string length only after finding the normalized
                # title; titles in these cards normally preserve spacing.
                raw_pos = left.lower().replace("ё", "е").find(
                    self._inline_text(title).lower().replace("ё", "е")
                )
                if raw_pos >= 0:
                    left = left[raw_pos + len(self._inline_text(title)):].strip()

        if salary:
            salary_text = self._inline_text(salary)
            raw_pos = left.find(salary_text)
            if raw_pos >= 0:
                left = left[raw_pos + len(salary_text):].strip()

        # Remove recurring metadata that appears before the employer.
        patterns = (
            r"^[,;:\s]*(?:на руки|до вычета налогов)\b[,;:\s]*",
            r"^[,;:\s]*(?:без опыта|опыт не требуется)\b[,;:\s]*",
            r"^[,;:\s]*опыт\s+(?:\d+\s*[-–—]\s*\d+\s+(?:год|года|лет)|более\s+\d+\s+лет)\b[,;:\s]*",
            r"^[,;:\s]*(?:вахта|удаленная работа|удалённая работа)\b[,;:\s]*",
            r"^[,;:\s]*выплаты:\s*(?:два раза в месяц|раз в неделю|еженедельно|ежемесячно)\b[,;:\s]*",
        )
        changed = True
        while changed and left:
            changed = False
            for pattern in patterns:
                updated = re.sub(pattern, "", left, count=1, flags=re.I).strip()
                if updated != left:
                    left = updated
                    changed = True

        candidate = acceptable(left.strip(" -–—,;:"))
        return candidate or "Не указана"

    @staticmethod
    def _normalize_text(value):
        text = str(value or "").strip().lower().replace("ё", "е")
        text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def _normalize_city_key(cls, value):
        text = cls._normalize_text(value)
        text = re.sub(r"^г\.?\s*", "", text)
        text = re.sub(r"[-‐‑–—]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _normalize_date(value):
        text = str(value or "").strip()
        if not text:
            return ""
        low = text.lower()
        today = datetime.now().date()
        if low in {"сегодня", "today"}:
            return today.isoformat()
        if low in {"вчера", "yesterday"}:
            from datetime import timedelta
            return (today - timedelta(days=1)).isoformat()
        relative = re.search(r"(\d+)\s+(?:день|дня|дней)\s+назад", low)
        if relative:
            from datetime import timedelta
            return (today - timedelta(days=int(relative.group(1)))).isoformat()
        iso_match = re.match(r"(\d{4}-\d{2}-\d{2})", text)
        if iso_match:
            return iso_match.group(1)
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        return ""

    @staticmethod
    def _is_cancelled(cancel_event):
        return bool(cancel_event and cancel_event.is_set())

    def _request(
        self,
        url,
        *,
        params=None,
        expect_json=False,
        timeout=None,
        verify=True,
        method="GET",
        data=None,
        headers=None,
        retry=True,
    ):
        method = str(method or "GET").upper()
        request_session = self.session if retry else self.no_retry_session
        response = request_session.request(
            method,
            url,
            params=params if method == "GET" else None,
            data=data if method != "GET" else None,
            timeout=timeout or self.REQUEST_TIMEOUT,
            verify=verify,
            headers=headers,
            allow_redirects=True,
        )
        response.raise_for_status()
        if expect_json:
            return response.json()
        return response

    def update_currency_rates(self):
        """Load official NBRB daily rates.

        On failure the parser continues. Cross-currency filtering of HTML-only
        sources becomes conservative instead of using stale hard-coded rates.
        """
        if self.currency_rates_updated_at and self.currency_rates_updated_at.date() == datetime.now().date():
            return True

        try:
            data = self._request(
                self.NBRB_RATES_URL,
                params={"periodicity": 0},
                expect_json=True,
                timeout=(4, 10),
            )
            rates = {"BYN": 1.0}
            for item in data if isinstance(data, list) else []:
                code = str(item.get("Cur_Abbreviation") or "").upper()
                if code == "RUR":
                    code = "RUB"
                if code not in {"USD", "EUR", "RUB"}:
                    continue
                scale = float(item.get("Cur_Scale") or 1)
                official = float(item.get("Cur_OfficialRate") or 0)
                if scale > 0 and official > 0:
                    rates[code] = official / scale

            if len(rates) > 1:
                self.currency_rates = rates
                self.currency_rates_updated_at = datetime.now()
                formatted = ", ".join(
                    f"{code}={value:.4f} BYN" for code, value in rates.items() if code != "BYN"
                )
                self._log(f"Курсы НБРБ обновлены: {formatted}")
                return True
        except Exception as exc:
            self._log(f"Курсы НБРБ недоступны: {exc}. Поиск продолжится без приблизительных курсов.")

        return False

    def _build_area_index(self):
        index = {}
        try:
            data = self._request(
                self.HH_AREAS_URL,
                params={"locale": "RU"},
                expect_json=True,
                timeout=(5, 20),
            )

            def walk(node, country_code, country_name):
                name = str(node.get("name") or "").strip()
                area_id = node.get("id")
                if name and area_id is not None:
                    key = self._normalize_city_key(name)
                    index.setdefault(key, []).append({
                        "id": int(area_id),
                        "country": country_code,
                        "country_name": country_name,
                        "name": name,
                    })
                for child in node.get("areas") or []:
                    walk(child, country_code, country_name)

            for country in data if isinstance(data, list) else []:
                country_name = str(country.get("name") or "")
                normalized = self._normalize_text(country_name)
                if "беларус" in normalized:
                    code = "BY"
                elif "росси" in normalized:
                    code = "RU"
                else:
                    code = "OTHER"
                walk(country, code, country_name)

            if index:
                self._log(f"Справочник регионов HH загружен: {sum(len(v) for v in index.values())} записей.")
        except Exception as exc:
            self._log(f"Не удалось обновить справочник регионов HH: {exc}. Используется встроенный резервный список.")

        self._area_index = index

    def resolve_area(self, city_name):
        key = self._normalize_city_key(city_name)
        if not key:
            return None

        # Built-in fallback keys are normalized too, so "Санкт-Петербург",
        # "Санкт Петербург" and similar user input resolve identically.
        fallback = None
        for raw_key, info in self.FALLBACK_AREAS.items():
            if self._normalize_city_key(raw_key) == key:
                fallback = info
                break

        # Для известных городов не делаем лишний запрос к HH /areas.
        # Это особенно важно в анонимном режиме: публичный поиск вакансий HH
        # может потребовать CAPTCHA после первого API-запроса. Поэтому первый
        # запрос лучше тратить именно на /vacancies, а не на справочник.
        if fallback:
            return dict(fallback)

        if self._area_index is None:
            self._build_area_index()

        candidates = (self._area_index or {}).get(key, [])
        if candidates:
            # Prefer Belarus/Russia because those are the supported HH hosts.
            preferred = [c for c in candidates if c["country"] in {"BY", "RU"}]
            chosen = (preferred or candidates)[0]
            return dict(chosen)

        return None

    @staticmethod
    def is_belarus_city(area_info):
        return bool(area_info and area_info.get("country") == "BY")

    def matches_position(self, position, queries):
        position_norm = self._normalize_text(position)
        for query in queries:
            query_norm = self._normalize_text(query)
            if not query_norm:
                continue
            if query_norm in position_norm:
                return True
            words = [w for w in re.split(r"\s+", query_norm) if len(w) >= 2]
            if words and all(word in position_norm for word in words):
                return True
        return False

    def _contains_excluded(self, title, excluded_words):
        title_norm = self._normalize_text(title)
        return any(self._normalize_text(word) in title_norm for word in excluded_words if word)

    @staticmethod
    def _normalize_currency(code):
        code = str(code or "").upper()
        if code in {"RUR", "RUB"}:
            return "RUB"
        if code in {"BYR", "BYN"}:
            return "BYN"
        return code

    @classmethod
    def _hh_currency_code(cls, code):
        """Map UI/display currency to the code expected by HH dictionaries."""
        normalized = cls._normalize_currency(code)
        if normalized == "BYN":
            return "BYR"
        if normalized == "RUB":
            return "RUR"
        return normalized

    def parse_salary(self, salary_str, default_currency="BYN"):
        """Return normalized salary details or None.

        Result keys: min, max, currency. Values are in the original currency.
        """
        if not salary_str:
            return None
        text = self._inline_text(salary_str)
        low = text.lower()
        if any(token in low for token in ("договор", "не указ", "н/д", "по результатам", "по итогам")):
            return None

        if "usd" in low or "$" in text or "доллар" in low:
            currency = "USD"
        elif "eur" in low or "€" in text or "евро" in low:
            currency = "EUR"
        elif "byn" in low or "бел. руб" in low or "бел руб" in low or re.search(r"\bbr\b", low):
            currency = "BYN"
        elif "rub" in low or "rur" in low or "₽" in text or "рос. руб" in low or "рос руб" in low:
            currency = "RUB"
        else:
            currency = self._normalize_currency(default_currency) or "BYN"

        # Salary sites often use spaces as thousand separators.
        raw_numbers = re.findall(r"\d[\d\s.,]*", text)
        values = []
        has_thousands_word = bool(re.search(r"\bтыс(?:\.|яч)?\b", low))
        for raw in raw_numbers:
            cleaned = raw.strip().replace(" ", "")
            cleaned = cleaned.strip(".,")
            if not cleaned:
                continue

            # 2.5 тыс. -> 2500, while 2.500 -> 2500 for common salary formatting.
            if has_thousands_word and re.fullmatch(r"\d+[.,]\d+", cleaned):
                value = float(cleaned.replace(",", ".")) * 1000
            else:
                if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", cleaned):
                    cleaned = re.sub(r"[.,]", "", cleaned)
                else:
                    cleaned = cleaned.replace(",", ".")
                try:
                    value = float(cleaned)
                except ValueError:
                    continue
            if value > 0:
                values.append(value)

        if not values:
            return None

        if len(values) == 1:
            value = values[0]
            # Only treat «до» as an upper-bound marker when it directly
            # precedes the salary amount. Phrases such as «до вычета налогов»
            # must not turn a fixed salary into a max-only range.
            if re.search(r"(?:^|[^\w])до\s+\d", low):
                minimum, maximum = None, value
            else:
                minimum, maximum = value, None
        else:
            minimum, maximum = min(values[:2]), max(values[:2])

        if any(token in low for token in ("/час", "в час", "за час")):
            frequency = "HOUR"
        elif any(token in low for token in ("/день", "в день", "за день")):
            frequency = "DAY"
        elif any(token in low for token in ("/нед", "в неделю", "за неделю")):
            frequency = "WEEK"
        elif any(token in low for token in ("/смен", "за смену")):
            frequency = "SHIFT"
        else:
            frequency = "MONTH"

        return {"min": minimum, "max": maximum, "currency": currency, "frequency": frequency}

    def _salary_value_to_byn(self, value, currency):
        if value is None:
            return None
        currency = self._normalize_currency(currency)
        rate = self.currency_rates.get(currency)
        if rate is None:
            return None
        return float(value) * rate

    def convert_salary_to_byn(self, salary_str, default_currency="BYN"):
        parsed = self.parse_salary(salary_str, default_currency=default_currency)
        if not parsed or parsed.get("frequency") != "MONTH":
            return 0.0
        values = [
            self._salary_value_to_byn(parsed.get("min"), parsed["currency"]),
            self._salary_value_to_byn(parsed.get("max"), parsed["currency"]),
        ]
        values = [v for v in values if v is not None]
        return max(values) if values else 0.0

    def salary_sort_value(self, salary_str, default_currency="BYN"):
        parsed = self.parse_salary(salary_str, default_currency=default_currency)
        if not parsed or parsed.get("frequency") != "MONTH":
            return 0.0
        low = self._salary_value_to_byn(parsed.get("min"), parsed["currency"])
        high = self._salary_value_to_byn(parsed.get("max"), parsed["currency"])
        if low is not None and high is not None:
            return (low + high) / 2
        return low or high or 0.0

    def check_salary(
        self,
        salary_str,
        min_salary_req,
        salary_currency="BYN",
        strict=False,
        default_currency="BYN",
        mode=None,
    ):
        if not min_salary_req:
            return True

        if mode is None:
            mode = "Строгий" if strict else "Мягкий"
        if mode == "Не фильтровать":
            return True

        parsed = self.parse_salary(salary_str, default_currency=default_currency)
        if not parsed:
            return mode != "Строгий"
        if parsed.get("frequency") != "MONTH":
            return mode != "Строгий"

        required_byn = self._salary_value_to_byn(float(min_salary_req), salary_currency)
        if required_byn is None:
            return mode != "Строгий"

        low_byn = self._salary_value_to_byn(parsed.get("min"), parsed["currency"])
        high_byn = self._salary_value_to_byn(parsed.get("max"), parsed["currency"])

        if low_byn is None and high_byn is None:
            return mode != "Строгий"

        if mode == "Строгий":
            # Strict means a guaranteed lower bound. A max-only offer such as
            # «до 3000 BYN» does not guarantee 2000 and must be rejected.
            if low_byn is None:
                return False
            comparable = low_byn
        else:
            # Soft mode keeps vacancies without salary and ranges that can reach
            # the requested value.
            comparable = high_byn if high_byn is not None else low_byn
        return bool(comparable is not None and comparable >= required_byn)

    def _format_hh_salary(self, item):
        salary = item.get("salary_range") or item.get("salary")
        if not salary:
            return "Не указана"

        f_val = salary.get("from")
        t_val = salary.get("to")
        currency = self._normalize_currency(salary.get("currency")) or ""
        if f_val is not None and t_val is not None:
            text = f"{f_val:g} - {t_val:g} {currency}"
        elif f_val is not None:
            text = f"от {f_val:g} {currency}"
        elif t_val is not None:
            text = f"до {t_val:g} {currency}"
        else:
            return "Не указана"

        frequency = salary.get("frequency")
        if isinstance(frequency, dict):
            freq_id = frequency.get("id")
        else:
            freq_id = frequency
        frequency_labels = {
            "MONTH": "/мес.",
            "MONTHLY": "/мес.",
            "WEEK": "/нед.",
            "DAY": "/день",
            "HOUR": "/час",
            "SHIFT": "/смена",
        }
        if freq_id in frequency_labels:
            text += f" {frequency_labels[freq_id]}"
        return text.strip()

    @staticmethod
    def convert_hh_link_to_rabotaby(hh_link):
        if not hh_link:
            return hh_link
        match = re.search(r"/vacancy/(\d+)", str(hh_link))
        if match:
            return f"https://rabota.by/vacancy/{match.group(1)}"
        return hh_link


    def _hh_html_search(self, query, city_name, area_info, params, source, host, cancel_event=None):
        """Fallback to ordinary public vacancy pages when anonymous HH API is blocked.

        This is not a CAPTCHA bypass. The fallback only tries pages that a normal
        unauthenticated browser can open. Rabota.by sometimes answers 406 to the
        generic ``/search/vacancy`` endpoint, so a second public SEO category URL
        is tried for simple profession queries.
        """
        results = []
        diag = self._diag(source)
        min_salary, salary_currency, salary_mode = self._salary_from_params(params)
        excluded = [w.strip() for w in params.get("exclude", "").split(",") if w.strip()]
        queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
        requested_city = self._normalize_city_key(city_name)
        base_url = f"https://{host}/search/vacancy"
        page_url = base_url
        seen_links = set()
        using_seo = False

        seo_slug = self._slugify_ru(query)
        seo_url = f"https://{host}/vacancies/{seo_slug}" if seo_slug else None
        seo_started_at = None

        def collect_cards(page_soup):
            cards = page_soup.select(
                "[data-qa='vacancy-serp__vacancy'], "
                "[data-qa='vacancy-serp__vacancy_standard'], "
                "div.serp-item"
            )

            # Current public layouts can expose only title anchors. Build the
            # smallest useful card around each unique vacancy link.
            if not cards:
                page_cards = []
                page_ids = set()
                for title_tag in page_soup.select(
                    "a[data-qa='serp-item__title'], "
                    "a[data-qa='vacancy-serp__vacancy-title'], "
                    "a[href*='/vacancy/']"
                ):
                    href = str(title_tag.get("href") or "")
                    vac_id = re.search(r"/vacancy/(\d+)", href)
                    key = vac_id.group(1) if vac_id else href
                    if not key or key in page_ids:
                        continue
                    page_ids.add(key)

                    node = title_tag
                    chosen = None
                    for _ in range(8):
                        node = getattr(node, "parent", None)
                        if node is None:
                            break
                        vacancy_links = node.select("a[href*='/vacancy/']")
                        raw = node.get_text(" ", strip=True)
                        if (
                            1 <= len(vacancy_links) <= 3
                            and len(raw) >= len(title_tag.get_text(" ", strip=True)) + 12
                        ):
                            chosen = node
                            if node.name in {"article", "li"} or len(raw) >= 55:
                                break
                    if chosen is not None:
                        page_cards.append(chosen)
                cards = page_cards

            # Deduplicate structurally duplicated wrappers before statistics.
            unique_cards = []
            card_keys = set()
            for card in cards:
                title_tag = card.select_one(
                    "a[data-qa='serp-item__title'], "
                    "a[data-qa='vacancy-serp__vacancy-title'], "
                    "a[href*='/vacancy/']"
                )
                href = str(title_tag.get("href") or "") if title_tag else ""
                match = re.search(r"/vacancy/(\d+)", href)
                key = match.group(1) if match else href
                if not key or key in card_keys:
                    continue
                card_keys.add(key)
                unique_cards.append(card)
            return unique_cards

        def seo_response_keeps_profession(response):
            """Reject redirects from /vacancies/<profession> to generic /vacancies."""
            if not seo_url:
                return False
            expected_path = urllib.parse.unquote(
                urllib.parse.urlsplit(seo_url).path
            ).rstrip("/").lower()
            actual_path = urllib.parse.unquote(
                urllib.parse.urlsplit(str(getattr(response, "url", seo_url))).path
            ).rstrip("/").lower()
            if not actual_path:
                return False
            return actual_path == expected_path

        for page in range(self.MAX_HH_HTML_PAGES):
            if self._is_cancelled(cancel_event):
                break

            request_params = {
                "text": query,
                "area": area_info["id"],
                "page": page,
                "items_on_page": 100,
                "order_by": "publication_time",
            }
            period = self.PERIOD_MAP.get(params.get("period"), 30)
            if period:
                request_params["period"] = period

            if using_seo:
                local_page = page - int(seo_started_at or 0)
                request_params = {"area": area_info["id"]}
                if local_page:
                    request_params["page"] = local_page
                if period:
                    request_params["period"] = period

            try:
                diag["attempts"] += 1
                response = self._request(
                    page_url,
                    params=request_params if ("?" not in page_url or page_url in {base_url, seo_url}) else None,
                    headers=self._browser_headers(host),
                )
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", "?")
                self._diag_request_failure(
                    source, "rabota_html", exc, requested_url=page_url, params=request_params
                )

                # Rabota's public search endpoint can reject non-browser clients
                # with 406 even when ordinary public /vacancies/... pages exist.
                if (
                    page == 0
                    and source == "Rabota.by"
                    and str(status) in {"403", "406"}
                    and seo_url
                    and not using_seo
                ):
                    self._diag_note(
                        source,
                        f"generic public search returned HTTP {status}; trying SEO vacancy page {seo_url}",
                    )
                    self._log(
                        f"{source}: публичный /search/vacancy вернул HTTP {status}. "
                        f"Пробую обычную страницу профессии /vacancies/{seo_slug}."
                    )
                    try:
                        diag["attempts"] += 1
                        response = self._request(
                            seo_url,
                            params={"area": area_info["id"]},
                            headers=self._browser_headers(host),
                        )
                        if not seo_response_keeps_profession(response):
                            redirected = str(getattr(response, "url", seo_url))
                            self._diag_warning(
                                source,
                                "SEO profession URL redirected to a generic vacancies page; "
                                "secondary fallback stopped to avoid unrelated vacancies",
                            )
                            self._diag_note(source, f"SEO redirect target: {redirected}")
                            self._log(
                                f"{source}: страница профессии перенаправила на общую выдачу "
                                f"{redirected}. Не использую её, чтобы не собирать нерелевантные вакансии."
                            )
                            break
                        using_seo = True
                        seo_started_at = page
                        page_url = seo_url
                    except requests.HTTPError as seo_exc:
                        seo_status = getattr(seo_exc.response, "status_code", "?")
                        self._diag_request_failure(
                            source, "rabota_seo_fallback", seo_exc, requested_url=seo_url,
                            params={"area": area_info["id"]},
                        )
                        self._diag_error(
                            source,
                            f"HTML fallback HTTP {status}; SEO fallback HTTP {seo_status}: {seo_exc}",
                        )
                        self._log(
                            f"{source}: SEO fallback тоже недоступен: HTTP {seo_status}: {seo_exc}"
                        )
                        break
                    except requests.RequestException as seo_exc:
                        self._diag_request_failure(
                            source, "rabota_seo_fallback", seo_exc, requested_url=seo_url,
                            params={"area": area_info["id"]},
                        )
                        self._diag_error(
                            source,
                            f"HTML fallback HTTP {status}; SEO fallback network error: {seo_exc}",
                        )
                        self._log(f"{source}: SEO fallback: ошибка сети: {seo_exc}")
                        break
                else:
                    self._diag_error(source, f"HTML fallback HTTP {status}: {exc}")
                    self._log(f"{source}: HTML fallback HTTP {status}: {exc}")
                    break
            except requests.RequestException as exc:
                self._diag_request_failure(
                    source, "rabota_html", exc, requested_url=page_url, params=request_params
                )
                self._diag_error(source, f"HTML fallback network error: {exc}")
                self._log(f"{source}: HTML fallback: ошибка сети: {exc}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            if page == 0 and diag.get("reported_total") is None:
                diag["reported_total"] = self._extract_reported_total(soup.get_text(" ", strip=True))
            if (
                soup.select_one("[data-qa*='captcha'], form[action*='captcha']")
                or "captcha" in str(getattr(response, "url", page_url)).lower()
            ):
                self._diag_error(source, "HTML fallback also requires CAPTCHA")
                self._diag_note(source, self._response_debug_note(response))
                self._log(f"{source}: публичная HTML-выдача тоже запросила CAPTCHA.")
                break

            cards = collect_cards(soup)

            # Rabota public search can stop exposing parseable cards after a
            # few pages even though the page itself still reports many results.
            # Continue through the ordinary SEO profession listing, preserving
            # the same local title/city/salary filters and global dedup set.
            if (
                not cards
                and page > 0
                and source == "Rabota.by"
                and seo_url
                and not using_seo
            ):
                self._diag_warning(
                    source,
                    "public search pagination stopped exposing vacancy cards; "
                    "continuing with the public SEO profession listing",
                )
                self._log(
                    f"{source}: публичная search-пагинация перестала отдавать "
                    f"распознаваемые карточки на странице {page + 1}. "
                    f"Продолжаю через /vacancies/{seo_slug}."
                )
                try:
                    diag["attempts"] += 1
                    response = self._request(
                        seo_url,
                        params={"area": area_info["id"], **({"period": period} if period else {})},
                        headers=self._browser_headers(host),
                    )
                    if not seo_response_keeps_profession(response):
                        redirected = str(getattr(response, "url", seo_url))
                        self._diag_warning(
                            source,
                            "SEO profession URL redirected to a generic vacancies page; "
                            "secondary fallback stopped to avoid unrelated vacancies",
                        )
                        self._diag_note(source, f"SEO redirect target: {redirected}")
                        self._log(
                            f"{source}: SEO-страница профессии перенаправила на общую выдачу "
                            f"{redirected}. Дополнительный добор остановлен."
                        )
                        cards = []
                    else:
                        using_seo = True
                        seo_started_at = page
                        page_url = seo_url
                        soup = BeautifulSoup(response.text, "html.parser")
                        cards = collect_cards(soup)
                        if cards:
                            self._diag_note(
                                source,
                                "secondary SEO listing started after public-search pagination stall",
                            )
                except requests.RequestException as seo_exc:
                    self._diag_request_failure(
                        source,
                        "rabota_secondary_seo",
                        seo_exc,
                        requested_url=seo_url,
                        params={"area": area_info["id"]},
                    )
                    self._diag_warning(
                        source,
                        f"secondary SEO listing failed after public-search pagination stall: {seo_exc}",
                    )

            if not cards:
                self._diag_note(source, self._response_debug_note(response))
                self._log(
                    f"{source}: HTML fallback, страница {page + 1}: карточки не распознаны. "
                    f"{self._response_debug_note(response)}"
                )
                if page == 0:
                    self._diag_error(source, "HTML fallback markup not recognized")
                break

            diag["pages"] += 1
            diag["fetched"] += len(cards)
            before = len(results)

            for card in cards:
                if self._is_cancelled(cancel_event):
                    break
                title_tag = card.select_one(
                    "a[data-qa='serp-item__title'], "
                    "a[data-qa='vacancy-serp__vacancy-title'], "
                    "a[href*='/vacancy/']"
                )
                if not title_tag:
                    self._diag_filter(source, "invalid")
                    continue

                title = title_tag.get_text(" ", strip=True)
                link = urllib.parse.urljoin(
                    f"https://{host}/", str(title_tag.get("href") or "")
                ).split("?", 1)[0]
                canonical = self._canonical_link(link) or link
                if canonical in seen_links:
                    self._diag_filter(source, "duplicate_on_source")
                    continue
                seen_links.add(canonical)

                if excluded and self._contains_excluded(title, excluded):
                    self._diag_filter(source, "excluded")
                    continue
                if queries and not self.matches_position(title, queries):
                    self._diag_filter(source, "position")
                    self._diag_sample(source, "position", title=title, link=link)
                    continue

                raw_text = card.get_text(" ", strip=True)
                if (
                    params.get("schedule") == "Удаленная работа"
                    and "удален" not in self._normalize_text(raw_text)
                ):
                    self._diag_filter(source, "schedule")
                    continue

                salary_tag = card.select_one(
                    "[data-qa='vacancy-serp__vacancy-compensation'], "
                    "[data-qa='vacancy-serp__vacancy_salary'], "
                    "[data-qa='vacancy-serp__vacancy-salary'], "
                    "[data-qa*='compensation'], "
                    "[data-qa*='salary']"
                )
                salary = self._inline_text(salary_tag.get_text(" ", strip=True)) if salary_tag else ""
                # Public Rabota/HH layouts can remove/rename salary data-qa.
                # Fall back to a currency-anchored regex over the card text.
                if not self.parse_salary(salary, default_currency="BYN" if source == "Rabota.by" else "RUB"):
                    salary = self._extract_salary_from_text(raw_text, default="Не указана")

                if min_salary and not self.check_salary(
                    salary,
                    min_salary,
                    salary_currency,
                    default_currency="BYN" if source == "Rabota.by" else "RUB",
                    mode=salary_mode,
                ):
                    self._diag_filter(source, "salary")
                    self._diag_sample(
                        source,
                        "salary",
                        title=title,
                        raw_salary=salary,
                        salary_tag_found=bool(salary_tag),
                        card_text=raw_text,
                        link=link,
                    )
                    continue

                address_tag = card.select_one(
                    "[data-qa='vacancy-serp__vacancy-address'], "
                    "[data-qa*='address']"
                )
                date_tag = card.select_one(
                    "[data-qa='vacancy-serp__vacancy-date'], time"
                )
                actual_city = address_tag.get_text(" ", strip=True) if address_tag else city_name
                company = self._extract_hh_company_from_card(
                    card,
                    title=title,
                    salary=salary,
                    city=actual_city,
                )

                # SEO pages may not obey ?area= on every deployment. If the
                # card explicitly says another city, do not silently relabel it.
                actual_city_norm = self._normalize_city_key(actual_city)
                if (
                    requested_city
                    and address_tag is not None
                    and requested_city not in actual_city_norm
                    and actual_city_norm not in requested_city
                ):
                    self._diag_filter(source, "city")
                    self._diag_sample(
                        source, "city", title=title, city=actual_city, requested=city_name, link=link
                    )
                    continue

                raw_date = ""
                if date_tag:
                    raw_date = date_tag.get("datetime") or date_tag.get_text(" ", strip=True)
                self._diag_sample(
                    source, "accepted", title=title, salary=salary, company=company,
                    city=actual_city, link=link,
                )
                results.append({
                    "position": title,
                    "salary": salary,
                    "company": company,
                    "source": source,
                    "link": link,
                    "city": actual_city,
                    "date": self._normalize_date(raw_date),
                })
                if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                    break

            page_added = len(results) - before
            self._diag_page(
                source,
                page=page + 1,
                strategy="seo" if using_seo else "public_search",
                url=str(getattr(response, "url", page_url)),
                http=getattr(response, "status_code", 200),
                html_chars=len(getattr(response, "text", "") or ""),
                cards=len(cards),
                accepted=page_added,
            )
            self._log(
                f"{source}: HTML fallback, страница {page + 1}: карточек={len(cards)}, "
                f"добавлено={page_added}"
                + ("; SEO-страница" if using_seo else "")
                + "."
            )
            if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                break

            next_url = self._discover_next_page_url(
                soup, str(getattr(response, "url", page_url)), page + 2
            )
            if next_url:
                page_url = next_url
            elif len(cards) >= 20:
                # Bounded numeric pagination for layouts without rel=next.
                if using_seo:
                    local_next_page = page - int(seo_started_at or 0) + 1
                    page_url = self._url_with_query(
                        seo_url,
                        page=local_next_page,
                        area=area_info["id"],
                    )
                else:
                    page_url = base_url
            else:
                break

        if diag.get("status") != "error" and diag.get("fetched", 0) > 0:
            # The source itself worked through HTML even when strict local
            # filters reduced accepted results to zero. API 403 remains a
            # warning, not a false source failure.
            diag["error"] = None
            self._diag_finish(source, len(results), status="fallback_success")
            self._diag_note(source, "HH API unavailable; public HTML fallback was used")
        elif diag.get("status") != "error":
            self._diag_finish(source, len(results))
        return results

    def _hh_search(self, query, city_name, area_info, params, cancel_event=None):
        source = "Rabota.by" if area_info["country"] == "BY" else "HH.ru"
        host = "rabota.by" if area_info["country"] == "BY" else "hh.ru"
        results = []
        diag = self._diag(source)
        if diag.get("status") == "not_run":
            diag["status"] = "running"

        api_params = {
            "text": query,
            "search_field": "name",
            "area": area_info["id"],
            "per_page": 100,
            "order_by": "publication_time",
            "period": self.PERIOD_MAP.get(params.get("period"), 30),
            "host": host,
            "locale": "RU",
        }

        excluded = [w.strip() for w in params.get("exclude", "").split(",") if w.strip()]
        if excluded:
            api_params["excluded_text"] = ",".join(excluded)

        min_salary, salary_currency, salary_mode = self._salary_from_params(params)
        # To maximize recall, soft mode is intentionally filtered locally:
        # sending salary to HH would also remove vacancies with unspecified pay.
        if min_salary > 0 and salary_mode == "Строгий":
            api_params["salary"] = min_salary
            api_params["currency"] = self._hh_currency_code(salary_currency)
            api_params["salary_mode"] = "MONTH"
            api_params["salary_frequency"] = "MONTHLY"
            api_params["label"] = "with_salary"

        exp = self.EXPERIENCE_MAP.get(params.get("experience"))
        if exp:
            api_params["experience"] = exp

        schedule = params.get("schedule", "Любой")
        work_format = self.WORK_FORMAT_MAP.get(schedule)
        if work_format:
            api_params["work_format"] = work_format
        else:
            legacy_schedule = self.LEGACY_SCHEDULE_MAP.get(schedule)
            if legacy_schedule:
                api_params["schedule"] = legacy_schedule

        pages_to_fetch = 1
        page_limit = self.MAX_HH_PAGES if self.hh_authorized else 1
        if not self.hh_authorized:
            self._log(
                f"{source}: анонимный HH API: максимум одна API-страница. "
                "При CAPTCHA/403 программа автоматически попробует публичную HTML-выдачу."
            )

        for page in range(page_limit):
            if self._is_cancelled(cancel_event):
                break
            api_params["page"] = page
            try:
                diag["attempts"] += 1
                data = self._request(self.HH_API_URL, params=api_params, expect_json=True)
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", "?")
                self._diag_request_failure(
                    source, "hh_api", exc, requested_url=self.HH_API_URL, params=api_params
                )
                if status == 403:
                    message = "HH API returned 403 (CAPTCHA/anonymous access restriction)"
                    self._diag_warning(source, message)
                    self._diag_note(source, "API 403 is recoverable when public HTML fallback succeeds")
                    self._log(
                        f"{source}: HTTP 403 от HH API. Переключаюсь на публичную web-выдачу; "
                        "OAuth-токен HH_API_TOKEN остаётся рекомендуемым вариантом для стабильной API-пагинации."
                    )
                    return self._hh_html_search(
                        query, city_name, area_info, params, source, host, cancel_event
                    )
                elif status == 429:
                    self._diag_error(source, "HH API rate limit (HTTP 429)")
                    self._log(f"{source}: HTTP 429 — превышен лимит запросов.")
                else:
                    self._diag_error(source, f"HH API HTTP {status}: {exc}")
                    self._log(f"{source}: HTTP {status}: {exc}")
                break
            except (requests.RequestException, ValueError) as exc:
                if isinstance(exc, requests.RequestException):
                    self._diag_request_failure(
                        source, "hh_api", exc, requested_url=self.HH_API_URL, params=api_params
                    )
                self._diag_error(source, f"HH API request error: {exc}")
                self._log(f"{source}: ошибка запроса: {exc}")
                break

            if page == 0:
                found = int(data.get("found") or 0)
                pages_to_fetch = max(1, min(int(data.get("pages") or 1), page_limit))
                self._diag_note(source, f"HH API found={found}")
                self._log(
                    f"{source}: API нашёл {found}; будет загружено до {pages_to_fetch * 100} "
                    f"результатов для «{query}» / {city_name}."
                )

            items = data.get("items") or []
            diag["pages"] += 1
            diag["fetched"] += len(items)
            for item in items:
                if self._is_cancelled(cancel_event):
                    break

                title = str(item.get("name") or "").strip()
                if not title:
                    self._diag_filter(source, "invalid")
                    continue
                if excluded and self._contains_excluded(title, excluded):
                    self._diag_filter(source, "excluded")
                    continue

                queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
                if queries and not self.matches_position(title, queries):
                    self._diag_filter(source, "position")
                    continue

                salary_txt = self._format_hh_salary(item)
                if min_salary > 0 and not self.check_salary(
                    salary_txt,
                    min_salary,
                    salary_currency,
                    default_currency=salary_currency,
                    mode=salary_mode,
                ):
                    self._diag_filter(source, "salary")
                    continue

                area = item.get("area") or {}
                employer = item.get("employer") or {}
                link = item.get("alternate_url")
                vacancy_id = str(item.get("id") or "")
                if not link and vacancy_id:
                    link = f"https://{host}/vacancy/{vacancy_id}"
                if source == "Rabota.by":
                    link = self.convert_hh_link_to_rabotaby(link)

                company_name = str(employer.get("name") or "Не указана")
                result_city = str(area.get("name") or area_info.get("name") or city_name)
                self._diag_sample(
                    source, "accepted", title=title, salary=salary_txt, company=company_name,
                    city=result_city, link=str(link or ""),
                )
                results.append({
                    "position": title,
                    "salary": salary_txt,
                    "company": company_name,
                    "source": source,
                    "link": str(link or ""),
                    "city": result_city,
                    "date": self._normalize_date(str(item.get("published_at") or "")),
                })
                if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                    break

            if len(results) >= self.MAX_RESULTS_PER_SOURCE or page + 1 >= pages_to_fetch or not items:
                break

        self._diag_finish(source, len(results))
        filtered = diag["filtered"]
        self._log(
            f"{source}: получено={diag['fetched']}, добавлено={len(results)}; "
            f"отсеяно: название={filtered['position']}, зарплата={filtered['salary']}, "
            f"исключения={filtered['excluded']}, график={filtered['schedule']}, некорректные={filtered['invalid']}."
        )
        return results

    def _salary_from_params(self, params):
        try:
            value = int(str(params.get("salary", "")).strip() or 0)
        except ValueError:
            value = 0
        mode = self._salary_mode(params)
        if mode == "Не фильтровать":
            value = 0
        return max(value, 0), params.get("salary_currency", "BYN"), mode

    def search_praca(self, query, city_name, params, cancel_event=None):
        results = []
        source = "Praca.by"
        diag = self._diag(source)
        if diag.get("status") == "not_run":
            diag["status"] = "running"

        if self._normalize_city_key(city_name) != "минск":
            message = (
                f"источник пропущен для «{city_name}»: надёжный фильтр города "
                "в текущем адаптере настроен только для Минска"
            )
            self._diag_error(source, message)
            self._log(f"Praca.by: {message}.")
            return results

        min_salary, salary_currency, salary_mode = self._salary_from_params(params)
        excluded = [w.strip() for w in params.get("exclude", "").split(",") if w.strip()]
        queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
        base_url = "https://praca.by/search/vacancies/"
        page_url = base_url
        seen_links = set()

        for page in range(self.MAX_PRACA_PAGES):
            if self._is_cancelled(cancel_event):
                break

            request_params = None
            if page_url == base_url:
                request_params = {
                    "search[query]": query,
                    "sort": "date",
                    "search[city-id-1]": "1",
                }
                if page:
                    request_params["page"] = page + 1

            try:
                diag["attempts"] += 1
                response = self._request(page_url, params=request_params)
            except requests.RequestException as exc:
                self._diag_request_failure(
                    source, "praca_listing", exc, requested_url=page_url, params=request_params
                )
                self._diag_error(source, f"network error: {exc}")
                self._log(f"Praca.by: ошибка сети: {exc}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            if page == 0 and diag.get("reported_total") is None:
                diag["reported_total"] = self._extract_reported_total(soup.get_text(" ", strip=True))
            # The live Praca layout currently has two ``vac-small__column``
            # wrappers per vacancy. Only one contains the vacancy title link.
            # Counting both made diagnostics report 200 fetched / 100 invalid
            # while there were really about 100 vacancy cards.
            items = [
                item
                for item in soup.select("div.vac-small__column")
                if item.select_one("a.vac-small__title-link")
            ]
            if not items:
                # Tolerant fallback for a changed wrapper.
                items = [
                    tag.find_parent(["article", "li", "div"])
                    for tag in soup.select("a.vac-small__title-link")
                ]
                items = [item for item in items if item is not None]

            if not items:
                if page == 0:
                    self._diag_error(source, "listing markup not recognized or no results")
                self._log(f"Praca.by: страница {page + 1}: карточки не распознаны или результатов нет.")
                break

            diag["pages"] += 1
            diag["fetched"] += len(items)
            before = len(results)

            for item in items:
                if self._is_cancelled(cancel_event):
                    break
                title_tag = item.select_one("a.vac-small__title-link")
                if not title_tag:
                    self._diag_filter(source, "invalid")
                    self._diag_sample(source, "invalid", card_text=item.get_text(" ", strip=True))
                    continue

                title = title_tag.get_text(" ", strip=True)
                link = urllib.parse.urljoin("https://praca.by/", str(title_tag.get("href") or "")).split("?", 1)[0]
                if link and link in seen_links:
                    self._diag_filter(source, "duplicate_on_source")
                    continue
                if link:
                    seen_links.add(link)

                if excluded and self._contains_excluded(title, excluded):
                    self._diag_filter(source, "excluded")
                    continue
                if queries and not self.matches_position(title, queries):
                    self._diag_filter(source, "position")
                    self._diag_sample(source, "position", title=title, link=link)
                    continue

                raw_text = item.get_text(" ", strip=True)
                if params.get("schedule") == "Удаленная работа" and "удален" not in self._normalize_text(raw_text):
                    self._diag_filter(source, "schedule")
                    continue

                salary_tag = item.select_one("div.vac-small__salary")
                salary = salary_tag.get_text(" ", strip=True) if salary_tag else "По договоренности"
                if min_salary and not self.check_salary(
                    salary,
                    min_salary,
                    salary_currency,
                    default_currency="BYN",
                    mode=salary_mode,
                ):
                    self._diag_filter(source, "salary")
                    self._diag_sample(source, "salary", title=title, raw_salary=salary, card_text=raw_text, link=link)
                    continue

                company_tag = item.select_one(
                    "a.vac-small__customer-link, div.vac-small__customer, "
                    "a[class*='customer'], [class*='customer'], "
                    "a[class*='company'], a[class*='employer'], "
                    "a[href*='/company/'], a[href*='/employer/'], a[href*='/organization/']"
                )
                company = "Н/Д"
                if company_tag is not None:
                    candidate = company_tag.get_text(" ", strip=True)
                    if candidate and len(candidate) <= 120:
                        candidate_norm = self._normalize_text(candidate)
                        if (
                            candidate_norm != self._normalize_text(title)
                            and not re.search(
                                r"\d[\d\s\u00a0.,]*(?:BYN|Br|руб|USD|EUR|\$|€|₽)",
                                candidate,
                                re.I,
                            )
                        ):
                            company = candidate

                if company == "Н/Д":
                    # Layout-tolerant fallback: take another short link from the
                    # card that looks like an employer, not an action/city link.
                    for candidate_tag in item.find_all("a", href=True):
                        if candidate_tag is title_tag:
                            continue
                        candidate = candidate_tag.get_text(" ", strip=True)
                        if not candidate or len(candidate) > 100:
                            continue
                        norm = self._normalize_text(candidate)
                        href = str(candidate_tag.get("href") or "").lower()
                        if any(word in norm for word in ("подробнее", "отклик", "ваканси", "минск")):
                            continue
                        if re.search(
                            r"\d[\d\s\u00a0.,]*(?:BYN|Br|руб|USD|EUR|\$|€|₽)",
                            candidate,
                            re.I,
                        ):
                            continue
                        if any(token in href for token in ("company", "employer", "customer", "organization")):
                            company = candidate
                            break
                date_tag = item.select_one("time, .vac-small__date, .vac-small__date-text")
                raw_date = ""
                if date_tag:
                    raw_date = date_tag.get("datetime") or date_tag.get_text(" ", strip=True)

                result_city = city_name.strip().title()
                self._diag_sample(
                    source, "accepted", title=title, salary=salary, company=company,
                    city=result_city, link=link,
                )
                results.append({
                    "position": title,
                    "salary": salary,
                    "company": company,
                    "source": source,
                    "link": link,
                    "city": result_city,
                    "date": self._normalize_date(raw_date),
                })
                if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                    break

            page_added = len(results) - before
            self._diag_page(
                source, page=page + 1, url=str(getattr(response, "url", page_url)),
                http=getattr(response, "status_code", 200),
                html_chars=len(getattr(response, "text", "") or ""),
                cards=len(items), accepted=page_added,
            )
            self._log(
                f"Praca.by: страница {page + 1}: карточек={len(items)}, "
                f"добавлено={page_added}."
            )
            if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                break

            next_url = self._discover_next_page_url(soup, str(getattr(response, 'url', page_url)), page + 2)
            if not next_url:
                # If Praca does not expose rel=next in the current layout, a
                # page query is still tried while the current page looks full.
                if len(items) < 20:
                    break
                page_url = base_url
            else:
                page_url = next_url

        self._diag_finish(source, len(results))
        filtered = diag["filtered"]
        self._log(
            f"Praca.by: получено={diag['fetched']}, страниц={diag['pages']}, добавлено={len(results)}; "
            f"отсеяно: название={filtered['position']}, зарплата={filtered['salary']}, "
            f"исключения={filtered['excluded']}, график={filtered['schedule']}, "
            f"дубли_источника={filtered['duplicate_on_source']}, некорректные={filtered['invalid']}."
        )
        return results

    def search_belmeta(self, query, city_name, params, cancel_event=None):
        """Search Belmeta with bounded pagination and tolerant card extraction."""
        results = []
        source = "Belmeta"
        diag = self._diag(source)
        if diag.get("status") == "not_run":
            diag["status"] = "running"

        min_salary, salary_currency, salary_mode = self._salary_from_params(params)
        excluded = [w.strip() for w in params.get("exclude", "").split(",") if w.strip()]
        queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
        requested_city = self._normalize_city_key(city_name)
        profession_path = urllib.parse.quote(query.strip(), safe="")
        base_url = f"https://belmeta.com/вакансии/{profession_path}"
        search_query_url = self._url_with_query(
            "https://belmeta.com/vacansii",
            q=query.strip(),
        )
        page_url = base_url
        seen_vacancy_links = set()

        def sane_text(tag, *, max_len=120):
            if tag is None:
                return ""
            value = tag.get_text(" ", strip=True)
            if not value or len(value) > max_len:
                return ""
            return value

        def extract_company(card, title, salary, raw_text):
            # Prefer explicit semantic selectors. The old broad
            # ``[class*='company']`` selector could accidentally select a large
            # wrapper and place salary/city text into the Company column.
            selectors = (
                "[itemprop='hiringOrganization'] [itemprop='name']",
                "[itemprop='hiringOrganization']",
                "a[href*='/company/']",
                "a[href*='/employer/']",
                "a[class~='company']",
                "div.job-data.company",
                ".company",
                ".employer",
            )
            for selector in selectors:
                candidate = card.select_one(selector)
                value = sane_text(candidate)
                if not value:
                    continue
                norm = self._normalize_text(value)
                if self._normalize_text(title) in norm and len(norm) > len(self._normalize_text(title)) + 8:
                    continue
                if salary and self._normalize_text(salary) in norm:
                    continue
                if requested_city and requested_city in self._normalize_city_key(value):
                    continue
                return value

            # Last-resort heuristic: short linked text that is not the vacancy
            # title, salary, city, date or an action button.
            for candidate in card.find_all(["a", "span", "div"]):
                value = sane_text(candidate, max_len=90)
                if not value:
                    continue
                norm = self._normalize_text(value)
                if norm == self._normalize_text(title):
                    continue
                if requested_city and requested_city in self._normalize_city_key(value):
                    continue
                if re.search(r"\d[\d\s\u00a0.,]*(?:BYN|Br|руб|USD|EUR|\$|€|₽)", value, re.I):
                    continue
                if any(word in norm for word in ("сегодня", "вчера", "отклик", "подробнее", "ваканси")):
                    continue
                href = str(candidate.get("href") or "")
                if href and any(token in href.lower() for token in ("company", "employer", "customer")):
                    return value
            return "Н/Д"

        def collect_jobs(soup):
            title_links = soup.select(
                "a[href*='/viewjob'], a[href*='viewjob'], "
                "a[href*='/jobdesc'], a[href*='jobdesc']"
            )
            jobs = []
            page_seen = set()
            for title_tag in title_links:
                href = str(title_tag.get("href") or "")
                absolute = urllib.parse.urljoin("https://belmeta.com/", href)
                key_match = re.search(r"(?:viewjob|jobdesc)\?[^#]*\bid=(\d+)", absolute)
                key = key_match.group(1) if key_match else absolute
                if not key or key in page_seen:
                    continue
                page_seen.add(key)

                card = None
                node = title_tag
                for _ in range(8):
                    node = getattr(node, "parent", None)
                    if node is None:
                        break
                    links_here = node.select(
                        "a[href*='/viewjob'], a[href*='viewjob'], "
                        "a[href*='/jobdesc'], a[href*='jobdesc']"
                    )
                    raw = node.get_text(" ", strip=True)
                    if (
                        1 <= len(links_here) <= 2
                        and len(raw) >= max(25, len(title_tag.get_text(" ", strip=True)) + 10)
                    ):
                        card = node
                        if node.name in {"article", "li"} or len(raw) >= 60:
                            break
                if card is not None:
                    jobs.append((title_tag, card, absolute, key))
            return jobs

        prefetched_response = None
        for page in range(self.MAX_BELMETA_PAGES):
            if self._is_cancelled(cancel_event):
                break
            if prefetched_response is not None:
                response = prefetched_response
                prefetched_response = None
            else:
                try:
                    diag["attempts"] += 1
                    response = self._request(
                        page_url,
                        headers=self._browser_headers("belmeta.com"),
                    )
                except requests.RequestException as exc:
                    self._diag_request_failure(
                        source, "belmeta_listing", exc, requested_url=page_url
                    )
                    self._diag_error(source, f"network error: {exc}")
                    self._log(f"Belmeta: ошибка сети: {exc}")
                    break

            soup = BeautifulSoup(response.text, "html.parser")
            if page == 0 and diag.get("reported_total") is None:
                diag["reported_total"] = self._extract_reported_total(soup.get_text(" ", strip=True))
            jobs = collect_jobs(soup)

            if not jobs:
                if page == 0:
                    self._diag_error(source, "listing markup not recognized or no results")
                    self._diag_note(source, self._response_debug_note(response))
                self._log(
                    f"Belmeta: страница {page + 1}: карточки не распознаны или результатов нет."
                )
                break

            diag["pages"] += 1
            diag["fetched"] += len(jobs)
            before = len(results)
            seen_before = len(seen_vacancy_links)

            for title_tag, job, link, vacancy_key in jobs:
                if self._is_cancelled(cancel_event):
                    break
                if vacancy_key in seen_vacancy_links:
                    self._diag_filter(source, "duplicate_on_source")
                    continue
                seen_vacancy_links.add(vacancy_key)

                title = title_tag.get_text(" ", strip=True)
                if not title:
                    self._diag_filter(source, "invalid")
                    continue
                if excluded and self._contains_excluded(title, excluded):
                    self._diag_filter(source, "excluded")
                    continue
                if queries and not self.matches_position(title, queries):
                    self._diag_filter(source, "position")
                    continue

                raw_text = job.get_text(" ", strip=True)
                raw_city = self._normalize_city_key(raw_text)
                if requested_city and requested_city not in raw_city:
                    self._diag_filter(source, "city")
                    self._diag_sample(source, "city", title=title, requested=city_name, card_text=raw_text, link=link)
                    continue
                if (
                    params.get("schedule") == "Удаленная работа"
                    and "удален" not in self._normalize_text(raw_text)
                ):
                    self._diag_filter(source, "schedule")
                    continue

                salary_tag = job.select_one(
                    "div.job-data.salary, .salary, [class~='salary'], [data-qa*='salary']"
                )
                if salary_tag:
                    salary = salary_tag.get_text(" ", strip=True)
                else:
                    salary_match = re.search(
                        r"(?i)(?:от\s+|до\s+)?\d[\d\s\u00a0.,]*"
                        r"(?:\s*[-–—]\s*\d[\d\s\u00a0.,]*)?\s*"
                        r"(?:BYN|Br|руб\.?|USD|EUR|\$|€|₽)",
                        raw_text,
                    )
                    salary = salary_match.group(0).strip() if salary_match else "По договоренности"

                if min_salary and not self.check_salary(
                    salary,
                    min_salary,
                    salary_currency,
                    default_currency="BYN",
                    mode=salary_mode,
                ):
                    self._diag_filter(source, "salary")
                    self._diag_sample(source, "salary", title=title, raw_salary=salary, card_text=raw_text, link=link)
                    continue

                company = extract_company(job, title, salary, raw_text)

                source_tag = job.select_one("div.job-data.source, .job-data.source")
                source_text = sane_text(source_tag, max_len=70)
                real_source = (
                    f"Belmeta ({source_text})"
                    if source_text and source_text.lower() != "belmeta"
                    else "Belmeta"
                )

                date_tag = job.select_one("time, .job-data.date, [class~='date']")
                raw_date = ""
                if date_tag:
                    raw_date = date_tag.get("datetime") or date_tag.get_text(" ", strip=True)
                if not raw_date:
                    relative_date = re.search(
                        r"(?i)(сегодня|вчера|\d+\s+(?:день|дня|дней)\s+назад)",
                        raw_text,
                    )
                    raw_date = relative_date.group(1) if relative_date else ""

                result_city = city_name.strip().title()
                self._diag_sample(
                    source, "accepted", title=title, salary=salary, company=company,
                    city=result_city, link=link,
                )
                results.append({
                    "position": title,
                    "salary": salary,
                    "company": company,
                    "source": real_source,
                    "link": link,
                    "city": result_city,
                    "date": self._normalize_date(raw_date),
                })
                if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                    break

            page_added = len(results) - before
            current_page_url = str(getattr(response, "url", page_url))
            exposed_pagination = self._discover_pagination_urls(
                soup,
                current_page_url,
                page + 2,
                base_url=base_url,
                page_size=20,
            )
            exposed_pagination = self._rank_pagination_candidates(
                exposed_pagination,
                query_text=query,
                current_url=current_page_url,
                base_url=base_url,
            )
            self._diag_page(
                source,
                page=page + 1,
                url=current_page_url,
                http=getattr(response, "status_code", 200),
                html_chars=len(getattr(response, "text", "") or ""),
                cards=len(jobs),
                accepted=page_added,
                pagination_candidates=exposed_pagination[:6],
            )
            self._log(
                f"Belmeta: страница {page + 1}: карточек={len(jobs)}, "
                f"добавлено={page_added}."
            )
            if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                break

            if len(seen_vacancy_links) == seen_before and page > 0:
                # The site sometimes ignores an unsupported page parameter and
                # silently returns page 1 again. Probe a few bounded pagination
                # shapes and continue only if a candidate contains unseen IDs.
                current_url = str(getattr(response, "url", page_url))
                logical_page = page + 1
                found_alternative = False
                probe_notes = []

                exposed_candidates = self._discover_pagination_urls(
                    soup,
                    current_url,
                    logical_page + 1,
                    base_url=base_url,
                    page_size=20,
                )
                exposed_candidates = self._rank_pagination_candidates(
                    exposed_candidates,
                    query_text=query,
                    current_url=current_url,
                    base_url=base_url,
                )
                probe_candidates = [
                    *exposed_candidates,
                    *self._pagination_probe_urls(search_query_url, logical_page, page_size=20),
                    *self._pagination_probe_urls(search_query_url, logical_page + 1, page_size=20),
                ]
                probe_candidates = self._rank_pagination_candidates(
                    probe_candidates,
                    query_text=query,
                    current_url=current_url,
                    base_url=search_query_url,
                )
                seen_probe_urls = set()
                for candidate in probe_candidates:
                    if (
                        candidate == current_url
                        or candidate == page_url
                        or candidate in seen_probe_urls
                    ):
                        continue
                    seen_probe_urls.add(candidate)
                    try:
                        diag["attempts"] += 1
                        candidate_response = self._request(
                            candidate, headers=self._browser_headers("belmeta.com")
                        )
                    except requests.RequestException as exc:
                        self._diag_request_failure(
                            source, "belmeta_pagination_probe", exc, requested_url=candidate
                        )
                        probe_notes.append(f"{candidate} -> error {exc}")
                        continue
                    candidate_soup = BeautifulSoup(candidate_response.text, "html.parser")
                    candidate_jobs = collect_jobs(candidate_soup)
                    candidate_keys = {row[3] for row in candidate_jobs}
                    unseen = candidate_keys.difference(seen_vacancy_links)
                    probe_notes.append(
                        f"{candidate} -> cards={len(candidate_jobs)}, unseen={len(unseen)}"
                    )
                    if unseen:
                        page_url = candidate
                        prefetched_response = candidate_response
                        found_alternative = True
                        self._diag_note(
                            source,
                            "pagination alternative selected: "
                            + candidate
                            + (" (exposed by site HTML)" if candidate in exposed_candidates else " (bounded probe)"),
                        )
                        break
                for note in probe_notes[:6]:
                    self._diag_note(source, "pagination probe: " + note)
                if found_alternative:
                    continue
                self._diag_warning(source, "pagination repeated the previous vacancy set; no alternative URL worked")
                break

            current_url = str(getattr(response, "url", page_url))
            next_candidates = self._discover_pagination_urls(
                soup,
                current_url,
                page + 2,
                base_url=base_url,
                page_size=20,
            )
            next_candidates = self._rank_pagination_candidates(
                next_candidates,
                query_text=query,
                current_url=current_url,
                base_url=base_url,
            )
            if next_candidates:
                page_url = next_candidates[0]
                self._diag_note(
                    source,
                    f"pagination URL discovered from Belmeta HTML: {page_url}",
                )
            elif len(jobs) >= 20:
                # Only after the page itself exposes no usable navigation do we
                # try a bounded conventional query. Duplicate detection and the
                # alternative-probe branch above prevent endless page-1 loops.
                page_url = self._url_with_query(
                    search_query_url,
                    page=page + 2,
                )
            else:
                break

        self._diag_finish(source, len(results))
        filtered = diag["filtered"]
        self._log(
            f"Belmeta: получено={diag['fetched']}, страниц={diag['pages']}, добавлено={len(results)}; "
            f"отсеяно: город={filtered['city']}, название={filtered['position']}, "
            f"зарплата={filtered['salary']}, исключения={filtered['excluded']}, "
            f"график={filtered['schedule']}, дубли_источника={filtered['duplicate_on_source']}, "
            f"некорректные={filtered['invalid']}."
        )
        return results

    def search_gsz(self, query, city_name, params, cancel_event=None):
        """Search the Belarus national vacancy bank through its public GET contract.

        Real public links use query parameters such as ``profession``, ``region``,
        ``salary_min``, ``search_period``, ``paginate_by`` and
        ``sort_by=sort_published_at_desc``. The previous implementation submitted
        whichever HTML form it found and could end up with a page that contained
        no result markup. This implementation derives a numeric region value when
        possible, then uses the public vacancy-search URL directly and parses
        official ``detail-public`` vacancy links.
        """
        results = []
        source = "GSZ.gov.by"
        diag = self._diag(source)
        if diag.get("status") == "not_run":
            diag["status"] = "running"

        min_salary, salary_currency, salary_mode = self._salary_from_params(params)
        excluded = [w.strip() for w in params.get("exclude", "").split(",") if w.strip()]
        queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
        requested_city = self._normalize_city_key(city_name)
        base_url = "https://gsz.gov.by/registration/vacancy-search/"

        verify = True
        landing = None
        last_error = None

        # Load the public search page only to discover location option values and
        # retain any hidden defaults/cookies the portal expects.
        try:
            # Use a one-shot request for the TLS probe. The main Session has
            # retries enabled for ordinary network resilience, but retrying a
            # certificate-chain failure can waste ~15-20 seconds before the
            # already-supported verify=False fallback is attempted.
            diag["attempts"] += 1
            landing = self._request(
                base_url,
                timeout=(3, 8),
                verify=True,
                headers=self._browser_headers("gsz.gov.by"),
                retry=False,
            )
            try:
                self.session.cookies.update(landing.cookies)
            except Exception:
                pass
        except requests.exceptions.SSLError as exc:
            last_error = exc
            self._diag_request_failure(source, "gsz_landing_tls", exc, requested_url=base_url)
            self._diag_warning(source, f"TLS verify failed: {exc}")
            self._log(
                "GSZ.gov.by: не удалось проверить цепочку сертификата. "
                "Повторяю запрос к публичному GSZ с verify=False."
            )
            try:
                import warnings
                from urllib3.exceptions import InsecureRequestWarning
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                    diag["attempts"] += 1
                    landing = self._request(
                        base_url,
                        timeout=(5, 18),
                        verify=False,
                        headers=self._browser_headers("gsz.gov.by"),
                    )
                    verify = False
            except requests.RequestException as fallback_exc:
                self._diag_request_failure(
                    source, "gsz_landing_tls_fallback", fallback_exc, requested_url=base_url
                )
                last_error = fallback_exc
        except requests.RequestException as exc:
            self._diag_request_failure(source, "gsz_landing", exc, requested_url=base_url)
            last_error = exc

        if landing is None:
            self._diag_error(source, f"search page unavailable: {last_error}")
            self._log(f"GSZ.gov.by: страница поиска недоступна: {last_error}")
            return results

        landing_soup = BeautifulSoup(landing.text, "html.parser")
        location_fields, location_controls = self._discover_gsz_location_fields(
            landing_soup,
            city_name,
        )

        if location_controls:
            self._diag_note(
                source,
                "location controls inspected: "
                + json.dumps(location_controls[:6], ensure_ascii=False),
            )

        if location_fields:
            self._diag_note(
                source,
                "location filter: " + ", ".join(f"{k}={v}" for k, v in location_fields.items()),
            )
        else:
            self._diag_note(
                source,
                f"numeric location value for {city_name!r} was not found; "
                "searching by profession and filtering city locally",
            )

        seen_links = set()
        repeated_page = False

        for page_index in range(self.MAX_GSZ_PAGES):
            if self._is_cancelled(cancel_event):
                break

            # Do not send empty form fields. The live GSZ endpoint has been
            # observed returning HTTP 500 when optional location fields are
            # present with empty values. Try progressively simpler public GET
            # requests before declaring the source unavailable.
            full_params = {
                "profession": query,
                "paginate_by": "100",
                "sort_by": "sort_published_at_desc",
                **location_fields,
            }
            if page_index:
                full_params["page"] = page_index + 1

            minimal_params = {
                "profession": query,
                "paginate_by": "100",
                "sort_by": "sort_published_at_desc",
            }
            if page_index:
                minimal_params["page"] = page_index + 1

            wide_params = {
                "paginate_by": "100",
                "sort_by": "sort_published_at_desc",
            }
            if page_index:
                wide_params["page"] = page_index + 1

            strategies = [("profession+location", full_params)]
            if minimal_params != full_params:
                strategies.append(("profession-only", minimal_params))
            strategies.append(("latest-wide-local-filter", wide_params))

            response = None
            strategy_used = None
            strategy_errors = []
            for strategy_name, request_params in strategies:
                try:
                    diag["attempts"] += 1
                    if verify:
                        candidate = self._request(
                            base_url,
                            params=request_params,
                            timeout=(5, 22),
                            headers=self._browser_headers("gsz.gov.by"),
                        )
                    else:
                        import warnings
                        from urllib3.exceptions import InsecureRequestWarning
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", InsecureRequestWarning)
                            candidate = self._request(
                                base_url,
                                params=request_params,
                                timeout=(5, 22),
                                verify=False,
                                headers=self._browser_headers("gsz.gov.by"),
                            )
                    response = candidate
                    strategy_used = strategy_name
                    if strategy_errors:
                        self._diag_warning(
                            source,
                            "earlier GSZ request strategies failed: " + " | ".join(strategy_errors[:3]),
                        )
                    break
                except requests.RequestException as exc:
                    self._diag_request_failure(
                        source, f"gsz_{strategy_name}", exc, requested_url=base_url, params=request_params
                    )
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    detail = f"{strategy_name}: HTTP {status}" if status else f"{strategy_name}: {exc}"
                    strategy_errors.append(detail)
                    self._log(f"GSZ.gov.by: стратегия {strategy_name} не сработала: {exc}")

            if response is None:
                error_text = "all vacancy-search strategies failed: " + " | ".join(strategy_errors)
                self._diag_error(source, error_text)
                self._log(f"GSZ.gov.by: все варианты запроса выдачи завершились ошибкой: {error_text}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            if page_index == 0 and diag.get("reported_total") is None:
                diag["reported_total"] = self._extract_reported_total(soup.get_text(" ", strip=True))
            self._diag_note(source, f"page {page_index + 1}: {self._response_debug_note(response)}")

            # Official public vacancy detail URLs currently contain this path.
            detail_links = []
            page_seen = set()
            for anchor in soup.select(
                "a[href*='/registration/employer/vacancy/'][href*='/detail-public/'], "
                "a[href*='/employer/vacancy/'][href*='/detail-public/']"
            ):
                href = str(anchor.get("href") or "")
                candidates = self._gsz_public_link_candidates(href)
                if not candidates:
                    continue
                absolute = candidates[0]
                match = re.search(r"/vacancy/(?:create-future/)?(\d+)/detail-public/?", absolute)
                key = match.group(1) if match else absolute
                if not key or key in page_seen:
                    continue
                page_seen.add(key)
                self._diag_sample(
                    source, "link_candidate", raw_href=href, public_link=absolute, vacancy_key=key,
                )
                detail_links.append((anchor, absolute, key))

            # Some deployments link to a vacancy detail without the explicit
            # ``detail-public`` suffix. Keep a conservative second pass.
            if not detail_links:
                for anchor in soup.select("a[href*='/registration/employer/vacancy/']"):
                    href = str(anchor.get("href") or "")
                    candidates = self._gsz_public_link_candidates(href)
                    if not candidates:
                        continue
                    absolute = candidates[0]
                    match = re.search(r"/vacancy/(?:create-future/)?(\d+)/detail-public/?", absolute)
                    key = match.group(1) if match else absolute
                    if not key or key in page_seen:
                        continue
                    page_seen.add(key)
                    self._diag_sample(
                        source, "link_candidate", raw_href=href, public_link=absolute, vacancy_key=key, fallback=True,
                    )
                    detail_links.append((anchor, absolute, key))

            # Gracefully distinguish an empty result set from a markup failure.
            page_text_norm = self._normalize_text(soup.get_text(" ", strip=True))
            explicit_empty = any(
                phrase in page_text_norm
                for phrase in (
                    "вакансии не найдены",
                    "ничего не найдено",
                    "по вашему запросу ничего",
                    "нет подходящих вакансий",
                    "0 ваканс",
                )
            )

            if not detail_links:
                if explicit_empty:
                    self._log(
                        f"GSZ.gov.by: страница {page_index + 1}: сайт сообщил, что вакансий нет."
                    )
                    break

                # Table fallback for older portal layouts.
                table_rows = []
                for row in soup.select("table tr"):
                    if row.find("a", href=True) and len(row.select("td")) >= 2:
                        table_rows.append(row)

                if table_rows:
                    detail_links = []
                    for row in table_rows:
                        anchor = row.select_one("a[href*='/registration/employer/vacancy/'], a[href*='/employer/vacancy/']")
                        if anchor is None:
                            continue
                        href = str(anchor.get("href") or "")
                        candidates = self._gsz_public_link_candidates(href)
                        if not candidates:
                            self._diag_sample(source, "invalid", reason="GSZ table row has no public vacancy id", raw_href=href)
                            continue
                        absolute = candidates[0]
                        match = re.search(r"/vacancy/(?:create-future/)?(\d+)/detail-public/?", absolute)
                        key = match.group(1) if match else absolute
                        if key in page_seen:
                            continue
                        page_seen.add(key)
                        self._diag_sample(
                            source, "link_candidate", raw_href=href, public_link=absolute, vacancy_key=key, table_fallback=True,
                        )
                        detail_links.append((anchor, absolute, key))
                else:
                    if page_index == 0:
                        self._diag_error(source, "result vacancy links not recognized")
                    self._diag_sample(
                        source, "invalid",
                        page=page_index + 1,
                        strategy=strategy_used,
                        page_text=soup.get_text(" ", strip=True),
                    )
                    self._log(
                        "GSZ.gov.by: выдача получена, но ссылки вакансий не распознаны. "
                        + self._response_debug_note(response)
                    )
                    break

            diag["pages"] += 1
            diag["fetched"] += len(detail_links)
            before = len(results)
            unique_before = len(seen_links)

            for title_tag, link, vacancy_key in detail_links:
                if self._is_cancelled(cancel_event):
                    break
                if vacancy_key in seen_links:
                    self._diag_filter(source, "duplicate_on_source")
                    continue
                seen_links.add(vacancy_key)

                # Find the smallest useful row/card around the vacancy anchor.
                card = title_tag.find_parent("tr")
                if card is None:
                    node = title_tag
                    for _ in range(8):
                        node = getattr(node, "parent", None)
                        if node is None:
                            break
                        raw = node.get_text(" ", strip=True)
                        detail_count = len(
                            node.select(
                                "a[href*='/employer/vacancy/'], "
                                "a[href*='/registration/employer/vacancy/']"
                            )
                        )
                        if 1 <= detail_count <= 2 and len(raw) >= 25:
                            card = node
                            if node.name in {"article", "li"} or len(raw) >= 55:
                                break
                card = card or title_tag.parent
                raw_text = self._inline_text(card.get_text(" ", strip=True) if card else title_tag.get_text(" ", strip=True))

                # Prefer explicit table columns when GSZ renders a structured table.
                # This is much more reliable than guessing company/salary from the
                # concatenated row text and also prevents newline-heavy salary cells.
                structured = {}
                if card is not None and getattr(card, "name", "") == "tr":
                    table = card.find_parent("table")
                    cells = card.find_all("td", recursive=False) or card.find_all("td")
                    headers = []
                    if table is not None:
                        header_row = table.find("tr")
                        if header_row is not None:
                            headers = [self._inline_text(node.get_text(" ", strip=True)) for node in header_row.find_all(["th", "td"])]
                    for idx, cell in enumerate(cells):
                        if idx >= len(headers):
                            continue
                        header = self._normalize_text(headers[idx])
                        value = self._inline_text(cell.get_text(" ", strip=True))
                        if not value:
                            continue
                        if any(token in header for token in ("професс", "должн", "ваканси")):
                            structured.setdefault("position", value)
                        elif any(token in header for token in ("зарплат", "заработ", "оплат")):
                            structured.setdefault("salary", value)
                        elif any(token in header for token in ("нанимат", "организац", "работодат", "предприят")):
                            structured.setdefault("company", value)
                        elif any(token in header for token in ("город", "регион", "населен", "место работ")):
                            structured.setdefault("city", value)
                        elif any(token in header for token in ("дата", "опублик", "размещ")):
                            structured.setdefault("date", value)

                    self._diag_sample(
                        source,
                        "table_structure",
                        page=page_index + 1,
                        headers=headers,
                        cells=[self._inline_text(c.get_text(" ", strip=True)) for c in cells[:12]],
                        recognized=structured,
                    )

                title = self._inline_text(title_tag.get_text(" ", strip=True))
                if not title or len(title) > 250 or self._normalize_text(title) in {"подробнее", "просмотр", "открыть"}:
                    # The link itself can contain only "Подробнее". Prefer the
                    # profession column, then a short heading/cell.
                    if structured.get("position"):
                        title = structured["position"]
                    else:
                        heading = card.select_one("h2, h3, h4, td, [class*='profession']") if card else None
                        heading_text = self._inline_text(heading.get_text(" ", strip=True)) if heading else ""
                        if heading_text:
                            title = heading_text
                if not title:
                    self._diag_filter(source, "invalid")
                    self._diag_sample(source, "invalid", link=link, card_text=raw_text)
                    continue

                if excluded and self._contains_excluded(title, excluded):
                    self._diag_filter(source, "excluded")
                    continue
                if queries and not self.matches_position(title, queries):
                    # If title link text is generic, try to locate the query in
                    # the surrounding card before discarding the row.
                    matched_heading = None
                    for candidate in card.find_all(["h2", "h3", "h4", "strong", "td"]) if card else []:
                        value = candidate.get_text(" ", strip=True)
                        if value and self.matches_position(value, queries):
                            matched_heading = value
                            break
                    if matched_heading:
                        title = matched_heading
                    else:
                        self._diag_filter(source, "position")
                        self._diag_sample(source, "position", title=title, card_text=raw_text, link=link)
                        continue

                raw_norm = self._normalize_city_key(raw_text)
                server_city_filtered = bool(location_fields) and strategy_used == "profession+location"
                if (
                    requested_city
                    and not server_city_filtered
                    and requested_city not in raw_norm
                ):
                    self._diag_filter(source, "city")
                    self._diag_sample(source, "city", title=title, requested=city_name, card_text=raw_text, link=link)
                    continue

                if (
                    params.get("schedule") == "Удаленная работа"
                    and "удален" not in self._normalize_text(raw_text)
                ):
                    self._diag_filter(source, "schedule")
                    continue

                salary_source = structured.get("salary") or raw_text
                salary = self._extract_salary_from_text(salary_source, default="Не указана")
                if min_salary and not self.check_salary(
                    salary,
                    min_salary,
                    salary_currency,
                    default_currency="BYN",
                    mode=salary_mode,
                ):
                    self._diag_filter(source, "salary")
                    self._diag_sample(source, "salary", title=title, raw_salary=salary, card_text=raw_text, link=link)
                    continue

                raw_date = structured.get("date") or ""
                if not raw_date:
                    date_match = re.search(
                        r"\b(\d{1,2}[./]\d{1,2}[./]\d{2,4})\b",
                        raw_text,
                    )
                    raw_date = date_match.group(1) if date_match else ""

                # Prefer an explicit employer column. Fall back to a bounded
                # heuristic only when the current GSZ layout does not expose
                # header names that we understand.
                company = self._inline_text(structured.get("company")) or "Не указана"
                if company == "Не указана":
                    text_company = self._extract_gsz_company_from_card_text(
                        raw_text,
                        title=title,
                        salary=salary,
                    )
                    if text_company:
                        company = text_company
                        self._diag_sample(
                            source,
                            "company_fallback",
                            title=title,
                            salary=salary,
                            company=company,
                            card_text=raw_text,
                            link=link,
                        )

                if company == "Не указана" and card:
                    cells = [self._inline_text(c.get_text(" ", strip=True)) for c in card.select("td")]
                    for value in cells:
                        norm = self._normalize_text(value)
                        if (
                            value
                            and value != title
                            and len(value) <= 160
                            and not re.search(r"\d[\d\s\u00a0.,]*(?:BYN|Br|руб)", value, re.I)
                            and requested_city not in self._normalize_city_key(value)
                            and not re.fullmatch(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", value)
                            and any(token in norm for token in (
                                "ооо", "оао", "зао", "чуп", "унитар", "предприят",
                                "организац", "комбинат", "завод", "филиал", "центр",
                                "учрежден", "ип ", "уп ", "гуп",
                            ))
                        ):
                            company = value
                            break

                result_city = self._inline_text(structured.get("city")) or city_name.strip().title()
                self._diag_sample(
                    source, "accepted", title=title, salary=salary, company=company,
                    city=result_city, link=link,
                )
                results.append({
                    "position": title,
                    "salary": salary,
                    "company": company,
                    "source": source,
                    "link": link,
                    "city": result_city,
                    "date": self._normalize_date(raw_date),
                })
                if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                    break

            page_added = len(results) - before
            self._diag_page(
                source, page=page_index + 1, strategy=strategy_used,
                url=str(getattr(response, "url", base_url)),
                http=getattr(response, "status_code", 200),
                html_chars=len(getattr(response, "text", "") or ""),
                cards=len(detail_links), accepted=page_added,
            )
            self._log(
                f"GSZ.gov.by: страница {page_index + 1}: стратегия={strategy_used}, "
                f"карточек={len(detail_links)}, добавлено={page_added}."
            )

            if len(results) >= self.MAX_RESULTS_PER_SOURCE:
                break
            if len(seen_links) == unique_before and page_index > 0:
                repeated_page = True
                self._diag_note(source, "pagination repeated the previous vacancy set; stopped")
                break

            # If fewer than requested were returned and no explicit next link is
            # visible, there is no reason to issue another page request.
            next_url = self._discover_next_page_url(
                soup, str(getattr(response, "url", base_url)), page_index + 2
            )
            if next_url:
                # The next iteration keeps the same known query contract; page=N
                # is enough for current Django-style pagination.
                pass
            elif len(detail_links) < 80:
                break

        if results:
            diag["error"] = None
        self._diag_finish(source, len(results))
        filtered = diag["filtered"]
        self._log(
            f"GSZ.gov.by: получено={diag['fetched']}, страниц={diag['pages']}, добавлено={len(results)}; "
            f"отсеяно: город={filtered['city']}, название={filtered['position']}, "
            f"зарплата={filtered['salary']}, исключения={filtered['excluded']}, "
            f"график={filtered['schedule']}, дубли_источника={filtered['duplicate_on_source']}, "
            f"некорректные={filtered['invalid']}."
        )
        return results

    @staticmethod
    def _canonical_link(link):
        """Build a deduplication key without mixing unrelated job boards.

        HH.ru and Rabota.by share vacancy IDs, so those two hosts intentionally
        use one namespace. Other sites must keep their own namespace: numeric
        IDs from Praca or GSZ can coincidentally be the same as an HH vacancy ID.

        Belmeta is especially important here because its vacancy identifier is
        stored in ``?id=...``. Stripping the whole query string collapsed every
        ``/viewjob?id=...`` vacancy into one row.
        """
        if not link:
            return ""
        raw = str(link).strip()
        try:
            parts = urllib.parse.urlsplit(raw)
            host = parts.netloc.lower().split(":", 1)[0]
            if host.startswith("www."):
                host = host[4:]
            path = parts.path.rstrip("/") or "/"
            query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))

            path_vacancy_id = re.search(r"/vacancy/(\d+)", path)

            if host == "hh.ru" or host.endswith(".hh.ru") or host == "rabota.by" or host.endswith(".rabota.by"):
                if path_vacancy_id:
                    return f"hh-vacancy:{path_vacancy_id.group(1)}"

            if host == "praca.by" or host.endswith(".praca.by"):
                if path_vacancy_id:
                    return f"praca-vacancy:{path_vacancy_id.group(1)}"
                for key in ("id", "vacancy_id", "job_id"):
                    if query.get(key):
                        return f"praca-vacancy:{query[key]}"

            if host == "gsz.gov.by" or host.endswith(".gsz.gov.by"):
                if path_vacancy_id:
                    return f"gsz-vacancy:{path_vacancy_id.group(1)}"

            if host == "belmeta.com" or host.endswith(".belmeta.com"):
                for key in ("id", "vacancy_id", "job_id"):
                    if query.get(key):
                        return f"belmeta-vacancy:{query[key]}"

            # Preserve only identifier-like query parameters. Tracking/search
            # parameters are intentionally discarded.
            stable_query = [
                (key, value)
                for key, value in query.items()
                if key.lower() in {"id", "vacancy_id", "job_id"}
            ]
            return urllib.parse.urlunsplit(
                (
                    parts.scheme.lower(),
                    host,
                    path,
                    urllib.parse.urlencode(sorted(stable_query)),
                    "",
                )
            )
        except Exception:
            return raw

    def deduplicate_results(self, results):
        unique = {}
        order = []
        duplicates = 0
        for item in results:
            link_key = self._canonical_link(item.get("link"))
            fallback_key = "|".join([
                self._normalize_text(item.get("position")),
                self._normalize_text(item.get("company")),
                self._normalize_text(item.get("city")),
            ])
            key = link_key or fallback_key
            if not key:
                key = f"row:{len(order)}"

            if key not in unique:
                unique[key] = dict(item)
                order.append(key)
                continue

            duplicates += 1
            existing = unique[key]
            # Prefer a row with a specified salary and retain source provenance.
            if self.salary_sort_value(existing.get("salary")) <= 0 < self.salary_sort_value(item.get("salary")):
                old_source = existing.get("source", "")
                existing.update(item)
                if old_source and old_source not in existing.get("source", ""):
                    existing["source"] = f"{old_source} / {existing.get('source', '')}".strip(" /")
            else:
                new_source = str(item.get("source") or "")
                current_sources = str(existing.get("source") or "")
                if new_source and new_source not in current_sources:
                    existing["source"] = f"{current_sources} / {new_source}".strip(" /")

        if duplicates:
            self._log(f"Удалено дублей: {duplicates}.")
        return [unique[key] for key in order]

    def _sites_for_area(self, enabled_sites, area_info):
        if not area_info:
            return []
        if area_info.get("country") == "BY":
            return [site for site in self.BELARUS_SITES if site in enabled_sites]
        if area_info.get("country") == "RU":
            return ["HH.ru"] if "HH.ru" in enabled_sites else []
        return []

    def search(self, params, progress_callback=None, cancel_event=None):
        queries = [q.strip() for q in params.get("queries", "").split(",") if q.strip()]
        cities = [c.strip() for c in params.get("city", "").split(",") if c.strip()]
        enabled_sites = list(params.get("enabled_sites") or [])
        self._reset_source_diagnostics(enabled_sites)

        self._log("=== НАЧАЛО ПОИСКА ===")
        self._log(f"Запросы: {', '.join(queries)}")
        self._log(f"Города: {', '.join(cities)}")
        self._log(f"Источники: {', '.join(enabled_sites)}")
        salary_mode = self._salary_mode(params)
        self._log(
            f"Фильтр зарплаты: {salary_mode}; минимум: "
            f"{params.get('salary') or 'не задан'} {params.get('salary_currency', 'BYN')}."
        )
        if salary_mode == "Мягкий":
            self._log(
                "Мягкий режим не отправляет минимальную зарплату в HH API: "
                "вакансии без зарплаты сохраняются, а диапазоны фильтруются локально."
            )
        if params.get("period") in {"За все время", "За месяц"}:
            self._log("Период HH API ограничен 30 днями; используется максимум 30 дней.")
        if any(site in enabled_sites for site in ("Praca.by", "Belmeta", "GSZ.gov.by")):
            self._log(
                "Для HTML-источников период зависит от доступной выдачи сайта; "
                "искусственная дата вакансии не подставляется."
            )

        self.update_currency_rates()

        resolved = []
        for city in cities:
            if self._is_cancelled(cancel_event):
                break
            area = self.resolve_area(city)
            if not area:
                self._log(
                    f"Город «{city}» не найден в справочнике HH. "
                    "Чтобы не получить вакансии из неправильного региона, город пропущен."
                )
                continue
            resolved.append((city, area))
            self._log(f"Регион: {city} -> {area.get('name')} (ID {area.get('id')}, {area.get('country')}).")

        tasks = []
        applicable_sources = set()
        for city, area in resolved:
            for query in queries:
                for site in self._sites_for_area(enabled_sites, area):
                    tasks.append((city, area, query, site))
                    applicable_sources.add(site)

        for source in enabled_sites:
            if source not in applicable_sources and self._diag(source)["status"] == "not_run":
                self._diag_error(source, "source is not applicable to selected city/country")

        total_steps = len(tasks)
        if total_steps == 0:
            self._log("Нет применимых комбинаций «город × запрос × источник».")
            if progress_callback:
                progress_callback(0, 0, "Нет источников для выбранных городов")
            return []

        results = []
        for step, (city, area, query, site) in enumerate(tasks, start=1):
            if self._is_cancelled(cancel_event):
                self._log("Поиск остановлен пользователем.")
                break

            if progress_callback:
                progress_callback(step - 1, total_steps, f"{site}: {query} / {city}")
            self._log(f"--- {site}: «{query}», {city} ---")

            if site in {"HH.ru", "Rabota.by"}:
                chunk = self._hh_search(query, city, area, params, cancel_event)
            elif site == "Praca.by":
                chunk = self.search_praca(query, city, params, cancel_event)
            elif site == "Belmeta":
                chunk = self.search_belmeta(query, city, params, cancel_event)
            elif site == "GSZ.gov.by":
                chunk = self.search_gsz(query, city, params, cancel_event)
            else:
                chunk = []
            results.extend(chunk)

            if progress_callback:
                progress_callback(step, total_steps, f"{site}: завершено")
            if site not in {"HH.ru", "Rabota.by"} and not self._is_cancelled(cancel_event):
                time.sleep(0.2)

        results = self.deduplicate_results(results)
        results.sort(key=lambda item: str(item.get("date") or ""), reverse=True)

        counts = self.source_counts(results)
        errors = self.source_errors()
        self._log("=== РЕЗУЛЬТАТЫ ПО ИСТОЧНИКАМ ===")
        for source in enabled_sites:
            diag = self._diag(source)
            self._log(
                f"{source}: статус={diag.get('status')}, результат={counts.get(source, 0)}, "
                f"получено_кандидатов={diag.get('fetched', 0)}, страниц={diag.get('pages', 0)}, "
                f"ошибка={diag.get('error') or 'нет'}."
            )
        if errors:
            self._log(f"Источники с ошибками: {', '.join(errors)}.")
        self._log(f"=== ИТОГО: {len(results)} уникальных вакансий ===")

        if progress_callback and not self._is_cancelled(cancel_event):
            progress_callback(total_steps, total_steps, f"Поиск завершен. Найдено: {len(results)}")
        return results


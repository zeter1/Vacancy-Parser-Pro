import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("job_scraper", ROOT / "job_scraper.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class JobScraperCoreTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MODULE.JobScraper()
        self.scraper.currency_rates = {
            "BYN": 1.0,
            "USD": 3.0,
            "EUR": 3.5,
            "RUB": 0.035,
        }

    def tearDown(self):
        self.scraper.close()

    def test_russian_high_area_id_is_not_belarus(self):
        area = {"id": 1975, "country": "RU", "name": "Барнаул"}
        self.assertFalse(self.scraper.is_belarus_city(area))

    def test_belarus_area_is_belarus(self):
        area = {"id": 1002, "country": "BY", "name": "Минск"}
        self.assertTrue(self.scraper.is_belarus_city(area))

    def test_salary_range_parse(self):
        parsed = self.scraper.parse_salary("2 000 - 3 500 BYN")
        self.assertEqual(parsed["min"], 2000)
        self.assertEqual(parsed["max"], 3500)
        self.assertEqual(parsed["currency"], "BYN")

    def test_salary_thousands_decimal_parse(self):
        parsed = self.scraper.parse_salary("от 2.5 тыс. BYN")
        self.assertEqual(parsed["min"], 2500)

    def test_hh_currency_code_for_belarus(self):
        self.assertEqual(self.scraper._hh_currency_code("BYN"), "BYR")
        self.assertEqual(self.scraper._hh_currency_code("RUB"), "RUR")

    def test_currency_conversion(self):
        self.assertEqual(self.scraper.convert_salary_to_byn("1000 USD"), 3000)

    def test_soft_salary_uses_upper_bound(self):
        self.assertTrue(self.scraper.check_salary("1000 - 3000 BYN", 2500, "BYN", strict=False))

    def test_strict_salary_uses_lower_bound(self):
        self.assertFalse(self.scraper.check_salary("1000 - 3000 BYN", 2500, "BYN", strict=True))

    def test_missing_salary_soft_vs_strict(self):
        self.assertTrue(self.scraper.check_salary("Не указана", 2000, "BYN", strict=False))
        self.assertFalse(self.scraper.check_salary("Не указана", 2000, "BYN", strict=True))


    def test_hh_search_uses_current_salary_and_work_format_params(self):
        captured = {}

        def fake_request(url, *, params=None, expect_json=False, timeout=None):
            captured["url"] = url
            captured["params"] = dict(params or {})
            return {"found": 0, "pages": 1, "items": []}

        self.scraper._request = fake_request
        params = {
            "queries": "Python",
            "exclude": "",
            "salary": "2000",
            "salary_currency": "BYN",
            "experience": "Не имеет значения",
            "schedule": "Удаленная работа",
            "period": "За неделю",
            "strict_salary": True,
        }
        area = {"id": 1002, "country": "BY", "name": "Минск"}
        result = self.scraper._hh_search("Python", "Минск", area, params)

        self.assertEqual(result, [])
        self.assertEqual(captured["params"]["host"], "rabota.by")
        self.assertEqual(captured["params"]["currency"], "BYR")
        self.assertEqual(captured["params"]["salary_mode"], "MONTH")
        self.assertEqual(captured["params"]["salary_frequency"], "MONTHLY")
        self.assertEqual(captured["params"]["label"], "with_salary")
        self.assertEqual(captured["params"]["work_format"], "REMOTE")

    def test_hourly_salary_not_compared_to_monthly(self):
        self.assertEqual(self.scraper.salary_sort_value("20 BYN /час"), 0)
        self.assertFalse(self.scraper.check_salary("20 BYN /час", 1000, "BYN", strict=True))

    def test_date_normalization(self):
        self.assertEqual(self.scraper._normalize_date("12.08.2026"), "2026-08-12")
        self.assertEqual(self.scraper._normalize_date("2026-08-12T10:00:00+0300"), "2026-08-12")
        self.assertEqual(self.scraper._normalize_date("неизвестно"), "")


    def test_city_normalization_handles_prefix_and_hyphen(self):
        self.assertEqual(self.scraper._normalize_city_key("г. Санкт-Петербург"), "санкт петербург")
        self.assertEqual(self.scraper._normalize_city_key("Санкт Петербург"), "санкт петербург")

    def test_praca_non_minsk_is_skipped_before_network(self):
        called = {"value": False}

        def fail_request(*args, **kwargs):
            called["value"] = True
            raise AssertionError("network should not be called")

        self.scraper._request = fail_request
        result = self.scraper.search_praca(
            "Python",
            "Гродно",
            {
                "queries": "Python",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "strict_salary": False,
                "schedule": "Любой",
            },
        )
        self.assertEqual(result, [])
        self.assertFalse(called["value"])

    def test_known_minsk_area_does_not_call_hh_areas_api(self):
        called = {"value": False}

        def fail_request(*args, **kwargs):
            called["value"] = True
            raise AssertionError("known fallback city must not spend an HH API request")

        self.scraper._request = fail_request
        area = self.scraper.resolve_area("Минск")
        self.assertEqual(area["id"], 1002)
        self.assertEqual(area["country"], "BY")
        self.assertFalse(called["value"])

    def test_relative_russian_date_normalization(self):
        from datetime import datetime, timedelta
        expected = (datetime.now().date() - timedelta(days=3)).isoformat()
        self.assertEqual(self.scraper._normalize_date("3 дня назад"), expected)

    def test_belmeta_viewjob_fallback_parses_current_style_card(self):
        class Response:
            text = """
            <html><body>
              <div class="vacancy-card">
                <h2><a href="/viewjob?id=123&src=js">Кладовщик-комплектовщик</a></h2>
                <div class="company">Склад Сервис</div>
                <div class="salary">От 2 500 BYN</div>
                <div class="location">Минск</div>
                <div class="date">Сегодня</div>
              </div>
            </body></html>
            """

        captured = {}
        def fake_request(url, **kwargs):
            captured["url"] = url
            return Response()

        self.scraper._request = fake_request
        result = self.scraper.search_belmeta(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "strict_salary": False,
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertIn("/вакансии/", captured["url"])
        self.assertEqual(result[0]["position"], "Кладовщик-комплектовщик")
        self.assertEqual(result[0]["company"], "Склад Сервис")
        self.assertIn("2500", result[0]["salary"].replace(" ", ""))


    def test_position_matching(self):
        self.assertTrue(self.scraper.matches_position("Python-разработчик", ["Python"]))
        self.assertTrue(self.scraper.matches_position("Junior Python Developer", ["Junior Python"]))
        self.assertFalse(self.scraper.matches_position("Бухгалтер", ["Python"]))

    def test_deduplicate_hh_and_rabota_link(self):
        rows = [
            {
                "position": "Python Developer", "salary": "Не указана",
                "company": "A", "source": "HH.ru",
                "link": "https://hh.ru/vacancy/123?from=search", "city": "Минск", "date": "2026-08-01",
            },
            {
                "position": "Python Developer", "salary": "2000 BYN",
                "company": "A", "source": "Rabota.by",
                "link": "https://rabota.by/vacancy/123", "city": "Минск", "date": "2026-08-01",
            },
        ]
        result = self.scraper.deduplicate_results(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("2000", result[0]["salary"])


    def test_salary_mode_none_disables_filter(self):
        self.assertTrue(
            self.scraper.check_salary(
                "500 BYN",
                2000,
                "BYN",
                mode="Не фильтровать",
            )
        )
        self.assertTrue(
            self.scraper.check_salary(
                "Не указана",
                2000,
                "BYN",
                mode="Не фильтровать",
            )
        )

    def test_soft_hh_search_does_not_send_salary_filter_to_api(self):
        captured = {}

        def fake_request(url, *, params=None, expect_json=False, timeout=None, **kwargs):
            captured["params"] = dict(params or {})
            return {"found": 0, "pages": 1, "items": []}

        self.scraper._request = fake_request
        params = {
            "queries": "Python",
            "exclude": "",
            "salary": "2000",
            "salary_currency": "BYN",
            "experience": "Не имеет значения",
            "schedule": "Любой",
            "period": "За неделю",
            "salary_mode": "Мягкий",
            "strict_salary": False,
        }
        self.scraper._hh_search(
            "Python",
            "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            params,
        )
        self.assertNotIn("salary", captured["params"])
        self.assertNotIn("label", captured["params"])

    def test_hh_403_uses_public_html_fallback(self):
        class Response:
            status_code = 403

        class HtmlResponse:
            url = "https://rabota.by/search/vacancy?text=кладовщик&area=1002"
            text = """
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/123">Кладовщик</a>
                <span data-qa="vacancy-serp__vacancy-compensation">от 2 300 Br за месяц</span>
                <a data-qa="vacancy-serp__vacancy-employer">Склад Тест</a>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
            </body></html>
            """

        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            if url == self.scraper.HH_API_URL:
                raise MODULE.requests.HTTPError("403", response=Response())
            return HtmlResponse()

        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        result = self.scraper._hh_search(
            "кладовщик",
            "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "experience": "Не имеет значения",
                "schedule": "Любой",
                "period": "За неделю",
                "salary_mode": "Мягкий",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "Rabota.by")
        self.assertEqual(self.scraper.get_source_diagnostics()["Rabota.by"]["status"], "fallback_success")
        self.assertTrue(any("search/vacancy" in url for url in calls))

    def test_belmeta_parses_jobdesc_and_follows_next_page(self):
        class Response:
            def __init__(self, url, text):
                self.url = url
                self.text = text

        first = Response(
            "https://belmeta.com/вакансии/Кладовщик",
            """
            <html><body>
              <div class="vacancy-card">
                <h2><a href="/jobdesc?id=1&src=js">Кладовщик</a></h2>
                <div class="company">A</div><div class="salary">2 500 BYN</div>
                <div class="location">Минск</div><div class="date">Сегодня</div>
              </div>
              <a href="/вакансии/Кладовщик?page=2">2</a>
            </body></html>
            """,
        )
        second = Response(
            "https://belmeta.com/вакансии/Кладовщик?page=2",
            """
            <html><body>
              <div class="vacancy-card">
                <h2><a href="/viewjob?id=2&src=js">Кладовщик-комплектовщик</a></h2>
                <div class="company">B</div><div class="salary">2 700 BYN</div>
                <div class="location">Минск</div><div class="date">Вчера</div>
              </div>
            </body></html>
            """,
        )
        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            return first if len(calls) == 1 else second

        self.scraper._reset_source_diagnostics(["Belmeta"])
        self.scraper._request = fake_request
        result = self.scraper.search_belmeta(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(any("jobdesc" in row["link"] for row in result))
        diag = self.scraper.get_source_diagnostics()["Belmeta"]
        self.assertEqual(diag["pages"], 2)
        self.assertEqual(diag["fetched"], 2)

    def test_praca_records_full_filter_statistics(self):
        class Response:
            url = "https://praca.by/search/vacancies/"
            text = """
            <html><body>
              <div class="vac-small__column">
                <a class="vac-small__title-link" href="/vacancy/1">Кладовщик</a>
                <div class="vac-small__salary">2 500 BYN</div>
                <div class="vac-small__customer">A</div>
              </div>
              <div class="vac-small__column">
                <a class="vac-small__title-link" href="/vacancy/2">Кладовщик</a>
                <div class="vac-small__salary">1 000 BYN</div>
                <div class="vac-small__customer">B</div>
              </div>
            </body></html>
            """

        self.scraper._reset_source_diagnostics(["Praca.by"])
        self.scraper._request = lambda *args, **kwargs: Response()
        result = self.scraper.search_praca(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "salary_mode": "Строгий",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 1)
        diag = self.scraper.get_source_diagnostics()["Praca.by"]
        self.assertEqual(diag["fetched"], 2)
        self.assertEqual(diag["filtered"]["salary"], 1)

    def test_gsz_uses_public_get_contract_and_numeric_region(self):
        class Response:
            status_code = 200

            def __init__(self, url, text):
                self.url = url
                self.text = text

        landing = Response(
            "https://gsz.gov.by/registration/vacancy-search/",
            """
            <html><body>
              <form method="get">
                <input type="text" name="profession">
                <select name="region">
                  <option value="">Все регионы</option>
                  <option value="17041">Минск</option>
                </select>
              </form>
            </body></html>
            """,
        )
        result_page = Response(
            "https://gsz.gov.by/registration/vacancy-search/?profession=кладовщик&region=17041",
            """
            <html><body><table class="table">
              <tr><th>Вакансия</th><th>Зарплата</th><th>Компания</th><th>Город</th><th>Дата</th></tr>
              <tr>
                <td><a href="/registration/employer/vacancy/55/detail-public/">Кладовщик</a></td>
                <td>2 500 BYN</td><td>ООО ГосСклад</td><td>Минск</td><td>12.08.2026</td>
              </tr>
            </table></body></html>
            """,
        )
        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            return landing if len(calls) == 1 else result_page

        self.scraper._reset_source_diagnostics(["GSZ.gov.by"])
        self.scraper._request = fake_request
        result = self.scraper.search_gsz(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "salary_mode": "Строгий",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertIs(calls[0][1].get("retry"), False)
        self.assertEqual(calls[1][1]["params"]["profession"], "кладовщик")
        self.assertEqual(calls[1][1]["params"]["region"], "17041")
        self.assertEqual(calls[1][1]["params"]["paginate_by"], "100")
        self.assertIn("/detail-public/", result[0]["link"])

    def test_rabota_406_search_endpoint_tries_seo_page(self):
        class ErrorResponse:
            status_code = 403

        class NotAcceptable:
            status_code = 406

        class HtmlResponse:
            status_code = 200
            url = "https://rabota.by/vacancies/kladovschik?area=1002"
            text = """
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/321">Кладовщик</a>
                <span data-qa="vacancy-serp__vacancy-compensation">от 2 400 Br за месяц</span>
                <a data-qa="vacancy-serp__vacancy-employer">Склад Плюс</a>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
            </body></html>
            """

        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            if url == self.scraper.HH_API_URL:
                raise MODULE.requests.HTTPError("403", response=ErrorResponse())
            if "/search/vacancy" in url:
                raise MODULE.requests.HTTPError("406", response=NotAcceptable())
            return HtmlResponse()

        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        result = self.scraper._hh_search(
            "кладовщик",
            "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "experience": "Не имеет значения",
                "schedule": "Любой",
                "period": "За 30 дней",
                "salary_mode": "Строгий",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(any("/vacancies/kladovschik" in url for url, _ in calls))
        diag = self.scraper.get_source_diagnostics()["Rabota.by"]
        self.assertEqual(diag["status"], "fallback_success")

    def test_praca_ignores_layout_columns_without_title_link(self):
        class Response:
            url = "https://praca.by/search/vacancies/"
            text = """
            <html><body>
              <div class="vac-small__column">
                <a class="vac-small__title-link" href="/vacancy/1">Кладовщик</a>
                <div class="vac-small__salary">2 500 BYN</div>
              </div>
              <div class="vac-small__column">
                <div class="vac-small__meta">служебная правая колонка карточки</div>
              </div>
            </body></html>
            """

        self.scraper._reset_source_diagnostics(["Praca.by"])
        self.scraper._request = lambda *args, **kwargs: Response()
        result = self.scraper.search_praca(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 1)
        diag = self.scraper.get_source_diagnostics()["Praca.by"]
        self.assertEqual(diag["fetched"], 1)
        self.assertEqual(diag["filtered"]["invalid"], 0)

    def test_belmeta_query_ids_are_not_collapsed_during_dedup(self):
        rows = [
            {
                "position": "Кладовщик", "salary": "2 500 BYN",
                "company": "A", "source": "Belmeta",
                "link": "https://belmeta.com/viewjob?id=101&src=js",
                "city": "Минск", "date": "",
            },
            {
                "position": "Кладовщик", "salary": "2 700 BYN",
                "company": "B", "source": "Belmeta",
                "link": "https://belmeta.com/viewjob?id=102&src=js",
                "city": "Минск", "date": "",
            },
        ]
        result = self.scraper.deduplicate_results(rows)
        self.assertEqual(len(result), 2)

    def test_numeric_vacancy_ids_do_not_mix_unrelated_sites(self):
        rows = [
            {
                "position": "Кладовщик", "salary": "2 500 BYN",
                "company": "A", "source": "Rabota.by",
                "link": "https://rabota.by/vacancy/123",
                "city": "Минск", "date": "",
            },
            {
                "position": "Кладовщик", "salary": "2 500 BYN",
                "company": "B", "source": "Praca.by",
                "link": "https://praca.by/vacancy/123",
                "city": "Минск", "date": "",
            },
        ]
        result = self.scraper.deduplicate_results(rows)
        self.assertEqual(len(result), 2)

    def test_search_status_is_partial_when_one_source_failed(self):
        self.scraper._reset_source_diagnostics(["Rabota.by", "Praca.by"])
        self.scraper._diag_error("Rabota.by", "HTTP 403")
        self.scraper._diag_finish("Praca.by", 3)
        status = self.scraper.search_status(
            [{"source": "Praca.by", "position": "X"}]
        )
        self.assertEqual(status, "partial_success")
        self.assertEqual(self.scraper.source_counts([{"source": "Praca.by"}]), {"Rabota.by": 0, "Praca.by": 1})

    def test_rabota_html_fallback_extracts_salary_from_card_text_without_salary_selector(self):
        class ApiResponse:
            status_code = 403

        class HtmlResponse:
            status_code = 200
            url = "https://rabota.by/search/vacancy?text=кладовщик&area=1002"
            text = """
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/991">Кладовщик</a>
                <div>2 325 – 2 560 Br за месяц, до вычета налогов</div>
                <a data-qa="vacancy-serp__vacancy-employer">ЗАО Тест</a>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
            </body></html>
            """

        def fake_request(url, **kwargs):
            if url == self.scraper.HH_API_URL:
                raise MODULE.requests.HTTPError("403", response=ApiResponse())
            return HtmlResponse()

        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        result = self.scraper._hh_search(
            "кладовщик", "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик", "exclude": "", "salary": "2000",
                "salary_currency": "BYN", "experience": "Не имеет значения",
                "schedule": "Любой", "period": "За 30 дней",
                "salary_mode": "Строгий",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertIn("2325", result[0]["salary"].replace(" ", ""))
        diag = self.scraper.get_source_diagnostics()["Rabota.by"]
        self.assertEqual(diag["status"], "fallback_success")
        self.assertFalse(self.scraper.source_errors())
        self.assertTrue(diag["warnings"])

    def test_rabota_fallback_with_only_filtered_rows_is_warning_not_source_error(self):
        class ApiResponse:
            status_code = 403

        class HtmlResponse:
            status_code = 200
            url = "https://rabota.by/search/vacancy?text=кладовщик&area=1002"
            text = """
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/992">Кладовщик</a>
                <div>1 500 Br за месяц</div>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
            </body></html>
            """

        def fake_request(url, **kwargs):
            if url == self.scraper.HH_API_URL:
                raise MODULE.requests.HTTPError("403", response=ApiResponse())
            return HtmlResponse()

        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        result = self.scraper._hh_search(
            "кладовщик", "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик", "exclude": "", "salary": "2000",
                "salary_currency": "BYN", "experience": "Не имеет значения",
                "schedule": "Любой", "period": "За 30 дней",
                "salary_mode": "Строгий",
            },
        )
        self.assertEqual(result, [])
        diag = self.scraper.get_source_diagnostics()["Rabota.by"]
        self.assertEqual(diag["status"], "fallback_success")
        self.assertEqual(diag["filtered"]["salary"], 1)
        self.assertEqual(len(diag["samples"]["salary"]), 1)
        self.assertFalse(self.scraper.source_errors())

    def test_belmeta_probes_alternative_pagination_when_page_parameter_repeats(self):
        class Response:
            status_code = 200
            def __init__(self, url, job_id):
                self.url = url
                self.text = f"""
                <html><body>
                  <div class="vacancy-card">
                    <h2><a href="/viewjob?id={job_id}&src=js">Кладовщик</a></h2>
                    <div class="company">Company {job_id}</div>
                    <div class="salary">2 500 BYN</div>
                    <div class="location">Минск</div>
                  </div>
                  {'<a href="/вакансии/Кладовщик?page=2">2</a>' if job_id == 1 else ''}
                </body></html>
                """

        calls = []
        def fake_request(url, **kwargs):
            calls.append(url)
            if "page=1" in url:
                return Response(url, 2)
            if "page=2" in url:
                return Response(url, 1)  # server ignored this shape
            return Response(url, 1)

        self.scraper._reset_source_diagnostics(["Belmeta"])
        self.scraper._request = fake_request
        result = self.scraper.search_belmeta(
            "кладовщик", "Минск",
            {"queries": "кладовщик", "exclude": "", "salary": "",
             "salary_currency": "BYN", "salary_mode": "Не фильтровать", "schedule": "Любой"},
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(any("page=1" in url for url in calls))
        diag = self.scraper.get_source_diagnostics()["Belmeta"]
        self.assertTrue(any("pagination alternative selected" in n for n in diag["notes"]))

    def test_gsz_retries_without_empty_optional_fields_and_can_use_wide_local_filter(self):
        class Response:
            status_code = 200
            def __init__(self, url, text):
                self.url = url
                self.text = text

        landing = Response(
            "https://gsz.gov.by/registration/vacancy-search/",
            "<html><body><form><input name='profession'></form></body></html>",
        )
        result_page = Response(
            "https://gsz.gov.by/registration/vacancy-search/?paginate_by=100",
            """<html><body><table><tr>
            <td>Кладовщик</td><td>2 500 BYN</td><td>ООО Тест</td><td>Минск</td>
            <td><a href="/registration/employer/vacancy/77/detail-public/">Кладовщик</a></td>
            </tr></table></body></html>""",
        )

        calls = []
        def fake_request(url, **kwargs):
            params = dict(kwargs.get("params") or {})
            calls.append(params)
            if len(calls) == 1:
                return landing
            if params.get("profession"):
                class ErrorResponse:
                    status_code = 500
                raise MODULE.requests.HTTPError("500", response=ErrorResponse())
            return result_page

        self.scraper._reset_source_diagnostics(["GSZ.gov.by"])
        self.scraper._request = fake_request
        result = self.scraper.search_gsz(
            "кладовщик", "Минск",
            {"queries": "кладовщик", "exclude": "", "salary": "2000",
             "salary_currency": "BYN", "salary_mode": "Строгий", "schedule": "Любой"},
        )
        self.assertEqual(len(result), 1)
        self.assertNotIn("region", calls[1])
        diag = self.scraper.get_source_diagnostics()["GSZ.gov.by"]
        self.assertTrue(diag["warnings"])
        self.assertEqual(diag["pages_detail"][0]["strategy"], "latest-wide-local-filter")


    def test_fixed_salary_with_do_vycheta_is_not_misread_as_max_only(self):
        parsed = self.scraper.parse_salary("2 000 Br за месяц, до вычета налогов")
        self.assertEqual(parsed["min"], 2000)
        self.assertIsNone(parsed["max"])
        self.assertTrue(
            self.scraper.check_salary(
                "2 000 Br за месяц, до вычета налогов", 2000, "BYN", mode="Строгий"
            )
        )

    def test_max_only_salary_is_rejected_by_strict_mode(self):
        parsed = self.scraper.parse_salary("до 3 000 BYN")
        self.assertIsNone(parsed["min"])
        self.assertEqual(parsed["max"], 3000)
        self.assertFalse(self.scraper.check_salary("до 3 000 BYN", 2000, "BYN", mode="Строгий"))
        self.assertTrue(self.scraper.check_salary("до 3 000 BYN", 2000, "BYN", mode="Мягкий"))


    def test_extract_reported_total_from_listing_text(self):
        self.assertEqual(self.scraper._extract_reported_total("1-20 из 489 вакансий"), 489)
        self.assertEqual(self.scraper._extract_reported_total("Работа кладовщиком, 171 вакансия"), 171)



    def test_gsz_preserves_source_search_marker_from_listing(self):
        candidates = self.scraper._gsz_public_link_candidates(
            "/registration/employer/vacancy/194889/detail-public/?source=search"
        )
        self.assertTrue(candidates)
        self.assertEqual(
            candidates[0],
            "https://gsz.gov.by/registration/employer/vacancy/194889/detail-public/?source=search",
        )
        self.assertIn(
            "https://gsz.gov.by/registration/employer/vacancy/194889/detail-public/",
            candidates,
        )

    def test_gsz_search_result_keeps_exact_source_marker_in_saved_link(self):
        class Response:
            status_code = 200
            def __init__(self, url, text):
                self.url = url
                self.text = text

        landing = Response(
            "https://gsz.gov.by/registration/vacancy-search/",
            "<html><body><form method='get'></form></body></html>",
        )
        page = Response(
            "https://gsz.gov.by/registration/vacancy-search/?profession=кладовщик",
            """
            <html><body><table>
            <tr><th>Вакансия</th><th>Зарплата</th><th>Город</th></tr>
            <tr>
              <td><a href="/registration/employer/vacancy/194889/detail-public/?source=search">Кладовщик</a></td>
              <td>2500 руб.</td><td>Минск</td>
            </tr>
            </table></body></html>
            """,
        )
        calls = []
        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            return landing if len(calls) == 1 else page

        self.scraper._reset_source_diagnostics(["GSZ.gov.by"])
        self.scraper._request = fake_request
        result = self.scraper.search_gsz(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "salary_mode": "Строгий",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 1)
        self.assertIn("?source=search", result[0]["link"])

    def test_gsz_resolver_tries_source_search_marker_before_route_family_fallback(self):
        class Response:
            def __init__(self, url, text, status_code=200):
                self.url = url
                self.text = text
                self.status_code = status_code

        calls = []
        def fake_request(url, **kwargs):
            calls.append(url)
            if "source=search" in url:
                return Response(url, "<html><body><h1>Кладовщик</h1></body></html>")
            return Response(url, "<html><body>Что-то пошло не так</body></html>")

        self.scraper._request = fake_request
        resolved, details = self.scraper.resolve_gsz_vacancy_link(
            "https://gsz.gov.by/registration/employer/vacancy/194889/detail-public/"
        )
        self.assertEqual(len(calls), 2)
        self.assertNotIn("source=search", calls[0])
        self.assertIn("source=search", calls[1])
        self.assertIn("source=search", resolved)
        self.assertTrue(details["corrected"])


class VacancyParserV47RegressionTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MODULE.JobScraper()

    def tearDown(self):
        self.scraper.close()

    def test_gsz_browser_link_preparation_is_local_and_preserves_search_marker(self):
        def forbidden_network(*args, **kwargs):
            raise AssertionError("browser-link preparation must not perform network I/O")

        self.scraper._request = forbidden_network
        original = (
            "https://gsz.gov.by/registration/employer/vacancy/88562/"
            "detail-public/?source=search"
        )
        prepared = self.scraper.prepare_vacancy_link_for_browser(
            original, "GSZ.gov.by"
        )
        self.assertEqual(prepared, original)
        self.assertIn("source=search", prepared)

    def test_non_gsz_browser_link_is_not_rewritten(self):
        original = "https://rabota.by/vacancy/123?from=search"
        self.assertEqual(
            self.scraper.prepare_vacancy_link_for_browser(original, "Rabota.by"),
            original,
        )


class VacancyParserV45RegressionTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MODULE.JobScraper()
        self.scraper.currency_rates = {"BYN": 1.0, "RUB": 0.035, "USD": 3.0, "EUR": 3.5}

    def tearDown(self):
        self.scraper.close()

    def test_salary_extraction_collapses_newlines_for_treeview(self):
        salary = self.scraper._extract_salary_from_text("2 390 –\n2 600 руб.")
        self.assertEqual(salary, "2 390 – 2 600 руб.")
        self.assertNotIn("\n", salary)

    def test_gsz_internal_route_is_canonicalized_to_public_detail(self):
        candidates = self.scraper._gsz_public_link_candidates(
            "/registration/employer/vacancy/245241/edit/"
        )
        self.assertEqual(
            candidates[0],
            "https://gsz.gov.by/registration/employer/vacancy/245241/detail-public/",
        )
        self.assertIn(
            "https://gsz.gov.by/registration/employer/vacancy/create-future/245241/detail-public/",
            candidates,
        )

    def test_gsz_create_future_route_is_preserved_first(self):
        candidates = self.scraper._gsz_public_link_candidates(
            "/registration/employer/vacancy/create-future/22563/edit/"
        )
        self.assertEqual(
            candidates[0],
            "https://gsz.gov.by/registration/employer/vacancy/create-future/22563/detail-public/",
        )

    def test_gsz_resolver_tries_alternate_public_route_when_first_is_error_page(self):
        class Response:
            def __init__(self, url, text, status_code=200):
                self.url = url
                self.text = text
                self.status_code = status_code

        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            if "/vacancy/245241/detail-public/" in url and "create-future" not in url:
                return Response(url, "<html><body>Что-то пошло не так</body></html>")
            return Response(url, "<html><body><h1>Грузчик</h1></body></html>")

        self.scraper._request = fake_request
        resolved, details = self.scraper.resolve_gsz_vacancy_link(
            "https://gsz.gov.by/registration/employer/vacancy/245241/detail-public/"
        )
        self.assertIn("/create-future/245241/detail-public/", resolved)
        self.assertEqual(len(calls), 3)
        self.assertIn("source=search", calls[1])
        self.assertIn("/create-future/245241/detail-public/", calls[2])
        self.assertTrue(details["corrected"])

    def test_gsz_search_converts_service_link_before_returning_result(self):
        class Response:
            status_code = 200

            def __init__(self, url, text):
                self.url = url
                self.text = text

        landing = Response(
            "https://gsz.gov.by/registration/vacancy-search/",
            """
            <html><body><select name="region"><option value="17041">Минск</option></select></body></html>
            """,
        )
        result_page = Response(
            "https://gsz.gov.by/registration/vacancy-search/?profession=грузчик&region=17041",
            """
            <html><body><table>
              <tr><th>Профессия</th><th>Заработная плата</th><th>Наниматель</th><th>Город</th></tr>
              <tr>
                <td><a href="/registration/employer/vacancy/245241/edit/">Грузчик</a></td>
                <td>2 390 –\n2 600 руб.</td><td>ООО Склад</td><td>Минск</td>
              </tr>
            </table></body></html>
            """,
        )
        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            return landing if len(calls) == 1 else result_page

        self.scraper._reset_source_diagnostics(["GSZ.gov.by"])
        self.scraper._request = fake_request
        rows = self.scraper.search_gsz(
            "грузчик",
            "Минск",
            {
                "queries": "грузчик",
                "exclude": "",
                "salary": "2000",
                "salary_currency": "BYN",
                "salary_mode": "Строгий",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["salary"], "2 390 – 2 600 руб.")
        self.assertEqual(rows[0]["company"], "ООО Склад")
        self.assertTrue(rows[0]["link"].endswith("/vacancy/245241/detail-public/"))

class VacancyParserV48RegressionTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MODULE.JobScraper()
        self.scraper.currency_rates = {
            "BYN": 1.0,
            "USD": 3.0,
            "EUR": 3.5,
            "RUB": 0.035,
        }

    def tearDown(self):
        self.scraper.close()

    def test_gsz_company_fallback_extracts_employer_from_card_text(self):
        company = self.scraper._extract_gsz_company_from_card_text(
            'Кладовщик 1300 – 1450 руб. ООО "Экокор групп" '
            'Ставка: 1,0 Общее базовое г. Минск, Панфилова, 3',
            title="Кладовщик",
            salary="1300 – 1450 руб.",
        )
        self.assertEqual(company, 'ООО "Экокор групп"')

    def test_gsz_company_fallback_supports_complex_legal_name(self):
        company = self.scraper._extract_gsz_company_from_card_text(
            'Кладовщик 1000 – 1460 руб. Филиал "Вендорож" РУП "Могилевэнерго" '
            'Ставка: 1,0 Среднее специальное р-н Могилевский',
            title="Кладовщик",
            salary="1000 – 1460 руб.",
        )
        self.assertEqual(company, 'Филиал "Вендорож" РУП "Могилевэнерго"')

    def test_pagination_discovery_finds_arrow_and_data_url(self):
        soup = MODULE.BeautifulSoup(
            """
            <html><body>
              <nav class="pagination">
                <a href="/vacancies/kladovschik?p=2" aria-label="Следующая">›</a>
              </nav>
              <button data-url="/vacancies/kladovschik?p=3" title="Следующая"></button>
            </body></html>
            """,
            "html.parser",
        )
        urls = self.scraper._discover_pagination_urls(
            soup,
            "https://belmeta.com/vacancies/kladovschik",
            2,
            base_url="https://belmeta.com/vacancies/kladovschik",
        )
        self.assertTrue(urls)
        self.assertEqual(urls[0], "https://belmeta.com/vacancies/kladovschik?p=2")

    def test_belmeta_follows_site_exposed_next_arrow(self):
        class Response:
            status_code = 200

            def __init__(self, url, job_id, next_href=None):
                self.url = url
                next_link = (
                    f'<a class="next" aria-label="Следующая" href="{next_href}">›</a>'
                    if next_href
                    else ""
                )
                self.text = f"""
                <html><body>
                  <div class="vacancy-card">
                    <h2><a href="/viewjob?id={job_id}">Кладовщик</a></h2>
                    <div class="company">Company {job_id}</div>
                    <div class="salary">2 500 BYN</div>
                    <div class="location">Минск</div>
                  </div>
                  <nav class="pagination">{next_link}</nav>
                </body></html>
                """

        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            if "cursor=abc" in url:
                return Response(url, 2)
            return Response(
                url,
                1,
                "/вакансии/кладовщик?cursor=abc",
            )

        self.scraper._reset_source_diagnostics(["Belmeta"])
        self.scraper._request = fake_request
        result = self.scraper.search_belmeta(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(any("cursor=abc" in url for url in calls))
        diag = self.scraper.get_source_diagnostics()["Belmeta"]
        self.assertTrue(
            any("pagination URL discovered from Belmeta HTML" in note for note in diag["notes"])
        )

    def test_rabota_search_stall_continues_with_seo_listing(self):
        class Response:
            status_code = 200

            def __init__(self, url, text):
                self.url = url
                self.text = text

        def card(vacancy_id, salary="2 500 Br", next_href=""):
            next_link = (
                f'<a rel="next" href="{next_href}">Следующая</a>'
                if next_href
                else ""
            )
            return f"""
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/{vacancy_id}">Кладовщик</a>
                <span data-qa="vacancy-serp__vacancy-compensation">{salary}</span>
                <span data-qa="vacancy-serp__vacancy-employer">Склад {vacancy_id}</span>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
              {next_link}
            </body></html>
            """

        calls = []
        self.scraper.MAX_HH_HTML_PAGES = 3

        def fake_request(url, **kwargs):
            params = dict(kwargs.get("params") or {})
            url_query = dict(
                MODULE.urllib.parse.parse_qsl(
                    MODULE.urllib.parse.urlsplit(url).query,
                    keep_blank_values=True,
                )
            )
            effective = {**url_query, **params}
            calls.append((url, effective))
            if "/vacancies/kladovschik" in url:
                local_page = int(effective.get("page", 0))
                if local_page == 0:
                    return Response(url, card(2))
                return Response(url, "<html><body>Конец выдачи</body></html>")
            page = int(effective.get("page", 0))
            if page == 0:
                return Response(
                    url,
                    card(1, next_href="/search/vacancy?page=1"),
                )
            return Response(
                "https://rabota.by/search/vacancy?page=1",
                "<html><body><h1>Работа кладовщиком, 496 вакансий</h1></body></html>",
            )

        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        rows = self.scraper._hh_html_search(
            "кладовщик",
            "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
                "period": "За 30 дней",
            },
            "Rabota.by",
            "rabota.by",
        )
        self.assertEqual({row["link"] for row in rows}, {
            "https://rabota.by/vacancy/1",
            "https://rabota.by/vacancy/2",
        })
        self.assertTrue(any("/vacancies/kladovschik" in url for url, _ in calls))
        diag = self.scraper.get_source_diagnostics()["Rabota.by"]
        self.assertTrue(
            any("secondary SEO listing started" in note for note in diag["notes"])
        )

    def test_gsz_search_recovers_company_from_card_text_without_headers(self):
        class Response:
            status_code = 200

            def __init__(self, url, text):
                self.url = url
                self.text = text

        landing = Response(
            "https://gsz.gov.by/registration/vacancy-search/",
            "<html><body><select name='region'><option value='17041'>Минск</option></select></body></html>",
        )
        page = Response(
            "https://gsz.gov.by/registration/vacancy-search/?profession=кладовщик&region=17041",
            """
            <html><body><table>
              <tr>
                <td>
                  <a href="/registration/employer/vacancy/228541/detail-public/?source=search">
                    Кладовщик
                  </a>
                </td>
                <td>1300 – 1450 руб.</td>
                <td>ООО "Экокор групп"</td>
                <td>Ставка: 1,0</td>
                <td>г. Минск, Панфилова, 3</td>
              </tr>
            </table></body></html>
            """,
        )
        calls = []

        def fake_request(url, **kwargs):
            calls.append((url, kwargs))
            return landing if len(calls) == 1 else page

        self.scraper._reset_source_diagnostics(["GSZ.gov.by"])
        self.scraper._request = fake_request
        rows = self.scraper.search_gsz(
            "кладовщик",
            "Минск",
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["company"], 'ООО "Экокор групп"')


class VacancyParserV49RegressionTests(unittest.TestCase):
    def setUp(self):
        self.scraper = MODULE.JobScraper()
        self.scraper.currency_rates = {
            "BYN": 1.0,
            "USD": 3.0,
            "EUR": 3.5,
            "RUB": 0.035,
        }

    def tearDown(self):
        self.scraper.close()

    def test_belmeta_pagination_prefers_query_preserving_page_link(self):
        candidates = [
            "https://belmeta.com/vacansii",
            "https://belmeta.com/vacansii?q=%D0%9A%D0%BB%D0%B0%D0%B4%D0%BE%D0%B2%D1%89%D0%B8%D0%BA&page=2",
            "https://belmeta.com/vacansii?q=%D0%9A%D0%BB%D0%B0%D0%B4%D0%BE%D0%B2%D1%89%D0%B8%D0%BA&df=1",
        ]
        ranked = self.scraper._rank_pagination_candidates(
            candidates,
            query_text="Кладовщик",
            current_url="https://belmeta.com/вакансии/Кладовщик",
            base_url="https://belmeta.com/вакансии/Кладовщик",
        )
        self.assertIn("q=", ranked[0])
        self.assertIn("page=2", ranked[0])
        self.assertNotEqual(ranked[0], "https://belmeta.com/vacansii")

    def test_belmeta_search_does_not_switch_to_generic_feed(self):
        class Response:
            status_code = 200

            def __init__(self, url, job_id, next_links=""):
                self.url = url
                self.text = f"""
                <html><body>
                  <div class="vacancy-card">
                    <h2><a href="/viewjob?id={job_id}">Кладовщик</a></h2>
                    <div class="company">Склад {job_id}</div>
                    <div class="salary">2 500 BYN</div>
                    <div class="location">Минск</div>
                  </div>
                  <nav class="pagination">{next_links}</nav>
                </body></html>
                """

        calls = []

        def fake_request(url, **kwargs):
            calls.append(url)
            if "page=2" in url and "q=" in url:
                return Response(url, 2)
            return Response(
                url,
                1,
                """
                <a rel="next" href="/vacansii">Следующая</a>
                <a href="/vacansii?q=Кладовщик&page=2">2</a>
                """,
            )

        self.scraper.MAX_BELMETA_PAGES = 2
        self.scraper._reset_source_diagnostics(["Belmeta"])
        self.scraper._request = fake_request
        rows = self.scraper.search_belmeta(
            "Кладовщик",
            "Минск",
            {
                "queries": "Кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
            },
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(any("q=" in url and "page=2" in url for url in calls))
        self.assertFalse(any(url == "https://belmeta.com/vacansii" for url in calls[1:]))

    def test_rabota_company_is_recovered_when_data_qa_is_missing(self):
        card = MODULE.BeautifulSoup(
            """
            <div>
              Сейчас смотрят 3 человека
              <a href="/vacancy/123">Кладовщик SELA</a>
              <span>2 500 Br за месяц</span>
              Опыт 1-3 года
              <span>ООО Фэшн Бизнес</span>
              <span>Минск</span>
              Откликнуться
            </div>
            """,
            "html.parser",
        ).div
        company = self.scraper._extract_hh_company_from_card(
            card,
            title="Кладовщик SELA",
            salary="2 500 Br за месяц",
            city="Минск",
        )
        self.assertEqual(company, "ООО Фэшн Бизнес")

    def test_rabota_secondary_seo_stops_on_generic_redirect(self):
        class Response:
            status_code = 200

            def __init__(self, url, text):
                self.url = url
                self.text = text

        def one_card(vacancy_id):
            return f"""
            <html><body>
              <div data-qa="vacancy-serp__vacancy">
                <a data-qa="serp-item__title" href="/vacancy/{vacancy_id}">Кладовщик</a>
                <span data-qa="vacancy-serp__vacancy-compensation">2 500 Br</span>
                <span data-qa="vacancy-serp__vacancy-employer">Склад</span>
                <span data-qa="vacancy-serp__vacancy-address">Минск</span>
              </div>
            </body></html>
            """

        calls = []

        def fake_request(url, **kwargs):
            params = dict(kwargs.get("params") or {})
            url_query = dict(
                MODULE.urllib.parse.parse_qsl(
                    MODULE.urllib.parse.urlsplit(url).query,
                    keep_blank_values=True,
                )
            )
            effective = {**url_query, **params}
            calls.append((url, effective))
            if "/vacancies/kladovschik" in url:
                return Response(
                    "https://rabota.by/vacancies",
                    one_card(999),
                )
            page = int(effective.get("page", 0))
            if page == 0:
                return Response(
                    url,
                    one_card(1) + '<a rel="next" href="/search/vacancy?page=1">Следующая</a>',
                )
            return Response(
                "https://rabota.by/search/vacancy?page=1",
                "<html><body>Нет распознаваемых карточек</body></html>",
            )

        self.scraper.MAX_HH_HTML_PAGES = 10
        self.scraper._reset_source_diagnostics(["Rabota.by"])
        self.scraper._request = fake_request
        rows = self.scraper._hh_html_search(
            "кладовщик",
            "Минск",
            {"id": 1002, "country": "BY", "name": "Минск"},
            {
                "queries": "кладовщик",
                "exclude": "",
                "salary": "",
                "salary_currency": "BYN",
                "salary_mode": "Не фильтровать",
                "schedule": "Любой",
                "period": "За 30 дней",
            },
            "Rabota.by",
            "rabota.by",
        )
        self.assertEqual([row["link"] for row in rows], ["https://rabota.by/vacancy/1"])
        seo_calls = [url for url, _ in calls if "/vacancies/kladovschik" in url]
        self.assertEqual(len(seo_calls), 1)
        diag = self.scraper.get_source_diagnostics()["Rabota.by"]
        self.assertTrue(
            any("generic vacancies page" in warning for warning in diag["warnings"])
        )

    def test_gsz_location_discovery_accepts_changed_region_control_id(self):
        soup = MODULE.BeautifulSoup(
            """
            <html><body>
              <select id="vacancy_region_filter" name="geo">
                <option value="">Все регионы</option>
                <option value="17041">г. Минск</option>
              </select>
            </body></html>
            """,
            "html.parser",
        )
        fields, details = self.scraper._discover_gsz_location_fields(soup, "Минск")
        self.assertEqual(fields, {"region": "17041"})
        self.assertTrue(details)
        self.assertTrue(details[0]["numeric_match"])


if __name__ == "__main__":
    unittest.main()

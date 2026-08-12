import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from problem_logging import SearchProblemLogger


class ProblemLoggingTests(unittest.TestCase):
    def test_each_search_gets_separate_session_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "Логи проблем"
            logger = SearchProblemLogger(root, "Vacancy Parser Pro", "4.1", keep_sessions=5)

            first = logger.start_session({"queries": "Python", "city": "Минск", "enabled_sites": ["Belmeta"]})
            logger.append("[10:00:00] first")
            logger.finalize(status="success", result_count=2, error=None, cancelled=False, source_counts={"Belmeta": 2})

            second = logger.start_session({"queries": "Кладовщик", "city": "Минск", "enabled_sites": ["Praca.by"]})
            logger.append("[10:01:00] second")
            logger.finalize(status="no_results", result_count=0, error=None, cancelled=False, source_counts={})

            self.assertEqual(first.parent, root)
            self.assertEqual(second.parent, root)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())

            expected = {
                "00_прочитать_нейросети_сначала.txt",
                "01_лог_поиска.log",
                "02_параметры_поиска.json",
                "03_итог.json",
                "04_диагностика_источников.json",
                "05_проверка_ссылок.jsonl",
                "06_итог_проверки_ссылок.txt",
            }
            self.assertEqual({p.name for p in first.iterdir()}, expected)
            self.assertEqual({p.name for p in second.iterdir()}, expected)

            summary = json.loads((first / "03_итог.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["result_count"], 2)
            self.assertEqual(summary["source_counts"], {"Belmeta": 2})
            diagnostics = json.loads((first / "04_диагностика_источников.json").read_text(encoding="utf-8"))
            self.assertTrue(diagnostics["generated_for_ai"])
            self.assertIn("Belmeta", diagnostics["sources"])


    def test_summary_keeps_zero_sources_errors_and_partial_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "Логи проблем"
            logger = SearchProblemLogger(root, "Vacancy Parser Pro", "4.2", keep_sessions=5)
            folder = logger.start_session({
                "queries": "Кладовщик",
                "city": "Минск",
                "salary": "2000",
                "salary_currency": "BYN",
                "salary_mode": "Мягкий",
                "enabled_sites": ["Rabota.by", "Praca.by", "GSZ.gov.by"],
            })
            logger.finalize(
                status="partial_success",
                result_count=5,
                error=None,
                cancelled=False,
                requested_sources=["Rabota.by", "Praca.by", "GSZ.gov.by"],
                source_counts={"Praca.by": 5},
                source_errors={"Rabota.by": "HTTP 403", "GSZ.gov.by": "HTTP 500"},
                source_stats={
                    "Rabota.by": {"status": "error", "fetched": 0, "pages": 0},
                    "Praca.by": {"status": "success", "fetched": 20, "pages": 1},
                    "GSZ.gov.by": {"status": "error", "fetched": 0, "pages": 0},
                },
            )
            summary = json.loads((folder / "03_итог.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "partial_success")
            self.assertEqual(
                summary["source_counts"],
                {"Rabota.by": 0, "Praca.by": 5, "GSZ.gov.by": 0},
            )
            self.assertEqual(summary["source_errors"]["Rabota.by"], "HTTP 403")
            readme = (folder / "00_прочитать_нейросети_сначала.txt").read_text(encoding="utf-8")
            self.assertIn("режим зарплаты: Мягкий", readme)
            self.assertIn("Rabota.by: 0", readme)
            self.assertIn("ОШИБКА=HTTP 403", readme)


    def test_link_summary_detects_repeated_same_vacancy(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            logger = SearchProblemLogger(pathlib.Path(td) / "Логи проблем", "Vacancy Parser Pro", "4.6")
            session = logger.start_session({"enabled_sites": ["GSZ.gov.by"], "queries": "кладовщик"})
            payload = {
                "source": "GSZ.gov.by",
                "original": "https://gsz.gov.by/registration/employer/vacancy/1/detail-public/?source=search",
                "action": "open_unverified_detail_in_browser",
            }
            logger.append_link_check(payload)
            logger.append_link_check(payload)
            summary = (session / "06_итог_проверки_ссылок.txt").read_text(encoding="utf-8")
            self.assertIn("повторно", summary.lower())
            self.assertIn("2 раз", summary)


class VacancyParserV47LinkLoggingTests(unittest.TestCase):
    def test_direct_gsz_open_summary_records_no_preflight_and_dispatch_time(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            logger = SearchProblemLogger(
                pathlib.Path(td) / "Логи проблем",
                "Vacancy Parser Pro",
                "4.7",
            )
            session = logger.start_session({
                "enabled_sites": ["GSZ.gov.by"],
                "queries": "кладовщик",
            })
            logger.append_link_check({
                "source": "GSZ.gov.by",
                "position": "Кладовщик",
                "original": "https://gsz.gov.by/registration/employer/vacancy/1/detail-public/?source=search",
                "prepared": "https://gsz.gov.by/registration/employer/vacancy/1/detail-public/?source=search",
                "preflight_skipped": True,
                "open_call_ms": 12.5,
                "action": "open_direct_detail",
            })
            summary = (session / "06_итог_проверки_ссылок.txt").read_text(encoding="utf-8")
            self.assertIn("open_direct_detail=1", summary)
            self.assertIn("без HTTP-preflight", summary)
            self.assertIn("12.5", summary)


class LinkCheckLoggingTests(unittest.TestCase):
    def test_link_check_is_written_to_session_jsonl(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as td:
            logger = SearchProblemLogger(pathlib.Path(td) / "Логи проблем", "Vacancy Parser Pro", "4.5")
            session = logger.start_session({"enabled_sites": ["GSZ.gov.by"], "queries": "грузчик"})
            logger.append_link_check({
                "source": "GSZ.gov.by",
                "original": "https://gsz.gov.by/registration/employer/vacancy/1/detail-public/",
                "resolved": "https://gsz.gov.by/registration/employer/vacancy/create-future/1/detail-public/",
                "action": "open_resolved_detail",
            })
            path = session / "05_проверка_ссылок.jsonl"
            text = path.read_text(encoding="utf-8")
            self.assertIn("GSZ.gov.by", text)
            self.assertIn("open_resolved_detail", text)
            summary = (session / "06_итог_проверки_ссылок.txt").read_text(encoding="utf-8")
            self.assertIn("Всего событий: 1", summary)
            self.assertIn("open_resolved_detail=1", summary)


if __name__ == "__main__":
    unittest.main()

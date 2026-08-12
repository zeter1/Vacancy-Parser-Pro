from __future__ import annotations

import json
import os
import platform
import shutil
import ssl
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class SearchProblemLogger:
    """Компактные диагностические логи: одна папка на одну сессию поиска."""

    def __init__(self, base_dir: Path, app_name: str, app_version: str, keep_sessions: int = 15):
        self.base_dir = Path(base_dir)
        self.app_name = app_name
        self.app_version = app_version
        self.keep_sessions = max(3, int(keep_sessions))
        self._lock = threading.RLock()
        self.session_dir: Path | None = None
        self.log_path: Path | None = None
        self.params_path: Path | None = None
        self.summary_path: Path | None = None
        self.diagnostics_path: Path | None = None
        self.link_checks_path: Path | None = None
        self.link_summary_path: Path | None = None
        self.readme_path: Path | None = None
        self.session_id: str | None = None
        self.started_at: datetime | None = None
        self._params: dict[str, Any] = {}

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): SearchProblemLogger._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [SearchProblemLogger._json_safe(v) for v in value]
        return str(value)

    def _ensure_root(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _unique_session_dir(self, started_at: datetime) -> Path:
        base_name = started_at.strftime("%Y-%m-%d_%H-%M-%S")
        candidate = self.base_dir / base_name
        counter = 2
        while candidate.exists():
            candidate = self.base_dir / f"{base_name}_{counter}"
            counter += 1
        return candidate

    @staticmethod
    def _runtime_versions() -> dict[str, str]:
        versions: dict[str, str] = {}
        try:
            from importlib.metadata import PackageNotFoundError, version
            for package in ("requests", "urllib3", "beautifulsoup4", "pandas", "openpyxl", "certifi"):
                try:
                    versions[package] = version(package)
                except PackageNotFoundError:
                    versions[package] = "not-installed"
        except Exception:
            pass
        return versions

    def start_session(self, params: dict[str, Any]) -> Path:
        """Создать отдельную папку для нового поиска и записать стартовую диагностику."""
        with self._lock:
            # Не даём новому поиску случайно дописывать в предыдущую сессию,
            # даже если создание новой папки завершится ошибкой.
            self.session_dir = None
            self.log_path = None
            self.params_path = None
            self.summary_path = None
            self.diagnostics_path = None
            self.link_checks_path = None
            self.link_summary_path = None
            self.readme_path = None
            self.session_id = None
            self.started_at = None
            self._params = {}

            self._ensure_root()
            self.started_at = datetime.now()
            self.session_dir = self._unique_session_dir(self.started_at)
            self.session_dir.mkdir(parents=True, exist_ok=False)
            self.session_id = self.session_dir.name
            self.log_path = self.session_dir / "01_лог_поиска.log"
            self.params_path = self.session_dir / "02_параметры_поиска.json"
            self.summary_path = self.session_dir / "03_итог.json"
            self.diagnostics_path = self.session_dir / "04_диагностика_источников.json"
            self.link_checks_path = self.session_dir / "05_проверка_ссылок.jsonl"
            self.link_summary_path = self.session_dir / "06_итог_проверки_ссылок.txt"
            self.readme_path = self.session_dir / "00_прочитать_нейросети_сначала.txt"
            self._params = self._json_safe(dict(params or {}))

            payload = {
                "session_id": self.session_id,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "app": self.app_name,
                "version": self.app_version,
                "params": self._params,
                "environment": {
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                    "executable": sys.executable,
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "pid": os.getpid(),
                    "openssl": getattr(ssl, "OPENSSL_VERSION", ""),
                    "packages": self._runtime_versions(),
                    # Never write token/proxy values themselves. Presence is
                    # enough to diagnose why network behaviour differs.
                    "env_flags": {
                        "HH_API_TOKEN_set": bool(os.environ.get("HH_API_TOKEN")),
                        "HH_USER_AGENT_set": bool(os.environ.get("HH_USER_AGENT")),
                        "HTTP_PROXY_set": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
                        "HTTPS_PROXY_set": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
                    },
                },
            }
            self.params_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.log_path.write_text("", encoding="utf-8")
            if self.link_checks_path is not None:
                self.link_checks_path.write_text("", encoding="utf-8")
            if self.link_summary_path is not None:
                self.link_summary_path.write_text(
                    "Проверки ссылок ещё не выполнялись.\n",
                    encoding="utf-8",
                )
            self._write_readme(status="running", result_count=0, error=None, cancelled=False)
            self.cleanup_old_sessions(exclude=self.session_dir)
            return self.session_dir

    def append(self, line: str) -> None:
        with self._lock:
            if not self.log_path:
                return
            try:
                with self.log_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(str(line).rstrip("\r\n") + "\n")
            except OSError:
                # Логирование не должно ломать сам поиск.
                return

    def append_link_check(self, payload: dict[str, Any]) -> None:
        """Append one post-search vacancy-link validation event.

        The file intentionally lives in the same search-session folder so a
        later broken-link report can be diagnosed together with the exact
        source/search diagnostics that produced that row.
        """
        with self._lock:
            if not self.link_checks_path:
                return
            event = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                **self._json_safe(dict(payload or {})),
            }
            try:
                with self.link_checks_path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                self._rewrite_link_check_summary()
            except OSError:
                return

    def _rewrite_link_check_summary(self) -> None:
        """Rewrite a compact human/AI summary of post-search link checks."""
        if not self.link_checks_path or not self.link_summary_path:
            return
        events = []
        try:
            for line in self.link_checks_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    events.append(payload)
        except OSError:
            return

        if not events:
            text = "Проверки ссылок ещё не выполнялись.\n"
        else:
            action_counts: dict[str, int] = {}
            for event in events:
                action = str(event.get("action") or "unknown")
                action_counts[action] = action_counts.get(action, 0) + 1

            findings = []
            if action_counts.get("open_search_fallback", 0) or action_counts.get("open_search_fallback_no_vacancy_id", 0):
                findings.append(
                    "Есть переходы на общий поиск GSZ: смотреть original/candidates/attempts — "
                    "это означает, что точная карточка не была подтверждена."
                )
            if action_counts.get("open_unverified_detail_in_browser", 0):
                findings.append(
                    "Фоновая HTTP-проверка GSZ не подтвердила карточку, но браузеру передана точная "
                    "ссылка из поисковой выдачи; сравнить browser_candidate с raw_href/source=search."
                )
            if action_counts.get("open_direct_detail", 0):
                findings.append(
                    "GSZ открыт напрямую без HTTP-preflight. Это штатный быстрый путь: "
                    "requests-проверка намеренно исключена из критического пути открытия."
                )

            # Detect repeated actions for the same vacancy in one session. This
            # is useful for diagnosing accidental double-click/re-entry.
            by_original: dict[str, int] = {}
            for event in events:
                original = str(event.get("original") or "")
                if original:
                    by_original[original] = by_original.get(original, 0) + 1
            repeated = sorted(
                ((url, count) for url, count in by_original.items() if count > 1),
                key=lambda item: item[1],
                reverse=True,
            )
            if repeated:
                findings.append(
                    "Одна и та же ссылка проверялась повторно в этой сессии: возможен двойной клик "
                    "или параллельный запуск открытия вакансии."
                )

            direct_open_ms = []
            for event in events:
                if event.get("action") == "open_direct_detail":
                    try:
                        direct_open_ms.append(float(event.get("open_call_ms")))
                    except (TypeError, ValueError):
                        pass

            lines = [
                "ИТОГ ПРОВЕРКИ ССЫЛОК VACANCY PARSER PRO",
                "",
                f"Сессия: {self.session_id or 'неизвестно'}",
                f"Всего событий: {len(events)}",
                "Действия: " + ", ".join(f"{k}={v}" for k, v in sorted(action_counts.items())),
                "",
                "Автоматические выводы:",
            ]
            if direct_open_ms:
                lines.append(
                    f"- Прямой вызов браузера GSZ: среднее {sum(direct_open_ms) / len(direct_open_ms):.1f} мс, "
                    f"максимум {max(direct_open_ms):.1f} мс. Это время передачи URL браузеру, не загрузки сайта."
                )
            if findings:
                lines.extend(f"- {item}" for item in findings)
            else:
                lines.append("- Явных проблем по зарегистрированным открытиям ссылок не обнаружено.")

            if repeated:
                lines.append("")
                lines.append("Повторно проверенные ссылки:")
                for url, count in repeated[:10]:
                    lines.append(f"- {count} раз: {url}")

            lines.append("")
            lines.append("Последние события:")
            for event in events[-10:]:
                lines.append(
                    "- "
                    + json.dumps(
                        {
                            "timestamp": event.get("timestamp"),
                            "source": event.get("source"),
                            "position": event.get("position"),
                            "action": event.get("action"),
                            "original": event.get("original"),
                            "resolved": event.get("resolved"),
                            "browser_candidate": event.get("browser_candidate"),
                            "prepared": event.get("prepared"),
                            "preflight_skipped": event.get("preflight_skipped"),
                            "open_call_ms": event.get("open_call_ms"),
                            "reason": event.get("reason"),
                        },
                        ensure_ascii=False,
                    )
                )
            text = "\n".join(lines) + "\n"

        tmp = self.link_summary_path.with_suffix(self.link_summary_path.suffix + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, self.link_summary_path)
        except OSError:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    @staticmethod
    def _source_diagnosis(source: str, stat: dict[str, Any], count: int, error_text: str | None) -> list[str]:
        """Generate compact machine-friendly hypotheses from collected evidence."""
        findings: list[str] = []
        fetched = int(stat.get("fetched", 0) or 0)
        accepted = int(stat.get("accepted", count) or 0)
        attempts = int(stat.get("attempts", 0) or 0)
        pages = int(stat.get("pages", 0) or 0)
        filtered = stat.get("filtered") if isinstance(stat.get("filtered"), dict) else {}
        warnings = stat.get("warnings") if isinstance(stat.get("warnings"), list) else []

        if error_text:
            if fetched == 0:
                findings.append("Источник не дошёл до карточек вакансий: сначала проверять HTTP/TLS/URL/форму сайта.")
            else:
                findings.append("Часть данных получена, но источник завершён ошибкой: проверять fallback/статус, а не считать сайт полностью недоступным.")

        if attempts and pages == 0 and fetched == 0:
            findings.append("Есть сетевые попытки, но нет обработанных страниц — сбой происходит до разбора выдачи.")

        reported_total = stat.get("reported_total")
        try:
            reported_total = int(reported_total) if reported_total is not None else None
        except (TypeError, ValueError):
            reported_total = None
        if reported_total and reported_total > fetched:
            findings.append(
                f"На странице найден счётчик около {reported_total} вакансий, а парсер обработал {fetched}. "
                "Счётчик может относиться как к текущей выдаче, так и ко всему сайту; сверить pages_detail "
                "и предупреждения пагинации перед выводом о потере результатов."
            )

        if fetched > 0:
            salary_dropped = int(filtered.get("salary", 0) or 0)
            position_dropped = int(filtered.get("position", 0) or 0)
            city_dropped = int(filtered.get("city", 0) or 0)
            duplicate_dropped = int(filtered.get("duplicate_on_source", 0) or 0)
            if salary_dropped / max(1, fetched) >= 0.60:
                findings.append(
                    f"Зарплатный фильтр отбросил {salary_dropped}/{fetched} кандидатов (>=60%): проверить samples.salary и извлечение raw_salary."
                )
            if position_dropped / max(1, fetched) >= 0.60:
                findings.append(
                    f"Фильтр названия отбросил {position_dropped}/{fetched} кандидатов (>=60%): проверить релевантность поисковой выдачи и matches_position."
                )
            if city_dropped / max(1, fetched) >= 0.50:
                findings.append(
                    f"Фильтр города отбросил {city_dropped}/{fetched} кандидатов (>=50%): проверить серверный фильтр города и разбор адреса."
                )
            if duplicate_dropped / max(1, fetched) >= 0.40:
                findings.append(
                    f"Дубликаты составили {duplicate_dropped}/{fetched} кандидатов (>=40%): вероятно повторяется страница пагинации или неверен ключ вакансии."
                )
            if accepted == 0 and not findings:
                findings.append("Карточки получены, но ничего не принято: смотреть filtered и samples по причинам отсева.")

        samples = stat.get("samples") if isinstance(stat.get("samples"), dict) else {}
        accepted_samples = samples.get("accepted") if isinstance(samples.get("accepted"), list) else []
        if len(accepted_samples) >= 3:
            missing_company = 0
            for sample in accepted_samples:
                company = str(sample.get("company") or "").strip().lower() if isinstance(sample, dict) else ""
                if company in {"", "не указана", "н/д", "нет данных", "неизвестно"}:
                    missing_company += 1
            if missing_company / max(1, len(accepted_samples)) >= 0.80:
                findings.append(
                    f"В {missing_company}/{len(accepted_samples)} сохранённых принятых примеров не определён работодатель: "
                    "проверить структуру карточки/колонки компании и samples.accepted."
                )

        request_errors = samples.get("request_error") if isinstance(samples.get("request_error"), list) else []
        if request_errors:
            first = request_errors[0] if isinstance(request_errors[0], dict) else {}
            http_status = first.get("http_status")
            stage = first.get("stage") or "network request"
            if http_status:
                findings.append(
                    f"Есть сохранённый HTTP-сбой на этапе {stage} (HTTP {http_status}); смотреть samples.request_error: URL, Content-Type и короткий ответ сервера."
                )
            else:
                findings.append(
                    f"Есть сохранённый сетевой сбой на этапе {stage}; смотреть samples.request_error для типа ошибки и URL."
                )

        status = str(stat.get("status") or "")
        if status == "fallback_success":
            findings.append("Основной API не сработал, но публичный HTML fallback успешно обработал источник; это предупреждение, а не полный отказ сайта.")
        if warnings:
            findings.append("Есть предупреждения источника: " + " | ".join(str(x) for x in warnings[:3]))
        return findings[:8]

    def _build_diagnostics_payload(
        self,
        *,
        requested: list[str],
        counts: dict[str, int],
        errors: dict[str, str],
        stats: dict[str, Any],
    ) -> dict[str, Any]:
        sources = {}
        for source in requested or sorted(set(counts) | set(stats)):
            stat = stats.get(source) if isinstance(stats.get(source), dict) else {}
            source_payload = dict(stat)
            source_payload["result_count"] = int(counts.get(source, 0) or 0)
            source_payload["error"] = errors.get(source) or source_payload.get("error")
            source_payload["ai_diagnosis"] = self._source_diagnosis(
                source, source_payload, source_payload["result_count"], errors.get(source)
            )
            sources[source] = self._json_safe(source_payload)
        return {
            "session_id": self.session_id,
            "generated_for_ai": True,
            "sources": sources,
            "reading_order": [
                "00_прочитать_нейросети_сначала.txt",
                "04_диагностика_источников.json",
                "05_проверка_ссылок.jsonl",
                "06_итог_проверки_ссылок.txt",
                "03_итог.json",
                "01_лог_поиска.log",
                "02_параметры_поиска.json",
            ],
        }

    def finalize(
        self,
        *,
        status: str,
        result_count: int,
        error: str | None,
        fatal_traceback: str | None = None,
        cancelled: bool = False,
        source_counts: dict[str, int] | None = None,
        source_errors: dict[str, str] | None = None,
        source_stats: dict[str, Any] | None = None,
        requested_sources: list[str] | None = None,
    ) -> None:
        with self._lock:
            if not self.session_dir:
                return
            finished_at = datetime.now()
            started_at = self.started_at or finished_at

            requested = list(dict.fromkeys(requested_sources or self._params.get("enabled_sites") or []))
            counts = {source: 0 for source in requested}
            counts.update({str(k): int(v or 0) for k, v in (source_counts or {}).items()})

            errors = {str(k): str(v) for k, v in (source_errors or {}).items() if v}
            stats = self._json_safe(source_stats or {})

            payload = {
                "session_id": self.session_id,
                "status": status,
                "started_at": started_at.isoformat(timespec="seconds"),
                "finished_at": finished_at.isoformat(timespec="seconds"),
                "duration_seconds": round(max(0.0, (finished_at - started_at).total_seconds()), 3),
                "result_count": int(result_count or 0),
                "cancelled": bool(cancelled),
                "error": error,
                "fatal_traceback": self._json_safe(fatal_traceback) if fatal_traceback else None,
                "requested_sources": requested,
                "source_counts": counts,
                "source_errors": errors,
                "source_stats": stats,
            }
            try:
                assert self.summary_path is not None
                self.summary_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if self.diagnostics_path is not None:
                    diagnostics_payload = self._build_diagnostics_payload(
                        requested=requested, counts=counts, errors=errors, stats=stats
                    )
                    self.diagnostics_path.write_text(
                        json.dumps(diagnostics_payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                self._write_readme(
                    status=status,
                    result_count=result_count,
                    error=error,
                    cancelled=cancelled,
                    source_counts=counts,
                    source_errors=errors,
                    source_stats=stats,
                )
            except OSError:
                return

    def _write_readme(
        self,
        *,
        status: str,
        result_count: int,
        error: str | None,
        cancelled: bool,
        source_counts: dict[str, int] | None = None,
        source_errors: dict[str, str] | None = None,
        source_stats: dict[str, Any] | None = None,
    ) -> None:
        if not self.readme_path:
            return

        requested = list(dict.fromkeys((self._params or {}).get("enabled_sites") or []))
        counts = {source: 0 for source in requested}
        counts.update(source_counts or {})
        errors = source_errors or {}
        stats = source_stats or {}

        source_lines = []
        for source in requested or sorted(counts):
            count = int(counts.get(source, 0) or 0)
            source_stat = stats.get(source) if isinstance(stats, dict) else None
            state = source_stat.get("status") if isinstance(source_stat, dict) else None
            error_text = errors.get(source)
            extra = []
            if state:
                extra.append(f"статус={state}")
            if isinstance(source_stat, dict):
                extra.append(f"получено={int(source_stat.get('fetched', 0) or 0)}")
                extra.append(f"страниц={int(source_stat.get('pages', 0) or 0)}")
                if source_stat.get("reported_total"):
                    extra.append(f"сайт_сообщает≈{int(source_stat.get('reported_total') or 0)}")
            if error_text:
                extra.append(f"ОШИБКА={error_text}")
            if isinstance(source_stat, dict):
                warnings = source_stat.get("warnings") or []
                if warnings:
                    extra.append(f"предупреждений={len(warnings)}")
                filtered = source_stat.get("filtered") or {}
                if isinstance(filtered, dict) and filtered:
                    top = sorted(
                        ((str(k), int(v or 0)) for k, v in filtered.items()),
                        key=lambda pair: pair[1],
                        reverse=True,
                    )[:3]
                    top = [f"{k}={v}" for k, v in top if v]
                    if top:
                        extra.append("главный отсев: " + ", ".join(top))
            suffix = f" ({'; '.join(extra)})" if extra else ""
            source_lines.append(f"- {source}: {count}{suffix}")

        if not source_lines:
            source_lines.append("- пока нет итоговой статистики")

        params = self._params or {}
        salary_mode = params.get("salary_mode")
        if not salary_mode:
            salary_mode = "Строгий" if params.get("strict_salary") else "Мягкий"

        status_explain = {
            "success": "все отработавшие источники завершились без ошибок",
            "partial_success": "вакансии найдены, но один или несколько источников завершились ошибкой",
            "no_results": "поиск завершился без результатов и без критической ошибки",
            "error": "поиск не смог нормально завершиться",
            "cancelled": "поиск остановлен пользователем",
            "running": "поиск ещё выполняется",
        }.get(status, "")

        diagnosis_lines = []
        for source in requested or sorted(counts):
            source_stat = stats.get(source) if isinstance(stats, dict) and isinstance(stats.get(source), dict) else {}
            findings = self._source_diagnosis(
                source, source_stat, int(counts.get(source, 0) or 0), errors.get(source)
            )
            if findings:
                diagnosis_lines.append(f"- {source}:")
                diagnosis_lines.extend(f"  * {item}" for item in findings)
        if not diagnosis_lines:
            diagnosis_lines.append("- Явных проблем по автоматическим правилам не обнаружено.")

        sample_lines = []
        for source in requested or sorted(counts):
            source_stat = stats.get(source) if isinstance(stats, dict) and isinstance(stats.get(source), dict) else {}
            samples = source_stat.get("samples") if isinstance(source_stat.get("samples"), dict) else {}
            picked = []
            for reason in ("salary", "city", "position", "invalid"):
                rows = samples.get(reason) if isinstance(samples, dict) else None
                if not isinstance(rows, list):
                    continue
                for row in rows[:2]:
                    if not isinstance(row, dict):
                        continue
                    title = str(row.get("title") or "без названия")
                    salary = str(row.get("raw_salary") or "")
                    detail = f"{reason}: {title}"
                    if salary:
                        detail += f" | raw_salary={salary}"
                    picked.append(detail)
            if picked:
                sample_lines.append(f"- {source}:")
                sample_lines.extend(f"  * {item}" for item in picked[:5])
        if not sample_lines:
            sample_lines.append("- Нет сохранённых примеров отсева.")

        text = "\n".join([
            "ЛОГИ ПРОБЛЕМ VACANCY PARSER PRO — ЧИТАТЬ СНАЧАЛА",
            "",
            f"Сессия: {self.session_id or ''}",
            f"Версия программы: {self.app_version}",
            f"Статус: {status}",
            f"Расшифровка статуса: {status_explain or 'нет'}",
            f"Найдено уникальных вакансий: {int(result_count or 0)}",
            f"Отменено пользователем: {'да' if cancelled else 'нет'}",
            f"Критическая ошибка приложения: {error or 'нет'}",
            "",
            "Параметры поиска:",
            f"- запросы: {params.get('queries', '')}",
            f"- города: {params.get('city', '')}",
            f"- источники: {', '.join(requested)}",
            f"- минимальная зарплата: {params.get('salary') or 'не задана'} {params.get('salary_currency', '')}",
            f"- режим зарплаты: {salary_mode}",
            f"- исключения: {params.get('exclude') or 'нет'}",
            "",
            "Результаты и состояние источников:",
            *source_lines,
            "",
            "Автоматическая диагностика для нейросети:",
            *diagnosis_lines,
            "",
            "Примеры отсева (первые несколько, чтобы быстро увидеть неправильный парсинг):",
            *sample_lines,
            "",
            "Что читать нейросети:",
            "1. 00_прочитать_нейросети_сначала.txt — краткий итог и автоматические гипотезы.",
            "2. 04_диагностика_источников.json — samples отсева, warnings, pages_detail и ai_diagnosis по каждому сайту.",
            "3. 05_проверка_ссылок.jsonl — фактические открытия вакансий: исходный/подготовленный URL, был ли preflight пропущен и сколько занял вызов браузера.",
            "4. 03_итог.json — source_counts, source_errors и полный source_stats.",
            "5. 01_лог_поиска.log — последовательный ход поиска, HTTP/SSL, fallback и пагинация.",
            "6. 02_параметры_поиска.json — точные параметры и окружение запуска.",
            "",
            "Для проблемы «мало вакансий» сравнивайте fetched/accepted и filtered по каждому источнику.",
            "Если fetched=0 и есть source_errors — проблема в доступе/разметке источника, а не в фильтрах.",
            "",
        ])
        self.readme_path.write_text(text, encoding="utf-8")

    def cleanup_old_sessions(self, exclude: Path | None = None) -> None:
        """Удаляет только старые папки сессий внутри «Логи проблем»."""
        try:
            self._ensure_root()
            dirs = [p for p in self.base_dir.iterdir() if p.is_dir()]
            dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            kept = 0
            for folder in dirs:
                if exclude is not None and folder.resolve() == exclude.resolve():
                    continue
                kept += 1
                if kept >= self.keep_sessions:
                    try:
                        shutil.rmtree(folder)
                    except OSError:
                        pass
        except OSError:
            return

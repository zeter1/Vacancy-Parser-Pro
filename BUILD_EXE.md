**Язык / Language:** **Русский** · [English](BUILD_EXE_EN.md)

# Сборка Vacancy Parser Pro в готовый EXE

Для обычной сборки достаточно дважды щёлкнуть `build_exe.bat`. Он является короткой точкой входа; основной проверяемый pipeline находится в `tools/build_windows.ps1`.

## Что получится

После сообщения `[OK] READY BUILD CREATED AND VERIFIED` каталог `dist/` содержит:

```text
dist/
├─ Vacancy Parser Pro.exe
├─ icon.ico
├─ Vacancy-Parser-Pro-portable-x64.zip
├─ build_info.json
└─ SHA256SUMS.txt
```

На компьютере, где запускается готовая поставка, Python, pandas, requests, openpyxl, BeautifulSoup и PyInstaller устанавливать не требуется: Python-зависимости упакованы в EXE. `icon.ico` намеренно остаётся рядом с EXE, потому что приложение использует каталог frozen-программы для локальных ресурсов и данных.

## Что автоматически делает build_exe.bat

1. Проверяет Windows x64, право записи, обязательные исходники/`icon.ico` и минимум 3 ГБ свободного места.
2. Ищет Python 3.13 x64. Если его нет, обычная локальная сборка сначала пробует `winget`, затем официальный Python 3.13.15 installer с проверкой SHA-256.
3. Создаёт изолированный `.build-venv`.
4. Устанавливает все `requirements.txt`, PyInstaller 6.22.3 и совместимые hooks; выполняет `pip check`.
5. Компилирует код, запускает весь offline unit-test suite и `vacancy_parser.py --self-test`.
6. Генерирует Windows manifest (`asInvoker`, Per-Monitor DPI, long paths) и FileVersion/ProductVersion.
7. Собирает `onefile` EXE без UPX в staging-каталог, а не сразу в `dist/`.
8. Проверяет размер артефакта и запускает self-test собранного EXE с timeout.
9. Копирует EXE и `icon.ico` в отдельную временную папку с пробелами и кириллицей и снова выполняет self-test — без исходников проекта.
10. Создаёт portable ZIP, распаковывает его в новую чистую папку, сверяет SHA-256 и ещё раз запускает EXE.
11. Создаёт `build_info.json` и `SHA256SUMS.txt`.
12. Только после всех проверок публикует новую `dist/`. Предыдущая хорошая поставка сохраняется в `dist_previous/`.

То есть наличие `.exe` после PyInstaller само по себе не считается успешной сборкой.

## Режимы

```bat
build_exe.bat             rem полный рекомендуемый pipeline
build_exe.bat --fast      rem переиспользует совместимые build-кэши
build_exe.bat --clean     rem пересоздаёт build-env и кэши
build_exe.bat --diagnose  rem только проверяет среду, ничего не собирает
build_exe.bat --ci        rem режим GitHub Actions/Codex без pause и глобальной установки Python
```

Даже в `--fast` не отключаются packaged/portable/ZIP проверки.

## Логи для диагностики

Полный transcript каждого запуска:

```text
build_logs/build_YYYYMMDD_HHMMSS.log
```

Короткое структурированное резюме для ChatGPT/Codex:

```text
build_logs/last_build_summary.json
```

Оно содержит этап, статус, ошибку, версии Python/PyInstaller, commit и итоговый artifact. Хранятся только 20 последних подробных build-логов.

## Проверка целостности

`SHA256SUMS.txt` содержит SHA-256 EXE и ZIP. `build_info.json` содержит версию приложения, архитектуру, commit SHA (или `source-archive` при сборке из ZIP), версии toolchain и список реально выполненных проверок.

## Безопасная публикация

Новая сборка сначала живёт в `.build/`. Рабочая `dist/` не удаляется в начале. Только полностью проверенный кандидат заменяет её; прежняя версия переносится в `dist_previous/`. Поэтому неудачный новый build не должен уничтожать последнюю рабочую поставку.

## Что можно удалить

Можно безопасно удалить `.build/`, `.build-cache/`, `.build-venv/`, `build_logs/` и `dist_previous/`. Они будут созданы заново. Пользователю для переноса программы удобнее передавать `dist/Vacancy-Parser-Pro-portable-x64.zip`.

## Если сборка упала

Смотрите первое `[ERROR]`, затем `build_logs/last_build_summary.json` и самый новый `build_logs/build_*.log`. Типичные причины: proxy/антивирус блокирует `pip` или python.org, мало места на диске, нет права записи или защитное ПО блокирует новый unsigned EXE. Сборщик не подавляет такие ошибки и не объявляет непроверенный EXE готовым.

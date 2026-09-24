# Изменения Windows-сборки

- Готовый `Vacancy Parser Pro.exe` теперь публикуется как постоянный GitHub Release.
- В релиз также входит portable-архив `Vacancy-Parser-Pro-portable-x64.zip`.
- Для опубликованных файлов доступен `SHA256SUMS.txt`.
- Перед публикацией CI выполняет compile, импорт модулей, unit tests, source self-test и packaged verification.
- README теперь содержит прямую информацию о скачивании готовой Windows-версии.

## Проверка

CI подтверждает корректность сборки и её packaging metadata на GitHub-hosted Windows runner. Реальный поиск вакансий зависит от текущей доступности внешних сайтов, их HTML/API и сетевых ограничений и требует runtime-проверки.

from __future__ import annotations

import sys

from vacancy_gui import ICON_FILE, main


def self_test() -> int:
    """Offline smoke test used both before and after PyInstaller packaging."""
    from job_scraper import JobScraper

    if not ICON_FILE.is_file():
        raise RuntimeError(f"Required runtime resource is missing: {ICON_FILE}")

    scraper = JobScraper()
    try:
        if not scraper.BELARUS_SITES or not scraper.RUSSIA_SITES:
            raise RuntimeError("Vacancy source registry is empty.")
    finally:
        scraper.close()

    print(f"self-test: ok | icon={ICON_FILE}")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    main()

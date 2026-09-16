**Язык / Language:** [Русский](BUILD_EXE.md) · **English**

# Building Vacancy Parser Pro as a ready Windows EXE

For a normal build, just double-click `build_exe.bat`. The BAT remains a small entry point; the reliable packaging pipeline lives in `tools/build_windows.ps1`.

## Output

After `[OK] READY BUILD CREATED AND VERIFIED`, `dist/` contains:

```text
dist/
├─ Vacancy Parser Pro.exe
├─ icon.ico
├─ Vacancy-Parser-Pro-portable-x64.zip
├─ build_info.json
└─ SHA256SUMS.txt
```

The target PC does not need Python, pandas, requests, openpyxl, BeautifulSoup, or PyInstaller installed. Python runtime dependencies are packaged into the EXE. `icon.ico` intentionally remains next to the executable because the frozen application uses its own directory for local resources and writable state.

## What the builder does automatically

1. Checks Windows x64, write access, required source/resource files, and at least 3 GB of free disk space.
2. Finds Python 3.13 x64. A normal local build first tries `winget` when Python is missing, then falls back to the official Python 3.13.15 installer with SHA-256 verification.
3. Creates an isolated `.build-venv`.
4. Installs `requirements.txt`, PyInstaller 6.22.3 and compatible hooks, then runs `pip check`.
5. Compiles the source, runs the complete offline unit-test suite, and executes `vacancy_parser.py --self-test`.
6. Generates a Windows manifest (`asInvoker`, per-monitor DPI awareness, long-path support) and FileVersion/ProductVersion metadata.
7. Builds a `onefile` EXE without UPX into a staging directory rather than directly into `dist/`.
8. Validates artifact size and runs the packaged self-test with a hard timeout.
9. Copies the EXE and `icon.ico` into a clean temporary path containing spaces and Cyrillic and runs the self-test again without project source files.
10. Creates the portable ZIP, extracts it into another clean directory, verifies EXE SHA-256, and runs the packaged self-test once more.
11. Writes `build_info.json` and `SHA256SUMS.txt`.
12. Publishes the new `dist/` only after every check succeeds; the previous good distribution is preserved in `dist_previous/`.

Merely producing an `.exe` is therefore not treated as a successful build.

## Modes

```bat
build_exe.bat             rem full recommended pipeline
build_exe.bat --fast      rem reuse compatible build caches
build_exe.bat --clean     rem recreate build environment and caches
build_exe.bat --diagnose  rem inspect environment only
build_exe.bat --ci        rem GitHub Actions/Codex mode without pause or global Python install
```

Critical packaged, portable-folder, and ZIP verification remains enabled in `--fast` mode.

## Build diagnostics

Detailed transcript:

```text
build_logs/build_YYYYMMDD_HHMMSS.log
```

Compact ChatGPT/Codex-friendly summary:

```text
build_logs/last_build_summary.json
```

It records stage, status, error, Python/PyInstaller versions, commit and final artifact. Only the 20 newest detailed build logs are retained.

## Integrity metadata

`SHA256SUMS.txt` contains hashes for the EXE and ZIP. `build_info.json` records application version, architecture, Git commit (or `source-archive` when built from a downloaded ZIP), toolchain versions and the verification levels that actually ran.

## Safe publication

A candidate build stays under `.build/` until verification completes. The current `dist/` is not deleted at the start. Only a fully verified candidate replaces it, while the previous distribution is moved to `dist_previous/`.

## Safe to delete

`.build/`, `.build-cache/`, `.build-venv/`, `build_logs/`, and `dist_previous/` are build-only data and can be deleted. For distribution, the easiest file to share is `dist/Vacancy-Parser-Pro-portable-x64.zip`.

## If the build fails

Check the first `[ERROR]`, then `build_logs/last_build_summary.json`, then the newest `build_logs/build_*.log`. Typical causes are proxy/antivirus blocking `pip` or python.org, insufficient disk space, missing write permissions, or security software temporarily blocking a new unsigned executable. The builder deliberately does not suppress these errors and never marks an unverified EXE as ready.

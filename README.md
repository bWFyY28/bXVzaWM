# bXVzaVM

A local music TUI with the simplicity of foobar2000 and the navigation of a modern music app. The interface uses minimal brutalist panels and a dark Gruvbox Material palette with muted blue accents.

Built for personal, single-user use: straightforward Python modules, SQLite, and standard file/import safeguards. Keep implementation complexity proportional to the features actually in use.

**Status:** project foundation implemented. The package includes a starter Textual interface, command-line configuration, external library layout, transactional SQLite migrations, tests, and Docker check configuration. File indexing, playback, catalogs, and verified imports remain upcoming milestones. Dependency installation, the TUI, Ruff, and Docker checks have not yet been validated because this session restricts network and service access.

Keep the original name **`bXVzaVM`**. `bxvzm` is its Python package and command alias. Local `PLAN.md` and `AGENTS.md` record implementation decisions; update both whenever ideas, scope, or design decisions change. Git ignores these documents and related local agent/planning artifacts, while preserving them on disk.

## Planned experience

- Browse Library, Search, Favorites, Playlists, and Imports with keyboard or mouse.
- Keep playback controls visible: play/pause, queue, previous/next, seek, volume, shuffle, and repeat.
- Search Deezer and use MusicBrainz to identify album editions and tracklists.
- Accept browser-selected Amazon Music, TIDAL, and other DoubleDouble-supported links without requiring provider credentials.
- Choose the exact original, remastered, deluxe, anniversary, explicit, or clean edition before importing.
- Hold incomplete or uncertain albums for review instead of silently adding the wrong release.

## Technology board

| Area | Planned technology | Purpose |
| --- | --- | --- |
| Runtime | Python 3.13.x | Previous stable feature series selected for this project |
| Terminal interface | Textual 8.1.1, Textual CSS | Navigation, tables, dialogs, blue-accented theme |
| Catalog requests | HTTPX | Deezer and MusicBrainz metadata adapters |
| Audio metadata | Mutagen | Read tags, duration, codec, and available quality information |
| Library index | Python's built-in SQLite | Metadata, relative paths, playlists, favorites, import state |
| Audio playback | mpv, local JSON IPC | Native playback without a separate player window |
| Windows IPC | Windows-only IPC support | Communicate with mpv through named pipes |
| Isolation | `.venv`, pinned dependency locks | Keep project packages out of global Python |
| Reproducible checks | Docker, pytest, Ruff | Test and lint using a separate tooling image |

Use maintained fixes within the selected feature series. Pin resolved dependencies and the Docker image during implementation; do not use floating `latest` tags or prereleases.

## Download workflow

1. Search for an album or paste a supported provider link.
2. Select an edition and review its expected tracklist.
3. Copy the provider URL and open [DoubleDouble](https://us.doubledouble.top/) in the browser.
4. Submit the URL and complete the website download manually.
5. Import the downloaded ZIP, audio file, or folder into bXVzaVM.
6. Review completeness and edition evidence before committing the album to the library.

DoubleDouble's [FAQ](https://us.doubledouble.top/faq/) states that it has no API and asks users not to automate the website. The app will use a browser handoff rather than website automation.

Automated catalog access varies by provider. [Amazon's catalog API](https://www.developer.amazon.com/docs/music/API_web_search_v2.html) is in closed beta; [TIDAL's API](https://developer.tidal.com/documentation/api-sdk/api-sdk-authorization) requires developer credentials. Their links remain usable in the manual workflow. If metadata cannot be resolved automatically, select a reference release; a pasted link alone does not establish its edition.

## Files and database

The default Windows library will be configurable and stored outside the repository:

```text
%USERPROFILE%\Music\bXVzaVM\
  library.sqlite3
  music\Artist\Album [edition and release ID]\01 - Title.flac
  playlists\
  .staging\
```

Songs stay as ordinary audio files. SQLite stores their index and relative paths, file hashes, metadata, edition references, verification evidence, favorites, playlist ordering, import history, and saved playback state. It does not store audio blobs.

Imports preserve the original downloaded audio. Embedded tags determine readable folder names; Windows-safe sanitization and hash suffixes prevent filename collisions. Different album editions have separate folders. Files with missing tags receive explicit fallback labels.

Pending imports stay in `.staging` until the user repairs them, selects a better reference, discards them, or explicitly accepts the mismatch. Accepted mismatches remain labeled in the library.

### Completeness and edition checks

Count expected track slots across all discs and compare them with imported files using available IDs, ISRCs, track positions, titles, artist credits, and durations. Equal file counts alone do not prove completeness: duplicates or unexpected songs cannot replace missing tracks.

Store tracklist completeness separately from edition confidence. Missing explicit/clean or remaster evidence stays unknown. Metadata matching cannot conclusively prove a particular mastering or uncensored recording.

### Audio quality

Prefer genuine **FLAC**, but accept original MP3, AAC, and other supported formats when lossless downloads are unavailable. FLAC is a format; bit depth and sample rate describe resolution, such as 16-bit/44.1 kHz. Show available quality information and preserve the source format. Converting lossy files to FLAC does not improve their quality, and source availability determines download resolution.

### Export and backup

- Export selected tracks, albums, or playlists by copying audio and generating relative-path M3U8 playlists.
- Back up the full library using a consistent SQLite backup plus audio files, preserving favorites and verification records.
- Move a copied library by selecting its new root; stored song paths remain relative.
- Rescan files to recover the song index. Restoring favorites and playlists requires the database backup.
- Exclude pending staging imports from ordinary music exports.

## Setup and development

The initial playback target remains native Windows. WSL may host development and Docker checks. Do not share one virtual environment between Windows and Linux: recreate `.venv` in whichever environment runs the commands. If developing on WSL's Linux filesystem, clone or copy the project there and configure an accessible library root explicitly.

Install a maintained Python 3.13 patch before creating a virtual environment. The bootstrap session found Python **3.13.0** at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`; the launcher did not detect it. That older interpreter was used for storage tests only. Upgrade it and recreate `.venv` before acceptance.

```powershell
# Windows
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
# If the launcher does not detect an installed Python 3.13:
# & "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
```

```sh
# WSL, with python3.13 installed
python3.13 -m venv .venv
source .venv/bin/activate
```

`requirements/runtime.txt` pins runtime dependencies, `requirements/build.txt` pins packaging tools, and `requirements/dev.txt` adds pytest and Ruff with their dependencies. These are provisional, fully pinned dependency snapshots; installation and resolver validation are pending. Development tools are not runtime dependencies. Install from a network-enabled shell:

```sh
python -m pip install -r requirements/dev.txt
python -m pip install --no-deps --no-build-isolation -e ".[dev]"
python -m pip check
bxvzm
```

For a runtime-only install, install `requirements/runtime.txt` and `requirements/build.txt`, then `python -m pip install --no-deps --no-build-isolation -e .`. Keep dependency changes pinned in the appropriate snapshots and validate a clean environment on each target OS.

The starter interface provides five views, numeric shortcuts `1`–`5`, arrow/Tab navigation, `?` for help, and `q` to quit. The square panels use the planned Gruvbox Material colors. Views describe the features still to come; there is no audio playback or import action yet.

The default library is `~/Music/bXVzaVM`. Select another root outside the source repository:

```sh
bxvzm --library /path/to/library --check
bxvzm
```

On Windows, for example: `bxvzm --library "D:\Music\bXVzaVM" --check`. `--check` initializes the directories and SQLite database without starting the TUI. `--library` remembers the selection only after successful initialization. An explicit root overrides the `BXVZM_LIBRARY` environment variable, which overrides the saved selection. The environment override is temporary.

Preferences live outside the library at `%LOCALAPPDATA%\bxvzm\config.json` on Windows, or `$XDG_CONFIG_HOME/bxvzm/config.json` (default `~/.config/bxvzm/config.json`) on Linux. `--config PATH` selects a different preferences file. The library contains `music/`, `playlists/`, `.staging/`, and `library.sqlite3`; the initial database holds portable application state and creation metadata. Future migrations will add the song index and import records. It refuses a newer database schema and rolls back failed migrations. No playback starts automatically.

Run the full checks after installation:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
docker compose run --rm checks
```

The Docker checks use the patch-pinned `python:3.13.16-slim-trixie` tooling image and the same dependency snapshots. Docker handles tests and tooling; native Windows will handle interactive audio. Linux mpv uses Unix sockets rather than Windows named pipes. Running playback inside WSL requires a separately verified audio setup and is not an initial acceptance requirement. Docker image build and execution remain unverified.

The storage tests also work without third-party dependencies. They use temporary directories outside the repository and do not import user audio:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# These module commands also work before editable installation:
.\.venv\Scripts\python.exe -m bxvzm --version
.\.venv\Scripts\python.exe -m bxvzm --help
```

In Linux, use `PYTHONPATH=src python -m unittest discover -s tests -v`. The bootstrap run passed 18 tests and skipped two: the Textual check needs dependencies, and the symlink check needs OS permission. pytest collects the same tests once installed. To capture a terminal screenshot after installation, set `BXVZM_SCREENSHOT_DIR=tests/artifacts` and run `python -m pytest tests/test_ui.py`; the headless 80x24 check saves `foundation.svg` there.

The bootstrap environment could not reach PyPI (`WinError 10013`), access the Docker engine, or enumerate WSL distributions. Git is not available on PATH and this workspace has no `.git` directory. Resume with dependency installation and full validation, then continue to local indexing and playback in milestone 2.

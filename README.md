# bXVzaVM

A local music TUI with the simplicity of foobar2000 and the navigation of a modern music app. The interface uses minimal brutalist panels and a dark Gruvbox Material palette with muted blue accents.

Built for personal, single-user use: straightforward Python modules, SQLite, and standard file/import safeguards. Application data and settings stay inside this folder for portability. Python is installed separately. Keep implementation complexity proportional to the features actually in use.

**Status:** version 0.1.1 adds cross-platform setup and launching to the project foundation. The package includes a starter Textual interface, portable configuration and library layout, transactional SQLite migrations, tests, and Docker check configuration. File indexing, playback, catalogs, and verified imports remain upcoming milestones.

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

Application files live under this project's ignored `data/` folder:

```text
bXVzaWM\
  run.cmd
  .venv\
  data\
    config.json
    library\
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
- Move the whole project folder, including `data/`; preferences and stored song paths remain relative.
- Rescan files to recover the song index. Restoring favorites and playlists requires the database backup.
- Exclude pending staging imports from ordinary music exports.

## Setup and development

Install Python **3.13** separately and open a terminal in this folder. The same setup script works on Windows, Linux/WSL, and macOS:

```sh
python install.py
python run.py
```

Use `py -3.13` on Windows or `python3.13` on Linux/macOS if `python` is not your Python 3.13 command. You can also pass the full path to an installed Python 3.13 executable. The first setup needs internet access. No environment activation, PowerShell policy changes, or administrator access are required by the setup script.

Setup creates `.venv`, installs pinned runtime/build dependencies and the app, verifies dependencies, and initializes `data/library`. Temporary installation files stay in `data/.setup-tmp`, and global pip download caching is disabled. Rerun setup after updating the code. For development tools, use `python install.py --dev`. To rebuild the environment after moving computers or OSes, use `python install.py --recreate`; `data/` is preserved. Recognized incompatible environments are rebuilt automatically. macOS uses the same Python setup flow, but native playback remains a future acceptance target.

On Windows you can also use `./run.cmd`. Both launchers find the source relative to their own location, so another working directory does not change where data lives. Keep `data/` when moving the application. Python and Docker themselves remain separately installed tools.

`requirements/runtime.txt` pins runtime dependencies, `requirements/build.txt` pins packaging tools, and `requirements/dev.txt` adds pytest and Ruff with their dependencies. Development tools are not runtime dependencies. The installer uses these files; manual installation remains available.

For manual runtime-only setup, install `requirements/runtime.txt` and `requirements/build.txt` in `.venv`, then `python -m pip install --no-deps --no-build-isolation -e .`. Keep dependency changes pinned in the appropriate snapshots. Do not share one virtual environment between Windows and Linux.

The starter interface provides five views, numeric shortcuts `1`–`5`, arrow/Tab navigation, `?` for help, and `q` to quit. The square panels use the planned Gruvbox Material colors. Views describe the features still to come; there is no audio playback or import action yet.

The default library is `data/library`, resolved from the application folder rather than the current working directory. To select another library within `data/`:

```sh
bxvzm --library data/another-library --check
bxvzm
```

On Windows, for example: `./run.cmd --library data/another-library --check`. `--check` initializes the directories and SQLite database without starting the TUI. `--library` remembers the selection only after successful initialization. An explicit root overrides the `BXVZM_LIBRARY` environment variable, which overrides the saved selection. All roots must stay inside this application's `data/` folder; external paths and symlink escapes are rejected. The environment override is temporary.

Preferences live at `data/config.json`. Saved selections use a relative path such as `data/library`, so moving the folder needs no path edits. `--config PATH` can select another preferences file inside `data/`. AppData, XDG config folders, and the user's Music folder are not used. The library contains `music/`, `playlists/`, `.staging/`, and `library.sqlite3`; the initial database holds portable application state and creation metadata. Future migrations will add the song index and import records. It refuses a newer database schema and rolls back failed migrations. No playback starts automatically.

Run the full checks after `python install.py --dev`, using `.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on Linux/macOS in place of `python`:

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
docker compose run --rm --build checks
```

Start Docker Desktop with Linux containers before running the Compose command. No local `.venv` is needed for Docker checks. The first build needs internet access to download the image and packages; checks run with container networking disabled. Rebuild after source changes because the image contains a copy of the project.

The Docker checks use the digest-pinned `python:3.13.16-slim-trixie` tooling image. The build runs the same `python install.py --dev` setup, including `pip check`; the container runs pytest, Ruff linting, and Ruff formatting checks with its local `.venv`. Docker handles tests and tooling; native Windows will handle interactive audio. Linux mpv uses Unix sockets rather than Windows named pipes. Running playback inside WSL requires a separately verified audio setup and is not an initial acceptance requirement.

To preview the starter interface in Docker with project-local data, run from PowerShell:

```powershell
docker compose run --rm -it --volume "${PWD}/data:/app/data" checks bxvzm
```

The bind mount preserves settings and the library in this folder's `data/` directory. Without that mount, application data exists only in the temporary container. Docker's images and cache are managed separately by Docker Desktop.

The storage tests also work without third-party dependencies. They model portable bundles in temporary test directories and do not import user audio or touch the real `data/` folder:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# These module commands also work before editable installation:
.\.venv\Scripts\python.exe -m bxvzm --version
.\.venv\Scripts\python.exe -m bxvzm --help
```

In Linux, use `PYTHONPATH=src python -m unittest discover -s tests -v`. Version 0.1.1 passes all 29 tests in Docker and 28 on Windows, with one Windows symlink-privilege skip. Both pass linting, formatting, and dependency checks. Fresh Linux setup and repeat Windows setup are verified; macOS has not been manually tested. Tests include bundle relocation, relative settings, external path rejection, UI navigation, and setup/recreation behavior. The terminal screenshot is [tests/artifacts/foundation.svg](tests/artifacts/foundation.svg). To regenerate it, set `BXVZM_SCREENSHOT_DIR=tests/artifacts` and run the UI test through the local environment's Python.

Local commands and Docker builds can require reviewed access outside the agent sandbox. Completed versions are committed and pushed to the configured remote after checks pass, without force-pushing. Git ignores local agent/planning files and user data. The next feature milestone is local indexing and playback.

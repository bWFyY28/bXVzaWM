# bXVzaVM

A portable, personal music terminal app. Version **0.2.0** adds local indexing, fuzzy song lookup, favorites, and background mpv playback. The TUI uses text labels, square panels, and muted Gruvbox colors. Animation is disabled; the Windows tray uses a small static monochrome `b`. `bxvzm` is the Python package and command alias.

## Install and run

Install Python **3.13** separately, then run from this folder:

```sh
python install.py
python run.py
```

Use `py -3.13` on Windows or `python3.13` on Linux/macOS if needed. Windows also supports `./run.cmd`. Setup creates the local `.venv`, installs pinned dependencies, checks them, and initializes the library. No activation or administrator access is needed. Rerun setup after updating; use `python install.py --recreate` after moving computers or OSes. Recreation preserves `data/`. Setup temporary files stay under `data/.setup-tmp`, with global pip caching disabled.

Playback needs **mpv 0.41.0**. Download the appropriate Windows ZIP from the [official stable release](https://github.com/mpv-player/mpv/releases/tag/v0.41.0), unpack it (including its nested ZIP), and place `mpv.exe` and its accompanying DLLs in `data/tools/`. An mpv installation on PATH also works. The app uses [mpv JSON IPC](https://mpv.io/manual/master/#json-ipc), with no player window or user mpv configuration. Missing mpv leaves browsing and scanning available.

Install **JetBrains Mono Nerd Font** separately and select `JetBrainsMono Nerd Font` in your terminal's font settings. For Windows Terminal, the profile font setting is:

```json
"font": { "face": "JetBrainsMono Nerd Font" }
```

Terminal fonts are controlled by the terminal, rather than Textual. The UI uses ordinary text and does not require icon glyphs. Keep the terminal at least 80 columns by 24 rows.

## Add music and play

Copy your audio files or artist/album folders into `data/library/music/`, then scan:

```sh
python run.py --scan
python run.py --song "cirle"
python run.py --status
python run.py --pause
python run.py --stop-service
```

`--song` fuzzy-searches indexed local titles and artist names, so `cirle` can match `Circles - Post Malone` when that song is in your library. A confident match starts the background service if necessary and plays immediately. Similar editions or weak matches show numbered candidates; choose with `--song "cirle" --match 2`. No match returns exit code 1; a choice needing selection returns 2. Search does not download songs.

To type the installed command directly in the current PowerShell session, temporarily add this bundle's environment to PATH:

```powershell
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
bxvzm --song "cirle"
bxvzm
```

On Linux/macOS, use `export PATH="$PWD/.venv/bin:$PATH"`. The launchers work without changing PATH and resolve data independently of the working directory.

Scanning accepts MP3, FLAC, M4A/AAC, OGG/Opus, and WAV. It reads local tags, duration and available quality fields, hashes original bytes, and stores relative file paths. Untagged files use their filenames and explicit Unknown labels. Duplicate files remain separate; missing or unreadable files remain indexed as unavailable, preserving favorites. A failed directory traversal preserves the previous snapshot. Linked files/folders and Windows junctions are excluded. `--scan` prints file issues and returns 1 when issues are found. Scanning does not prove album completeness, mastering, or clean/explicit status.

## TUI and background service

Opening the TUI starts or connects to the selected library's background process. Windows shows the monochrome `b` in the notification area, possibly under hidden tray icons. Right-click it and choose **Exit bXVzaVM** to stop the service and mpv. `--daemon` starts it without opening the TUI; `--stop-service` also stops it.

| Key | Action |
| --- | --- |
| `1` to `5` | Library, Search, Favorites, Playlists, Imports |
| Arrows or `j` / `k` | Navigate tracks |
| `/` | Filter local title, artist, album, or path; title/artist typos are supported |
| Enter in filter / Esc | Return to tracks |
| Enter on track | Play through the background process |
| Space | Pause/resume |
| `h` / `l` | Seek backward/forward 5 seconds |
| `-` / `+` | Adjust volume |
| `f` | Toggle selected favorite |
| `r` | Rescan `music/` in a worker |
| `?` | Help |
| `q` | Close the TUI; background playback continues |

Typing in the filter takes precedence over shortcuts. The player bar follows CLI changes while the TUI is open. One service owns playback per selected library. Selection, position, and volume persist; starting the service never automatically plays audio. Exit the service before moving the bundle or rebuilding `.venv`.

This is a per-user background process, with no administrator-level Windows Service or login-startup registration. Windows tray behavior is the initial target. Linux/macOS use a background process without a tray; their native audio playback has not been accepted yet.

Catalog search, playlist/queue editing, shuffle/repeat, verified imports, export, and backup remain upcoming. The Search, Playlists, and Imports tabs currently describe that work. Future downloads use manual DoubleDouble browser handoff; uncertain editions remain under review.

## Portable storage

```text
bXVzaWM/
  .venv/
  data/
    config.json
    tools/mpv.exe
    library/
      library.sqlite3
      music/
      playlists/
      .staging/
      .service.json
      .service.log
```

All application storage stays inside ignored `data/`. Settings and indexed paths are relative to the bundle; audio remains on disk. Storage outside `data/` and symlink escapes are rejected. No application files are placed in AppData, XDG directories, the home folder, or Music. Service endpoint credentials/logs stay within the selected library and are not committed.

`python run.py --check` initializes without opening the interface or starting a service. `--library data/another-library` selects a library and remembers it after initialization. Command-line selection overrides `BXVZM_LIBRARY`, which overrides saved preferences; the environment override is temporary. `--config PATH` selects another preferences file inside `data/`. Existing schema-1 libraries migrate transactionally to schema 2 without removing saved state.

## Development

`dev` contains tests, screenshots, editor settings, and development tools. `main` contains runtime/setup files and concise user instructions. Validate on `dev`, copy only validated runtime changes and the matching version to `main`, commit/push both without force-pushing, and return to `dev`. Preserve ignored local `PLAN.md`, `AGENTS.md`, `.venv`, and `data/` across switches.

Docker is no longer part of this project. Use the native environment:

```powershell
python install.py --dev
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m ruff format --check .
./.venv/Scripts/python.exe -m pip check
```

Use `.venv/bin/python` on Linux/macOS. Tests use synthetic audio and isolated temporary bundles, mock playback, and check migration, rollback, relocation, duplicates, missing files, fuzzy lookup, service authentication/lifecycle, and keyboard behavior. Regenerate terminal screenshots with `BXVZM_SCREENSHOT_DIR=tests/artifacts` when running the UI tests. The populated example is [tests/artifacts/library.svg](tests/artifacts/library.svg).

Native Windows smoke validation uses a silent synthetic WAV to check the hidden tray window, single instance, real mpv named-pipe playback, pause, seek, volume, exit cleanup, and restart without autoplay. Audible output and the visible right-click menu still require human verification. Linux/macOS playback, Windows login startup, and long-library performance are not validated.

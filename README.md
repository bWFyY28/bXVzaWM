# bXVzaVM

A portable, personal music terminal app. Version **0.3.0** adds manual music download handoff, safe ZIP/folder import and review, recoverable acceptance, and a complete Docker app build. Local indexing, fuzzy song lookup, favorites, and background mpv playback are available. The TUI uses text labels, square panels, and muted Gruvbox colors. Animation is disabled; the Windows tray uses a small static monochrome `b`. `bxvzm` is the Python package and command alias.

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
bxvzm open tui
```

On Linux/macOS, use `export PATH="$PWD/.venv/bin:$PATH"`. The launchers work without changing PATH and resolve data independently of the working directory.

Scanning accepts MP3, FLAC, M4A/AAC, OGG/Opus, and WAV. It reads local tags, duration and available quality fields, hashes original bytes, and stores relative file paths. Untagged files use their filenames and explicit Unknown labels. Duplicate files remain separate; missing or unreadable files remain indexed as unavailable, preserving favorites. A failed directory traversal preserves the previous snapshot. Linked files/folders and Windows junctions are excluded. `--scan` prints file issues and returns 1 when issues are found. Scanning does not prove album completeness, mastering, or clean/explicit status.

## Download and import music

In **Search** (`2`), paste a direct HTTPS Deezer, TIDAL, or Amazon Music album/track link. Use **Copy link** and **Open DoubleDouble**, paste the link in the browser, and finish the download manually. DoubleDouble is never automated; its [FAQ](https://us.doubledouble.top/faq/) describes its manual workflow and lack of an API. Shortened links and other hosts are rejected.

In **Imports** (`5`), enter the downloaded ZIP, audio file, or folder path and choose **Stage files**. Review the full file list, local tags, disc/track numbers, formats, duplicate count, and any errors. **Accept unverified** copies the original bytes into a separate import folder and indexes them. **Discard staged** removes only that job's staging copies. Source files remain untouched.

The same flow works from the CLI (replace `JOB` with the full ID printed when staging):

```sh
bxvzm --download "https://www.deezer.com/album/123" --open-browser
bxvzm --import "path/to/download.zip" --source-url "https://www.deezer.com/album/123"
bxvzm --imports
bxvzm --review-import JOB
bxvzm --accept-import JOB --accept-unverified
bxvzm --discard-import JOB
```

Use `python run.py` in place of `bxvzm` if the command is not on PATH. `--source-url` is optional evidence. This milestone reads local files; reference tracklists, album completeness, clean/explicit status, and edition verification remain **unknown**. Acceptance requires an explicit choice. Corrupt audio blocks acceptance; repair the originals and stage them again. Separate imports remain separate even when tags or hashes match. No transcoding or quality claims are made.

ZIPs are limited to 10,000 entries and 10 GiB of extracted data. All entry names are checked; traversal, absolute paths, links, encrypted entries, and case-insensitive collisions are rejected. Folder imports reject links/junctions and enforce the entry/audio-byte limits. Cover images and other non-audio files are not imported. A failed job keeps its error for inspection. Acceptance journals its state, prepares an entire directory, then publishes files and database history; repeat the accept command to resume an interrupted copy or database commit. Pending acceptance files are excluded from scans. Exit the service before moving the bundle.

## Run the complete app in Docker

Docker is optional. The image installs Python dependencies and mpv, and starts a persistent daemon; subsequent commands execute inside that container. All Docker files and wrappers are grouped in `docker/`. Native Windows remains the route for the Windows tray and speaker playback. The supplied Docker Desktop configuration has no host audio device or Windows tray integration, so it supports TUI, CLI, downloads/imports, and indexing without providing audible Windows playback.

From this project folder in PowerShell, define the command for the current session:

```powershell
$bxvzmDockerLauncher = (Resolve-Path ./docker/bxvzm.ps1).Path
function bxvzm { powershell -NoProfile -ExecutionPolicy Bypass -File $bxvzmDockerLauncher @args }
bxvzm open tui
bxvzm --status
bxvzm --song "circle"
bxvzm --stop-service
```

The wrapper automatically builds/updates the image and waits for the daemon. Closing the TUI leaves the container running; `--stop-service` stops and removes the app container, preserving `data/`. Building requires internet on first use. Direct equivalents:

```sh
docker compose -f docker/compose.yaml up -d --build --wait app
docker compose -f docker/compose.yaml exec app bxvzm open tui
docker compose -f docker/compose.yaml exec -T app bxvzm --song "circle"
docker compose -f docker/compose.yaml down
```

On Linux/macOS, `sh docker/bxvzm.sh open tui` provides the same wrapper. For a **native Linux Docker host** with ALSA devices, add `-f docker/compose.audio.yaml` to the direct Compose commands to expose `/dev/snd`. This optional audio configuration has not been tested on a Linux audio device. Docker Desktop Windows/macOS does not gain sound from that override. Browser opening is done on the host; in a container use `--download URL` and open the printed DoubleDouble URL manually. Clipboard forwarding on Unix/container terminals depends on terminal OSC 52 support.

The bind mount exposes only this bundle's `data/`. Container settings use `data/container-config.json` and a separate `data/container-library` to avoid conflicting with a native daemon. Place downloaded files in `data/downloads/` and import using `/app/data/downloads/...`. Container paths are Linux paths. No service ports are published. Do not run two daemons against the same library across the host and container.

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

Catalog search, playlist/queue editing, shuffle/repeat, reference-verified imports, export, and backup remain upcoming. Search currently provides the manual download handoff; Imports provides staging and explicit unverified acceptance.

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

`python run.py --check` initializes without opening the interface or starting a service. `--library data/another-library` selects a library and remembers it after initialization. Command-line selection overrides `BXVZM_LIBRARY`, which overrides saved preferences; the environment override is temporary. `--config PATH` selects another preferences file inside `data/`. Existing libraries migrate transactionally to schema 3, preserving tracks, favorites, and playback state while adding import jobs/history.

## File map and debugging

| Location | Responsibility |
| --- | --- |
| `src/bxvzm/cli.py` | Command arguments and dispatch |
| `src/bxvzm/ui/` | Main TUI and download/import panels |
| `src/bxvzm/transfers/links.py` | Provider URL validation and browser handoff |
| `src/bxvzm/transfers/imports.py` | Bounded staging, hashes, acceptance and recovery |
| `src/bxvzm/database.py` | SQLite migrations, jobs/history, index transactions |
| `src/bxvzm/metadata.py`, `indexing.py`, `search.py` | Local tags, scans, fuzzy matching |
| `src/bxvzm/service.py`, `playback.py`, `tray.py`, `locking.py` | Daemon, mpv IPC, native tray, OS locks |
| `src/bxvzm/themes/` | Terminal styling |
| `docker/`, `requirements/`, `tests/` | Container setup, dependency pins, automated checks |

For import failures, use `--imports` and `--review-import JOB` to inspect the saved state, full file evidence, hashes, and error. Staged copies are in the selected library's `.staging/JOB/`; accepted audio is in `music/Imported [unverified-JOB]/`. Keep an interrupted acceptance's files and repeat acceptance to resume. Service startup diagnostics are in `.service.log`; `--status` checks connectivity. For containers, use `docker compose -f docker/compose.yaml logs app`. All application diagnostics and state remain inside `data/`.

Tests, development tools, screenshots, and the Docker checks target/service live on [dev](https://github.com/bWFyY28/bXVzaWM/tree/dev). Main ships the runtime image and launchers only. Native Windows tray and silent-audio playback smoke checks pass; audible output and visible tray-menu interaction need human verification. Container Unix IPC was checked with null audio; audible container playback and Linux ALSA passthrough are unverified.

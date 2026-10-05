# bXVzaVM Implementation Plan

## Current state and agreed scope

The first milestone now contains a Python package and CLI, external library-root configuration, portable path handling, transactional SQLite migrations, starter Textual views, tests, and Docker check configuration. Local Python 3.13.0 was found and a Windows `.venv` was created. Dependency installation is blocked by network restrictions, and Docker/WSL service access is denied in this session. UI, lint, package installation, and Docker checks still need validation.

Keep the original project and display name **`bXVzaVM`** exactly. `bxvzm` remains its Python package and command alias.

Whenever an idea or decision changes scope, behavior, architecture, dependencies, storage, or workflow, update **both `PLAN.md` and `AGENTS.md` in the same change**. Keep decisions aligned with implementation and record unfinished work here. Update `README.md` for user-facing changes. Preserve the local planning/agent documents even though Git ignores them.

Build a local music TUI with foobar2000-style library ownership and modern music-app navigation. The first acceptance target is native Windows; WSL is suitable for development and Docker checks. No Spotify account integration or automatic Downloads-folder monitoring is required.

This is for personal, single-user use. Keep the implementation small and direct, with ordinary Python modules and SQLite. Introduce abstractions only for concrete implemented needs. Avoid speculative infrastructure, extra service layers, plugin systems, account management, and enterprise features. Retain standard security and data-integrity checks: path validation, safe bounded ZIP extraction, validated provider URLs, parameterized SQL, credential hygiene, recoverable imports, and source-audio preservation.

## Locked decisions

| Area | Decision |
| --- | --- |
| Name | `bXVzaVM`; Python package and command: `bxvzm` |
| Scope | Personal, single-user application; simple implementation with standard security |
| Runtime | Python 3.13.x; use an available maintained Windows build and record its exact version |
| UI | Textual 8.1.1; square panels, compact tables, Gruvbox Material dark with blue accents |
| Theme | Background `#282828`, text `#d4be98`, primary blue `#7daea3`; readable focus indicators |
| Runtime packages | Textual, HTTPX, Mutagen, and Windows-only IPC support; standard-library SQLite, ZIP, and hashing |
| Playback | mpv controlled by local JSON IPC; native Windows named pipes |
| Isolation | Repository `.venv`; locked dependencies; separate development tools |
| Docker | Pinned Python tooling image for tests and linting, not Windows audio playback |
| Discovery | Deezer catalog plus MusicBrainz release references; no provider credentials |
| Other sources | Accept Amazon Music/TIDAL/provider links through browser-assisted selection |
| Downloads | Copy provider URL, open DoubleDouble, download manually, import selected files |
| Edition choice | Explicit selection per album; no automatic preference for remasters or explicit editions |
| Quality | Prefer genuine FLAC, accept original lossy audio, do not transcode |
| Uncertain imports | Hold in staging until repair, discard, reference correction, or explicit acceptance |
| Database | Index, metadata, relative paths, playlists, evidence, and state; no audio blobs |

Use compatible maintenance fixes without automatically upgrading feature series. Resolve and lock exact remaining dependency versions when bootstrapping; do not introduce extra frameworks or floating Docker `latest` tags.

## Architecture and behavior

### User interface and playback

Create Library, Search, Favorites, Playlists, and Imports views with a persistent player bar. Support play/pause, previous/next, seek, volume, shuffle, repeat, queue editing, and playlist ordering. Restore queue and position without automatically starting playback.

Use arrows and `j/k` for navigation, Enter for selection/playback, Space for pause, and `/` for search. Show import, queue, seek, help, and quit shortcuts. Text-entry widgets take precedence over global shortcuts. Support mouse selection and an 80x24 minimum terminal.

Keep expensive I/O in workers. Maintain one playback session; dispatch player events back to the UI and clean up the child process on exit. Missing mpv must produce setup guidance while leaving browsing and importing usable. Abstract player transport so Docker can use a fake player and future Linux playback can use Unix sockets.

### Provider metadata and reference editions

Separate provider adapters from UI code. Search Deezer tracks/albums and query MusicBrainz releases with appropriate identification, throttling, caching, pagination, and retryable error handling. Keep catalog results source-labeled; one unavailable provider must not disable local playback.

Accept supported provider links without assuming their metadata can always be fetched. If automatic reference resolution fails, present candidate releases for user selection. Amazon/TIDAL catalog search is not promised without supported API access. Do not scrape private endpoints or automate DoubleDouble.

The edition picker shows available release title, edition qualifiers, date, territory, source ID, clean/explicit status, disc count, and tracklist. Distinguish individual releases from album groups. Missing fields remain unknown.

Persist a selected reference snapshot containing source and release IDs, relevant edition attributes, and ordered expected track slots with available identifiers, titles, artist credits, and durations. Do not replace an edition silently if another provider returns a similar album.

### Import and verification

Accept ZIPs, individual audio files, and folders. Initial formats: MP3, FLAC, M4A/AAC, OGG/Opus, and WAV. Extract into a job-specific staging directory, reject traversal and symbolic links, and enforce configurable limits, initially 10,000 entries and 10 GiB of extracted data. Enforce limits while extracting, not just from archive headers.

Read tags and audio properties with Mutagen; use filenames and explicit Unknown labels when tags are missing. Compute content hashes for duplicate detection. Match expected slots using available release/track identifiers, ISRCs, disc/track positions, artist credits, version-aware titles, and duration evidence. Do not remove edition qualifiers during normalization.

Each expected slot must be accounted for. Duplicate or unexpected files cannot satisfy an unrelated missing slot. Preserve intentional repeated recordings in the reference tracklist instead of collapsing their slots. Conflicting strong identifiers cannot be overridden by a similar filename. Ambiguous evidence remains uncertain.

Keep two independent results: tracklist completeness and edition confidence. Show missing, duplicate, unexpected, mismatched, and uncertain tracks in a review table. No complete reference means completeness is unknown. Absence of an explicit flag is not evidence of a clean recording. Similar metadata cannot conclusively prove mastering or censorship.

Incomplete or uncertain jobs remain outside the committed library. Review actions can add files, exclude duplicates/extras, change the reference, discard the job, or accept a mismatch. Reference changes rerun verification. Record explicit acceptance without relabeling the result as verified. Repairs open the manual download workflow.

Move accepted files and commit index changes through a recoverable import process. Track staging/commit state so interruption does not leave an apparently complete album with missing files. Resume or report interrupted jobs on startup.

### Library persistence and export

Default Windows root: `%USERPROFILE%\Music\bXVzaVM`, configurable independently of the repository. Store `library.sqlite3`, `music/`, `playlists/`, and `.staging/` under it. Keep machine-specific preferences outside the portable library.

Organize audio by album artist, album, edition/release ID, disc where needed, and track title. Sanitize Windows-reserved names and separators, bound path lengths, and resolve collisions with content-hash suffixes. Do not overwrite different editions or change imported audio bytes.

Use versioned SQLite migrations. Store files and hashes, edition-specific track associations, relative paths, expected references, verification evidence, playlists, favorites, import history, and saved playback state. Preserve references across restarts for offline review. A shared audio asset must not collapse separate edition memberships.

Support selected tracks/albums/playlists export to a chosen destination, copying source audio and creating relative-path M3U8 playlists. Never silently overwrite unrelated destination files. Export a portable full backup with audio and a consistent SQLite snapshot; exclude pending staging jobs from ordinary music exports. The first full-backup flow should require imports to finish or pause during snapshot creation.

Selecting a relocated library root must restore paths and playlists without rewriting every indexed filename. Rescanning can rebuild file metadata, but favorites and verification history require a database backup.

## Implementation checklist

### 1. Environment and project foundation

- [x] Verify the resumed Windows/WSL environment, installed Python, Docker availability, and repository state.
- [x] Create `pyproject.toml`, `src/bxvzm/`, theme assets, and `tests/`.
- [ ] Create the local `.venv` and dependency locks with separate runtime/development requirements.
- [x] Add ignores for environments, credentials, databases, audio, caches, staging, and local agent/planning artifacts.
- [x] Add the `bxvzm` entry point, configuration, library-root selection, and migration foundation.
- [x] Add a Dockerfile and Compose `checks` service using a pinned base image and pinned dependency files (execution validation pending).

Bootstrap validation: 18 standard-library tests passed; Textual and symlink checks were skipped because dependencies and symlink privileges are unavailable. Tests cover preference precedence, invalid configuration, relative paths, schema compatibility, migration rollback, concurrent initialization, and relocated state. No user music was imported. Python is currently 3.13.0; upgrade to a maintained 3.13 patch and recreate `.venv` before acceptance. The Python launcher reports no installations, Git is unavailable on PATH, and there is no `.git` directory in this workspace.

Remaining foundation work: install and validate the pinned dependencies and editable package, run pytest/Ruff and headless Textual checks, capture the terminal screenshot, and run Docker checks. The starter views expose navigation only; indexing, playback, catalogs, and imports retain their later milestone scope.

### 2. Local library and playback

- [ ] Implement metadata reading, file indexing, relative-path persistence, and rescanning.
- [ ] Implement library navigation, favorites, playlists, and the blue-accented theme.
- [ ] Integrate native Windows mpv IPC and the persistent player bar.
- [ ] Implement queue behavior and restart-state persistence.

### 3. Discovery and edition selection

- [ ] Implement Deezer and MusicBrainz metadata adapters with offline/error states.
- [ ] Implement source-labeled results, provider-link input, edition picker, and reference snapshots.
- [ ] Implement URL copy and DoubleDouble browser handoff.

### 4. Verified import and review

- [ ] Implement safe extraction, staging jobs, progress reporting, and duplicate detection.
- [ ] Implement track-slot matching and separate completeness/edition results.
- [ ] Implement review actions, manual repair, explicit mismatch acceptance, and interruption recovery.
- [ ] Commit accepted imports to edition-specific folders and SQLite.

### 5. Export, validation, and handoff

- [ ] Implement music/M3U8 export, consistent full backup, and library relocation.
- [ ] Run automated checks in `.venv` and Docker.
- [ ] Verify native Windows playback and the browser/download/import workflow manually.
- [ ] Replace planned README commands with verified setup/run instructions and update contributor guidance.

## Acceptance scenarios

- Navigate a responsive 80x24 TUI while imports or searches run in the background.
- Play, pause, seek, reorder the queue, save playlists, and restore state on restart.
- Select a specific remastered/explicit/deluxe edition and retain its reference after restart.
- Detect an album with the correct file count but a duplicate replacing a missing song.
- Correctly handle multi-disc numbering, bonus tracks, intentional repeated recordings, and conflicting identifiers.
- Hold unknown clean/explicit or remaster evidence for review instead of assuming a match.
- Add missing files to a pending import, rerun verification, and commit only after resolution or explicit acceptance.
- Reject unsafe/corrupt archives and recover interrupted imports without false completeness.
- Preserve FLAC/MP3/AAC bytes and report actual available audio properties without quality guarantees.
- Keep separate editions in separate folders and persist their playlist associations.
- Export an album and M3U8 playlist, then open the exported files with another player.
- Restore a full backup at a new root with favorites, playlists, and verification records intact.
- Pass deterministic tests using mocked catalog and playback interfaces; run actual audio checks outside Docker.

## Restart handoff

Start at the first unchecked task. The remaining foundation task is dependency installation and validation; then continue to local library indexing and playback. Use the current README for setup commands and known environment limits. Recreate `.venv` after switching OS environments. Keep user music outside the repository and configure its root deliberately when moving between Windows and WSL. Preserve `AGENTS.md` and `PLAN.md`, and update both whenever project ideas or decisions change.

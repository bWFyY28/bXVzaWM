# bXVzaVM

A portable, personal music terminal app. Version **0.1.2** provides a starter Textual interface, portable settings, and SQLite storage. File indexing, playback, catalogs, and imports are still upcoming features. `bxvzm` is the Python package and command alias.

`main` is the release branch and contains the files needed to install and run the app. Development, tests, Docker checks, and editor configuration live together on [`dev`](https://github.com/bWFyY28/bXVzaWM/tree/dev).

## Install and run

Install Python **3.13** separately. Download this branch or clone it:

```sh
git clone --branch main https://github.com/bWFyY28/bXVzaWM.git
cd bXVzaWM
python install.py
python run.py
```

If `python` selects another version, use `py -3.13` on Windows or `python3.13` on Linux/macOS. Setup needs internet access and creates a local `.venv` with pinned runtime and packaging dependencies. Environment activation is unnecessary. Windows also supports `./run.cmd`.

Rerun `python install.py` after updating the code. After moving to another computer or operating system, use `python install.py --recreate` to rebuild `.venv`, preserving `data/`. Python stays separately installed. Windows and Linux setup are verified; macOS setup has not been manually tested.

## Use and portable data

The starter interface has Library, Search, Favorites, Playlists, and Imports views. Press `1` to `5` to switch views, `?` for help, and `q` to quit. Playback and import actions are not implemented yet.

```sh
python run.py --version
python run.py --check
python run.py --library data/another-library --check
```

`--check` initializes the library without opening the interface. `--library` saves a selection after successful initialization. A command-line selection overrides `BXVZM_LIBRARY`, which overrides saved preferences; the environment override is temporary. `--config PATH` selects an alternative preferences file within `data/`.

All application data and settings stay under this folder's ignored `data/` directory:

```text
bXVzaWM/
  .venv/
  data/
    config.json
    library/
      library.sqlite3
      music/
      playlists/
      .staging/
```

Move the whole application folder, including `data/`, to keep preferences and library paths portable. Saved paths are relative to the bundle. Storage outside `data/` and symlink escapes are rejected. Launchers resolve the application folder independently of the terminal's current directory. Setup uses `data/.setup-tmp` and disables global pip download caching. Application storage does not use AppData, XDG directories, or the user's Music folder.

For development or Docker checks, switch to `dev` and follow its README. Each completed version is validated, committed, and pushed to both branches; release files remain focused on installation and runtime.

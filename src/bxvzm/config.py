"""Portable preferences and storage confined to the application's data folder."""

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    """Configuration cannot safely be used."""


@dataclass(frozen=True)
class Settings:
    library_root: Path
    config_file: Path
    app_root: Path


def application_root() -> Path:
    """Locate the source bundle independently of the current working directory."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "bxvzm").is_dir():
            return parent
    return Path.cwd().resolve()


def portable_path(path: Path, app_root: Path) -> Path:
    """Interpret relative paths from the bundle and reject external/symlink escapes."""
    resolved = (path if path.is_absolute() else app_root / path).resolve()
    if not resolved.is_relative_to(app_root / "data"):
        raise ConfigurationError(f"Keep application files inside {app_root / 'data'}.")
    return resolved


def validate_library_root(root: Path, app_root: Path | None = None) -> Path:
    anchor = (app_root or application_root()).resolve()
    resolved = portable_path(root, anchor)
    if resolved.exists() and not resolved.is_dir():
        raise ConfigurationError(f"Library root is not a directory: {resolved}")
    return resolved


def load_settings(
    library_root: Path | None = None,
    config_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
    app_root: Path | None = None,
) -> Settings:
    """Precedence: command line, environment, saved selection, default."""
    env = os.environ if environ is None else environ
    anchor = (app_root or application_root()).resolve()
    config = portable_path(config_file or Path("data/config.json"), anchor)
    selection: str | Path | None = library_root or env.get("BXVZM_LIBRARY")
    if selection is None and config.exists():
        try:
            saved = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ConfigurationError(f"Cannot read preferences {config}: {error}") from error
        if not isinstance(saved, dict) or saved.get("version") != 1:
            raise ConfigurationError(f"Unsupported preferences format: {config}")
        selection = saved.get("library_root")
        if not isinstance(selection, str) or not selection.strip():
            raise ConfigurationError(f"Missing library_root in preferences: {config}")
        if Path(selection).is_absolute() or ":" in selection or "\\" in selection:
            raise ConfigurationError(f"Saved library_root must be portable and relative: {config}")
    if selection is None:
        selection = Path("data/library")
    if isinstance(selection, str) and not selection.strip():
        raise ConfigurationError("Library root must not be empty.")
    return Settings(validate_library_root(Path(selection), anchor), config, anchor)


def save_settings(settings: Settings) -> None:
    """Replace preferences atomically, saving a path relative to the bundle."""
    portable_path(settings.config_file, settings.app_root)
    root = validate_library_root(settings.library_root, settings.app_root)
    payload = {"version": 1, "library_root": root.relative_to(settings.app_root).as_posix()}
    settings.config_file.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=settings.config_file.parent,
            prefix=".config-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(settings.config_file)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

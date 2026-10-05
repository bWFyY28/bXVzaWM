"""Machine preferences, independent of the portable library."""

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


def default_config_file(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    if os.name == "nt":
        base = Path(env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(env.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "bxvzm" / "config.json"


def repository_root() -> Path | None:
    """Find a source checkout; installed wheels have no repository restriction."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "bxvzm").is_dir():
            return parent
    return None


def validate_library_root(root: Path, checkout: Path | None = None) -> Path:
    resolved = root.expanduser().resolve()
    checkout = repository_root() if checkout is None else checkout.resolve()
    if checkout is not None and resolved.is_relative_to(checkout):
        raise ConfigurationError("Choose a library root outside the source repository.")
    if resolved.exists() and not resolved.is_dir():
        raise ConfigurationError(f"Library root is not a directory: {resolved}")
    return resolved


def load_settings(
    library_root: Path | None = None,
    config_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Precedence: command line, environment, saved selection, default."""
    env = os.environ if environ is None else environ
    config = (config_file or default_config_file(env)).expanduser().resolve()
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
        if not Path(selection).is_absolute():
            raise ConfigurationError(f"Saved library_root must be absolute: {config}")
    if selection is None:
        selection = Path.home() / "Music" / "bXVzaVM"
    if isinstance(selection, str) and not selection.strip():
        raise ConfigurationError("Library root must not be empty.")
    return Settings(validate_library_root(Path(selection)), config)


def save_settings(settings: Settings) -> None:
    """Replace preferences atomically; never put an absolute root in SQLite."""
    settings.config_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "library_root": str(settings.library_root)}
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

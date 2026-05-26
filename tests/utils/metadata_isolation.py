"""Isolate library metadata JSON files from the user's ``library_data/data`` tree."""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Dict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLE_DATA_DIR = _PROJECT_ROOT / "library_data" / "data"

_METADATA_KEYS = (
    "artists_file",
    "composers_file",
    "forms_file",
    "genres_file",
    "instruments_file",
)

_EXAMPLE_NAMES = {
    "artists_file": "artists_example.json",
    "composers_file": "composers_example.json",
    "forms_file": "forms_example.json",
    "genres_file": "genres_example.json",
    "instruments_file": "instruments_example.json",
}


def copy_example_metadata_to(target_dir: Path) -> Dict[str, str]:
    """Copy example JSON files into *target_dir*; return config key → absolute path."""
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: Dict[str, str] = {}
    for key, example_name in _EXAMPLE_NAMES.items():
        src = _EXAMPLE_DATA_DIR / example_name
        if not src.is_file():
            raise FileNotFoundError(f"Missing example metadata file: {src}")
        dest = target_dir / example_name
        shutil.copy2(src, dest)
        paths[key] = str(dest.resolve())
    return paths


def apply_metadata_paths_to_config(config, paths: Dict[str, str]) -> None:
    for key, path in paths.items():
        setattr(config, key, path)
        if hasattr(config, "dict"):
            config.dict[key] = path


def reload_metadata_singletons(monkeypatch) -> None:
    """Rebuild in-memory metadata registries from the current ``config`` paths."""
    from library_data.artist import ArtistsData
    from library_data.composer import ComposersData
    from library_data.form import FormsData
    from library_data.genre import GenresData
    from library_data.instrument import InstrumentsData

    patches = {
        "library_data.composer.composers_data": ComposersData(),
        "library_data.artist.artists_data": ArtistsData(),
        "library_data.form.forms_data": FormsData(),
        "library_data.genre.genre_data": GenresData(),
        "library_data.instrument.instruments_data": InstrumentsData(),
    }
    for target, instance in patches.items():
        module_name, attr = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, attr, instance)

    import library_data.library_data as library_data_mod

    ld_module = library_data_mod
    if hasattr(ld_module, "LibraryData"):
        pass  # LibraryData() reads singletons on __init__; callers should construct fresh instances

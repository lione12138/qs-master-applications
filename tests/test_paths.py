from __future__ import annotations

import runpy
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installed_cli_resolves_data_from_repository_working_directory(
    tmp_path, monkeypatch
) -> None:
    installed_module = (
        tmp_path / "lib" / "python3.13" / "site-packages" / "gradwindow" / "paths.py"
    )
    installed_module.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "src" / "gradwindow" / "paths.py", installed_module)
    monkeypatch.chdir(ROOT)

    namespace = runpy.run_path(str(installed_module))

    assert namespace["ROOT"] == ROOT
    assert namespace["APPLICATIONS_PATH"] == ROOT / "data" / "applications.json"

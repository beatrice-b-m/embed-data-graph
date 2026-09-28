"""Build the distribution and use it from a clean environment."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from tarfile import open as open_tar
import venv
from zipfile import ZipFile

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SMOKE = """
from pathlib import Path
from importlib.metadata import version
import embed_data_graph
from embed_data_graph import load_embed

assert "site-packages" in Path(embed_data_graph.__file__).as_posix()
assert embed_data_graph.__version__ == version("embed-data-graph")
graph = load_embed(magview=[{"empi_anon": "P", "acc_anon": "A", "numfind": 1, "side": "L"}]).graph
assert graph.exam("A").findings == (graph.finding("A", "1"),)
"""


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """Build sdist and wheel from a copy of the project and install the wheel."""

    root = tmp_path_factory.mktemp("wheel")
    source = root / "project"
    shutil.copytree(
        PROJECT_ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "*_cache", "build", "dist", "*.egg-info", "__pycache__"
        ),
    )
    dist = root / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--sdist", "--no-isolation", "--outdir", str(dist)],
        cwd=source, check=True, capture_output=True, text=True,
    )
    environment = root / "env"
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    wheel = next(dist.glob("*.whl"))
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        check=True, capture_output=True, text=True,
    )
    clean = os.environ.copy()
    clean.pop("PYTHONPATH", None)
    clean.pop("MYPYPATH", None)
    return {"root": root, "dist": dist, "wheel": wheel, "python": python, "env": clean}


def test_archives_contain_package_typing_marker_and_license(installed):
    with ZipFile(installed["wheel"]) as archive:
        names = archive.namelist()
    assert "embed_data_graph/py.typed" in names
    assert any(".dist-info/" in name and Path(name).name.lower().startswith("license") for name in names)
    with open_tar(next(installed["dist"].glob("*.tar.gz"))) as archive:
        assert any(name.endswith("/src/embed_data_graph/py.typed") for name in archive.getnames())


def test_installed_package_loads_data_outside_the_checkout(installed):
    result = subprocess.run(
        [str(installed["python"]), "-c", SMOKE],
        cwd=installed["root"], env=installed["env"], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_installed_package_type_checks_the_consumer_journey(installed):
    consumer = installed["root"] / "public_api.py"
    shutil.copyfile(PROJECT_ROOT / "tests" / "typing" / "public_api.py", consumer)
    config = installed["root"] / "mypy.ini"
    config.write_text("[mypy]\npython_version = 3.9\n")
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", str(config),
         "--python-executable", str(installed["python"]), str(consumer)],
        cwd=installed["root"], env=installed["env"], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_installed_package_runs_the_researcher_example(installed):
    example = installed["root"] / "researcher_journeys.py"
    shutil.copyfile(PROJECT_ROOT / "examples" / example.name, example)
    result = subprocess.run(
        [str(installed["python"]), str(example)],
        cwd=installed["root"], env=installed["env"], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

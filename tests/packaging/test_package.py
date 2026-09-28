"""The importable package: exports, version and runnable docstring examples."""

import doctest
import importlib
from importlib.metadata import version
import pkgutil

import pytest

import embed_data_graph


MODULES = sorted(
    module.name
    for module in pkgutil.walk_packages(embed_data_graph.__path__, "embed_data_graph.")
)


def test_every_root_export_resolves():
    for name in embed_data_graph.__all__:
        assert getattr(embed_data_graph, name) is not None, name


def test_version_matches_the_distribution():
    assert embed_data_graph.__version__ == version("embed-data-graph")


@pytest.mark.parametrize("name", ["embed_data_graph", *MODULES])
def test_docstring_examples_run(name):
    module = importlib.import_module(name)
    assert doctest.testmod(module, optionflags=doctest.ELLIPSIS).failed == 0

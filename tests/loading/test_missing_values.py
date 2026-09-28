"""NaN, pd.NA, NaT and blank strings are missing values in every table."""

import numpy as np
import pandas as pd
import pytest

from embed_data_graph import load_embed

MISSING = [None, float("nan"), np.nan, pd.NA, pd.NaT, "", "   "]


@pytest.mark.parametrize("missing", MISSING, ids=repr)
def test_missing_identity_rejects_the_row(missing):
    report = load_embed(exams=[{"acc_anon": missing, "desc": "x"}])

    assert not report.graph.exams
    assert "missing_exam_identity" in {issue.code for issue in report.issues}


@pytest.mark.parametrize("missing", MISSING, ids=repr)
def test_missing_field_is_a_supplied_null_in_refresh_and_ignored_by_merge(missing):
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}]).graph

    load_embed(exams=[{"acc_anon": "A1", "desc": missing}], into=graph, mode="merge")
    assert graph.exam("A1").description == "screen"
    load_embed(exams=[{"acc_anon": "A1", "desc": missing}], into=graph)
    assert graph.exam("A1").description is None


def test_float_identifiers_from_dataframes_match_integer_ones():
    frame = pd.DataFrame([{"empi_anon": 1.0, "acc_anon": 7.0, "numfind": 1.0, "side": "L"}])
    graph = load_embed(magview=frame).graph

    assert graph.finding("7", "1") is not None and graph.patient("1") is not None


@pytest.mark.parametrize("missing", MISSING, ids=repr)
def test_missing_procedure_side_leaves_the_procedure_unresolved(missing):
    report = load_embed(
        procedures=[{"empi_anon": "P", "procdate_anon": "2020-01-01", "type": "B", "bside": missing, "acc_anon": "A"}]
    )

    assert not report.graph.procedures
    assert "incomplete_procedure_identity" in {issue.code for issue in report.issues}


@pytest.mark.parametrize("missing", MISSING, ids=repr)
def test_missing_history_flag_is_unknown_not_no(missing):
    graph = load_embed(hormone_history=[{"empi_anon": "P", "type": "H", "code": "ESTRO", "current": missing}]).graph

    (history,) = graph.patient("P").medication_history
    assert history.current is None

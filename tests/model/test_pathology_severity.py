"""EMBED pathology severity groups."""

from embed_data_graph import load_embed
from embed_data_graph.clinical.pathology import PathologySeverity


def test_severity_codes_carry_their_inverse_clinical_meaning():
    assert PathologySeverity(0) is PathologySeverity.INVASIVE_BREAST_CANCER
    assert PathologySeverity(5) is PathologySeverity.NON_BREAST_CANCER
    assert min(PathologySeverity.BENIGN, PathologySeverity.IN_SITU_BREAST_CANCER) is PathologySeverity.IN_SITU_BREAST_CANCER


def test_loaded_severity_is_labelled_and_code_six_stays_raw_only():
    def row(severity):
        return {
            "empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "bside": "L",
            "type": "B", "procdate_anon": "2020-01-02", "path1": "X", "path_severity": severity,
        }

    (labelled,) = load_embed(magview=[row(1)]).graph.pathology
    (invalid,) = load_embed(magview=[row(6)]).graph.pathology

    assert labelled.severity is PathologySeverity.IN_SITU_BREAST_CANCER
    assert (invalid.severity, invalid.raw_severity) == (None, 6)

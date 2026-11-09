"""Flat records without pandas; run with python -m examples.tabular_views."""
from embed_data_graph import load_embed


def main() -> None:
    """Inspect every assessment, including a row without a finding number."""
    graph = load_embed(magview=[
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "asses": "A", "studydate_anon": "2020-01-02"},
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": None, "asses": "S", "studydate_anon": "2020-01-02"},
    ]).graph
    assert graph.records("findings")[0]["assessment"] == "A"
    assert graph.records("unresolved")[0]["assessment"] == "S"
    assert graph.records("exams")[0]["exam_date"].year == 2020
    assert graph.table_schema("exams").columns["exam_date"] == "datetime"
    selection = graph.select(level="patient", predicate=lambda patient: patient.patient_id == "P1")
    assert selection.records("findings") == graph.records("findings")
    print("One keyed finding and one retained unkeyed assessment are visible.")


if __name__ == "__main__":
    main()

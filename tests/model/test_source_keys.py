from datetime import date, datetime

import pandas as pd

from embed_data_graph.core.source import SourceRef
from embed_data_graph.core.tables import iter_records


def test_source_keys_are_typed_and_round_trip() -> None:
    refs = [
        SourceRef("scope", "table", True),
        SourceRef("scope", "table", 1),
        SourceRef("scope", "table", 1.0),
        SourceRef("scope", "table", "1"),
        SourceRef("scope", "table", date(2020, 1, 2)),
        SourceRef("scope", "table", datetime(2020, 1, 2, 3, 4)),
        SourceRef("scope", "table", (1, "1")),
    ]

    assert len(set(refs)) == len(refs)
    assert [SourceRef.from_dict(ref.to_dict()) for ref in refs] == refs


def test_requested_duplicate_or_nullable_keys_are_not_claimed_stable() -> None:
    frame = pd.DataFrame(
        {
            "source_id": pd.Series(["same", "same", pd.NA], dtype="string"),
            "empi_anon": ["P-1", "P-2", "P-3"],
        }
    )

    records = list(iter_records(frame, key="source_id"))

    assert all(record.source_key is None for record in records)
    assert [record.issues[0].code for record in records] == [
        "duplicate_source_key",
        "duplicate_source_key",
        "unusable_source_key",
    ]


def test_unrequested_dataframe_indexes_are_not_diagnostic_identity():
    frame = pd.DataFrame({"empi_anon": ["P", "Q"]}, index=[4, 4])
    assert all(record.source_key is None for record in iter_records(frame))

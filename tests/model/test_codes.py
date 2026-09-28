"""Source codes and their decoded meanings."""

import pytest

from embed_data_graph import Code
from embed_data_graph.core.codes import Vocabulary

TABLE = Vocabulary("demo", {"B": "Biopsy", "U": "An ultrasound exam"}, delimited=True)


def test_codes_compare_by_code_not_meaning_and_never_equal_strings():
    assert Code("S", "Suspicious") == Code("S")
    assert Code("S") != "S"
    assert len({Code("S", "Suspicious"), Code("S")}) == 1


def test_str_is_the_meaning_or_the_code_when_unknown():
    assert str(Code("S", "Suspicious")) == "Suspicious"
    assert str(Code("9")) == "9"


def test_decoding_ignores_case_and_whitespace_but_keeps_the_source_code():
    code = Vocabulary("assessment", {"S": "Suspicious"}).decode(" s ")

    assert (code.code, code.meaning, code.is_known) == ("s", "Suspicious", True)


def test_unknown_code_keeps_its_code_without_a_meaning():
    code = Vocabulary("assessment", {"S": "Suspicious"}).decode("Q")

    assert (code.code, code.meaning, code.unknown, code.is_known) == ("Q", None, ("Q",), False)


def test_comma_separated_codes_decode_each_part_and_compare_unordered():
    code = TABLE.decode("B,U")

    assert code.tokens == ("B", "U")
    assert code.meaning == "Biopsy; An ultrasound exam"
    assert code == TABLE.decode("U, B")
    assert TABLE.decode("B") == Code("B")


def test_partly_unknown_list_reports_the_unknown_parts():
    code = TABLE.decode("B,ZZ")

    assert code.meaning == "Biopsy" and code.unknown == ("ZZ",) and not code.is_known


def test_blank_values_decode_to_none_and_blank_codes_are_rejected():
    assert TABLE.decode(None) is None and TABLE.decode("  ") is None
    with pytest.raises(ValueError):
        Code(" ")


def test_to_dict_is_json_ready():
    assert TABLE.decode("B,ZZ").to_dict() == {
        "code": "B,ZZ",
        "meaning": "Biopsy",
        "tokens": ["B", "ZZ"],
        "unknown": ["ZZ"],
    }

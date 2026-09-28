"""Small mutable public-API example; run from the installed project environment."""
from embed_data_graph import load_embed, validate


def main() -> None:
    graph = load_embed(magview=[{"empi_anon": "P", "acc_anon": "A", "numfind": 1, "side": "L"}]).graph
    exam = graph.exam("A")
    exam.update(description="reviewed")
    parts = graph.partition(level="exam", key=lambda obj: "reviewed")
    assert parts["reviewed"].exam("A") is not exam
    print(validate(exam))


if __name__ == "__main__":
    main()

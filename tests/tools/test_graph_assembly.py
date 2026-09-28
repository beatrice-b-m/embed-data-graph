"""The graph assembly page generator still tells the truth about the library."""

import json
import re

from tools.visualization import graph_assembly


def test_story_keeps_the_subset_and_its_objects_across_later_loads():
    stages = graph_assembly.trace_story()

    assert [stage["id"] for stage in stages] == ["clinical", "subset", "images", "registry"]
    assert stages[0]["counts"]["exam"] == 9
    assert {stage["counts"]["exam"] for stage in stages[1:]} == {3}
    assert stages[2]["issues"] == [
        {"code": "rows_outside_graph", "severity": "info", "context": {"table": "images", "rows": 24}}
    ]
    assert stages[2]["counts"]["image"] == 12 and stages[2]["counts"]["roi"] == 3
    assert [len(stage["unresolved"]) for stage in stages] == [2, 3, 3, 1]
    assert stages[1]["tracked"] == stages[2]["tracked"] == stages[3]["tracked"]


def test_scale_run_attaches_only_to_the_subset():
    scale = graph_assembly.trace_scale(40)

    assert scale["attached"] + scale["skipped"] == scale["image_rows"]
    assert scale["subset_after"]["exam"] == scale["subset_before"]["exam"]
    assert scale["subset_after"]["patient"] == scale["subset_before"]["patient"]


def test_build_writes_a_self_contained_page(tmp_path):
    out = graph_assembly.main(["--out", str(tmp_path / "page.html"), "--scale-patients", "0",
                               "--trace-json", str(tmp_path / "trace.json")])
    page = out.read_text(encoding="utf-8")

    assert "__TRACE_JSON__" not in page and "/*__BEA" not in page
    assert "--status-partial" in page and "window.Bea" in page
    data = re.search(r'<script type="application/json" id="trace">(.*?)</script>', page, re.S).group(1)
    assert json.loads(data)["stages"] == json.loads((tmp_path / "trace.json").read_text())["stages"]
    external = set(re.findall(r'(?:src|href)="(https?://[^"]+)"', page)) | set(re.findall(r'@import url\("([^"]+)"\)', page))
    assert all(url.startswith("https://fonts.googleapis.com/") for url in external)

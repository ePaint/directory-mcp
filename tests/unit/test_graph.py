import importlib.util
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "graph" / "build_graph.py"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("build_graph", _PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_to_graph_marks_self_and_groups_by_kind() -> None:
    mod = _module()
    entities = [(1, "person", "Me", 1, ""), (2, "project", "Acme", 0, "platform")]
    anchors = [(1, "slack", "U1"), (1, "email", "a@b")]
    edges = [(1, 2, "works_on")]

    graph = mod.to_graph(entities, anchors, edges)

    nodes = {n["id"]: n for n in graph["nodes"]}
    assert nodes[1]["group"] == "self" and nodes[1]["shape"] == "star"
    assert nodes[2]["group"] == "project"
    assert "email" in nodes[1]["title"] and "slack" in nodes[1]["title"]
    assert graph["edges"][0] == {"from": 1, "to": 2, "label": "works_on", "arrows": "to"}


def test_render_html_embeds_data() -> None:
    mod = _module()
    html = mod.render_html({"nodes": [{"id": 9, "label": "X"}], "edges": [], "groups": {}})
    assert '"id": 9' in html and "vis-network" in html and "__DATA__" not in html

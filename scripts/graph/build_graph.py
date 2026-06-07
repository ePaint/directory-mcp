"""Render the directory graph as a standalone HTML file (vis-network).

Reads the live directory DB and writes directory-graph.html next to this script, with the
data spliced into template.html, so it opens in a browser with no server.

    uv run python scripts/graph/build_graph.py
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text  # noqa: E402

from directory.config import Config  # noqa: E402

_GROUPS = {
    "self": "#ffd60a",
    "person": "#4f8ef7",
    "project": "#34c759",
    "team": "#ff9f0a",
    "org": "#af52de",
    "tag": "#8e8e93",
}


def to_graph(
    entities: list[tuple[int, str, str, int, str]],
    anchors: list[tuple[int, str, str]],
    edges: list[tuple[int, int, str]],
) -> dict[str, Any]:
    systems: dict[int, set[str]] = {}
    for entity_id, system, _value in anchors:
        systems.setdefault(entity_id, set()).add(system)

    nodes = []
    for entity_id, kind, name, is_self, notes in entities:
        reach = " · ".join(sorted(systems.get(entity_id, set())))
        tooltip = kind + (f"\n{reach}" if reach else "") + (f"\n\n{notes}" if notes else "")
        nodes.append({
            "id": entity_id,
            "label": name,
            "group": "self" if is_self else kind,
            "title": tooltip,
            "shape": "star" if is_self else "dot",
        })

    return {
        "nodes": nodes,
        "edges": [{"from": f, "to": t, "label": rel, "arrows": "to"} for f, t, rel in edges],
        "groups": _GROUPS,
    }


_TEMPLATE_PATH = Path(__file__).parent / "template.html"


def render_html(data: dict[str, Any]) -> str:
    return _TEMPLATE_PATH.read_text().replace("__DATA__", json.dumps(data))


def main() -> None:
    engine = create_engine(Config().database_url)
    with engine.begin() as c:
        entities = [tuple(r) for r in c.execute(
            text("select id, kind, display_name, is_self, coalesce(notes,'') from entity"))]
        anchors = [tuple(r) for r in c.execute(text("select entity_id, system, value from anchor"))]
        edges = [tuple(r) for r in c.execute(text("select from_id, to_id, type from edge"))]

    data = to_graph(entities, anchors, edges)
    out = Path(__file__).parent / "directory-graph.html"
    out.write_text(render_html(data))
    print(f"wrote {out}  ({len(data['nodes'])} nodes, {len(data['edges'])} edges)")


if __name__ == "__main__":
    main()

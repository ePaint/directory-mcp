"""Render the directory graph as a standalone HTML file (vis-network).

Reads the live directory DB and writes directory-graph.html next to this script with the
data embedded inline, so it opens in a browser with no server.

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


def render_html(data: dict[str, Any]) -> str:
    return _TEMPLATE.replace("__DATA__", json.dumps(data))


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


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>directory-mcp graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0b0e14;color:#e6e6e6}
  #net{position:absolute;inset:0}
  #panel{position:absolute;top:12px;left:12px;z-index:5;background:rgba(20,24,33,.92);
    border:1px solid #2a2f3a;border-radius:10px;padding:12px 14px;max-width:240px}
  #panel h1{font-size:14px;margin:0 0 8px}
  .row{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:13px;cursor:pointer}
  .sw{width:12px;height:12px;border-radius:3px;display:inline-block}
  #search{width:100%;box-sizing:border-box;margin-bottom:8px;padding:6px 8px;border-radius:6px;
    border:1px solid #2a2f3a;background:#0e1219;color:#e6e6e6}
  .muted{opacity:.6;font-size:11px;margin-top:8px}
</style>
</head>
<body>
<div id="panel">
  <h1>directory-mcp</h1>
  <input id="search" placeholder="focus a name…" autocomplete="off">
  <div id="legend"></div>
  <label class="row"><input type="checkbox" id="edgelabels" checked> edge labels</label>
  <div class="muted" id="stats"></div>
</div>
<div id="net"></div>
<script>
const DATA = __DATA__;
const allNodes = new vis.DataSet(DATA.nodes);
const allEdges = new vis.DataSet(DATA.edges);
const groups = {};
for (const [g, c] of Object.entries(DATA.groups))
  groups[g] = {color:{background:c,border:"#0b0e14"},font:{color:"#e6e6e6"}};
const hidden = new Set();

const net = new vis.Network(document.getElementById("net"),
  {nodes: allNodes, edges: allEdges},
  {groups,
   nodes:{borderWidth:2,size:16,font:{size:14}},
   edges:{color:{color:"#586072",highlight:"#9aa4b8"},font:{size:10,color:"#9aa4b8",strokeWidth:0},
          smooth:{type:"continuous"},arrows:{to:{scaleFactor:.5}}},
   physics:{barnesHut:{gravitationalConstant:-9000,springLength:130,springConstant:.03},stabilization:{iterations:220}},
   interaction:{hover:true,tooltipDelay:120}});

const legend = document.getElementById("legend");
for (const [g, c] of Object.entries(DATA.groups)){
  const n = DATA.nodes.filter(x=>x.group===g).length;
  if(!n) continue;
  const row=document.createElement("label"); row.className="row";
  row.innerHTML=`<input type="checkbox" checked data-g="${g}"><span class="sw" style="background:${c}"></span>${g} (${n})`;
  row.querySelector("input").onchange=(e)=>{
    e.target.checked?hidden.delete(g):hidden.add(g); applyFilter();};
  legend.appendChild(row);
}
function applyFilter(){
  allNodes.forEach(nd=>allNodes.update({id:nd.id,hidden:hidden.has(nd.group)}));
}
document.getElementById("edgelabels").onchange=(e)=>{
  const on=e.target.checked;
  allEdges.forEach(ed=>allEdges.update({id:ed.id,font:{color:on?"#9aa4b8":"rgba(0,0,0,0)"}}));
};
document.getElementById("search").oninput=(e)=>{
  const q=e.target.value.trim().toLowerCase();
  if(!q) return;
  const hit=DATA.nodes.find(n=>n.label.toLowerCase().includes(q));
  if(hit){net.focus(hit.id,{scale:1.1,animation:true}); net.selectNodes([hit.id]);}
};
document.getElementById("stats").textContent=`${DATA.nodes.length} nodes · ${DATA.edges.length} edges`;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

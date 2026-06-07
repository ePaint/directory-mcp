---
name: directory-graph
description: Render the local `directory` MCP database to an interactive graph and open it in the browser. Use when the user wants to see, visualize, or explore their directory — e.g. "show me my directory", "graph my org", "visualize the directory", "open the directory graph" — or invokes `/directory-graph`.
---

# directory-graph

Render the live directory SQLite DB to a standalone interactive vis-network graph and open it.

## Steps

1. Render from the project root:

   ```sh
   uv run python scripts/graph/build_graph.py
   ```

   It writes `scripts/graph/directory-graph.html` and prints the node/edge counts.

2. Open the file in the default browser:

   ```sh
   open scripts/graph/directory-graph.html
   ```

   (On Linux use `xdg-open`; on Windows use `start`.)

3. Report the node/edge counts from the renderer's output.

## Notes

- The rendered HTML is a full dump of the directory — it is gitignored and must never be
  committed.
- If the renderer fails because the database doesn't exist yet, the directory is empty: tell
  the user there's nothing to graph until they've recorded people/projects via the MCP.

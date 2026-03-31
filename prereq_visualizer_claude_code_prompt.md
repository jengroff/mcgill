# Claude Code Prompt — Prerequisite Chain Visualizer

## What to build

Add a D3 force-directed prerequisite chain visualizer to the McGill Course Explorer.
It renders on the CoursePage below the existing course detail card.

---

## Backend: one new endpoint only

Add to `src/mcgill/api/routes/courses.py`. Do not touch any other backend file.
Do not reuse or modify the existing `/graph/prereqs/{code}` endpoint — it returns
chains (lists of lists) which cannot represent a course that appears at multiple
depths in the prerequisite DAG (e.g. CHEM 110 required by both CHEM 212 and CHEM 130
would appear twice). The new endpoint must return deduplicated flat nodes + edges.

```python
@router.get("/graph/tree/{code}")
async def get_prerequisite_tree_graph(code: str):
    import re
    code = code.upper().replace("-", " ")
    m = re.match(r"([A-Z]{2,6})\s*(\d{3,4}[A-Z]?)", code)
    if m:
        code = f"{m.group(1)} {m.group(2)}"

    from mcgill.db.neo4j import run_query

    # Query 1: all nodes reachable from root, with shortest-path depth.
    # min(length(path)) handles nodes reachable via multiple paths.
    node_rows = await run_query(
        """
        MATCH path = (root:Course {code: $code})-[:PREREQUISITE_OF*0..4]->(n:Course)
        RETURN DISTINCT n.code AS code, n.title AS title, n.credits AS credits,
               min(length(path)) AS depth
        """,
        {"code": code},
    )

    if not node_rows:
        return {"root": code, "nodes": [], "edges": []}

    codes = [r["code"] for r in node_rows]

    # Query 2: all PREREQUISITE_OF edges where both endpoints are in the node set.
    # Pass codes as a parameter — do not interpolate into the query string.
    prereq_edges = await run_query(
        """
        MATCH (src:Course)-[:PREREQUISITE_OF]->(tgt:Course)
        WHERE src.code IN $codes AND tgt.code IN $codes
        RETURN src.code AS source, tgt.code AS target
        """,
        {"codes": codes},
    )

    # Query 3: corequisite edges within the same node set.
    coreq_edges = await run_query(
        """
        MATCH (src:Course)-[:COREQUISITE_OF]->(tgt:Course)
        WHERE src.code IN $codes AND tgt.code IN $codes
        RETURN src.code AS source, tgt.code AS target
        """,
        {"codes": codes},
    )

    nodes = [
        {
            "code": r["code"],
            "title": r["title"] or r["code"],
            "credits": r["credits"],
            "depth": r["depth"],
        }
        for r in node_rows
    ]
    edges = [
        {"source": r["source"], "target": r["target"], "type": "prerequisite"}
        for r in prereq_edges
    ] + [
        {"source": r["source"], "target": r["target"], "type": "corequisite"}
        for r in coreq_edges
    ]

    return {"root": code, "nodes": nodes, "edges": edges}
```

---

## Frontend: new component

Create `frontend/src/components/PrereqGraph.tsx`.

### Install dependency first
```bash
npm install d3 @types/d3
```

### D3/React pattern — critical

**Use the ref-owned D3 pattern.** D3 must own everything inside the SVG element.
Do not use React state to store node x/y positions. Do not call setState on simulation
ticks. The reason: D3's force simulation fires hundreds of tick callbacks asynchronously
as it cools — calling setState on each tick causes hundreds of React re-renders that
produce visible lag. Instead, D3 mutates SVG DOM attributes directly on each tick
(e.g. `nodeSelection.attr("cx", d => d.x)`), and React never sees intermediate positions.

The component structure:
- `const svgRef = useRef<SVGSVGElement>(null)`
- In `useEffect`: select `svgRef.current`, clear it with `.selectAll("*").remove()`,
  build the simulation, attach tick handler that mutates DOM directly
- Cleanup: `return () => { simulation.stop(); d3.select(svgRef.current).selectAll("*").remove() }`
- The JSX renders only `<svg ref={svgRef} />` — D3 puts everything else inside it

### Visual spec (dark theme — match existing CSS variables)

Background of SVG: transparent (parent card provides #141820 bg).

**Nodes:**
- Root node (depth === 0): circle r=28, fill `#ED1B2F`, label color `#fff`
- Depth 1: circle r=22, fill `#1c2029`, stroke `#ED1B2F` 1.5px, label color `#e8eaf0`
- Depth 2+: circle r=18, fill `#141820`, stroke `#2a2f3a` 1px, label color `#8891a4`
- Label: course code (e.g. "CHEM 212"), font-size 9px, font-family monospace,
  text-anchor middle, dominant-baseline central
- On hover: show tooltip div (position: absolute over the SVG container) with
  full title + credits. Use a React-managed tooltip state for this — it's fine to
  use React state for the tooltip since it doesn't trigger simulation re-renders.
  Attach mouseover/mouseout handlers in the D3 setup that call a ref callback.
- On click: navigate to `/course/{code}` using react-router's `useNavigate`.
  Attach click handlers in D3 setup using a ref'd navigate function.

**Edges:**
- Prerequisite: stroke `#ED1B2F`, opacity 0.35, stroke-width 1.5px
- Corequisite: stroke `#3b82f6`, opacity 0.35, stroke-width 1.5px,
  stroke-dasharray "4 3"
- All edges: arrowhead marker. Define in SVG `<defs>`:
  ```
  marker id="arrow-prereq": refX=28 (clears node radius), fill #ED1B2F opacity 0.6
  marker id="arrow-coreq": refX=28, fill #3b82f6 opacity 0.6
  ```
  Edge direction: prerequisite A→B means "A is required before B", so arrow points
  toward the course being unlocked (target).

**Force simulation:**
```js
d3.forceSimulation(nodes)
  .force("link", d3.forceLink(edges).id(d => d.code).distance(110))
  .force("charge", d3.forceManyBody().strength(-350))
  .force("center", d3.forceCenter(width / 2, height / 2))
  .force("collide", d3.forceCollide().radius(45))
```

**SVG size:** width 100% of container (read from `svgRef.current.parentElement.offsetWidth`
after mount). Height: `Math.max(400, nodes.length * 40)` px, capped at 600px.

**Empty state:** if `nodes.length === 0`, render a `<div>` (not SVG) with text
"No prerequisites found" in `--text-muted` color, centered, height 80px.

**nodes.length === 1** means only the root course itself — treat same as empty state.

---

## Frontend: update CoursePage

In `frontend/src/pages/CoursePage.tsx`:

1. Add import: `import PrereqGraph from '../components/PrereqGraph'`
2. Add to `frontend/src/api/client.ts`:
```ts
export async function fetchPrereqTree(code: string) {
  const res = await fetch(`${BASE}/api/v1/graph/tree/${encodeURIComponent(code)}`)
  return res.json()
}
```
3. Add import in CoursePage: `import { fetchPrereqTree } from '../api/client'`
4. Add state: `const [treeData, setTreeData] = useState<{root:string, nodes:any[], edges:any[]} | null>(null)`
5. In the existing `useEffect` that fetches course data, also call:
   `fetchPrereqTree(code).then(setTreeData).catch(() => {})`
6. After the closing `</div>` of the main course detail card, add:
```tsx
{treeData && treeData.nodes.length > 1 && (
  <div className="mt-4">
    <h2 className="text-xs font-medium uppercase tracking-wide mb-3"
        style={{ color: 'var(--text-muted)' }}>
      Prerequisite chain
    </h2>
    <div className="rounded-lg overflow-hidden relative"
         style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
      <PrereqGraph
        code={treeData.root}
        nodes={treeData.nodes}
        edges={treeData.edges}
      />
    </div>
  </div>
)}
```

---

## Files changed

| File | Change |
|---|---|
| `src/mcgill/api/routes/courses.py` | Add `GET /api/v1/graph/tree/{code}` endpoint |
| `frontend/src/components/PrereqGraph.tsx` | New file |
| `frontend/src/pages/CoursePage.tsx` | Add PrereqGraph section |
| `frontend/src/api/client.ts` | Add `fetchPrereqTree` |

No other files should be touched.

---

## Test cases

After implementation, verify with:

1. `CHEM 212` — should show CHEM 212 (root) → CHEM 110, CHEM 120 (depth 1).
   Two nodes at depth 1, two edges. Simple case.

2. `COMP 302` — should show a 3-level chain:
   COMP 302 (root) ← COMP 250 (depth 1) ← COMP 206 (depth 2) ← COMP 202 (depth 3).
   Verify that COMP 206 appears once even though it is a prerequisite of COMP 250
   (and might also be transitively reachable via another path).

3. A course with no prerequisites (e.g. `COMP 202`) — should show empty state,
   not an SVG with a single orphan node.

4. A cross-listed course that has prerequisites from two different departments —
   verify all prerequisite nodes render and no duplicates appear.

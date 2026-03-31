import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import * as d3 from 'd3'

interface Node {
  code: string
  title: string
  credits: number | null
  depth: number
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

interface Edge {
  source: string | Node
  target: string | Node
  type: 'prerequisite' | 'corequisite'
}

interface Props {
  code: string
  nodes: Node[]
  edges: Edge[]
}

export default function PrereqGraph({ code, nodes, edges }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const navigateRef = useRef<ReturnType<typeof useNavigate>>(null!)
  const navigate = useNavigate()
  navigateRef.current = navigate

  const [tooltip, setTooltip] = useState<{ x: number; y: number; title: string; credits: number | null } | null>(null)
  const tooltipSetRef = useRef(setTooltip)
  tooltipSetRef.current = setTooltip

  const handleClick = useCallback((nodeCode: string) => {
    navigateRef.current(`/course/${encodeURIComponent(nodeCode)}`)
  }, [])

  useEffect(() => {
    if (nodes.length <= 1) return
    const svg = svgRef.current
    if (!svg) return

    const container = svg.parentElement
    if (!container) return

    const width = container.offsetWidth
    const height = Math.min(600, Math.max(400, nodes.length * 40))
    svg.setAttribute('width', String(width))
    svg.setAttribute('height', String(height))

    const sel = d3.select(svg)
    sel.selectAll('*').remove()

    // Deep-clone data so D3 mutation doesn't affect React props
    const simNodes: Node[] = nodes.map((n) => ({ ...n }))
    const simEdges: Edge[] = edges.map((e) => ({ ...e }))

    // Defs: arrowhead markers
    const defs = sel.append('defs')

    defs
      .append('marker')
      .attr('id', 'arrow-prereq')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 28)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#ED1B2F')
      .attr('opacity', 0.6)

    defs
      .append('marker')
      .attr('id', 'arrow-coreq')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 28)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#3b82f6')
      .attr('opacity', 0.6)

    // Edges
    const linkSel = sel
      .append('g')
      .selectAll('line')
      .data(simEdges)
      .join('line')
      .attr('stroke', (d) => (d.type === 'corequisite' ? '#3b82f6' : '#ED1B2F'))
      .attr('stroke-opacity', 0.35)
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', (d) => (d.type === 'corequisite' ? '4 3' : null))
      .attr('marker-end', (d) =>
        d.type === 'corequisite' ? 'url(#arrow-coreq)' : 'url(#arrow-prereq)',
      )

    // Node groups
    const nodeSel = sel
      .append('g')
      .selectAll<SVGGElement, Node>('g')
      .data(simNodes)
      .join('g')
      .style('cursor', 'pointer')
      .on('mouseover', (event, d) => {
        const rect = container.getBoundingClientRect()
        tooltipSetRef.current({
          x: event.clientX - rect.left,
          y: event.clientY - rect.top - 10,
          title: d.title,
          credits: d.credits,
        })
      })
      .on('mouseout', () => {
        tooltipSetRef.current(null)
      })
      .on('click', (_event, d) => {
        handleClick(d.code)
      })
      .call(
        d3
          .drag<SVGGElement, Node>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )

    // Circles
    nodeSel
      .append('circle')
      .attr('r', (d) => (d.depth === 0 ? 28 : d.depth === 1 ? 22 : 18))
      .attr('fill', (d) =>
        d.depth === 0 ? '#ED1B2F' : d.depth === 1 ? '#1c2029' : '#141820',
      )
      .attr('stroke', (d) =>
        d.depth === 0 ? 'none' : d.depth === 1 ? '#ED1B2F' : '#2a2f3a',
      )
      .attr('stroke-width', (d) => (d.depth === 0 ? 0 : d.depth === 1 ? 1.5 : 1))

    // Labels
    nodeSel
      .append('text')
      .text((d) => d.code)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', '9px')
      .attr('font-family', 'monospace')
      .attr('fill', (d) =>
        d.depth === 0 ? '#fff' : d.depth === 1 ? '#e8eaf0' : '#8891a4',
      )
      .attr('pointer-events', 'none')

    // Simulation
    const simulation = d3
      .forceSimulation(simNodes)
      .force(
        'link',
        d3
          .forceLink<Node, Edge>(simEdges)
          .id((d) => d.code)
          .distance(110),
      )
      .force('charge', d3.forceManyBody().strength(-350))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(45))
      .on('tick', () => {
        linkSel
          .attr('x1', (d) => (d.source as Node).x!)
          .attr('y1', (d) => (d.source as Node).y!)
          .attr('x2', (d) => (d.target as Node).x!)
          .attr('y2', (d) => (d.target as Node).y!)

        nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
      })

    return () => {
      simulation.stop()
      d3.select(svg).selectAll('*').remove()
    }
  }, [code, nodes, edges, handleClick])

  if (nodes.length <= 1) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ color: 'var(--text-muted)', height: 80 }}
      >
        No prerequisites found
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      <svg ref={svgRef} />
      {tooltip && (
        <div
          className="rounded px-2 py-1 text-xs pointer-events-none"
          style={{
            position: 'absolute',
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, -100%)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            whiteSpace: 'nowrap',
            zIndex: 10,
          }}
        >
          {tooltip.title}
          {tooltip.credits != null && (
            <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>{tooltip.credits} cr</span>
          )}
        </div>
      )}
    </div>
  )
}

import { useMemo, useState } from "react";

/**
 * Renders draw.io pages as simple SVG with clickable nodes.
 * Clicking a node fires onNodeClick(serviceName) so parent can scroll to the
 * corresponding LLD section.
 */
export default function DiagramPreview({ pages, activeService, onNodeClick }) {
  const [activePageIdx, setActivePageIdx] = useState(0);

  const safePages = pages && pages.length > 0 ? pages : null;
  const page = safePages ? safePages[Math.min(activePageIdx, safePages.length - 1)] : { nodes: [], edges: [] };

  // Compute viewBox from nodes
  const viewBox = useMemo(() => {
    if (!page.nodes.length) return "0 0 800 600";
    const xs = page.nodes.map((n) => n.x);
    const ys = page.nodes.map((n) => n.y);
    const xMax = page.nodes.map((n) => n.x + n.w);
    const yMax = page.nodes.map((n) => n.y + n.h);
    const minX = Math.min(...xs) - 40;
    const minY = Math.min(...ys) - 40;
    const w = Math.max(...xMax) - minX + 40;
    const h = Math.max(...yMax) - minY + 40;
    return `${minX} ${minY} ${Math.max(w, 200)} ${Math.max(h, 200)}`;
  }, [page]);

  const nodeMap = useMemo(() => {
    const m = {};
    page.nodes.forEach((n) => (m[n.id] = n));
    return m;
  }, [page]);

  if (!safePages) {
    return (
      <div className="text-zinc-600 font-mono text-xs p-8 text-center">No diagram data</div>
    );
  }

  const renderNode = (n) => {
    const isAws = !!n.service;
    const isActive = activeService && n.service && n.service.toLowerCase() === activeService.toLowerCase();
    const fill = isAws ? "#18181B" : "#0F0F10";
    const stroke = isActive ? "#F59E0B" : isAws ? "#3F3F46" : "#27272A";
    const strokeWidth = isActive ? 3 : 1.2;
    const labelColor = isActive ? "#F59E0B" : isAws ? "#F4F4F5" : "#A1A1AA";

    return (
      <g
        key={n.id}
        style={{ cursor: n.service ? "pointer" : "default" }}
        onClick={() => n.service && onNodeClick?.(n.service)}
        data-testid={`diagram-node-${n.id}`}
      >
        <rect
          x={n.x}
          y={n.y}
          width={n.w}
          height={n.h}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
          rx={4}
        />
        {n.service && (
          <rect
            x={n.x}
            y={n.y}
            width={Math.max(n.w * 0.35, 40)}
            height={14}
            fill={isActive ? "#F59E0B" : "#27272A"}
          />
        )}
        {n.service && (
          <text
            x={n.x + 6}
            y={n.y + 10}
            fontFamily="JetBrains Mono, monospace"
            fontSize="8"
            fill={isActive ? "#09090B" : "#A1A1AA"}
            textTransform="uppercase"
          >
            {n.service.slice(0, 12)}
          </text>
        )}
        <text
          x={n.x + n.w / 2}
          y={n.y + n.h / 2 + 4}
          textAnchor="middle"
          fontFamily="Inter, sans-serif"
          fontSize={Math.min(12, Math.max(9, n.w / 14))}
          fill={labelColor}
          style={{ pointerEvents: "none" }}
        >
          {(n.label || n.service || "").slice(0, 22)}
        </text>
      </g>
    );
  };

  const renderEdge = (e) => {
    const src = nodeMap[e.source];
    const tgt = nodeMap[e.target];
    if (!src || !tgt) return null;
    const x1 = src.x + src.w / 2;
    const y1 = src.y + src.h / 2;
    const x2 = tgt.x + tgt.w / 2;
    const y2 = tgt.y + tgt.h / 2;
    return (
      <g key={e.id}>
        <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#52525B" strokeWidth={1.2} strokeDasharray="3 3" markerEnd="url(#arrow)" />
        {e.label && (
          <text
            x={(x1 + x2) / 2}
            y={(y1 + y2) / 2 - 4}
            textAnchor="middle"
            fontFamily="JetBrains Mono, monospace"
            fontSize="8"
            fill="#A1A1AA"
          >
            {e.label.slice(0, 18)}
          </text>
        )}
      </g>
    );
  };

  return (
    <div className="h-full flex flex-col">
      {safePages.length > 1 && (
        <div className="flex items-center gap-1 border-b border-zinc-800 px-3 py-2 overflow-x-auto">
          {safePages.map((p, i) => (
            <button
              key={p.id}
              data-testid={`diagram-tab-${i}`}
              onClick={() => setActivePageIdx(i)}
              className={`px-3 py-1 text-[10px] font-mono uppercase tracking-wider whitespace-nowrap transition-colors ${
                i === activePageIdx ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-white"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 dot-grid overflow-auto p-2">
        <svg viewBox={viewBox} className="w-full h-full min-h-[500px]" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#71717A" />
            </marker>
          </defs>
          <g>{page.edges.map(renderEdge)}</g>
          <g>{page.nodes.map(renderNode)}</g>
        </svg>
      </div>

      <div className="border-t border-zinc-800 px-3 py-2 flex items-center justify-between text-[10px] font-mono text-zinc-500">
        <span>
          {page.nodes.length} nodes · {page.edges.length} edges
        </span>
        <span className="text-amber-500">Click any AWS node →</span>
      </div>
    </div>
  );
}

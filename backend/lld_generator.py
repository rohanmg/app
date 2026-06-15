"""Claude-powered LLD generation."""
import os
import json
from typing import AsyncIterator, Dict, List

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """You are a Principal Cloud Architect generating a focused, production-grade Low-Level Design (LLD) from an AWS architecture diagram (draw.io).

Audience: senior cloud engineers, DevOps, SREs. Keep the document concise, opinionated, and actionable. Avoid filler. Aim for ~1500–2200 words total. Prefer bullets and short tables over long prose.

Output format: GitHub-flavored Markdown only. No preamble. Start directly with `# <Project Title> — Low-Level Design`.

CRITICAL: For each AWS service that appears in your text, wrap the canonical name in backticks (e.g., `EC2`, `S3`). For service-specific subsections under sections 5 or 9, use `### <Service Name>` with the anchor `<a id="svc-<servicename-lowercase>"></a>` directly before the heading so the frontend can scroll to it.

SECTIONS (mandatory, exact order, all H2):

1. ## Overview
   - 2 short paragraphs. Purpose, expected traffic profile, key non-functional requirements.
   - One-line summary of each drawio page (if multiple) — they are usually zoom-ins of the same architecture.

2. ## Components
   - Single markdown table: `Service | Role | Tier | Count`. One row per detected service.

3. ## Data Flow
   - Numbered list (max 8 steps). Each step: source → target, protocol, port, encryption. End-to-end request lifecycle.

4. ## Networking
   - VPC layout (CIDR examples), public vs private subnets, AZs, NAT/IGW/TGW, VPC endpoints.
   - Single table of inter-service links: `Source → Target | Protocol | Port | Encryption`.
   - Brief note covering relevant OSI layers (L3 routing, L4 TCP/UDP, L7 HTTP/2/gRPC/WebSocket, TLS termination) — keep to a short paragraph, not a layer-by-layer essay.

5. ## IAM & Security
   - For each compute/data service that needs a role: one short subsection `### <Service Name>` with anchor, listing the execution role and the ONE most important least-privilege policy snippet (fenced JSON, ≤15 lines).
   - Subsection `### Ingress` — bullet list: edge (CloudFront/WAF/Shield), SG/NACL highlights as a small table `Source | Port | Allow`.
   - Subsection `### Egress` — bullet list: NAT vs VPC endpoints, DNS controls, exfil mitigations.

6. ## Data Layer
   - 4–6 bullets covering schema/partition keys, replicas, backups (PITR/RTO/RPO), encryption at rest (KMS CMK vs aws-managed).

7. ## CI/CD
   - 4–6 bullets covering source → build → deploy, IaC tool, artifact store, promotion strategy (blue/green or canary), rollback.

8. ## Observability & Reliability
   - 3 short bullets each for: logs/metrics/traces, multi-AZ vs multi-region posture, top failure modes.

9. ## Cost & Optimization
   - Use the provided cost breakdown JSON (each item has `assumption` and `source`).
   - One markdown table: `Service | Count | Unit $/mo (assumption · source) | Total $/mo`.
   - 4–6 concrete optimization actions with quantified savings where possible (Graviton, Savings Plans, S3 IT, idle shutdown, request collapsing, CloudFront caching, Aurora I/O-Optimized, etc.).

10. ## Pros, Cons, Blockers
    - Three short bulleted lists under H3s: `### Pros`, `### Cons`, `### Blockers`. 3–5 bullets each. Be specific.

11. ## Recommendations
    - Prioritized P0 / P1 / P2 actions, ≤8 bullets total. Each bullet is one concrete next step.

Rules:
- No compliance section.
- Stay under ~2200 words.
- Prefer tables and bullets over paragraphs.
- Be specific about ports, protocols, and AWS service names.
"""


def _build_user_prompt(title: str, pages: List[Dict], service_counts: Dict[str, int],
                      cost_breakdown: List[Dict], total: float, xml_excerpt: str) -> str:
    pages_summary = []
    for p in pages:
        services_on_page = sorted({n.get("service") for n in p["nodes"] if n.get("service")})
        pages_summary.append({
            "name": p["name"],
            "node_count": len(p["nodes"]),
            "edge_count": len(p["edges"]),
            "detected_services": services_on_page,
            "node_labels_sample": [n["label"] for n in p["nodes"][:30] if n["label"]],
            "edge_labels_sample": [e["label"] for e in p["edges"][:20] if e.get("label")],
        })

    return f"""Generate the LLD for the AWS architecture below.

PROJECT TITLE: {title}

DETECTED SERVICES (canonical name + total count):
{json.dumps(service_counts, indent=2)}

DRAWIO PAGES (multiple pages are usually zoom-ins of the same architecture — reconcile them):
{json.dumps(pages_summary, indent=2)}

COST BREAKDOWN — use this verbatim in the Cost section. Each item carries its `assumption` and `source` (curated vs live AWS bulk JSON):
{json.dumps(cost_breakdown, indent=2)}
Approximate total: ${total}/month

RAW XML EXCERPT (first 3000 chars — for label/grouping clues only):
```xml
{xml_excerpt[:3000]}
```

Produce the focused LLD now. Markdown only. No preamble. Keep it under ~2200 words.
"""


async def generate_lld_stream(
    title: str,
    pages: List[Dict],
    service_counts: Dict[str, int],
    cost_breakdown: List[Dict],
    total_cost: float,
    xml_excerpt: str,
) -> AsyncIterator[str]:
    """Stream markdown tokens from Claude."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"lld-{title[:40]}",
        system_message=SYSTEM_PROMPT,
    ).with_model("anthropic", MODEL).with_params(max_tokens=7000)

    user_prompt = _build_user_prompt(title, pages, service_counts, cost_breakdown, total_cost, xml_excerpt)

    async for event in chat.stream_message(UserMessage(text=user_prompt)):
        if isinstance(event, TextDelta):
            yield event.content
        elif isinstance(event, StreamDone):
            break

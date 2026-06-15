"""Claude-powered LLD generation."""
import os
import json
from typing import AsyncIterator, Dict, List

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
MODEL = "claude-sonnet-4-5-20250929"

SYSTEM_PROMPT = """You are a Principal Cloud Architect generating an exhaustive, production-grade Low-Level Design (LLD) document from an AWS architecture diagram (draw.io).

Audience: senior cloud engineers, DevOps, and SREs. The output must be deeply technical, opinionated, and actionable.

Output format: GitHub-flavored Markdown ONLY. No preamble, no closing remarks. Start directly with `# <Project Title> — Low-Level Design`.

You MUST include EVERY one of the following sections in order. Use `## ` for top-level sections. For each AWS service detected, generate `### <Service Name>` blocks inside the relevant section with concrete configuration recommendations.

CRITICAL: For AWS service mentions, wrap the canonical name in backticks (e.g., `EC2`, `S3`, `RDS`) so they can be linked back to the diagram. Use HTML anchor tags `<a id="svc-<servicename-lowercase>"></a>` immediately before each `### <Service Name>` heading so the frontend can scroll to them.

SECTIONS (mandatory, in order):

1. ## Executive Summary
   - 2-3 paragraphs: purpose, traffic profile, business goals.

2. ## Architecture Overview
   - For each draw.io page/tab, write a `### Page: <Page Name>` subsection summarizing what it represents (often a zoom-in on a particular subsystem).
   - Describe how the pages relate to each other.

3. ## Component Inventory
   - Markdown table: Service | Purpose | Tier | Count
   - One row per detected service.

4. ## Networking (Layer 3 / Layer 4)
   - VPC layout, CIDR blocks, subnets (public/private/isolated), AZs, route tables.
   - NAT, IGW, TGW, VPC peering, VPC endpoints (interface/gateway).
   - Routing decisions and failure domains.

5. ## OSI 7-Layer Mapping
   - For EACH layer (L1 Physical, L2 Data Link, L3 Network, L4 Transport, L5 Session, L6 Presentation, L7 Application), describe which AWS construct operates there for this architecture, what protocols are in play (TCP/UDP/QUIC/TLS/HTTP/2/HTTP/3/gRPC/WebSocket/etc.), MTU, jumbo frames, ENA, placement groups where relevant.

6. ## Data Flow
   - Step-by-step request lifecycle (client → edge → app → data).
   - Include sequence-style numbered list. Mention protocol & port on each hop.

7. ## IAM & Authorization
   - For each compute service: execution role, instance profile, trust policy summary, least-privilege policy snippets (as fenced JSON code blocks).
   - Cross-account access, SCPs, permission boundaries, IAM Access Analyzer.
   - Authentication mechanisms (Cognito user pools/identity pools, SAML/OIDC, IAM Identity Center).

8. ## Security: Ingress
   - Edge: CloudFront, WAF rule groups, Shield Advanced, AWS Network Firewall, GuardDuty.
   - VPC: Security groups (with explicit allow rules table: protocol/port/source), NACLs.
   - TLS termination points, mTLS where applicable, certificate lifecycle (ACM).

9. ## Security: Egress
   - Egress filtering (NAT vs egress-only IGW vs VPC endpoints).
   - DNS firewall (Route 53 Resolver DNS Firewall), outbound HTTP proxies.
   - Data exfiltration controls, VPC Flow Logs, packet inspection.

10. ## Network Protocols & Ports
    - Markdown table: Source → Destination | Protocol | Port | Encryption
    - Cover every link visible in the diagram.

11. ## Data Layer Details
    - Schema choices, partition keys (DynamoDB), read replicas (RDS/Aurora), connection pooling (RDS Proxy), backups, PITR, encryption at rest (KMS CMK vs aws-managed), replication, secondary indexes.

12. ## CI/CD
    - Pipeline stages, source → build → test → deploy.
    - Tools: CodePipeline / CodeBuild / CodeDeploy / GitHub Actions / GitLab CI / ArgoCD as applicable.
    - Artifact storage (S3/ECR), promotion strategy (dev → staging → prod), blue/green & canary deploys.
    - IaC: CDK / Terraform / CloudFormation conventions.

13. ## Observability
    - Logs (CloudWatch Logs groups, retention, log subscriptions to Kinesis/OpenSearch).
    - Metrics (CloudWatch Metrics, custom EMF, namespaces).
    - Traces (X-Ray, ADOT, OpenTelemetry).
    - Dashboards & alarms with thresholds.

14. ## Reliability & Resilience
    - Multi-AZ vs multi-region.
    - RTO / RPO targets per data store.
    - Failure modes & mitigations.
    - Chaos testing approach.

15. ## Scalability
    - Auto Scaling policies (target tracking, step scaling), DynamoDB on-demand vs provisioned, RDS read replicas, EKS HPA/Cluster Autoscaler/Karpenter.

16. ## Estimated Monthly Cost
    - Use the provided cost breakdown JSON.
    - Add a `### Cost Optimization` block with concrete actions (Savings Plans, RI, Graviton, S3 IT, spot, rightsizing, idle-resource shutdown, request collapsing, CloudFront caching, Aurora I/O-Optimized vs Standard, etc.). Quantify savings where possible.

17. ## Pros
    - Bulleted list of strengths of this design.

18. ## Cons
    - Bulleted list of weaknesses and risks.

19. ## Blockers & Open Questions
    - Things the team must answer before implementation. Be specific.

20. ## Recommendations
    - Prioritized list of concrete next steps (P0 / P1 / P2).

Be thorough — aim for 2500–4500 words. No filler. Compliance is out of scope; do not produce a compliance section.
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

    return f"""Generate the Low-Level Design for the following AWS architecture.

PROJECT TITLE: {title}

DETECTED SERVICES (canonical names + count across all pages):
{json.dumps(service_counts, indent=2)}

DRAWIO PAGES (each may be a tab/zoom-in of the main diagram — treat each as part of the same architecture and reconcile them):
{json.dumps(pages_summary, indent=2)}

APPROXIMATE COST BREAKDOWN (USD/month, rule-of-thumb estimates from resource counts):
{json.dumps(cost_breakdown, indent=2)}
Approximate total: ${total}/month

RAW XML EXCERPT (first 4000 chars — use to glean labels, container/grouping cues, custom metadata):
```xml
{xml_excerpt[:4000]}
```

Produce the full LLD now. Remember: GitHub-flavored Markdown, every section, anchors before each `### <ServiceName>`, no preamble.
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
    ).with_model("anthropic", MODEL).with_params(max_tokens=8000)

    user_prompt = _build_user_prompt(title, pages, service_counts, cost_breakdown, total_cost, xml_excerpt)

    async for event in chat.stream_message(UserMessage(text=user_prompt)):
        if isinstance(event, TextDelta):
            yield event.content
        elif isinstance(event, StreamDone):
            break

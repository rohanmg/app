# Architecht — Draw.io to LLD Generator (PRD)

## Original Problem Statement
A webapp that generates a detailed Low-Level Design (LLD) from any AWS architecture diagram in draw.io.

## User Choices (locked in)
- LLM: **Claude Sonnet 4.5** (`claude-sonnet-4-5-20250929`) via Emergent Universal Key
- Input: file upload **AND** XML paste
- Output: interactive web view **+** Markdown **+** Word (.docx) **+** PDF (via print)
- Auth: simple email/password + JWT
- Cost: AWS Bulk Pricing JSON live refresh + curated SKU table + region multipliers
- Share: public read-only link per LLD, no auth required to view

## Architecture
- Backend: FastAPI + Motor + emergentintegrations + httpx
  - `/api/auth/*` (register, login, me)
  - `/api/drawio/parse` (multi-page XML parsing + AWS service detection)
  - `/api/lld/generate` (SSE stream from Claude Sonnet 4.5, persists on disconnect via asyncio.shield)
  - `/api/lld/*` (list, get, delete, find-by-title)
  - `/api/lld/:id/share` and `/api/lld/:id/share` DELETE (revoke)
  - `/api/public/lld/:token` (no-auth public viewer endpoint)
  - `/api/pricing` and `/api/pricing/refresh` (curated + live AWS Bulk JSON)
  - `/api/lld/:id/export/markdown` and `/export/docx`
- Frontend: React + Tailwind + Shadcn + Phosphor + react-markdown + framer-motion-free
  - `/`, `/login`, `/register`, `/dashboard`, `/generate`, `/lld/:id`, `/share/:token`

## Implemented
**2026-02-15 (initial MVP)**
- Email/password auth, JWT-protected routes
- Drawio XML parser (multi-page, compressed-payload safe)
- AWS service detection for 60+ services across 11 categories
- Claude Sonnet 4.5 streaming LLD generation
- Resource-based monthly cost approximation
- LLD Vault (list/delete/view) with cards
- Interactive split-pane viewer with clickable pills + nodes scrolling to anchored sections
- Multi-page drawio tabs in viewer
- Markdown + Word (.docx) export + print-to-PDF
- SSE heartbeat + shielded persistence + find-by-title recovery

**2026-02-15 (feature pass 2)**
- Public shareable read-only links per LLD with one-click create/copy/revoke
- `/share/:token` page renders LLD without auth (omits user_id and raw xml)
- AWS Pricing module: curated SKU table (Feb 2026 prices) + region multipliers (18 regions)
- Live AWS Bulk Pricing JSON fetcher for Lambda/S3/DynamoDB/SQS/SNS (no AWS creds needed)
- Region selector on Generate page + "Refresh AWS prices" button
- Per-service cost assumptions surfaced in pill tooltips and passed to Claude
- LLD output simplified to ~1500-2200 words covering the key aspects only:
  Overview, Components, Data Flow, Networking (with brief OSI mention), IAM & Security
  (Ingress + Egress), Data Layer, CI/CD, Observability & Reliability, Cost & Optimization,
  Pros/Cons/Blockers, Recommendations.

## Verified
- 24/32 backend pytest pass; 8 cascading failures from a single Emergent LLM budget cap exceeded — not a code bug (environmental).
- Frontend Playwright: 100% on auth, generate, viewer, share dialog + public page + revoke, region selector + refresh prices.

## Backlog / Next
### P1
- Pre-canned drawio examples for new users (one-click demo)
- Stripe subscription gating for >N LLDs / month (revenue)
- Per-LLD versioning + diff
- Add cost summary table directly to LLD viewer right pane (currently inside markdown)

### P2
- Improve picker accuracy for S3/DynamoDB/SQS/SNS bulk JSON SKU selection
- Optional sections (compliance, Terraform module skeleton)
- Read-only LLD comments on shared links

### P3
- Multi-cloud (Azure / GCP)
- Team workspaces with RBAC

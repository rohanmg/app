# Architecht — Draw.io to LLD Generator (PRD)

## Original Problem Statement
A webapp that generates a detailed Low-Level Design (LLD) from any AWS architecture diagram in draw.io. It should:
- Connect the dots between resources with pros/cons/blockers explained
- Cover networking, CI/CD, and all 7 OSI layers wherever possible
- Skip compliance standards for now
- Be clickable (nodes link to LLD sections)
- Include all IAM details, security concerns (ingress, egress), network protocols
- Parse all drawio tabs (zoom-ins of main entities)
- Include estimated cost optimization

## User Choices (locked in)
- LLM: **Claude Sonnet 4.5** (`claude-sonnet-4-5-20250929`) via Emergent Universal Key
- Input: file upload **AND** XML paste
- Output: interactive web view **+** Markdown **+** Word (.docx) **+** PDF (via print)
- Auth: simple email/password + JWT
- Cost: resource-based approximation **+** LLM-driven optimization advice

## Architecture
- Backend: FastAPI + Motor + emergentintegrations
  - `/api/auth/*` — register, login, me (JWT)
  - `/api/drawio/parse` — extract pages/nodes/edges/services
  - `/api/lld/generate` — SSE stream from Claude Sonnet 4.5, persists on disconnect
  - `/api/lld/*` — CRUD (list, get, delete, find-by-title)
  - `/api/lld/:id/export/markdown` and `/export/docx`
- Frontend: React + Tailwind + Shadcn + Phosphor icons
  - Landing → Login/Register → Dashboard (Vault) → Generate → LLD Viewer

## Implemented (2026-02-15)
- Email/password auth, JWT-protected routes
- Drawio XML parser (multi-page, compressed-payload safe)
- AWS service detection (60+ services, category + cost map)
- Claude Sonnet 4.5 streaming LLD generation with detailed system prompt:
  Executive Summary, Architecture Overview, Component Inventory, Networking, OSI 7-layer mapping, Data Flow, IAM, Ingress/Egress security, Network Protocols & Ports, Data Layer, CI/CD, Observability, Reliability, Scalability, Estimated Cost + Optimization, Pros/Cons/Blockers, Recommendations
- Resource-based monthly cost approximation
- LLD Vault (list/delete/view) with cards
- Interactive split-pane viewer: SVG diagram preview ↔ rendered Markdown with clickable service pills + nodes scrolling to anchored sections
- Multi-page drawio tabs in viewer
- Markdown + Word (.docx) export + print-to-PDF
- SSE streaming with heartbeat keepalive + shielded persistence + find-by-title recovery (robust to ingress idle-timeouts)

## Tested
- 20/20 backend pytest cases (auth, parse, real Claude streaming, CRUD, exports, find-by-title isolation)
- Frontend Playwright E2E: register → login → generate → viewer with pills/nodes/TOC/exports

## Backlog / Next
### P1
- Pre-canned drawio examples for new users (one-click demo)
- Stripe subscription gating for >N LLDs per month (revenue)
- Sharable read-only public link to an LLD

### P2
- AWS Pricing API integration (replace rule-of-thumb)
- Direct integration with draw.io desktop via plugin
- Diff between two LLD versions of the same architecture
- Optional sections (compliance, Terraform module skeleton)

### P3
- Multi-cloud support (Azure / GCP diagrams)
- Team/org workspace & RBAC

## Personas
1. **Cloud architect** — needs structured LLD to share with team & clients
2. **DevOps lead** — wants networking/CI/CD detail for implementation
3. **Tech lead** — wants pros/cons and blockers before committing budget

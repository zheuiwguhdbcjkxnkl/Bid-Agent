# Cross-Document Alignment Repair Implementation Plan

**Goal:** Align the six formal V1 documents and two Archify diagrams around confirmed API, database, workflow, and deployment contracts.

**Architecture:** Keep the PRD as product-scope authority, the technical plan as implementation authority, the API document as external contract, and the database document as physical-object summary. Extend only missing contract summaries; do not redesign the product or frontend.

**Tech Stack:** Markdown specifications, JSON Archify sources, Archify showcase validator.

## Global Constraints

- Preserve V1 as one government information-service procurement project and one primary package.
- Preserve five logical Agents, four Skills, four MCP domains, one MCP Server, and four human gates.
- Keep Chinese filenames and UTF-8 encoding.
- Do not introduce a standalone RAG product or expand GraphRAG into the V1 main path.
- Do not regenerate or delete existing formal deliverables.

## Tasks

- [ ] Normalize the database document H1 from 10 to 18.
- [ ] Extend the API document with consistent `/api/v1` paths and missing V1 endpoints.
- [ ] Add missing workflow, review, authoring, and handover database objects.
- [ ] Extend the business-flow diagram through manual submission registration.
- [ ] Add the explicit Caddy-to-FastAPI architecture route.
- [ ] Run UTF-8, cross-reference, and Archify validation.

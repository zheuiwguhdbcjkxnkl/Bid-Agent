# V1 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the confirmed 14-entry V1 frontend as a production-shaped Next.js application with a white-gray government-business visual system, typed Mock contracts, role-aware views, four human approval gates, and a clean path for replacing MSW with FastAPI.

**Architecture:** Create one `frontend/` Next.js App Router application organized by business feature slices. Shared contracts, API transport, authorization helpers, task polling, gate components, and UI primitives live in focused shared modules; page components consume feature services and never import fixtures directly. MSW intercepts the final `/api/v1/*` URLs so the backend can replace mocks without rewriting pages.

**Tech Stack:** Next.js App Router, React, TypeScript, CSS variables + CSS Modules, Zod, MSW, React Hook Form, Lucide React, Vitest, Testing Library, Playwright, ESLint.

## Global Constraints

- Confirmed first-level entries: global — 登录、我的工作台、项目、企业资料库、模板与规则、系统管理；project — 项目总览、文件与解析、要求与评分、响应规划、标书编制、审核与风险、交接与递交、项目记录。
- Frontend route names and business copy must follow `specs/17-技术方案与系统架构设计.md`.
- Preserve the confirmed white-gray government-business palette: `#F5F7FA`, `#FFFFFF`, `#1D2633`, `#667085`, `#DDE3EA`, `#1F5AA6`, `#153E73`, `#EAF2FB`, `#237B55`, `#B7791F`, `#C2413B`, `#A61B1B`.
- Use 6–8px radii, fine borders, restrained shadows, left-aligned dense information layout, and no purple gradients or marketing-style AI copy.
- Implement exactly 6 global entries and 8 project entries; `/projects/new` is a workflow route, not an additional first-level navigation entry.
- Use the seven representative personas: `bid_writer`, `bid_manager`, `commercial_reviewer`, `compliance_reviewer`, `material_admin`, `submission_owner`, `system_admin`.
- Every feature supports `default`, `empty`, `loading`, `error`, `readonly`, and `forbidden`; total fixed fixtures stay near 35–45.
- Fixtures use fixed IDs/timestamps, carry `[SIMULATED]`, source, version, permission, and status metadata, and never masquerade as real organizations or government projects.
- Components never import fixture objects; all data goes through `src/api` and real `/api/v1/*` paths intercepted by MSW.
- Long tasks poll every 2–3 seconds and stop on terminal state; V1 does not add SSE or WebSocket.
- Frontend permission checks improve UX only; every mutation assumes FastAPI will repeat authorization, object-scope, state, and version validation.
- Four approval gates are `REQUIREMENT_BASELINE_CONFIRMATION`, `RESPONSE_PLAN_CONFIRMATION`, `CHAPTER_DRAFT_CONFIRMATION`, and `REVIEW_RESULT_CONFIRMATION`.
- The source directory is not currently a Git repository. Do not add commit commands to execution steps; create filesystem checkpoints and initialize Git only if the user explicitly requests it.

## Target File Structure

```text
frontend/
├── package.json
├── next.config.ts
├── vitest.config.ts
├── playwright.config.ts
├── public/
└── src/
    ├── app/
    │   ├── (auth)/login/page.tsx
    │   ├── (workspace)/layout.tsx
    │   ├── (workspace)/workbench/page.tsx
    │   ├── (workspace)/projects/page.tsx
    │   ├── (workspace)/projects/new/page.tsx
    │   ├── (workspace)/projects/[projectId]/layout.tsx
    │   ├── (workspace)/projects/[projectId]/{overview,documents,requirements,response-plan,authoring,reviews,handover,records}/page.tsx
    │   ├── (workspace)/knowledge/page.tsx
    │   ├── (workspace)/templates-rules/page.tsx
    │   └── (workspace)/admin/page.tsx
    ├── api/
    │   ├── client.ts
    │   ├── errors.ts
    │   ├── polling.ts
    │   └── resources/*.ts
    ├── contracts/
    │   ├── common.ts
    │   ├── auth.ts
    │   ├── projects.ts
    │   ├── documents.ts
    │   ├── requirements.ts
    │   ├── planning.ts
    │   ├── authoring.ts
    │   ├── reviews.ts
    │   ├── handover.ts
    │   └── administration.ts
    ├── components/
    │   ├── ui/
    │   ├── layout/
    │   ├── status/
    │   ├── gates/
    │   └── feedback/
    ├── features/
    │   ├── auth/
    │   ├── workbench/
    │   ├── projects/
    │   ├── documents/
    │   ├── requirements/
    │   ├── response-plan/
    │   ├── authoring/
    │   ├── reviews/
    │   ├── handover/
    │   ├── records/
    │   ├── knowledge/
    │   ├── templates-rules/
    │   └── administration/
    ├── lib/{auth,formatting,permissions,query-state}.ts
    ├── mocks/{browser.ts,server.ts,handlers,fixtures,scenarios}/
    ├── styles/{tokens.css,globals.css}/
    └── test/{setup.ts,render.tsx}/
```

---

### Task 1: Scaffold the Frontend and Test Harness

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/page.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/smoke.test.tsx`

**Interfaces:**
- Produces: runnable `frontend` workspace with `dev`, `build`, `lint`, `test`, `test:watch`, and `test:e2e` scripts.
- Produces: `@/*` import alias and `jsdom` unit-test environment used by every later task.

- [x] **Step 1: Scaffold the App Router project**

Run from repository root:

```powershell
cmd /c npx create-next-app@latest frontend --typescript --eslint --app --src-dir --import-alias "@/*" --use-npm --no-tailwind --yes
```

Expected: `frontend/src/app/layout.tsx` and `frontend/package.json` exist; no Tailwind files are created.

- [x] **Step 2: Install the agreed frontend and testing dependencies**

```powershell
cd frontend
cmd /c npm install zod msw react-hook-form @hookform/resolvers lucide-react
cmd /c npm install -D vitest jsdom @vitejs/plugin-react @testing-library/react @testing-library/jest-dom @testing-library/user-event @playwright/test
```

- [x] **Step 3: Add the initial failing smoke test**

Create `frontend/src/test/smoke.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import Home from "@/app/page";

it("renders the platform name", () => {
  render(<Home />);
  expect(screen.getByText("投标文件智能编制与合规审核平台")).toBeInTheDocument();
});
```

- [x] **Step 4: Configure Vitest and make the smoke test pass**

Configure `vitest.config.ts` with React, `jsdom`, `@` alias, and `src/test/setup.ts`; replace the starter home page with the platform name and a link to `/login`.

Run:

```powershell
cmd /c npm test -- --run src/test/smoke.test.tsx
```

Expected: one passing test.

- [x] **Step 5: Verify the clean scaffold**

```powershell
cmd /c npm run lint
cmd /c npm run build
```

Expected: both commands exit 0. Record a filesystem checkpoint by copying the command output to `frontend/.verification/task-01.txt`.

---

### Task 2: Build Design Tokens and Shared UI Primitives

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Modify: `frontend/src/app/globals.css`
- Create: `frontend/src/components/ui/{button,badge,card,data-table,tabs,drawer,dialog,field,empty-state}.tsx`
- Create: `frontend/src/components/status/{risk-badge,stage-badge,task-status}.tsx`
- Create: `frontend/src/components/feedback/{page-loading,page-error,forbidden-state}.tsx`
- Test: `frontend/src/components/ui/ui-primitives.test.tsx`

**Interfaces:**
- Produces: `Button`, `Badge`, `Card`, `DataTable`, `Tabs`, `Drawer`, `Dialog`, and `Field` primitives.
- Produces: semantic status components that accept backend enum values rather than arbitrary colors.

- [x] **Step 1: Write failing semantic-style tests**

```tsx
it("renders a blocking risk with the danger semantic", () => {
  render(<RiskBadge level="BLOCKING" />);
  expect(screen.getByText("阻断")).toHaveAttribute("data-tone", "blocking");
});

it("keeps destructive actions distinct from primary actions", () => {
  render(<Button variant="danger">撤销</Button>);
  expect(screen.getByRole("button", { name: "撤销" })).toHaveAttribute("data-variant", "danger");
});
```

- [x] **Step 2: Define the CSS variable system**

Implement exact palette variables in `tokens.css`, plus spacing, 6px/8px radii, typography, border, focus ring, and table density tokens. Import tokens before global styles in `globals.css`.

- [x] **Step 3: Implement accessible primitives**

Use native elements and ARIA attributes. `Dialog` traps focus, `Drawer` closes on Escape, `Tabs` expose tab roles, `DataTable` uses semantic table markup, and all buttons show a visible keyboard focus ring.

- [x] **Step 4: Run component tests**

```powershell
cmd /c npm test -- --run src/components/ui/ui-primitives.test.tsx
```

Expected: all semantic and accessibility assertions pass.

- [x] **Step 5: Add a development-only component gallery**

Create `frontend/src/app/_dev/ui/page.tsx` guarded by `NODE_ENV !== "production"`; render all semantic states so the palette and density can be inspected without inventing business data.

---

### Task 3: Implement Contracts, API Transport, Polling, and MSW

**Files:**
- Create: `frontend/src/contracts/*.ts`
- Create: `frontend/src/api/{client,errors,polling}.ts`
- Create: `frontend/src/api/resources/*.ts`
- Create: `frontend/src/mocks/{browser,server}.ts`
- Create: `frontend/src/mocks/handlers/*.ts`
- Create: `frontend/src/mocks/fixtures/*.ts`
- Create: `frontend/src/mocks/scenarios/index.ts`
- Test: `frontend/src/api/client.test.ts`
- Test: `frontend/src/mocks/contracts.test.ts`

**Interfaces:**
- Produces: `apiRequest<T>(path, schema, init): Promise<T>`.
- Produces: `pollTask(taskId, options): Promise<TaskRun>` with 2500ms default interval and terminal-state stop.
- Produces: `setMockScenario(name)` for development/tests only.

- [x] **Step 1: Define common schemas first**

Create Zod schemas for `ApiError`, pagination, `AllowedAction`, `TaskRun`, source/version references, risk levels, page states, project roles, and the four gate codes. Export inferred TypeScript types from the same files.

- [x] **Step 2: Write failing transport tests**

```ts
it("throws ContractError when a response violates its Zod schema", async () => {
  server.use(http.get("/api/v1/example", () => HttpResponse.json({ bad: true })));
  await expect(apiRequest("/api/v1/example", z.object({ id: z.string() }))).rejects.toMatchObject({
    name: "ContractError",
  });
});
```

- [x] **Step 3: Implement the API client and polling**

Always send `credentials: "include"`; normalize non-2xx responses into `ApiError`; validate successful JSON with Zod; do not retry permission, validation, or external-data-blocked errors. `pollTask` stops for `SUCCEEDED`, `FAILED`, `CANCELLED`, or `PARTIAL`.

- [x] **Step 4: Build fixed scenario fixtures**

Create the seven personas and shared base scenarios. Use fixed ISO timestamps and IDs such as `project-sim-001`; include `[SIMULATED]` in display names. Page handlers must return the exact real API paths confirmed in `specs/17`.

- [x] **Step 5: Add contract tests for every handler**

For each handler, call the endpoint through `apiRequest` and parse with its exported Zod schema. Fail if a fixture omits source, version, permission, status, or required gate fields.

Run:

```powershell
cmd /c npm test -- --run src/api/client.test.ts src/mocks/contracts.test.ts
```

Expected: transport and fixture contracts pass.

---

### Task 4: Build Authentication, Permission Views, and Application Shells

**Files:**
- Create: `frontend/src/features/auth/*`
- Create: `frontend/src/lib/{auth,permissions}.ts`
- Create: `frontend/src/components/layout/{global-header,global-nav,project-sidebar,mobile-nav,user-menu}.tsx`
- Create: `frontend/src/app/(auth)/login/page.tsx`
- Create: `frontend/src/app/(workspace)/layout.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/layout.tsx`
- Test: `frontend/src/features/auth/auth.test.tsx`
- Test: `frontend/src/components/layout/navigation.test.tsx`

**Interfaces:**
- Produces: `SessionUser`, `PermissionContext`, `can(action, context): boolean`.
- Produces: shared global and project shells used by all pages.

- [ ] **Step 1: Write failing login and navigation tests**

```tsx
it("does not show system management to a bid writer", async () => {
  renderWorkspace({ persona: "bid_writer" });
  expect(screen.queryByRole("link", { name: "系统管理" })).not.toBeInTheDocument();
});

it("shows a generic login error without revealing account existence", async () => {
  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText("账号"), "unknown");
  await userEvent.type(screen.getByLabelText("密码"), "wrong");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByText("账号或密码错误，请重试")).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement login and session bootstrapping**

Use `/api/v1/auth/login`, `/logout`, and `/session`; redirect authenticated users from `/login` to `/workbench`; show first-login password change without adding self-service password recovery.

- [ ] **Step 3: Implement the six frontend permission views**

Map platform role plus project role into `authoring`, `project-management`, `review`, `material-management`, `submission`, and `system-management`. Return explicit readonly/forbidden states for object-level restrictions.

- [ ] **Step 4: Build desktop and mobile shells**

Global nav: workbench, projects, knowledge, templates/rules, admin. Project sidebar: overview, documents, requirements, response plan, authoring, reviews, handover, records. Mobile uses a drawer and keeps page title, status, and main action visible.

- [ ] **Step 5: Verify authentication and navigation**

```powershell
cmd /c npm test -- --run src/features/auth/auth.test.tsx src/components/layout/navigation.test.tsx
```

Expected: persona visibility, login errors, readonly states, and mobile navigation pass.

---

### Task 5: Deliver Workbench, Projects, New Project Wizard, and Overview

**Files:**
- Create: `frontend/src/features/workbench/*`
- Create: `frontend/src/features/projects/{list,wizard,overview}/*`
- Create: `frontend/src/app/(workspace)/workbench/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/new/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/overview/page.tsx`
- Test: `frontend/src/features/projects/projects-flow.test.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/me/workbench`, project list/create/update/member/document/ingestion endpoints, overview endpoint.
- Produces: reusable `CurrentActionCard`, `ProjectStageRail`, `TaskSummary`, and `ProjectTable`.

- [ ] **Step 1: Write the failing vertical-slice test**

```tsx
it("creates a draft project, saves members, uploads the main file, and starts ingestion", async () => {
  render(<NewProjectWizard />);
  await completeBasicInfo();
  await assignBidManager();
  await uploadMainProcurementFile();
  await userEvent.click(screen.getByRole("button", { name: "创建并启动解析" }));
  expect(await screen.findByText("解析任务已创建")).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement the personal workbench**

Render summary, ordered action items, recent projects, running tasks, and failures from one aggregate endpoint. Sort blocking, today-due, pending-gate, high-risk, then normal items.

- [ ] **Step 3: Implement project list and URL-backed filters**

Desktop uses a table and mobile uses cards. Store keyword, status, stage, manager, mine-only, and sort in URL search parameters.

- [ ] **Step 4: Implement the three-step wizard with recovery**

Persist each step through APIs, not localStorage. Create `DRAFT` after basic info; validate role separation; upload files independently; support “保存草稿” and “创建并启动解析”.

- [ ] **Step 5: Implement project overview**

Render six-stage rail, current action card, summary, blocking items, member tasks, recent changes, and running tasks. Gate actions navigate to business pages; overview never confirms a gate directly.

- [ ] **Step 6: Run the feature tests**

```powershell
cmd /c npm test -- --run src/features/projects/projects-flow.test.tsx
```

Expected: workbench ordering, filters, draft recovery, upload failure preservation, and overview readonly behavior pass.

---

### Task 6: Deliver Documents and Requirements with Gate One

**Files:**
- Create: `frontend/src/features/documents/*`
- Create: `frontend/src/features/requirements/*`
- Create: `frontend/src/components/gates/gate-panel.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/documents/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/requirements/page.tsx`
- Test: `frontend/src/features/documents/documents.test.tsx`
- Test: `frontend/src/features/requirements/requirements-gate.test.tsx`

**Interfaces:**
- Produces: generic `GatePanel` accepting `gate`, `status`, `remainingRequired`, `blockingReasons`, `expectedInputHash`, and `allowedActions`.
- Consumes: the 8 document endpoints and 10 requirement endpoints confirmed in `specs/17`.

- [ ] **Step 1: Write failing three-column document tests**

Assert that selecting a low-confidence segment updates the original preview and correction panel; critical corrections require review; a blocked multimodal call preserves OCR and shows manual handling.

- [ ] **Step 2: Implement the document workspace**

Left: files, versions, parse outline, anomaly filters. Center: readonly page preview and source highlight. Right: structured result, confidence, correction, review, and status. Poll ingestion/reparse tasks every 2500ms.

- [ ] **Step 3: Write failing requirement baseline tests**

```tsx
it("blocks requirement baseline confirmation while a critical conflict remains", () => {
  renderRequirements({ scenario: "gate-blocked" });
  expect(screen.getByRole("button", { name: "确认要求基线" })).toBeDisabled();
  expect(screen.getByText("存在 1 个未解决阻断项")).toBeInTheDocument();
});
```

- [ ] **Step 4: Implement requirements, scoring, and conflict tabs**

Use category/list/detail layout; bind every item to source/version; allow only low-risk batch confirmation; require individual confirmation for qualification, substantive, deadline, signature, score, formula, and material rules.

- [ ] **Step 5: Implement gate-one validation and confirmation**

Call validation first, display the readonly confirmation summary, then submit confirmation with `expected_input_hash`. Never expose a generic LangGraph resume button.

- [ ] **Step 6: Run both feature suites**

```powershell
cmd /c npm test -- --run src/features/documents/documents.test.tsx src/features/requirements/requirements-gate.test.tsx
```

Expected: source linkage, correction audit, conflict handling, stale baseline, and gate-one paths pass.

---

### Task 7: Deliver Response Planning and Authoring with Gates Two and Three

**Files:**
- Create: `frontend/src/features/response-plan/*`
- Create: `frontend/src/features/authoring/*`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/response-plan/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/authoring/page.tsx`
- Test: `frontend/src/features/response-plan/response-plan.test.tsx`
- Test: `frontend/src/features/authoring/authoring.test.tsx`

**Interfaces:**
- Consumes: response-plan and section/content-block endpoints confirmed in `specs/17`.
- Produces: `EvidenceCandidatePicker`, `CoverageMatrix`, `ChapterTree`, `StructuredBlockEditor`, and `VersionConflictDialog`.

- [ ] **Step 1: Write failing evidence-use and plan-gate tests**

Verify semantic matches begin as candidates, `NOT_APPLICABLE` requires a reason, missing evidence creates a task, and gate two remains disabled until owners and mappings are complete.

- [ ] **Step 2: Implement response planning tabs**

Build response matrix, scoring coverage, chapter/tasks, and gaps/conflicts. Keep subjective scoring as coverage-only and formula estimates labeled as deterministic, not predicted evaluation.

- [ ] **Step 3: Implement gate two with readonly baseline state**

Validate and confirm `RESPONSE_PLAN_CONFIRMATION`; after success, disable editing and show baseline/version metadata.

- [ ] **Step 4: Write failing authoring protection tests**

```tsx
it("does not silently replace a human-locked content block", async () => {
  renderAuthoring({ scenario: "human-locked" });
  await userEvent.click(screen.getByRole("button", { name: "局部重新生成" }));
  expect(await screen.findByText("该内容已由人工锁定")).toBeInTheDocument();
});
```

- [ ] **Step 5: Implement the structured block editor**

Support heading, paragraph, list, table, chart, pricing, citation, attachment notice, placeholder, and internal notice blocks. Show source, version, author, lock, and external-visibility metadata per block.

- [ ] **Step 6: Implement optimistic locking and gate three**

Send section version with mutations; show side-by-side conflict dialog on mismatch. Validate citations, confirmed pricing, internal-content isolation, required chapters, and blocking placeholders before `CHAPTER_DRAFT_CONFIRMATION`.

- [ ] **Step 7: Run planning and authoring tests**

```powershell
cmd /c npm test -- --run src/features/response-plan/response-plan.test.tsx src/features/authoring/authoring.test.tsx
```

Expected: evidence confirmation, plan baseline, locked content, stale citation, version conflict, and gate-three scenarios pass.

---

### Task 8: Deliver Reviews, Handover, and Project Records

**Files:**
- Create: `frontend/src/features/reviews/*`
- Create: `frontend/src/features/handover/*`
- Create: `frontend/src/features/records/*`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/reviews/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/handover/page.tsx`
- Create: `frontend/src/app/(workspace)/projects/[projectId]/records/page.tsx`
- Test: `frontend/src/features/reviews/review-flow.test.tsx`
- Test: `frontend/src/features/handover/handover-flow.test.tsx`

**Interfaces:**
- Consumes: review, risk, handover, submission, timeline, baseline, confirmation, task-run, and audit endpoints.
- Produces: `ReviewIssuePanel`, `RiskAcceptanceDialog`, `HandoverReadinessChecklist`, and `AuditTimeline`.

- [ ] **Step 1: Write failing reviewer-separation tests**

Verify an author cannot close their own issue; commercial and compliance reviewers can close only their domains; blocking risks cannot use ordinary acceptance.

- [ ] **Step 2: Implement review and risk tabs**

Build overview, issues, risks, and consistency tabs. Preserve review rounds, show source and affected chapters, and reopen stale issues after input changes.

- [ ] **Step 3: Implement gate four**

Require all review domains, zero blockers, reviewed remediation, valid citations, pricing consistency, and current input versions before `REVIEW_RESULT_CONFIRMATION`.

- [ ] **Step 4: Write failing handover gate tests**

Assert that incomplete PDF generation yields `PARTIAL` and cannot produce an effective package; password re-entry is required for internal handover; stale input revokes the package.

- [ ] **Step 5: Implement handover and submission recording**

Build readiness, package, and submission tabs. Display immutable baseline contents, hashes, receipt requirements, and explicit statement that external submission is manual.

- [ ] **Step 6: Implement the readonly project record page**

Build timeline, baselines, confirmations, task runs, and audit tabs. Allow only filtered, redacted CSV export; never expose mutation controls or complete sensitive prompts.

- [ ] **Step 7: Run review and handover tests**

```powershell
cmd /c npm test -- --run src/features/reviews/review-flow.test.tsx src/features/handover/handover-flow.test.tsx
```

Expected: separation of duties, risk acceptance, gate four, package validity, receipt recording, and readonly audit behavior pass.

---

### Task 9: Deliver Knowledge, Templates/Rules, and System Administration

**Files:**
- Create: `frontend/src/features/knowledge/*`
- Create: `frontend/src/features/templates-rules/*`
- Create: `frontend/src/features/administration/*`
- Create: `frontend/src/app/(workspace)/knowledge/page.tsx`
- Create: `frontend/src/app/(workspace)/templates-rules/page.tsx`
- Create: `frontend/src/app/(workspace)/admin/page.tsx`
- Test: `frontend/src/features/administration/support-pages.test.tsx`

**Interfaces:**
- Consumes: knowledge, template/rule/vocabulary, and admin endpoints confirmed in `specs/17`.
- Produces: versioned material table, template validation view, rule lifecycle view, user/session administration, model-profile status, health, backup, and audit panels.

- [ ] **Step 1: Write failing lifecycle and secret-display tests**

```tsx
it("never renders an API key value", () => {
  render(<ModelProfilePanel profile={configuredProfile} />);
  expect(screen.queryByText(configuredProfile.apiKey)).not.toBeInTheDocument();
  expect(screen.getByText("已配置")).toBeInTheDocument();
});
```

- [ ] **Step 2: Implement enterprise knowledge lifecycle**

Build material list, expiry queue, and usages. Preserve versions; show project-impact warnings for expired/disabled evidence; limit mutations to material administrators and reviewers.

- [ ] **Step 3: Implement templates, rules, and vocabularies**

Show validation results for placeholders, styles, loops, headers/footers, TOC, and sample rendering. Do not add Prompt/Agent/Skill/MCP management or arbitrary executable expressions.

- [ ] **Step 4: Implement system administration**

Build users/roles, model/external services, runtime status, and security/audit tabs. Support account disable, password reset, session revocation, connection testing, health and backup status; do not expose shell, restore, container, or plaintext-secret controls.

- [ ] **Step 5: Run support-page tests**

```powershell
cmd /c npm test -- --run src/features/administration/support-pages.test.tsx
```

Expected: role restrictions, lifecycle transitions, hidden secrets, service failures, capacity alerts, and readonly-admin scenarios pass.

---

### Task 10: Complete Responsive, Accessibility, E2E, and Production Verification

**Files:**
- Create: `frontend/e2e/{auth,project-flow,gates,responsive}.spec.ts`
- Modify: `frontend/src/styles/globals.css`
- Modify: all page feature styles requiring responsive fixes
- Create: `frontend/.verification/final.txt`

**Interfaces:**
- Produces: executable acceptance coverage for the full frontend-first V1 journey.
- Produces: verified production build ready for FastAPI endpoint replacement.

- [ ] **Step 1: Add Playwright authentication and navigation tests**

Test login, persona navigation visibility, desktop project navigation, and mobile drawer behavior at 390×844 and 1440×900.

- [ ] **Step 2: Add the primary project journey**

```text
login
→ create draft project
→ assign members
→ upload main document
→ observe ingestion task
→ inspect project overview
→ resolve document issue
→ confirm requirement baseline
→ confirm response plan
→ confirm chapter draft
→ confirm review result
→ generate handover package
→ record manual submission
```

Use MSW scenarios and deterministic fixtures; assert every gate blocks once before becoming confirmable.

- [ ] **Step 3: Add accessibility assertions**

Verify keyboard operation for tabs, drawers, dialogs, tables, wizard, editor controls, and gate confirmations; assert visible focus, form labels, error summaries, and non-color status text.

- [ ] **Step 4: Add responsive acceptance checks**

Desktop retains dense tables and multi-column workspaces. Mobile converts project lists to cards, uses drawers for navigation/details, and does not attempt full-scale chapter editing; show a clear desktop recommendation for complex editing.

- [ ] **Step 5: Run the complete verification suite**

```powershell
cmd /c npm run lint
cmd /c npm test -- --run
cmd /c npx playwright install chromium
cmd /c npm run test:e2e
cmd /c npm run build
```

Expected: all commands exit 0. Save full outputs and environment versions to `frontend/.verification/final.txt`.

- [ ] **Step 6: Confirm backend replacement readiness**

Disable MSW, point `NEXT_PUBLIC_API_BASE_URL` at a test FastAPI deployment, and run contract smoke tests. Every response must pass the same Zod schemas; no page may require fixture imports or `scenario` query parameters in production routes.

## Implementation Order and Checkpoints

```text
Foundation
Task 1 → Task 2 → Task 3 → Task 4

Project entry slice
Task 5

Core business closure
Task 6 → Task 7 → Task 8

Platform support
Task 9

Acceptance
Task 10
```

Each task ends with a runnable application and focused tests. Do not start all 14 pages as static shells in parallel; complete one vertical slice with contracts, handlers, permissions, page states, and tests before advancing.

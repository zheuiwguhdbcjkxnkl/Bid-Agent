# Evaluation Numeric Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add measurable minimum-release and target-excellence thresholds to the V1 evaluation and test baseline.

**Architecture:** Keep zero-tolerance gates separate from ordinary quality thresholds. Add one canonical threshold table, reference it from all nine L1 cards, and add explicit L3 performance, reliability, Token, cost, and L4 pilot-value thresholds without changing product scope.

**Tech Stack:** Markdown specification, UTF-8, PowerShell verification.

## Global Constraints

- Zero-tolerance conditions remain 100% correct or zero severe errors.
- Ordinary metrics use minimum-release and target-excellence levels.
- Metrics may not offset failures in another quality domain.
- L3 uses 15 hidden projects across five project types.
- Query peak throughput is 10 to 20 QPS and P99 is 500 milliseconds to 1 second.
- Evidence retrieval P99 is 3 to 5 seconds.
- A 100-page PDF parses asynchronously in 5 to 15 minutes.
- A complete multi-Agent review chain runs asynchronously in 10 to 30 minutes.
- L4 value thresholds remain provisional until the first five paired pilot projects establish a real baseline.

---

### Task 1: Define Canonical Threshold Policy

**Files:**
- Modify: `specs/15-评估体系与测试计划.md`

**Interfaces:**
- Consumes: Existing metric formulas and four metric categories.
- Produces: Canonical minimum-release and target-excellence tables referenced by L1, L2, L3, and L4.

- [ ] Add the three-level decision model: zero-tolerance, minimum release, target excellence.
- [ ] Add quality thresholds for ingestion, parsing, extraction, retrieval, generation, and review.
- [ ] State single-project floors and prohibit cross-domain score compensation.
- [ ] Preserve not-applicable handling for zero denominators.

### Task 2: Bind Nine L1 Cards

**Files:**
- Modify: `specs/15-评估体系与测试计划.md`

**Interfaces:**
- Consumes: Canonical threshold identifiers from Task 1.
- Produces: Explicit numeric release thresholds for L1-01 through L1-09.

- [ ] Replace every ordinary metric phrase that says it freezes after smoke testing.
- [ ] Keep deterministic and high-risk gates unchanged.
- [ ] Reference exact minimum and excellence values for each module.
- [ ] Separate observational human-adoption metrics from release blockers.

### Task 3: Add L3 Operational Thresholds

**Files:**
- Modify: `specs/15-评估体系与测试计划.md`

**Interfaces:**
- Consumes: User-confirmed latency and throughput ranges.
- Produces: Testable performance, reliability, Token, and provisional cost gates.

- [ ] Add query QPS and P99 thresholds.
- [ ] Add retrieval, PDF parsing, and Agent-chain duration thresholds.
- [ ] Add task success, recovery, idempotency, and availability thresholds.
- [ ] Add Token and variable-cost thresholds with model-selection recalibration rules.
- [ ] Add workload and sample-size requirements for performance reports.

### Task 4: Add L4 Value Thresholds

**Files:**
- Modify: `specs/15-评估体系与测试计划.md`

**Interfaces:**
- Consumes: Existing paired-pilot design.
- Produces: Provisional minimum-value and target-excellence thresholds.

- [ ] Add first-draft, review, search, and total-effort reduction targets.
- [ ] Add rework, first-pass approval, adoption, and human-takeover targets.
- [ ] Preserve zero new severe defects.
- [ ] Require policy freezing after five exploratory paired projects.

### Task 5: Verify Internal Consistency

**Files:**
- Verify: `specs/15-评估体系与测试计划.md`

**Interfaces:**
- Consumes: Updated evaluation document.
- Produces: Evidence that no vague release-threshold placeholders remain.

- [ ] Search for remaining smoke-calibration placeholder phrases.
- [ ] Verify all nine L1 sections contain numeric release thresholds.
- [ ] Verify performance ranges match the confirmed values.
- [ ] Verify no continuous question-mark encoding corruption exists.
- [ ] Verify the document still distinguishes L3 delivery acceptance from L4 business value.

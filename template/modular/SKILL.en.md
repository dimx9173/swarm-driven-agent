---
title: Swarm-Driven Development (SWDD) - Universal Framework
description: A multi-agent swarm intelligence workflow for high-quality software engineering. Features parallel planning, adversarial specification review (Crucible), and spec-driven implementation.
version: 2.7.0-self-evolving
tags: [orchestration, swarm-intelligence, workflow, architecture, quality-assurance, multi-agent]
related:
  - "SOUL Engine Runtime: [SOUL.md](../../SOUL.md)"
  - "RULE Engine Contract: [RULE.md](../../RULE.md)"
---

# Swarm-Driven Development (SWDD): Universal Framework

## 1. Overview

**Swarm-Driven Development (SWDD)** is a systematic multi-agent swarm intelligence workflow designed to solve complex engineering tasks. It focuses on **specification-first** development, using an adversarial process to "harden" architecture and design decisions before any production code is written.

Under the agent's dual-core architecture, **[SOUL.md](../../SOUL.md)** governs the top-level state machine transitions, while **SWDD** serves as the concrete **method of operation (Meta-Skill)**. SWDD guides the agent through each finite state machine (FSM) phase, ensuring structured analysis, adversarial review, and physical verification.

### Core Principles
1. **Spec-First**: Writing any production code is strictly prohibited until the architecture specification (SPEC) passes the "Crucible".
2. **Asymmetric Dialectic**: Assign isolated roles (Builder vs. Destroyer) to eliminate cognitive leniency bias.
3. **Parallel Intelligence**: Dispatch parallel, independent research swarm subagents (Alpha, Beta, Gamma) to rapidly explore the solution space.
4. **Verification-Centric**: Every state transition includes automated validation or multi-perspective verification.

---

## 2. SWDD Lifecycle & SOP Execution Directives (The SWDD Lifecycle)

The 6 conceptual phases of SWDD strictly map to the SOUL FSM Hooks defined in [RULE.md](../../RULE.md):

### PHASE 1: DESTRUCT (Parallel Research Swarm)
Dispatch parallel and completely isolated research swarm subagents (Alpha/Beta/Gamma) for multi-perspective research. Each subagent must run in an independent workspace. Information sharing or early alignment is strictly prohibited in Phase 1.
*   **Alpha Subagent (The Standard)**: Research industry best practices, standard frameworks, and mainstream canonical solutions.
*   **Beta Subagent (The Adversary)**: Focus on finding potential breaking points, including concurrency race conditions, edge-case vulnerabilities, resource leaks, technical debt, and security threats.
*   **Gamma Subagent (The Innovator)**: Seek cross-domain technical analogies and unconventional alternative solutions.

### PHASE 2: GATHER (Information Retrieval & Consolidation)
Consolidate the findings from Alpha, Beta, and Gamma. Dispatch 4 parallel retrieval subagents:
*   **Topology Discovery Subagent**: Call code graph tools to analyze AST-level dependencies and change boundaries.
*   **Memory & KB Retrieval Subagent**: Retrieve historical anti-patterns and relevant Knowledge Items (KIs).
*   **DB/Schema Probe Subagent**: Query system database tables, Redis schemas, and API contracts.
*   **Design Doc Inspector Subagent**: Inspect existing design documents, RFCs, and ADRs.
*   **Action**: Encapsulate the findings into the `<ANCHORED_MEMORY_AND_CONTEXT>` tag as the foundation for the design phase. **If the probe reveals a lack of SOP skills for the current technology or framework, you must call `swda discover` and `swda learn` to self-evolve and update the local workspace customizations.**

### PHASE 3 & 4: THE CRUCIBLE (Adversarial Specification Review & Trait Calibration)
Adversarial debate executed within the `[PHASE_3_HYPERPLAN]` state with beneficial trait calibration:
1.  **Builder Subagent (Architectural Design & Metacognitive Transparency)**: Propose a formal Architecture Specification with explicit reasoning chains and boundary assumptions. Must maintain **Alignment Persistence** without fawning or abandoning physically verified designs under pressure.
2.  **Destroyer Subagent (Crucible Review & Integrity Audit)**: Attack the Builder's specification for deadlocks and vulnerabilities, while auditing for fake green-lights, reward hacking, or deceptive reasoning.
3.  **Referee Subagent (Consensus & Rubric Governor)**: Monitor dialogue logs and grade using Rubric metrics for Metacognitive Transparency and No-Fawning Persistence. If scores stall for 2 rounds or remain FAILED at round 3, trip the circuit breaker and escalate to HITL.

### PHASE 5: SYNTHESIS (Final Blueprint & Verification Setup)
Encapsulate the Crucible-approved consensus into design documentation and implementation blueprints (stored as an ADR record), deeply combining the following contracts:
*   **Spec-Driven Contract**: Define strict API and interface contracts. List target files, modified function signatures, input/output parameters, and side effects.
*   **Test-Driven Contract**: Convert acceptance criteria into concrete test cases. Declare the target TDD test script path, specify positive, negative, and edge-case assertions (expected to fail initially in Red state), and define execution commands.

### PHASE 6: IMPLEMENT & REVIEW (Multi-Agent Implementation & Physical Execution)
1.  **Pre-Dispatch Gate**: Check if the task package contains `<ANCHORED_MEMORY_AND_CONTEXT>` and that the TDD failing script is ready. Block and retry up to 2 times, then escalate to HITL.
2.  **Sandbox Isolation**: Force implementation and testing inside temporary directories or isolated containers.
3.  **TDD Dual-Agent Execution**:
    *   **Test Writer Subagent**: Write the test script in sandbox, execute it, and verify it physically fails (Red State).
    *   **Developer Subagent**: Write production code to pass all tests (Green State) without modifying the test script.
4.  **Review & Verification (Reviewer)**: Review test coverage and code simplicity. If tests fail, run auto-debug (up to 3 retries, then escalate to HITL).

---

## 3. When to Enable SWDD

SWDD is the default, mandatory path for any code development, bug fixing, dependency changes, or configuration adjustments. Direct execution is only allowed for non-functional documentation or comment-only updates.

| Task Type | Enable SWDD? | Operational Logic |
| :--- | :---: | :--- |
| **Documentation / Comments** | No | Markdown spelling corrections or layout adjustments. |
| **Bug Fix (even 1 line)** | **Yes** | Prevent regressions, run code contract checks and tests. |
| **New Modules / Features** | **Yes** | Prevent architectural drift, define strict TDD and interface contracts. |
| **Legacy Code Refactoring** | **Yes** | Map hidden dependencies, establish AST change boundaries. |
| **Security-Critical Path** | **Yes** | Must pass Refute-or-Promote gates and sandbox PoC verification. |

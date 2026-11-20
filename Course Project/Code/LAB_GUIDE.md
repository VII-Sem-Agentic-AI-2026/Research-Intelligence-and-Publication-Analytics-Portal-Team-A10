# Lab Implementation and Demonstration Guide

This guide describes the original teaching sequence. `ENGINEERING_UPDATE.md`
defines current behavior: source agreement does not verify authors; attribution
and duplicate matches require individual authenticated review. Parallel faculty
workers are deterministic Python tasks. Local MCP now transports research reads
in Gemini report runs; see MCP.md. Automatic identity resolution is not implemented.
JSON is now a compatibility export over SQLite persistence.

## Architecture

The coordinator owns the run state, locked plan, retry budget and audit trail. Data
agents can only read through the governed connector. Faculty work fans out in
parallel, joins for deduplication and analytics, then passes a hard validation gate.
The local dashboard is a human gate: approval by the HoD, Research Dean or Research
Office is required before versioned publication.

## Labs 1–3: foundations of agency

1. **Agent vs chatbot.** `PlannerAgent.clarify` finds missing department, reporting
   year and requested metric pack. A vague prompt returns questions rather than an
   invented answer. `PlanSkill` produces a locked, editable plan after clarification.
2. **Tool-using agent.** Connector reads and `compute_h_index` are typed tool calls.
   The audit log proves the agent used them.
3. **Reusable skills.** Planning and report formatting accept schemas and work for
   any department, reporting year or metric pack.

## Labs 4–6: memory, connector and runtime

4. **Memory and retrieval.** Draft state lives under `runtime/runs`; long-term
   approved history lives under `runtime/history.json`. Retrieval filters by tags
   and ranks simple token similarity without mixing archives into live state.
5. **MCP-style connector.** `ResearchConnector` is the one governed source surface.
   It checks source consent and records provenance. Replace fixture methods with
   authorized adapters without changing agents.
6. **Controlled runtime.** Every step records intent, input, output, status and time.
   Checkpoints support resume, and the tool-call budget prevents runaway work.

## Labs 7–8: orchestration

7. **Node graph.** The executable graph is profile → parallel faculty workers →
   dashboard assembly → validation → bounded repair → human gate → publish.
8. **Parallel swarm.** Faculty units are processed using a thread pool and merged in
   stable faculty-ID order, preserving deterministic output.

## Labs 9–11: reliability

9. **Deep research/grounding.** Every publication contains source IDs, source URLs,
   retrieval dates and verification evidence. Every aggregate lists its evidence
   publication IDs.
10. **Ops resilience.** Validation diagnoses missing evidence, unverified authors,
    uncaveated metrics and premature publication. Only the failing portion is
    repaired; retries are capped and unresolved failures escalate.
11. **SDLC factory.** `AcceptanceSuite` treats the locked plan as a specification.
    A draft reaches the dashboard only with a fully green machine-readable report.

## Labs 12–14: governance and deployment

12. **Safety and governance.** Consent, role checks, approval, raw/published
    separation, audit, immutable versions and rollback are enforced in code.
13. **Discipline specialists.** The registry supports `bibliometric`,
    `collaboration`, and `altmetric` packs. Each pack returns checkable fields and
    caveats; unsupported packs fail safely.
14. **Capstone.** The CLI and browser dashboard run the same orchestrator. Demonstrate
    one complete session: create draft, inspect evidence/checks, approve, see version
    1, then rollback to a prior version if a later release exists.

## Viva/demo script

1. Run `python -m unittest discover -s tests -v` and show all lab checks passing.
2. Run `python -m publication_agent.cli demo`; note that publication stops pending
   approval.
3. Start the dashboard and open the pending run.
4. Inspect consent, cross-source evidence, duplicate proposals, h-index method,
   validation checks and audit log.
5. Approve as `Research Dean`; show the new version and published aggregate.
6. Explain that live licensed APIs plug into the connector while contracts and
   governance stay unchanged.


# Lab-wise execution architecture

Engineering update: `groq_graph.py` compiles and sequences dashboard runs;
`pipeline.py` defines dependencies and the offline path. Lab 07's named stages
are descriptive metadata, not separately compiled nodes. Repair occurs inside
Lab 10. Checkpoints now include serializable artifacts and frozen source data;
application-level resume skips completed labs. See `ENGINEERING_UPDATE.md`.

Every request now runs through fourteen separate modules under
`publication_agent/labs/`. Each module consumes named artifacts from earlier labs,
produces a serializable outcome, writes it to `RunContext.lab_results`, emits an
audit event, and checkpoints the run before the next lab starts.

| Order | File | Consumes | Produces |
|---|---|---|---|
| 01 | `lab01_agent_loop.py` | clarified request | locked plan |
| 02 | `lab02_typed_tools.py` | Lab 01 plan | typed faculty lookup |
| 03 | `lab03_reusable_skills.py` | Lab 01 plan | reusable formatter binding |
| 04 | `lab04_memory_retrieval.py` | Lab 01 plan | filtered prior-run history |
| 05 | `lab05_connector.py` | Lab 02 faculty | consented connector binding |
| 06 | `lab06_runtime.py` | Lab 05 sources | governed checkpoint and budget |
| 07 | `lab07_node_graph.py` | Lab 06 runtime | executable graph definition |
| 08 | `lab08_parallel_swarm.py` | Labs 03, 05, 07 | merged per-faculty results and draft |
| 09 | `lab09_grounding.py` | Lab 08 results | verified evidence outcome |
| 10 | `lab10_resilience.py` | Lab 09 evidence | repaired validation result |
| 11 | `lab11_sdlc_factory.py` | Lab 10 result | green acceptance build |
| 12 | `lab12_governance.py` | Lab 11 build | human approval hard stop |
| 13 | `lab13_specialists.py` | Lab 12 draft | verified metric specialist output |
| 14 | `lab14_capstone.py` | Labs 01–13 | dashboard-ready capstone run |

`pipeline.py` is the only component that sequences the labs. `contracts.py`
enforces required artifact handoffs. `PublicationOrchestrator` remains the stable
facade used by the dashboard, so the product API did not change.

Each checkpoint contains:

- the request and locked plan;
- current run status and retry count;
- faculty, publication and metric results;
- validation results;
- `lab_results.lab01` through `lab_results.lab14`;
- the assembled report and human-gate state.

If a required prior artifact is missing, execution stops with a descriptive error
instead of silently skipping a lab.

## Selectable execution

The dashboard can request any combination of labs. `LabPipeline.resolve()` expands
that selection with the minimum required dependency chain. For example, selecting
Lab 08 connects Labs 01, 02, 03, 05, 06, 07 and 08; Lab 04 is not run because its
history result is not required by Lab 08. Selecting Lab 14 connects all fourteen
labs because the capstone depends on every prior outcome.

Partial runs finish with `SELECTED_LABS_COMPLETED`. Only a chain containing the
governance stages can produce `AWAITING_APPROVAL`.

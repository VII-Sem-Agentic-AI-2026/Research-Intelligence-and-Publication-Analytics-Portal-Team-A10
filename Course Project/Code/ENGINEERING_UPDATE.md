# Engineering review implementation

Authentication update: `ACCOUNTS.md` supersedes the single-reviewer-token setup
below. The active portal uses password accounts with Faculty, HoD, Dean, Research
Office and Administrator roles. Shared-token authentication has been removed.

## Setup and migration

Use the existing virtual environment and requirements. No new packages are needed.
In the same PowerShell session used to start the server, set GEMINI_API_KEY as before.
Set PORTAL_REVIEW_TOKEN to a securely generated private token of at least 24
characters, and PORTAL_REVIEWER to the responsible person's name. Do not commit
either credential. Sign in using the reviewer token in the dashboard.

First startup imports existing JSON files into runtime/portal.sqlite3. Before
importing missing documents it writes a pre-migration-*.zip archive containing
those original files. Existing published JSON versions are retained. New approved
versions are allocated transactionally in SQLite. SQLite documents are authoritative;
editing compatibility JSON files is not a supported update mechanism after migration.
New upload originals are retained as SQLite BLOBs with filename and SHA-256 hash.
Original files uploaded before this change cannot be reconstructed retroactively.

Run `python -B -m unittest discover -s tests -v` to verify in temporary datasets.
Do not run a second server against the same runtime directory. A process lock
enforces this restriction. Requests within the local server are serialized;
faculty work inside a report remains concurrent. This favors correctness over
multi-user throughput and avoids cross-run audit mixing.

## Changes against the eleven findings

1. Scope: cumulative publications through reporting year is the default; the
   selector can restrict to publication year. Citation counts remain imported
   snapshots, not historical citations received in that year. Invalid years and
   negative citation counts are rejected on dataset writes.
2. Attribution: source corroboration and faculty identity are separate statuses.
   A reviewer must record attribution evidence for each faculty. No automated
   ORCID resolution is claimed. Names alone never automatically prove identity.
3. Authentication: private server token exchanged for an expiring HttpOnly,
   SameSite session. All data endpoints and mutations require that session.
   Approval identity is server configured. Cross-origin browser writes are blocked.
   This is a local trusted-reviewer model, not multi-account RBAC or SSO.
4. Aggregation: department totals deduplicate globally by canonical publication
   identity, while faculty lists retain their associations. SQLite contains a
   publications table and faculty_publications join table. The all-years overview
   explicitly differs in scope from a year-filtered report.
5. Concurrency: FACULTY_MAX_WORKERS defaults to 4 and is configurable. Source
   reads within a worker are sequential so this is the overall source-read cap.
   RESEARCH_TOOL_BUDGET defaults to 10000; exceeding it fails rather than hiding
   records. Twenty-faculty regression cases are included.
6. Tools: the Gemini workflow supplies a tool-backed connector to the labs. Workers
   consume LangChain tool results directly; the discarded duplicate reads are gone.
7. LLM role: the execution order stays deterministic. Gemini's plan is advisory;
   it is not an autonomous planner or agent-to-agent negotiation system. Gemini
   remains an external explanation assistant.
8. Recovery: serializable lab artifacts and a frozen source snapshot are saved.
   Resume skips completed labs and reconstructs the formatter. The API and UI
   expose resume. Recovery is at completed-lab boundaries; an interrupted Lab 08
   restarts that lab. This is application-level recovery, not restoration of a
   persistent LangGraph scheduler checkpoint. Legacy runs without snapshots cannot
   safely resume.
9. Persistence: transactional SQLite documents/releases, unique temporary export
   files, a single-server process lock and serialized request handling prevent
   overlapping local writes. SQLite connections are explicitly closed.
10. Evidence: arbitrary probability labels are replaced by match rules. Local
    references are traceability, not source authenticity. Every duplicate is
    individually accepted or rejected. Rejecting a match blocks publication and
    requires correcting inputs and regenerating. Narratives run after validation;
    numbers absent from supplied metrics cause withholding. Semantic narrative
    correctness still requires human review.
11. Tests: regressions cover reporting periods, shared papers, partial consent,
    twenty faculty, author status, duplicate rejection, migration, concurrent
    version allocation, authentication, resume and association-safe imports.

## Boundaries

Local stdio MCP transport was added subsequently; see MCP.md for the current
report-workflow connection. Live licensed source connectors remain unimplemented.
CSV exports are research data exports, not certified NIRF/NAAC submissions.
The local sign-in is not suitable for public Internet deployment. An institution
must supply its identity provider and review policy for multi-user deployment.
Individual source request cancellation, distributed workers, automatic author
resolution, historical citation snapshots and full semantic LLM evaluation remain
future work. The original publication project is outside this update.

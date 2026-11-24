# Research Intelligence and Publication Analytics Portal

Course project artifact | Division A

Repository: [Naveen-R789/Research-Intelligence-and-Publication-Analytics-Portal](https://github.com/Naveen-R789/Research-Intelligence-and-Publication-Analytics-Portal)

We built a local research portal that brings publication records, citation analytics,
source evidence and academic review into one workflow. Faculty manage their own
profiles and authorized exports; HoDs, the Dean and the Research Office review
reports before publication.

## Team members

| Name | USN | Division |
|---|---|---|
| Naveen Rajdev | 01FE23BCI061 | A |
| Vaishnavi Talwar | 01FE23BCI115 | A |
| Prachi Lagare | 01FE23BCI015 | A |
| Darshan Desai | 01FE23BCI059 | A |

## Repository contents

```text
Research-Intelligence-and-Publication-Analytics-Portal/
  README.md
  .gitignore
  Course Project/
    Code/                         Application, tests and setup documentation
    Documentation/
      Original_Problem_Statement.docx
      Final_Course_Project_Report.docx
      Verification_Results.txt
      Demonstration_Guide.md
```

The 12 assignments have been deferred and are not included in this submission
snapshot. Their overview and links must be added before the repository satisfies
the complete course submission requirements. The 14 internal project labs are
implementation stages, not a substitute for the 12 course assignments.

## Project documentation

- [Project code](Course%20Project/Code/)
- [Original problem statement](Course%20Project/Documentation/Original_Problem_Statement.docx)
- [Final course project report](Course%20Project/Documentation/Final_Course_Project_Report.docx)
- [Verification results](Course%20Project/Documentation/Verification_Results.txt)
- [Demonstration guide](Course%20Project/Documentation/Demonstration_Guide.md)
- [Detailed setup](Course%20Project/Code/README.md)
- [Current scope and acceptance rules](Course%20Project/Code/PROJECT_SCOPE.md)
- [Account roles and permissions](Course%20Project/Code/ACCOUNTS.md)
- [MCP integration](Course%20Project/Code/MCP.md)

## Problem statement

Faculty publication information is fragmented across Google Scholar, Scopus and
Web of Science. Citation snapshots can disagree, duplicate records can distort
counts, and academic staff repeatedly compile spreadsheets for institutional
review and NIRF/NAAC reporting. Departments need a consistent view that preserves
source provenance and separates proposed analytics from approved reports.

The original course brief proposes consent-based harvesting, cross-source checks,
duplicate review, citation analytics, dashboards and human approval. This release
implements the workflow over authorized source exports. Licensed live source
adapters remain future work; imported evidence does not prove live indexing status.

## Objectives

1. Collect faculty profiles, source links and consent with role-based access.
2. Normalize roster and publication exports while preserving provenance.
3. Identify duplicate candidates without silently deleting original records.
4. Calculate reproducible citation metrics with explicit reporting periods.
5. Provide auditable review, publication, versioning, rollback and CSV exports.
6. Use an external language model for advisory plans and explanations while
   keeping calculations and authorization in deterministic application code.

## Approach and architecture

The browser interface communicates with a local Python HTTP server. Authenticated
accounts determine each user's data and action scope. SQLite stores application
documents, account/session information, publication associations and published
versions; JSON files remain compatibility exports.

For AI-assisted reports, a compiled LangGraph runs the selected dependency chain
of 14 lab stages. LangChain StructuredTools call an MCP client, which starts a
local stdio MCP subprocess backed by the governed ResearchConnector. Consent
checks apply to source reads. Faculty workers execute concurrently with a bounded
worker count; dependent validation and review stages retain their sequence.

```text
Browser -> authenticated Python API -> compiled LangGraph labs
                                       -> LangChain tools
                                          -> stdio MCP -> consented source records
                                       -> deduplication and metrics
                                       -> validation -> human review -> versioned report
                                       -> Gemini advisory plan and explanation
```

The current provider is Gemini, configured through GEMINI_API_KEY or the
administrator's Configure AI form. Legacy groq_* field and module names remain
for saved-report compatibility; they do not indicate current Groq requests.
Model availability, quotas and billing depend on the user's provider account.

## Agentic AI concepts demonstrated

The portal applies the following concepts to a concrete task: turning authorized
publication records into traceable analytics and human-approved reports.

| Evaluation parameter | How we use it in this project | Implementation evidence |
|---|---|---|
| Agents | A coordinator manages the reporting goal and delegates profile checks, source reads, duplicate detection, citation analytics, formatting and validation to specialized components. The compiled LangGraph connects their outputs into a complete report workflow, with Gemini providing an advisory plan and explanation. | [Compiled workflow](Course%20Project/Code/publication_agent/groq_graph.py), [lab stages](Course%20Project/Code/publication_agent/labs/) |
| Skills | `PlanSkill` converts clarified inputs into a structured reporting plan, and `ReportFormattingSkill` assembles results into a consistent report. These reusable components work across departments, reporting years and metric packs. | [Skill implementations](Course%20Project/Code/publication_agent/core.py), [reusable skill binding](Course%20Project/Code/publication_agent/labs/lab03_reusable_skills.py) |
| MCP | The report workflow connects LangChain tools to a working local stdio MCP server. Its `faculty_profiles`, `faculty_profile` and `publications_for_faculty` tools read consented records from a frozen dataset snapshot and preserve source provenance. | [MCP integration guide](Course%20Project/Code/MCP.md), [MCP server](Course%20Project/Code/publication_agent/mcp_server.py), [protocol tests](Course%20Project/Code/tests/test_local_mcp.py) |
| Swarms | Faculty workers process independent faculty tasks concurrently with a configurable worker limit. Their results join in stable faculty-ID order before report assembly, validation and human review. This provides coordinated parallel work with explicit responsibilities and dependencies. | [Parallel faculty workflow](Course%20Project/Code/publication_agent/labs/lab08_parallel_swarm.py), [dependency pipeline](Course%20Project/Code/publication_agent/labs/pipeline.py) |
| Deep Research | Source-grounded publication analysis combines authorized Scholar, Scopus and WoS exports, preserves source IDs, URLs and retrieval dates, and checks evidence before reporting. Citation methods, duplicate proposals and source coverage make findings relevant to the research task and traceable for reviewers. | [Evidence grounding](Course%20Project/Code/publication_agent/labs/lab09_grounding.py), [source-aware explanations](Course%20Project/Code/publication_agent/narrative.py), [report validation](Course%20Project/Code/publication_agent/validation.py) |

### Supporting engineering strengths

- **Reproducible analytics:** Python computes citation metrics and validates
  numerical results independently of the language model.
- **Human oversight:** attribution evidence, duplicate decisions and authorized
  academic approval govern the release of versioned reports.
- **Tested integrations:** regression tests exercise account permissions, source
  consent, imports, metrics, the compiled graph and actual MCP protocol calls.
- **Version-controlled delivery:** GitHub stores the application, tests, original
  problem statement, setup instructions and final report together for review.

## Implementation

### Faculty intake and source data

The portal supports Faculty, HoD, Dean, Research Office and Administrator accounts.
Faculty act on their assigned profiles and uploads; HoDs are department-scoped.
Academic approval is separate from administrator account management.

Roster inputs support CSV, TSV, XLSX and JSON. Publication imports additionally
support BibTeX and RIS. Records retain source IDs, source URLs, retrieval dates and
import provenance. Malformed counts and incomplete roster rows are rejected.

### Duplicate handling and analytics

DOI and normalized title/year rules propose matches. Missing DOI conflicts require
correction rather than automatic merging. Canonical publication records retain
faculty associations so a shared paper counts once in department totals while
remaining visible to its faculty authors.

Bibliometric results include h-index, total citations and citation snapshots
grouped by publication year. Cross-source citation counts use the maximum
observed value for a canonical record, with the method stated. Source agreement
is corroboration, not proof of author identity. Human attribution evidence and
match decisions are required before publication.

Reports can include publications through a chosen year or only publications in
that year. These filters do not reconstruct citations received during that year.

### Review and release

Validation recomputes key totals, checks metric evidence and enforces current
consent. A draft must pass the review requirements before an authorized academic
reviewer publishes it. Releases are versioned and support rollback. NIRF/NAAC
CSV outputs are research data exports, not certified regulatory submissions.

## Setup and run

Use Python 3.11 or newer. On Windows PowerShell, from the repository root:

```powershell
cd "Course Project/Code"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m publication_agent.cli serve --port 8001
```

Open http://127.0.0.1:8001. On a fresh runtime, create the first administrator,
then create role-specific accounts. Configure Gemini through Configure AI or set
GEMINI_API_KEY in the server's shell. Local data controls work without AI; model
requests require a configured key. No keys or real user accounts are supplied.

## Testing and results

Run the Python suite from Course Project/Code:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

The submission verification log records the result for this exact copied source
snapshot. Tests cover calculation and import behavior, review and publication,
authorization, account/session handling, MCP tools and the compiled graph with
injected model responses. Live model availability and real institution datasets
require separate validation. See the linked report and verification log for
measured results and limitations.

## Limitations and future work

Licensed Scholar/Scopus/WoS live adapters, automatic ORCID attribution, historical
citation reconstruction, institutional SSO and certified reporting remain future
scope. The HTTP server is intended for local use. A supported institutional
deployment needs a suitable server, TLS, identity integration and access policy.

## Submission status

Project code, team details, original problem statement and final report are
included here. Assignments are deferred. Transfer to the designated organization
and submission of the approval form remain pending until the organization's
link is supplied.

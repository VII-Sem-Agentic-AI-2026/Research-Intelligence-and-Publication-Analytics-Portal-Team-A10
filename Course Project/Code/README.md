# Research Intelligence & Publication Analytics Portal

Local MCP integration: see `MCP.md`. Gemini report runs now route their LangChain
research tools through an automatically managed local stdio MCP server.

Read `PROJECT_SCOPE.md` for the current scope, acceptance rules and fixes for the
16 engineering-audit findings. Historical audit findings remain evidence of the
pre-fix version, not a description of current behavior.

The signed-in portal includes a bottom-right Gemini assistant for questions and
dashboard actions. See `ASSISTANT.md` for available actions, private histories,
secure inline forms, confirmation controls and AI-key setup.

## Engineering review update

Read `ENGINEERING_UPDATE.md` first: it supersedes older lab descriptions where
they describe verified authors, automatic duplicate approval, or MCP integration.
SQLite now stores runtime documents and canonical publication associations. JSON
files remain compatibility exports. Original files are backed up before migration.

On first opening the dashboard, create an administrator login ID and password.
The administrator creates individual Faculty, HoD, Dean and Research Office
accounts under Account management. Faculty accounts must link to an existing
faculty profile; HoDs require a department. See `ACCOUNTS.md` for permissions.
Shared reviewer tokens are no longer accepted. Sessions use one-hour HttpOnly
cookies, and disabling an account or changing its password revokes its sessions.

Reports default to publications through the requested year, using imported
citation snapshots. The scope selector also supports publications in that year
only. Each faculty attribution requires an evidence note and each proposed match
requires a decision before publication.

A standalone Chapter 14 portal that combines a governed publication-analysis
pipeline with genuine LangChain tools, a compiled LangGraph workflow, and an
external Gemini chat model. The browser dashboard supports faculty/source consent,
publication imports, evidence inspection, selectable lab execution, human
approval, versioned publishing, rollback, and NIRF/NAAC CSV exports.

The Gemini API key can be supplied through `GEMINI_API_KEY` or saved once using
Configure AI. Saved keys use Windows DPAPI encryption tied to the Windows account
running the portal and are loaded automatically on startup. The encrypted file is
`runtime/gemini-key.dpapi`; plaintext is never written to source, logs, chat history,
or browser storage. Disable AI deletes the saved key. An explicitly supplied
environment key takes precedence at startup. Gemini's free-tier availability and rate
limits depend on the account; the application does not claim unlimited or
guaranteed free usage.

## Architecture

- `publication_agent/langchain_tools.py` exposes governed faculty and publication
  reads as real LangChain `StructuredTool` instances.
- `publication_agent/groq_graph.py` compiles the selected Lab 01–14 dependency
  chain with LangGraph. Gemini supplies a constrained plan and a grounded narrative;
  deterministic code retains control of data access, metrics, validation, and
  approval.
- `publication_agent/labs/` contains the fourteen explicit lab nodes and contracts.
- `publication_agent/web.py` provides the local HTTP API and serves the dashboard.
- `runtime/` stores local drafts, audit events, conversations, and approved
  versions. It is ignored by Git.

The dashboard always uses the Gemini-backed compiled graph. Core unit tests use the
same deterministic lab contracts without network calls; the framework integration
tests inject a fake chat model and still exercise real LangChain and LangGraph.

## Setup on Windows

Install Python 3.11 or newer, then run these commands from this directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a Gemini key at `https://aistudio.google.com/api-keys`, then set it only for the
current PowerShell session:

```powershell
$env:GEMINI_API_KEY = Read-Host -MaskInput "Gemini API key"
# Optional. The default is a current production model:
$env:GEMINI_MODEL = "gemini-3.5-flash-lite"
```

Do not put the real value in `.env.example` or any tracked file.

## Run

```powershell
.\start_agent.bat
```

Open `http://127.0.0.1:8001`. You can start without an API key and configure
Gemini through the administrator's secure Configure AI form. Every analysis run
makes external Gemini requests and is
therefore subject to the account's current model permissions and rate limits.

## Verify

The complete test suite is network-free:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To smoke-test the server after setting the key:

```powershell
.\.venv\Scripts\python.exe -m publication_agent.cli serve --port 8001
```

Sign in as an administrator and use Configure AI to set the Gemini key if it was
not supplied in the environment. The overview shows whether AI is configured.

The default is `gemini-3.5-flash-lite`, listed with free input/output on the
[Gemini Developer API pricing page](https://ai.google.dev/gemini-api/docs/pricing).
Use a project on Google's free tier; an API key does not itself enforce free-only
billing. Account quotas and model availability apply. Free-tier content may be
used by Google to improve its products. The portal uses the Developer API
explicitly, with no Vertex AI or alternate-provider fallback.

For saved-report compatibility, internal `use_groq`, `groq_configured` and
`groq_explanation` names are retained. New model calls and provider metadata use
Gemini. Existing reports are not rewritten.

## Governance and data boundaries

- Source access requires explicit faculty consent.
- Imported source records retain source IDs, URLs, filenames, and retrieval dates.
- Duplicate groups are proposals until human approval; source rows are not deleted.
- Metrics and validation are deterministic and grounded in the imported records.
- Gemini is asked only to plan against the validated request and explain the verified
  report; it cannot grant consent, change evidence, approve, publish, or roll back.
- Only HoD, Research Dean, or Research Office roles can publish a green draft.
- Draft data and approved versions remain separate and auditable.

See `LAB_GUIDE.md` for the lab demonstration and `LAB_EXECUTION.md` for the
dependency and artifact handoff map.

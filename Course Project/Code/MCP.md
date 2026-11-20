# Local MCP connection

The Gemini/LangGraph report workflow now uses a local MCP subprocess through the
official Python MCP SDK. No additional network port or API key is required.

Request path:

`LangGraph labs -> LangChain tools -> MCP client -> stdio MCP server -> ResearchConnector`

The server exposes `faculty_profiles`, `faculty_profile`, and
`publications_for_faculty`. It enforces stored source consent and returns imported
records with their existing provenance. It has no approval, publishing, import,
or account-management tools. The portal's existing authorization still controls
who may start a report. A separate desktop MCP client that you configure to launch
this server can read the selected dataset; portal login sessions do not apply to
that separate client.

## Install and use

From the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Restart the portal normally after saving any current work. Each Gemini report run
automatically starts, initializes, discovers, and closes its own MCP server.
The existing offline deterministic lab runner remains available for unit tests.
The dashboard assistant's separate action tools are unchanged.

The MCP subprocess receives a temporary frozen source snapshot, preserving resume
semantics. It does not receive Gemini keys or portal credentials. Audit events named
`mcp.call` record successful protocol calls alongside the existing `tool.*` reads
in the portal audit trail. Existing source-read counters are retained.
Finished runs include `framework_evidence.mcp` with the transport and discovered
tool names. Failed MCP calls propagate as errors; there is no local-read fallback.

## Use from another MCP client

Configure a stdio server with the absolute path to this project's
`.venv\Scripts\python.exe` as `command`, the project directory as `cwd`, and:

```json
["-B", "-m", "publication_agent.mcp_server", "--data", "C:/absolute/path/to/source_data.json"]
```

Use an explicit dataset export for another client. Omitting `--data` serves the
sample fixture, not the portal's live SQLite dataset. The server loads its dataset
at startup; reconnect to pick up a new export. Do not use stdout for diagnostics:
stdio carries MCP protocol messages.

## Verify without API calls

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_local_mcp.py -v
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_framework_integration.py -v
```

The first command tests real MCP handshake, discovery, concurrent reads, frozen
snapshots, consent denial, and unknown IDs. The second runs the compiled graph
through MCP with an injected chat model; it consumes no Gemini quota.

SDK reference: https://github.com/modelcontextprotocol/python-sdk/tree/v1.x

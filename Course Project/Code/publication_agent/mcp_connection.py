"""Synchronous connector backed by a managed local MCP subprocess."""

import json
import os
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@asynccontextmanager
async def _session(data_path):
    # Deliberately do not pass Gemini keys or portal credentials to the data server.
    env = {key: os.environ[key] for key in
           ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE")
           if key in os.environ}
    env["PYTHONUTF8"] = "1"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-B", "-m", "publication_agent.mcp_server", "--data", str(data_path)],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
            await session.initialize()
            yield session


class MCPResearchConnector:
    def __init__(self, raw, portal, session):
        self.data = raw.data
        self.audit = raw.audit
        self.portal = portal
        self.session = session
        self.tool_names = {tool.name for tool in portal.call(session.list_tools).tools}
        required = {"faculty_profiles", "faculty_profile", "publications_for_faculty"}
        if not required <= self.tool_names:
            raise RuntimeError("Local MCP server is missing required research tools")

    def call(self, name, arguments):
        result = self.portal.call(self.session.call_tool, name, arguments)
        if result.isError:
            self.audit("mcp.error", {"tool": name}, {"error": True})
            message = " ".join(item.text for item in result.content if item.type == "text")
            raise RuntimeError(f"MCP tool {name} failed: {message}")
        value = result.structuredContent
        if value is None:
            value = json.loads(next(item.text for item in result.content if item.type == "text"))
        action = "tool.publications" if name == "publications_for_faculty" else "tool." + name
        self.audit(action, arguments,
                   {"count": len(value.get("records", [])), "transport": "mcp-stdio"})
        self.audit("mcp.call", {"tool": name}, {"transport": "stdio", "success": True})
        return value

    def faculty_profiles(self, department):
        return self.call("faculty_profiles", {"department": department})["records"]

    def faculty_profile(self, faculty_id):
        return self.call("faculty_profile", {"faculty_id": faculty_id})["profile"]

    def publications(self, faculty, source):
        return self.call("publications_for_faculty", {
            "faculty_id": faculty["faculty_id"], "sources": [source]})["records"]


@contextmanager
def local_research_connection(raw):
    # Preserve the workflow's frozen source snapshot, including resumed runs.
    with TemporaryDirectory(prefix="research-mcp-") as temp:
        snapshot = Path(temp) / "source.json"
        snapshot.write_text(json.dumps(raw.data, ensure_ascii=False), encoding="utf-8")
        with start_blocking_portal() as portal:
            with portal.wrap_async_context_manager(_session(snapshot)) as session:
                yield MCPResearchConnector(raw, portal, session)

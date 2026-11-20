"""Read-only research tools exposed through the official MCP stdio transport."""

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .core import DEFAULT_DATA, ResearchConnector


def create_server(data_path: Path):
    server = FastMCP("Local Research Intelligence")
    connector = ResearchConnector(data_path)

    @server.tool()
    def faculty_profiles(department: str) -> dict:
        """Read faculty profiles in one department."""
        return {"records": connector.faculty_profiles(department)}

    @server.tool()
    def faculty_profile(faculty_id: str) -> dict:
        """Read a faculty profile by its exact ID."""
        return {"profile": connector.faculty_profile(faculty_id)}

    @server.tool()
    def publications_for_faculty(faculty_id: str, sources: list[str]) -> dict:
        """Read imported publications, enforcing stored consent for every source."""
        if not sources:
            raise ValueError("At least one source is required")
        faculty = connector.faculty_profile(faculty_id)
        return {"records": [record for source in sources
                            for record in connector.publications(faculty, source)]}

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()
    create_server(args.data).run(transport="stdio")


if __name__ == "__main__":
    main()

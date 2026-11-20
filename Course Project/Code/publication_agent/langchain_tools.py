"""Real LangChain tools wrapping the governed publication connector."""

from __future__ import annotations

from langchain_core.tools import StructuredTool


def build_research_tools(connector):
    def faculty_profiles(department: str) -> list[dict]:
        """Return consented faculty profiles for one department."""
        return connector.faculty_profiles(department)

    def publications_for_faculty(faculty_id: str, sources: list[str]) -> list[dict]:
        """Return provenance-preserving publications for an approved faculty and source list."""
        faculty = connector.faculty_profile(faculty_id)
        if not sources:
            raise ValueError("At least one publication source is required")
        return [
            publication
            for source in sources
            for publication in connector.publications(faculty, source)
        ]

    return {
        "faculty_profiles": StructuredTool.from_function(
            faculty_profiles,
            name="faculty_profiles",
            description="Read consented faculty profiles for a department.",
        ),
        "publications_for_faculty": StructuredTool.from_function(
            publications_for_faculty,
            name="publications_for_faculty",
            description="Read publications for one faculty member from approved sources.",
        ),
    }

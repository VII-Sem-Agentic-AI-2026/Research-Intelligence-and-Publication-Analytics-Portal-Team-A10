"""Protocol integration tests: launch a real local MCP process, without Gemini."""
import unittest
from concurrent.futures import ThreadPoolExecutor

from publication_agent.core import ResearchConnector
from publication_agent.mcp_connection import local_research_connection


class LocalMCPTests(unittest.TestCase):
    def test_discovery_reads_and_parallel_workers_use_real_stdio_session(self):
        events = []
        raw = ResearchConnector(audit=lambda *args: events.append(args))
        with local_research_connection(raw) as connector:
            self.assertEqual(connector.tool_names, {
                "faculty_profiles", "faculty_profile", "publications_for_faculty"})
            profiles = connector.faculty_profiles("CSE")
            self.assertEqual(profiles, raw.faculty_profiles("CSE"))
            with ThreadPoolExecutor(max_workers=3) as pool:
                results = list(pool.map(
                    lambda source: connector.publications(profiles[0], source),
                    ["scholar", "scopus", "wos"]))
            self.assertTrue(all(results))
            self.assertEqual(connector.faculty_profile(profiles[0]["faculty_id"]), profiles[0])
        self.assertTrue(any(event[0] == "mcp.call" for event in events))
        self.assertEqual(sum(event[0] == "tool.publications" for event in events), 3)

    def test_server_enforces_stored_consent_even_if_client_claims_consent(self):
        raw = ResearchConnector()
        faculty = raw.data["faculty"][0]
        faculty["consent"]["scholar"] = False
        forged = dict(faculty, consent={"scholar": True})
        with local_research_connection(raw) as connector:
            with self.assertRaisesRegex(RuntimeError, "consent"):
                connector.publications(forged, "scholar")
            with self.assertRaisesRegex(RuntimeError, "Unknown faculty"):
                connector.faculty_profile("DOES-NOT-EXIST")

    def test_connection_preserves_in_memory_snapshot(self):
        raw = ResearchConnector()
        raw.data["faculty"][0]["name"] = "Frozen snapshot name"
        with local_research_connection(raw) as connector:
            self.assertEqual(connector.faculty_profile(raw.data["faculty"][0]["faculty_id"])["name"],
                             "Frozen snapshot name")


if __name__ == "__main__":
    unittest.main()

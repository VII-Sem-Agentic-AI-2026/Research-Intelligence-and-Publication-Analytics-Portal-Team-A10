import json
import unittest

from publication_agent.importers import parse_faculty_roster, parse_publication_export


class ExportImporterTests(unittest.TestCase):
    def test_csv_roster(self):
        data=b"Faculty ID,Full Name,Department\nF100,Dr Meera Nair,CSE\n"
        rows=parse_faculty_roster("faculty.csv",data)
        self.assertEqual(rows[0]["faculty_id"],"F100")
        self.assertFalse(rows[0]["consent"]["scholar"])

    def test_csv_publications_are_normalized_with_provenance(self):
        data=b"Title,Year,DOI,Cited by,Authors,URL,EID\nAgent Systems,2025,10.1/x,7,A One;B Two,https://example.test/x,SC-1\n"
        rows=parse_publication_export("F100_Scopus.csv",data,"scopus","F100")
        self.assertEqual(rows[0]["citations"],7)
        self.assertEqual(rows[0]["source"],"scopus")
        self.assertEqual(rows[0]["import_file"],"F100_Scopus.csv")

    def test_ris_publication(self):
        data=b"TY  - JOUR\nTI  - Reliable Agents\nAU  - Nair, Meera\nPY  - 2024\nDO  - 10.1/ris\nTC  - 5\nUR  - https://example.test/ris\nER  - \n"
        rows=parse_publication_export("F100_WoS.ris",data,"wos","F100")
        self.assertEqual(rows[0]["title"],"Reliable Agents")
        self.assertEqual(rows[0]["year"],2024)

    def test_bibtex_publication(self):
        data=b"@article{key1,\n title={Publication Intelligence},\n author={One, A and Two, B},\n year={2023},\n doi={10.1/bib},\n url={https://example.test/bib}\n}\n"
        rows=parse_publication_export("F100_Scholar.bib",data,"scholar","F100")
        self.assertEqual(rows[0]["doi"],"10.1/bib")
        self.assertEqual(rows[0]["source_id"],"key1")

    def test_json_roster(self):
        data=json.dumps({"faculty":[{"Faculty ID":"F101","Full Name":"Dr Arun","Department":"ECE"}]}).encode()
        self.assertEqual(parse_faculty_roster("roster.json",data)[0]["department"],"ECE")


if __name__ == "__main__": unittest.main(verbosity=2)

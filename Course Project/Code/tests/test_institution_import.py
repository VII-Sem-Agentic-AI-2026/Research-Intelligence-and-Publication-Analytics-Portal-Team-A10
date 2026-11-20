import csv
import io
import unittest
from publication_agent.institution_import import prepare_institution_import
from publication_agent.validation import validate_dataset
from publication_agent.core import ResearchConnector,FacultyWorker

FIELDS=['faculty_id','faculty_name','department','source','publication_title','publication_year','citation_count','authors','doi','publication_source_url','retrieval_date','source_record_id','vidwan_publication_id','citation_count_origin','direct_source_verified']
def content(records):
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=FIELDS);writer.writeheader()
    for record in records:writer.writerow(record)
    return output.getvalue().encode()
def record(**changes):
    row=dict.fromkeys(FIELDS,'')
    row.update(faculty_id='VIDWAN-1',faculty_name='Synthetic Faculty',department='CSE',source='Google Scholar',publication_title='Synthetic Study',publication_year='2025',citation_count='7',authors='A One, B Two',doi='10.1234/synthetic',publication_source_url='https://scholar.google.com/citations?user=SYNTHETIC&citation_for_view=SYNTHETIC:x',retrieval_date='2026-10-26',source_record_id='SYNTHETIC:x',citation_count_origin='Direct Scholar as supplied',direct_source_verified='Yes')
    row.update(changes);return row

class InstitutionImportTests(unittest.TestCase):
    def empty(self):return {'faculty':[],'publications':[]}
    def test_consent_confirmation_required(self):
        with self.assertRaises(ValueError):prepare_institution_import(content([record()]),self.empty(),'x.csv')
    def test_complete_direct_record_and_profile_consent(self):
        data,summary=prepare_institution_import(content([record()]),self.empty(),'x.csv',True)
        self.assertEqual(summary['report_eligible'],1)
        self.assertTrue(data['faculty'][0]['consent']['scholar'])
        self.assertEqual(data['faculty'][0]['import_consent']['status'],'confirmed_by_user')
        self.assertEqual(data['publications'][0]['citations'],7)
        self.assertEqual(data['publications'][0]['source_metadata']['publication_title'],'Synthetic Study')
    def test_missing_values_are_preserved_without_entering_metrics(self):
        data,summary=prepare_institution_import(content([record(publication_year='',citation_count='')]),self.empty(),'x.csv',True)
        self.assertEqual(summary['needs_review'],1);self.assertEqual(data['publications'],[])
        p=data['pending_publications'][0];self.assertIsNone(p['year']);self.assertIsNone(p['citations'])
        connector=ResearchConnector();connector.data=data
        result=FacultyWorker(connector,'bibliometric',{'reporting_year':2026}).step(data['faculty'][0])
        self.assertEqual(result['publications'],[])
    def test_indirect_scopus_and_vidwan_do_not_create_false_corroboration(self):
        rows=[record(),record(source='Scopus',source_record_id='',direct_source_verified='No',publication_source_url='https://vidwan.inflibnet.ac.in/publication/123',vidwan_publication_id='123',citation_count_origin='Scopus count displayed by Vidwan'),record(source='Vidwan',source_record_id='VID-2',citation_count='',direct_source_verified='Yes (Vidwan only)',publication_source_url='https://vidwan.inflibnet.ac.in/publication/124')]
        data,summary=prepare_institution_import(content(rows),self.empty(),'x.csv',True)
        self.assertEqual(summary['imported_rows'],3);self.assertEqual(summary['needs_review'],2)
        connector=ResearchConnector();connector.data=data
        result=FacultyWorker(connector,'bibliometric',{'reporting_year':2026}).step(data['faculty'][0])
        self.assertFalse(result['publications'][0]['verified'])
        scopus=next(p for p in data['pending_publications'] if p['source']=='scopus')
        self.assertTrue(scopus['source_id'].startswith('LOCAL-'));self.assertEqual(scopus['original_source_record_id'],'')
    def test_reimport_is_idempotent_and_other_roster_members_remain(self):
        data,summary=prepare_institution_import(content([record()]),self.empty(),'x.csv',True)
        data['faculty'].append({'faculty_id':'OTHER','name':'Other Faculty','department':'ECE','consent':{},'profiles':{}})
        second,_=prepare_institution_import(content([record()]),data,'x.csv',True)
        self.assertEqual(len(second['publications']),1);self.assertEqual(len(second['faculty']),2)
        validate_dataset(second)

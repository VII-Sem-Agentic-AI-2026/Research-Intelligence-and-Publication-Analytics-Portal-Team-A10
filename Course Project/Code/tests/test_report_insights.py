import unittest
from publication_agent.report_insights import report_insights, completion_reply
from publication_agent.role_web import visible_run


class ReportInsightsTests(unittest.TestCase):
    def result(self, faculty_id, citations):
        return {'faculty': {'faculty_id': faculty_id}, 'publications': [
            {'publication_id': faculty_id+'-1', 'citations': citations, 'verified': False,
             'evidence': [{'source': 'scholar'}]}]}

    def test_single_source_citations_are_not_presented_as_zero(self):
        report={'faculty_results':[self.result('F1',967)]}
        insight=report_insights(report)
        self.assertEqual(insight['imported_citations'],967)
        self.assertEqual(insight['corroborated_citations'],0)
        self.assertEqual(insight['imported_h_index'],1)
        text=completion_reply({'report':report,'status':'AWAITING_APPROVAL'})
        self.assertIn('967 imported citations',text)
        self.assertIn('not citations earned during',text)

    def test_faculty_insights_only_include_their_own_records(self):
        run={'plan':{},'report':{'faculty_results':[self.result('F1',7),self.result('F2',900)]}}
        visible=visible_run(run,{'role':'faculty','faculty_id':'F1'})
        self.assertEqual(visible['report']['insights']['imported_citations'],7)
        self.assertEqual(visible['report']['insights']['publications'],1)

    def test_shared_publication_is_counted_once_using_maximum_snapshot(self):
        first=self.result('F1',7);second=self.result('F2',9)
        second['publications'][0]['publication_id']='F1-1'
        report={'faculty_results':[first,second]}
        insight=report_insights(report)
        self.assertEqual(insight['imported_citations'],9)
        self.assertEqual(insight['publications'],1)
        self.assertEqual(first['publications'][0]['citations'],7)

    def test_report_analysis_includes_scope_trends_top_papers_and_quality(self):
        result=self.result('F1',7)
        result['faculty'].update(name='Researcher One',department='CSE')
        result['publications'][0].update(title='Earlier paper',year=2024,doi='10.test/one',
            source_metadata={'journal_or_conference':'Example Journal'})
        result['publications'].append({'publication_id':'p2','title':'Later paper','year':2025,
            'citations':13,'verified':True,'evidence':[
                {'source':'scholar','url':'https://example.test/2','retrieved':'2026-01-01'},
                {'source':'scopus','url':'https://example.test/3','retrieved':'2026-01-01'}]})
        report={'plan':{'reporting_year':2025},'scope':'cumulative_through_year','faculty_results':[result]}
        insight=report_insights(report)
        self.assertEqual(insight['average_citations'],10)
        self.assertEqual(insight['reporting_year'],2025)
        self.assertEqual(insight['publication_years'],[
            {'year':2024,'publications':1,'imported_citations':7},
            {'year':2025,'publications':1,'imported_citations':13}])
        self.assertEqual(insight['top_publications'][0]['title'],'Later paper')
        self.assertEqual(insight['top_publications'][1]['venue'],'Example Journal')
        self.assertEqual(insight['quality']['missing_doi'],1)
        self.assertEqual(insight['quality']['missing_provenance'],1)
        self.assertTrue(any('Later paper' in line for line in insight['findings']))
        self.assertEqual(insight['source_coverage'],[
            {'source':'scholar','publications':2},{'source':'scopus','publications':1}])

    def test_shared_publication_preserves_all_source_links_without_mutation(self):
        first=self.result('F1',7);second=self.result('F2',9)
        second['publications'][0].update(publication_id='F1-1',evidence=[{'source':'scopus'}])
        insight=report_insights({'faculty_results':[first,second]})
        self.assertEqual(insight['sources'],['scholar','scopus'])
        self.assertEqual(len(insight['top_publications'][0]['evidence']),2)
        self.assertEqual(first['publications'][0]['evidence'],[{'source':'scholar'}])

    def test_faculty_trends_and_top_papers_do_not_include_other_faculty(self):
        one=self.result('F1',7);two=self.result('F2',900)
        one['publications'][0].update(title='Own paper',year=2024)
        two['publications'][0].update(title='Other faculty paper',year=2025)
        run={'plan':{'reporting_year':2025},'report':{'faculty_results':[one,two]}}
        insight=visible_run(run,{'role':'faculty','faculty_id':'F1'})['report']['insights']
        self.assertEqual(insight['top_publications'][0]['title'],'Own paper')
        self.assertEqual(insight['reporting_year'],2025)
        self.assertEqual([r['year'] for r in insight['publication_years']],[2024])

    def test_empty_report_does_not_invent_findings(self):
        insight=report_insights({})
        self.assertEqual(insight['average_citations'],0)
        self.assertEqual(insight['top_publications'],[])
        self.assertIn('No publications',insight['findings'][0])

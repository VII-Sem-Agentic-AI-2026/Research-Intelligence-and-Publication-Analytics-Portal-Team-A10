"""Actual source coverage and conservative checks on model source claims."""
import re

SOURCE_LABELS={'scholar':'Google Scholar','scopus':'Scopus','wos':'Web of Science'}
SOURCE_PATTERNS={
    'scholar':r'\b(?:google\s+)?scholar\b',
    'scopus':r'\bscopus\b',
    'wos':r'\b(?:wos|web[\s-]+of[\s-]+science)\b',
    'pubmed':r'\bpubmed\b','crossref':r'\bcrossref\b',
    'openalex':r'\bopenalex\b','semantic_scholar':r'\bsemantic\s+scholar\b',
}

def actual_source_coverage(report):
    faculty=[];queried=set();contributing=set()
    for result in report.get('faculty_results',[]):
        evidence_sources={e['source'] for p in result.get('publications',[]) for e in p.get('evidence',[]) if e.get('source')}
        # Worker coverage records actual consented reads, not the plan's defaults.
        reads=set(result.get('coverage',evidence_sources))
        faculty.append({'faculty_id':result.get('faculty',{}).get('faculty_id'),
                        'queried_sources':sorted(reads),'sources_with_in_scope_records':sorted(evidence_sources)})
        queried.update(reads);contributing.update(evidence_sources)
    return {'queried_sources':sorted(queried),'sources_with_in_scope_records':sorted(contributing),'faculty':faculty}

def unsupported_source_mentions(text,coverage):
    normalized=re.sub('[\u2010-\u2015]',' ',str(text)).casefold()
    named={source for source,pattern in SOURCE_PATTERNS.items() if re.search(pattern,normalized)}
    return sorted(named-set(coverage['sources_with_in_scope_records']))

def verified_fallback(report,coverage,reason):
    labels=[SOURCE_LABELS.get(s,s) for s in coverage['sources_with_in_scope_records']]
    sources=', '.join(labels) if labels else 'none with in-scope records'
    summary=report.get('summary',{})
    return (f'Narrative withheld: {reason}. Verified summary: '
            f"{summary.get('publications',0)} publications; {summary.get('citations',0)} citations. "
            f'Sources contributing records: {sources}. Counts reflect imported snapshots, not live indexing or citations received in the reporting year.')

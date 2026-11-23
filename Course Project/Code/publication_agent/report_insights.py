"""Read-only report analysis of imported snapshots and source corroboration."""
from .core import compute_h_index


def _venue(publication):
    metadata = publication.get('source_metadata') or {}
    return (publication.get('venue') or publication.get('journal')
            or metadata.get('journal_or_conference') or '')


def _analysis(report, records, citations):
    """Describe only the records in this report, without changing saved results."""
    faculty = report.get('faculty_results', [])
    plan = report.get('plan') or {}
    years = {}
    for publication, count in zip(records, citations):
        year = publication.get('year')
        if not year:
            continue
        row = years.setdefault(str(year), {'year': year, 'publications': 0, 'imported_citations': 0})
        row['publications'] += 1
        row['imported_citations'] += count
    trend = sorted(years.values(), key=lambda row: str(row['year']))
    sources = sorted({e['source'] for p in records for e in p.get('evidence', []) if e.get('source')})
    top = sorted(records, key=lambda p: (-max(0, int(p.get('citations') or 0)), str(p.get('title', ''))))[:10]
    quality = {
        'missing_doi': sum(not p.get('doi') for p in records),
        'missing_venue': sum(not _venue(p) for p in records),
        'missing_year': sum(not p.get('year') for p in records),
        'missing_citation_count': sum(p.get('citations') is None for p in records),
        'missing_provenance': sum(not p.get('evidence') or any(
            not e.get('url') or not e.get('retrieved') for e in p.get('evidence', [])) for p in records),
        'single_source_publications': sum(len({e.get('source') for e in p.get('evidence', []) if e.get('source')}) == 1 for p in records),
        'source_record_evidence': sum(len(p.get('evidence', [])) for p in records),
        'attribution_awaiting_review': sum(r.get('attribution_status') != 'reviewer_confirmed' for r in faculty),
    }
    proposals = {p.get('group', p.get('title', '')): p for r in faculty for p in r.get('duplicate_proposals', [])}
    quality['duplicate_groups'] = len(proposals)
    quality['pending_duplicate_groups'] = sum(p.get('decision', 'pending') == 'pending' for p in proposals.values())
    findings = []
    if records:
        findings.append(f"The report contains {len(records):,} distinct publications and {sum(citations):,} imported citations, averaging {sum(citations) / len(records):.2f} citations per publication.")
    if trend:
        peak = max(trend, key=lambda row: row['publications'])
        findings.append(f"The largest publication-year group is {peak['year']}, with {peak['publications']:,} publications. This describes output in the available records, not a complete assessment of research performance.")
    if top:
        findings.append(f"The most-cited included publication is “{top[0].get('title', 'Untitled')}” with {max(0, int(top[0].get('citations') or 0)):,} imported citations.")
    if quality['single_source_publications']:
        findings.append(f"{quality['single_source_publications']:,} publications have evidence from one source. Their imported citations are included, but they are not cross-source corroborated.")
    if not records:
        findings.append('No publications are included in this report; no citation or trend conclusions can be drawn.')
    dates = sorted({e['retrieved'] for p in records for e in p.get('evidence', []) if e.get('retrieved')})
    return {
        'average_citations': round(sum(citations) / len(records), 2) if records else 0,
        'publication_years': trend,
        'top_publications': [{
            'publication_id': p.get('publication_id'), 'title': p.get('title', 'Untitled'),
            'year': p.get('year'), 'venue': _venue(p), 'doi': p.get('doi', ''),
            'citations': max(0, int(p.get('citations') or 0)),
            'sources': sorted({e['source'] for e in p.get('evidence', []) if e.get('source')}),
            'evidence': [{k: e.get(k, '') for k in ('source', 'url', 'retrieved')} for e in p.get('evidence', [])],
        } for p in top],
        'faculty': [{k: r.get('faculty', {}).get(k, '') for k in ('faculty_id', 'name', 'department')} for r in faculty],
        'reporting_year': plan.get('reporting_year'),
        'scope': report.get('scope', plan.get('scope', 'cumulative_through_year')),
        'quality': quality, 'findings': findings, 'retrieval_dates': dates,
        'source_coverage': [{'source': source, 'publications': sum(
            any(e.get('source') == source for e in p.get('evidence', [])) for p in records)} for source in sources],
    }


def report_insights(report):
    publications = {}
    for result in report.get('faculty_results', []):
        for publication in result.get('publications', []):
            key = publication['publication_id']
            prior = publications.get(key)
            if prior is None:
                publications[key] = dict(publication)
                publications[key]['evidence'] = [dict(e) for e in publication.get('evidence', [])]
            else:
                prior['citations'] = max(prior.get('citations', 0), publication.get('citations', 0))
                prior['verified'] = prior.get('verified', False) or publication.get('verified', False)
                for evidence in publication.get('evidence', []):
                    if evidence not in prior['evidence']:
                        prior['evidence'].append(dict(evidence))
    records = list(publications.values())
    citations = [max(0, int(p.get('citations') or 0)) for p in records]
    return {
        'publications': len(records),
        'imported_citations': sum(citations),
        'imported_h_index': compute_h_index(citations),
        'corroborated_publications': sum(bool(p.get('verified')) for p in records),
        'corroborated_citations': sum(max(0, int(p.get('citations') or 0)) for p in records if p.get('verified')),
        'sources': sorted({e['source'] for p in records for e in p.get('evidence', []) if e.get('source')}),
        'citation_basis': 'Latest imported citation snapshots; not citations received in the reporting year. Imported totals include single-source records.',
        **_analysis(report, records, citations),
    }


def completion_reply(result):
    report = result.get('report', {})
    insight = report_insights(report)
    status = result.get('status', 'UNKNOWN')
    title = report.get('title', result.get('run_id', 'Report'))
    return (f'{title}\n\n'
            f"{insight['publications']:,} publications · {insight['imported_citations']:,} imported citations · "
            f"imported-record h-index {insight['imported_h_index']}.\n\n"
            f"Cross-source corroborated subset: {insight['corroborated_publications']:,} publications, "
            f"{insight['corroborated_citations']:,} citations. "
            'A zero here means no corroborated citation total, not necessarily no citations. '
            f"These are current imported snapshots, not citations earned during the reporting year.\n\n"
            f"Status: {status.replace('_', ' ').lower()}. Open the report below to inspect its metrics and records.")

"""Validate imported data before it becomes the active dataset."""
from datetime import date
from urllib.parse import urlparse

SOURCES={'scholar','scopus','wos'}

def validate_profile_links(profile):
    for source in SOURCES:
        if not profile.get('consent',{}).get(source):continue
        value=profile.get('profiles',{}).get(source,'')
        if not isinstance(value,str):raise ValueError(f'{source} profile URL is invalid')
        parsed=urlparse(value)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or any(c.isspace() for c in value) or parsed.username or parsed.password:
            raise ValueError(f'{source} requires an absolute HTTP(S) profile URL without credentials')


def validate_dataset(data):
    if not isinstance(data,dict) or not isinstance(data.get('faculty'),list) or not isinstance(data.get('publications'),list):
        raise ValueError('Expected faculty and publications arrays')
    ids=set()
    for f in data['faculty']:
        if not all(isinstance(f.get(k),str) and f[k].strip() for k in ('faculty_id','name','department')):
            raise ValueError('Faculty requires nonempty ID, name and department')
        if f['faculty_id'] in ids:raise ValueError('Duplicate faculty ID')
        ids.add(f['faculty_id'])
        if not isinstance(f.get('consent'),dict) or any(type(v) is not bool for v in f['consent'].values()):
            raise ValueError('Source consent values must be booleans')
        validate_profile_links(f)
    seen=set()
    for p in data['publications']:
        if p.get('faculty_id') not in ids or p.get('source') not in SOURCES:
            raise ValueError('Publication has unknown faculty or source')
        if not all(isinstance(p.get(k),str) and p[k].strip() for k in ('source_id','title','url','retrieved')):
            raise ValueError('Publication is missing provenance')
        if type(p.get('year')) is not int or not 1900 <= p['year'] <= date.today().year+1:
            raise ValueError('Invalid publication year')
        if type(p.get('citations')) is not int or p['citations']<0:
            raise ValueError('Citation count must be a known nonnegative integer; resolve missing or unknown counts before importing')
        date.fromisoformat(p['retrieved'][:10])
        if urlparse(p['url']).scheme not in {'https','http','import'}:
            raise ValueError('Evidence URL must use http, https or import')
        key=(p['faculty_id'],p['source'],p['source_id'])
        if key in seen:raise ValueError('Duplicate faculty/source/record identity')
        seen.add(key)
    pending=data.get('pending_publications',[])
    if not isinstance(pending,list):raise ValueError('Pending publications must be an array')
    for p in pending:
        if p.get('faculty_id') not in ids or p.get('source') not in SOURCES|{'vidwan','librarian'}:raise ValueError('Pending record has unknown faculty or source')
        if not all(isinstance(p.get(k),str) and p[k].strip() for k in ('source_id','title','url','retrieved')):raise ValueError('Pending record is missing provenance')
        if p.get('year') is not None and (type(p['year']) is not int or not 1900<=p['year']<=date.today().year+1):raise ValueError('Invalid pending publication year')
        if p.get('citations') is not None and (type(p['citations']) is not int or p['citations']<0):raise ValueError('Invalid pending citation count')
        if p.get('record_status')!='pending_review' or not isinstance(p.get('review_reasons'),list) or not p['review_reasons']:raise ValueError('Pending record must explain why review is required')
        date.fromisoformat(p['retrieved'][:10])
        if urlparse(p['url']).scheme not in {'http','https','import'}:raise ValueError('Invalid pending evidence URL')
        key=(p['faculty_id'],p['source'],p['source_id'])
        if key in seen:raise ValueError('Duplicate faculty/source/record identity')
        seen.add(key)
    return data

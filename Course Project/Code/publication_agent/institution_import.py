"""Lossless preparation of the supplied multi-faculty KLE publication CSV."""
import copy
import csv
import hashlib
import io
import re
from datetime import date
from urllib.parse import urlparse,parse_qs,urlencode
from .core import now
from .validation import validate_dataset
from .importers import _citations

SOURCE_MAP={'Google Scholar':'scholar','Scopus':'scopus','Vidwan':'vidwan'}

def prepare_institution_import(content,existing,filename,consent_confirmed=False):
    if consent_confirmed is not True:raise ValueError('Explicit confirmation of consent is required')
    data=copy.deepcopy(existing);data.setdefault('faculty',[]);data.setdefault('publications',[])
    data.setdefault('pending_publications',[])
    digest=hashlib.sha256(content).hexdigest();profiles={f['faculty_id']:f for f in data['faculty']}
    active={(p['faculty_id'],p['source'],p['source_id']):p for p in data['publications']}
    pending={(p['faculty_id'],p['source'],p['source_id']):p for p in data['pending_publications']}
    rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    if not rows:raise ValueError('CSV has no publication rows')
    faculty_sources={};seen=set()
    for number,row in enumerate(rows,2):
        fid=row.get('faculty_id','').strip();source=SOURCE_MAP.get(row.get('source'))
        if not fid or not row.get('faculty_name','').strip() or not row.get('department','').strip() or not row.get('publication_title','').strip() or not source:raise ValueError(f'Invalid faculty/publication/source on CSV row {number}')
        profile=profiles.get(fid)
        if profile is None:
            profile={'faculty_id':fid,'name':row['faculty_name'].strip(),'department':row['department'].strip().upper(),'consent':{s:False for s in ('scholar','scopus','wos')},'profiles':{}}
            profiles[fid]=profile;data['faculty'].append(profile)
        faculty_sources.setdefault(fid,set()).add(source)
        if source=='scholar':
            author=parse_qs(urlparse(row['publication_source_url']).query).get('user',[''])[0]
            if author:
                profile.setdefault('profiles',{})['scholar']='https://scholar.google.com/citations?'+urlencode({'user':author})
                profile.setdefault('consent',{})['scholar']=True
        raw_id=row.get('source_record_id','').strip()
        identity='|'.join([fid,source,row.get('vidwan_publication_id',''),row['publication_source_url'],row['publication_title'],row['publication_year']])
        source_id=raw_id or 'LOCAL-'+hashlib.sha256(identity.encode()).hexdigest()[:24]
        key=(fid,source,source_id)
        if key in seen:raise ValueError(f'Duplicate record identity on CSV row {number}')
        seen.add(key)
        reasons=[];year=None
        if re.fullmatch(r'\d{4}',row['publication_year'].strip()):
            value=int(row['publication_year'])
            if 1900<=value<=date.today().year+1:year=value
        if year is None:reasons.append('Publication year missing or invalid')
        citations=_citations(row.get('citation_count',''))
        if citations is None:reasons.append('Citation count unknown')
        if source=='vidwan':reasons.append('Vidwan metadata retained separately from supported metric sources')
        if source=='scopus' and row.get('direct_source_verified')!='Yes':reasons.append('Scopus information supplied through Vidwan; direct Scopus verification pending')
        if not raw_id:reasons.append('Original source record identifier unavailable; local import identifier assigned')
        if source in {'scholar','scopus','wos'} and not profile.get('consent',{}).get(source):reasons.append('Source author profile link required before connector access')
        authors=row.get('authors','')
        publication={'faculty_id':fid,'source':source,'source_id':source_id,'title':row['publication_title'].strip(),'year':year,'doi':row.get('doi','').strip().lower().removeprefix('https://doi.org/'),'citations':citations,'authors':[s.strip() for s in re.split(';' if ';' in authors else ',',authors) if s.strip()],'url':row['publication_source_url'].strip(),'retrieved':row['retrieval_date'].strip(),'import_file':filename,'import_sha256':digest,'csv_row':number,'original_source_record_id':raw_id,'source_id_origin':'original_source' if raw_id else 'local_import_identifier; not an original source identifier','citation_count_origin':row['citation_count_origin'],'direct_source_verified_as_supplied':row['direct_source_verified'],'source_metadata':row,'record_status':'pending_review' if reasons else 'report_eligible','review_reasons':reasons}
        if reasons:pending[key]=publication;active.pop(key,None)
        else:active[key]=publication;pending.pop(key,None)
    for fid,sources in faculty_sources.items():
        profiles[fid]['import_consent']={'status':'confirmed_by_user','sources':sorted(sources),'confirmed_at':now(),'basis':'User explicitly confirmed that all supplied CSV publication data is consented','import_sha256':digest}
    data['publications']=list(active.values());data['pending_publications']=list(pending.values())
    data.setdefault('institution_imports',{})[digest]={'filename':filename,'rows':len(rows),'faculty':len(faculty_sources),'consent_confirmed':True,'imported_at':now()}
    validate_dataset(data)
    return data,{'imported_rows':len(rows),'matched_faculty':len(faculty_sources),'report_eligible':sum(p['import_sha256']==digest for p in active.values() if p.get('import_sha256')),'needs_review':sum(p.get('import_sha256')==digest for p in pending.values()),'sha256':digest}

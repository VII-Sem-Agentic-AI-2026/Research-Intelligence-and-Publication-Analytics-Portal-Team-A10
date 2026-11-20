"""Local parsers for faculty rosters and Scholar/Scopus/WoS exports."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET


ALIASES = {
    "title": ("title", "document title", "publication title", "article title"),
    "year": ("year", "publication year", "cover date", "py"),
    "doi": ("doi", "digital object identifier"),
    "citations": ("citations", "cited by", "cited-by", "times cited", "tc"),
    "authors": ("authors", "author full names", "author", "au"),
    "url": ("url", "link", "source url", "document url"),
    "source_id": ("source id", "eid", "ut", "cluster id", "id"),
}


def _key(value): return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _value(row, field, default=""):
    normalized = {_key(k): v for k, v in row.items()}
    return next((normalized[a] for a in ALIASES[field] if a in normalized and normalized[a] not in (None, "")), default)


def _year(value):
    match = re.search(r"\b(19|20)\d{2}\b", str(value)); return int(match.group()) if match else 0


def _citations(value):
    text=str(value).strip()
    if text.lower() in {'','none','unknown','n/a','na','null'}:return None
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)',text):
        raise ValueError('Citation counts must be whole nonnegative integers; unknown counts must be resolved before import')
    return int(text.replace(',',''))


def _authors(value):
    if isinstance(value, list): return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in re.split(r";|\band\b", str(value), flags=re.I) if x.strip()]


def normalize_publications(rows, source, faculty_id, filename):
    output=[]
    for row in rows:
        title=str(_value(row,"title")).strip()
        if not title: raise ValueError('Publication row is missing a title')
        doi=str(_value(row,"doi")).strip().lower().replace("https://doi.org/", "")
        raw_id=str(_value(row,"source_id")).strip()
        digest=hashlib.sha1(f"{source}|{faculty_id}|{doi or title}".encode()).hexdigest()[:12]
        source_id=raw_id or f"{source.upper()}-{digest}"
        output.append({"source_id":source_id,"faculty_id":faculty_id,"source":source,"title":title,"year":_year(_value(row,"year")),"doi":doi,"citations":_citations(_value(row,"citations")),"authors":_authors(_value(row,"authors")),"url":str(_value(row,"url")).strip() or f"import://{filename}#{source_id}","retrieved":date.today().isoformat(),"import_file":filename})
    return output


def parse_csv(data):
    text=data.decode("utf-8-sig",errors="replace"); dialect=csv.Sniffer().sniff(text[:4096],delimiters=",;\t")
    return list(csv.DictReader(io.StringIO(text),dialect=dialect))


def _column_index(reference):
    letters=re.match(r"[A-Z]+",reference).group(); value=0
    for char in letters: value=value*26+ord(char)-64
    return value-1


def parse_xlsx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as book:
        shared=[]
        if "xl/sharedStrings.xml" in book.namelist():
            root=ET.fromstring(book.read("xl/sharedStrings.xml")); shared=["".join(node.itertext()) for node in root]
        sheet=next(name for name in book.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        root=ET.fromstring(book.read(sheet)); rows=[]
        for row in root.findall(".//{*}row"):
            values={}
            for cell in row.findall("{*}c"):
                idx=_column_index(cell.attrib.get("r","A1")); kind=cell.attrib.get("t"); node=cell.find("{*}v")
                value="" if node is None else node.text or ""
                if kind=="s" and value: value=shared[int(value)]
                elif kind=="inlineStr": value="".join(cell.itertext())
                values[idx]=value
            rows.append([values.get(i,"") for i in range(max(values,default=-1)+1)])
    if not rows:return []
    headers=[str(x) for x in rows[0]]
    return [dict(zip(headers,row+[""]*(len(headers)-len(row)))) for row in rows[1:] if any(str(x).strip() for x in row)]


def parse_bibtex(data):
    text=data.decode('utf-8-sig',errors='strict');rows=[];position=0
    def fields(body):
        parts=[];start=0;depth=0;quoted=False;escaped=False
        for i,char in enumerate(body):
            if escaped:escaped=False;continue
            if char=='\\':escaped=True;continue
            if char=='"' and depth==0:quoted=not quoted
            if not quoted:
                if char=='{':depth+=1
                elif char=='}':depth-=1
                elif char==',' and depth==0:parts.append(body[start:i]);start=i+1
        parts.append(body[start:]);return parts
    while True:
        match=re.search(r'@\s*(\w+)\s*([\{(])',text[position:])
        if not match:break
        entry_type=match.group(1).lower();start=position+match.end();opening=match.group(2)
        closing='}' if opening=='{' else ')';depth=1;braces=0;quoted=False;escaped=False;i=start
        while i<len(text):
            char=text[i]
            if escaped:escaped=False;i+=1;continue
            if char=='\\':escaped=True;i+=1;continue
            if char=='"' and (opening=='{' and depth==1 or opening=='(' and braces==0):quoted=not quoted
            if not quoted:
                if opening=='{':
                    if char=='{':depth+=1
                    elif char=='}':depth-=1
                else:
                    if char=='{':braces+=1
                    elif char=='}':braces-=1
                    elif char==closing and braces==0:depth=0
            if depth==0:break
            i+=1
        if depth:raise ValueError('Unclosed BibTeX entry')
        body=text[start:i];position=i+1
        if entry_type in {'comment','preamble'}:continue
        if entry_type=='string':raise ValueError('BibTeX string macros must be expanded before import')
        parts=fields(body)
        if not parts[0].strip():raise ValueError('BibTeX citation key is missing')
        row={'source id':parts[0].strip()}
        for field in parts[1:]:
            if not field.strip():continue
            name,separator,value=field.partition('=')
            if not separator:raise ValueError('Malformed BibTeX field')
            value=value.strip()
            if value.startswith('{') and value.endswith('}') or value.startswith('"') and value.endswith('"'):
                value=value[1:-1]
            elif not value.isdigit():raise ValueError('Unsupported BibTeX macro or concatenation; expand it before import')
            row[name.strip().lower()]=' '.join(value.split())
        rows.append(row)
    return rows


def parse_ris(data):
    rows=[]; current={}; authors=[]
    for line in data.decode("utf-8",errors="replace").splitlines():
        match=re.match(r"([A-Z0-9]{2})  - (.*)",line)
        if not match: continue
        tag,value=match.groups()
        if tag=="TY": current={}; authors=[]
        elif tag in ("TI","T1"): current["title"]=value
        elif tag=="AU": authors.append(value)
        elif tag in ("PY","Y1"): current["year"]=value
        elif tag=="DO": current["doi"]=value
        elif tag in ("TC","C3"): current["citations"]=value
        elif tag in ("UR","L2"): current["url"]=value
        elif tag in ("AN","UT"): current["source id"]=value
        elif tag=="ER": current["authors"]="; ".join(authors); rows.append(current)
    return rows


def parse_rows(filename, data):
    suffix=Path(filename).suffix.lower()
    if suffix in (".csv",".tsv"): return parse_csv(data)
    if suffix==".xlsx": return parse_xlsx(data)
    if suffix==".json":
        value=json.loads(data.decode("utf-8-sig"))
        if isinstance(value,dict): return value.get("publications") or value.get("faculty") or [value]
        return value
    if suffix in (".bib",".bibtex"): return parse_bibtex(data)
    if suffix==".ris": return parse_ris(data)
    raise ValueError("Supported formats: CSV, TSV, XLSX, JSON, BibTeX and RIS")


def parse_publication_export(filename, data, source, faculty_id):
    return normalize_publications(parse_rows(filename,data),source,faculty_id,filename)


def parse_faculty_roster(filename, data):
    rows=parse_rows(filename,data); output=[]
    rejected=[]
    for number,row in enumerate(rows,2):
        normalized={_key(k):v for k,v in row.items()}; faculty_id=str(normalized.get("faculty id",normalized.get("id",""))).strip(); name=str(normalized.get("full name",normalized.get("name",""))).strip(); department=str(normalized.get("department","")).strip().upper()
        if faculty_id and name and department: output.append({"faculty_id":faculty_id,"name":name,"department":department,"consent":{"scholar":False,"scopus":False,"wos":False},"profiles":{"scholar":"","scopus":"","wos":""}})
        else:rejected.append(str(number))
    if rejected:raise ValueError('Roster rows missing Faculty ID, Full Name or Department: '+', '.join(rejected)+'. No rows were imported.')
    if not output: raise ValueError("Roster needs Faculty ID, Full Name and Department columns")
    return output

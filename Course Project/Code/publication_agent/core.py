from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
import os
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "sample_research_data.json"
DEFAULT_RUNTIME = ROOT / "runtime"
APPROVER_ROLES = {"hod", "research dean", "research office"}
DEPARTMENT_ALIASES = {
    'computer science and engineering':'CSE','computer science':'CSE',
    'electronics and communication engineering':'ECE','electrical and electronics engineering':'EEE',
    'mechanical engineering':'ME','civil engineering':'CE','information technology':'IT',
    'artificial intelligence':'AI','data science':'DS',
}

def resolve_department(text):
    for name,code in DEPARTMENT_ALIASES.items():
        if re.search(r'\b'+re.escape(name)+r'\b',text,re.I):return code
    match=re.search(r'\b(CSE|ECE|EEE|ME|CE|IT|AI|DS)\b',text,re.I)
    return match.group(1).upper() if match else None

def reporting_year(value):
    if not re.fullmatch(r'\d{4}',str(value)):
        raise ValueError('Reporting year must be a four-digit year')
    year=int(value)
    if not 1900<=year<=datetime.now(timezone.utc).year+1:
        raise ValueError('Reporting year must be between 1900 and next year')
    return year


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, value: Any) -> None:
    from .storage import Store, runtime_root
    root = runtime_root(path)
    if root:
        Store(root).write(path, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def load(path: Path, default: Any = None) -> Any:
    from .storage import Store, runtime_root
    root = runtime_root(path)
    if root and (root / 'portal.sqlite3').exists():
        found, value = Store(root).read(path)
        if found:
            return value
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Plan:
    department: str
    reporting_year: int
    metric_pack: str
    scope: str = 'cumulative_through_year'
    sources: tuple[str, ...] = ("scholar", "scopus", "wos")
    status: str = "locked"


@dataclass
class ValidationReport:
    passed: bool
    checks: dict[str, bool]
    failing: list[str]
    diagnosis: dict[str, str]


@dataclass
class RunContext:
    run_id: str
    request: str
    plan: dict[str, Any]
    status: str = "RUNNING"
    attempts: int = 0
    tool_calls: int = 0
    faculty_results: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    lab_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    requested_labs: list[str] = field(default_factory=list)
    executed_labs: list[str] = field(default_factory=list)
    framework_evidence: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    review_assignment: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now)


class PlannerAgent:
    REQUIRED = ("department", "reporting_year", "metric_pack")

    def clarify(self, request: str, answers: dict[str, Any] | None = None) -> dict[str, Any]:
        answers = dict(answers or {})
        match = re.search(r"\b(20\d{2})\b", request)
        if match:
            answers.setdefault("reporting_year", int(match.group(1)))
        dept = resolve_department(request)
        if dept:
            answers.setdefault("department", dept)
        for pack in ("bibliometric", "collaboration", "altmetric"):
            if pack in request.lower():
                answers.setdefault("metric_pack", pack)
        questions = {
            "department": "Which department should the report cover?",
            "reporting_year": "Which reporting year should be used?",
            "metric_pack": "Which metric pack: bibliometric, collaboration, or altmetric?",
        }
        missing = [k for k in self.REQUIRED if not answers.get(k)]
        return {"answers": answers, "questions": [questions[k] for k in missing], "complete": not missing}

    def revise(self, answers: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
        revised = dict(answers)
        revised.update(feedback)
        return revised


class PlanSkill:
    def __call__(self, inputs: dict[str, Any]) -> Plan:
        missing = [x for x in PlannerAgent.REQUIRED if not inputs.get(x)]
        if missing:
            raise ValueError("Cannot lock plan; missing: " + ", ".join(missing))
        pack = str(inputs["metric_pack"]).lower()
        if pack not in SpecialistRegistry.names():
            raise ValueError(f"Unsupported metric pack: {pack}")
        scope = inputs.get('scope', 'cumulative_through_year')
        if scope not in {'cumulative_through_year', 'publication_year'}:
            raise ValueError('Unknown report scope')
        return Plan(resolve_department(str(inputs['department'])) or str(inputs['department']).strip().upper(), reporting_year(inputs['reporting_year']), pack, scope=scope)


class ResearchConnector:
    """One governed, typed surface for all research data sources."""

    def __init__(self, data_path: Path = DEFAULT_DATA, audit=None):
        self.data = load(data_path, {"faculty": [], "publications": []})
        self.audit = audit or (lambda *args, **kwargs: None)

    def faculty_profiles(self, department: str) -> list[dict[str, Any]]:
        result = [x for x in self.data["faculty"] if x["department"].upper() == department.upper()]
        self.audit("tool.faculty_profiles", {"department": department}, {"count": len(result)})
        return result

    def faculty_profile(self, faculty_id: str) -> dict[str, Any]:
        result = next(
            (x for x in self.data["faculty"] if x["faculty_id"] == faculty_id),
            None,
        )
        self.audit(
            "tool.faculty_profile",
            {"faculty_id": faculty_id},
            {"found": result is not None},
        )
        if result is None:
            raise KeyError(f"Unknown faculty ID: {faculty_id}")
        return result

    def publications(self, faculty: dict[str, Any], source: str) -> list[dict[str, Any]]:
        if source not in {"scholar", "scopus", "wos"}:
            raise ValueError("Unknown source")
        if not faculty.get("consent", {}).get(source):
            raise PermissionError(f"No {source} consent for {faculty['faculty_id']}")
        result = [dict(x) for x in self.data["publications"] if x["faculty_id"] == faculty["faculty_id"] and x["source"] == source]
        self.audit("tool.publications", {"faculty_id": faculty["faculty_id"], "source": source}, {"count": len(result)})
        return result

    def venue_metrics(self, doi: str) -> dict[str, Any]:
        result = {"doi": doi, "status": "not_in_demo", "claim": "No live venue metric queried"}
        self.audit("tool.venue_metrics", {"doi": doi}, result)
        return result


def normalized_title(title: str) -> str:
    return ''.join(c for c in title.casefold() if c.isalnum())


def deduplicate(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        doi = str(item.get('doi') or '').strip().lower().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
        key = doi or f"{normalized_title(item['title'])}:{item['year']}"
        groups.setdefault(key, []).append(item)
    merged, proposals = [], []
    for key, items in groups.items():
        canonical = dict(items[0])
        canonical["publication_id"] = key
        canonical["citations"] = max(int(x.get("citations", 0)) for x in items)
        canonical["evidence"] = [
            {"source_id": x["source_id"], "source": x["source"], "url": x["url"], "retrieved": x["retrieved"],
             'date_basis':x.get('date_basis','supplied_record_date'), 'import_file':x.get('import_file'),
             'import_sha256':x.get('import_sha256')}
            for x in items
        ]
        canonical["verified_sources"] = sorted({x["source"] for x in items})
        canonical["verified"] = len(canonical["verified_sources"]) >= 2
        canonical['corroboration_status'] = 'multiple_imported_sources' if canonical['verified'] else 'single_imported_source'
        canonical['attribution_status'] = 'unreviewed'
        canonical['evidence_type'] = 'imported_records'
        merged.append(canonical)
        if len(items) > 1:
            same_doi = bool(items[0].get("doi")) and len({x.get("doi") for x in items}) == 1
            proposals.append({"group": key, "title": canonical["title"], "source_ids": [x["source_id"] for x in items],
                              "sources": canonical["verified_sources"], "match_rule": 'exact_doi' if same_doi else 'normalized_title_year',
                              "reason": "matching DOI" if same_doi else "normalized title and year match",
                              "action": "merge_proposed", "review_required": True, "decision": "pending"})
    # Do not auto-merge uncertain DOI/no-DOI matches. Surface them for review.
    title_groups={}
    for publication in merged:
        title_groups.setdefault((normalized_title(publication['title']),publication['year']),[]).append(publication)
    for candidates in title_groups.values():
        for left in [p for p in candidates if p.get('doi')]:
            for right in [p for p in candidates if not p.get('doi')]:
                proposals.append({'group':'candidate:'+left['publication_id']+'|'+right['publication_id'],
                    'title':left['title'],'source_ids':[e['source_id'] for p in (left,right) for e in p['evidence']],
                    'sources':sorted(set(left['verified_sources']+right['verified_sources'])),
                    'match_rule':'title_year_with_missing_doi','reason':'matching title/year; one source lacks DOI',
                    'action':'metadata_correction_required','review_required':True,'decision':'pending'})
    return merged, proposals


def compute_h_index(citations: Iterable[int]) -> int:
    ordered = sorted((int(x) for x in citations), reverse=True)
    return max((i for i, value in enumerate(ordered, 1) if value >= i), default=0)


class MetricSpecialist:
    name = "base"

    def calculate(self, publications: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError


class BibliometricSpecialist(MetricSpecialist):
    name = "bibliometric"

    def calculate(self, publications):
        cites = [p["citations"] for p in publications if p["verified"]]
        by_year: dict[str, int] = {}
        for p in publications:
            if not p['verified']:
                continue
            by_year[str(p["year"])] = by_year.get(str(p["year"]), 0) + p["citations"]
        return {"h_index": compute_h_index(cites), "total_citations": sum(cites), "citations_grouped_by_publication_year": by_year,
                "method": "h-index computed from verified, deduplicated records; citation counts use the maximum observed cross-source count",
                "caveat": "Source coverage and update timing can differ; values require Research Office review."}


class CollaborationSpecialist(MetricSpecialist):
    name = "collaboration"

    def calculate(self, publications):
        publications = [p for p in publications if p.get('verified')]
        coauthored = sum(len(p.get("authors", [])) > 1 for p in publications)
        return {"coauthored_publications": coauthored, "total_publications": len(publications),
                "collaboration_rate": round(coauthored / max(len(publications), 1), 3),
                "method": "share of verified, deduplicated records with more than one listed author",
                "caveat": "Author affiliation is not available in the local fixture and is not inferred."}


class AltmetricSpecialist(MetricSpecialist):
    name = "altmetric"

    def calculate(self, publications):
        return {"coverage": 0, "method": "no authorized altmetric connector configured",
                "caveat": "No altmetric score is claimed; connect an authorized source before use."}


class SpecialistRegistry:
    _items = {x.name: x for x in (BibliometricSpecialist(), CollaborationSpecialist(), AltmetricSpecialist())}

    @classmethod
    def names(cls):
        return tuple(cls._items)

    @classmethod
    def get(cls, name: str) -> MetricSpecialist:
        if name not in cls._items:
            raise KeyError(name)
        return cls._items[name]


class FacultyWorker:
    def __init__(self, connector: ResearchConnector, metric_pack: str, plan=None):
        self.connector = connector
        self.specialist = SpecialistRegistry.get(metric_pack)
        self.plan = plan or {}

    def step(self, faculty: dict[str, Any]) -> dict[str, Any]:
        sources = [s for s in ('scholar', 'scopus', 'wos') if faculty.get('consent', {}).get(s)]
        if not sources:
            raise PermissionError(f"No authorized sources for {faculty['faculty_id']}")
        # A single worker owns source reads; the outer pool is the global cap.
        source_results = [self.connector.publications(faculty, source) for source in sources]
        records = [record for result in source_results for record in result]
        year = self.plan.get('reporting_year')
        if year:
            records = [r for r in records if 0 < int(r['year']) <= year and (self.plan.get('scope') != 'publication_year' or int(r['year']) == year)]
        publications, proposals = deduplicate(records)
        metrics = self.specialist.calculate(publications)
        evidence_ids = [p["publication_id"] for p in publications if p.get("evidence") and p.get('verified')]
        metrics["evidence_publication_ids"] = evidence_ids
        return {"faculty": faculty, "publications": publications, "duplicate_proposals": proposals, "metrics": metrics,
                'coverage': sources, 'attribution_status': 'unreviewed', 'citation_snapshot': 'counts observed in imported records; not historical annual citations'}


class ReportFormattingSkill:
    def __call__(self, ctx: RunContext) -> dict[str, Any]:
        from .narrative import actual_source_coverage
        # Aggregate source evidence across faculty before computing unique totals.
        records = [dict(p, **e) for r in ctx.faculty_results
                   for p in r.get('publications', []) for e in p.get('evidence', [])]
        combined, _ = deduplicate(records)
        unique = {p['publication_id']:p for p in combined}
        totals = {
            "faculty": len(ctx.faculty_results),
            "publications": len(unique),
            "citations": sum(p['citations'] for p in unique.values() if p.get('verified')),
        }
        return {
            "title": f"{ctx.plan['department']} Publication Analytics Report — {ctx.plan['reporting_year']}",
            "run_id": ctx.run_id, "status": "draft", "plan": ctx.plan, "summary": totals,
            "faculty_results": ctx.faculty_results,
            'actual_source_coverage':actual_source_coverage({'faculty_results':ctx.faculty_results}),
            'attribution_status': 'unreviewed; source corroboration does not establish author identity',
            'scope': ctx.plan.get('scope', 'cumulative_through_year'),
            'citation_basis': 'Latest imported snapshot for eligible publications; not citations received during reporting year',
            "reporting_note": "Local demonstration data; institution-facing use requires Research Office review and authorized live connectors.",
            "generated_at": now(),
        }


class AcceptanceSuite:
    def validate(self, report: dict[str, Any]) -> ValidationReport:
        from .narrative import actual_source_coverage, unsupported_source_mentions
        results = report.get("faculty_results", [])
        publications = [p for r in results for p in r.get("publications", [])]
        metrics = [r.get("metrics", {}) for r in results]
        checks = {
            'narrative source claims match evidence':not unsupported_source_mentions(report.get('groq_explanation',''),actual_source_coverage(report)),
            "each metric cites its source": bool(metrics) and all(
                isinstance(r.get('metrics',{}).get('evidence_publication_ids'),list) and
                all(isinstance(value,str) for value in r['metrics']['evidence_publication_ids']) and
                set(r['metrics']['evidence_publication_ids'])=={p['publication_id'] for p in r.get('publications',[]) if p.get('verified') and p.get('evidence')}
                for r in results),
            "attribution limitations are disclosed": bool(report.get('attribution_status')),
            "no ranking is published without review": report.get("status") == "draft",
            "metric caveats are stated": bool(metrics) and all(bool(m.get("caveat")) for m in metrics),
            "source access is consented": bool(results) and all(all(r['faculty']['consent'].get(e['source'], False) for p in r.get('publications', []) for e in p.get('evidence', [])) for r in results),
            "evidence provenance is present": all(p.get("evidence") and all(e.get("url") and e.get("retrieved") for e in p["evidence"]) for p in publications),
        }
        try:
            specialist=SpecialistRegistry.get(report['plan']['metric_pack'])
            checks['metric values match publications']=all(
                all(r.get('metrics',{}).get(k)==v for k,v in specialist.calculate(r.get('publications',[])).items() if k not in {'caveat','method'})
                for r in results)
            expected=ReportFormattingSkill()(RunContext(report.get('run_id','validation'),'',report['plan'],faculty_results=results))['summary']
            checks['summary matches unique publications']=report.get('summary')==expected
        except (KeyError,TypeError,ValueError):
            checks['metric values match publications']=False
            checks['summary matches unique publications']=False
        failing = [name for name, passed in checks.items() if not passed]
        diagnosis = {name: f"Repair required: {name}." for name in failing}
        return ValidationReport(not failing, checks, failing, diagnosis)


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path

    def remember(self, report: dict[str, Any]):
        history = load(self.path, [])
        history.append({"run_id": report["run_id"], "title": report["title"], "department": report["plan"]["department"],
                        "metric_pack": report["plan"]["metric_pack"], "summary": report["summary"], "published_at": now()})
        dump(self.path, history)

    def retrieve(self, query: str, tags: dict[str, str] | None = None, k: int = 5):
        items = load(self.path, [])
        tags = tags or {}
        filtered = [x for x in items if all(str(x.get(a, "")).lower() == str(b).lower() for a, b in tags.items())]
        tokens = set(re.findall(r"\w+", query.lower()))
        ranked = sorted(filtered, key=lambda x: len(tokens & set(re.findall(r"\w+", json.dumps(x).lower()))), reverse=True)
        return ranked[:k]


class GovernedRuntime:
    def __init__(self, root: Path = DEFAULT_RUNTIME, tool_budget: int | None = None):
        self.root = root
        self.tool_budget = int(tool_budget if tool_budget is not None else os.getenv('RESEARCH_TOOL_BUDGET', '10000'))
        if not 1<=self.tool_budget<=1000000:raise ValueError('Tool budget must be between 1 and 1000000')
        self.lock = threading.Lock()
        self.current: RunContext | None = None

    def audit(self, action: str, inputs: Any, outputs: Any, status: str = "ok"):
        if self.current and action.startswith("tool."):
            with self.lock:
                self.current.tool_calls += 1
                if self.current.tool_calls > self.tool_budget:
                    raise RuntimeError("Tool budget exceeded")
        event = {"time": now(), "run_id": self.current.run_id if self.current else None, "action": action,
                 "inputs": inputs, "outputs": outputs, "status": status}
        path = self.root / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def checkpoint(self, ctx: RunContext):
        dump(self.root / "runs" / f"{ctx.run_id}.json", asdict(ctx))

    def load_run(self, run_id: str) -> RunContext:
        value = load(self.root / "runs" / f"{run_id}.json")
        if not value:
            raise FileNotFoundError(run_id)
        return RunContext(**value)


class Governance:
    def __init__(self, runtime: GovernedRuntime, current_data=None):
        self.runtime = runtime
        self.memory = MemoryStore(runtime.root / "history.json")
        self.current_data=current_data

    def publish(self, ctx: RunContext, reviewer: str, role: str, edits: dict[str, Any] | None = None, reviewer_id=None):
        if role.strip().lower() not in APPROVER_ROLES:
            raise PermissionError("Reviewer role is not authorized to approve")
        if ctx.status != "AWAITING_APPROVAL" or not ctx.validation.get("passed"):
            raise RuntimeError("Only a validated pending draft can be approved")
        assignment=ctx.review_assignment
        if assignment and (assignment.get('status')!='accepted' or reviewer_id!=assignment.get('dean_id') or role.strip().lower()!='research dean'):
            raise PermissionError('The assigned Dean must accept the request and approve this report')
        validation=AcceptanceSuite().validate(ctx.report)
        if not validation.passed:raise RuntimeError('Draft revalidation failed: '+', '.join(validation.failing))
        if self.current_data is not None:
            profiles={f['faculty_id']:f for f in self.current_data().get('faculty',[])}
            for result in ctx.report.get('faculty_results',[]):
                profile=profiles.get(result['faculty']['faculty_id'],{})
                for p in result.get('publications',[]):
                    if any(not profile.get('consent',{}).get(e['source'],False) for e in p.get('evidence',[])):
                        raise PermissionError('Source consent changed after this draft. Regenerate and review a new report before publishing.')
        final = deepcopy(ctx.report)
        if any(r.get('attribution_status') != 'reviewer_confirmed' for r in final.get('faculty_results', [])):
            raise RuntimeError('Faculty attribution requires individual review with an evidence note')
        final['attribution_status']='reviewer_confirmed; manual review, not automated identity resolution'
        allowed = {"reporting_note", "title"}
        for key, value in (edits or {}).items():
            if key not in allowed:
                raise ValueError(f"Edit not allowed at approval: {key}")
            final[key] = value
        versions_dir = self.runtime.root / "published"
        versions_dir.mkdir(parents=True, exist_ok=True)
        if not reviewer.strip():
            raise ValueError('Reviewer identity is required')
        final.update({"status": "approved", "approved_by": reviewer, "approver_role": role, "approved_at": now()})
        if assignment:
            ctx.review_assignment={**assignment,'status':'completed','completed_at':final['approved_at']}
            final['review_assignment']=ctx.review_assignment
        for faculty_result in final.get("faculty_results", []):
            for proposal in faculty_result.get("duplicate_proposals", []):
                if proposal.get('decision') == 'pending':
                    raise RuntimeError('Every duplicate proposal requires an individual decision before publication')
        from .storage import Store
        final = Store(self.runtime.root).release(final)
        version = final['version']
        dump(versions_dir / f"version-{version}.json", final)
        dump(self.runtime.root / "published" / "current.json", final)
        ctx.status, ctx.report = "PUBLISHED", final
        self.runtime.current = ctx
        self.runtime.audit("governance.publish", {"reviewer": reviewer, "role": role}, {"version": version})
        self.runtime.checkpoint(ctx)
        self.memory.remember(final)
        if assignment:
            with Store(self.runtime.root).connect() as db:
                db.execute("UPDATE dean_review_requests SET status='completed' WHERE id=?",(assignment['request_id'],))
        return final

    def rollback(self, version: int):
        target = self.runtime.root / "published" / f"version-{version}.json"
        if not target.exists():
            raise FileNotFoundError(f"Published version {version}")
        value = load(target)
        if not value:raise FileNotFoundError(f"Published version {version} was deleted")
        value["rollback_activated_at"] = now()
        dump(self.runtime.root / "published" / "current.json", value)
        self.runtime.audit("governance.rollback", {"version": version}, {"active_version": version})
        return value


class PublicationOrchestrator:
    def __init__(
        self,
        data_path: Path = DEFAULT_DATA,
        runtime_root: Path = DEFAULT_RUNTIME,
        max_attempts: int = 2,
        use_groq: bool = False,
        llm: Any = None,
    ):
        self.runtime = GovernedRuntime(runtime_root)
        self.connector = ResearchConnector(data_path, self.runtime.audit)
        self.planner = PlannerAgent()
        self.max_attempts = max_attempts
        self.data_path=data_path
        self.governance = Governance(self.runtime,lambda:load(self.data_path,self.connector.data))
        self.use_groq = use_groq
        self.llm = llm

    def make_plan(self, request: str, answers: dict[str, Any] | None = None):
        clarified = self.planner.clarify(request, answers)
        if not clarified["complete"]:
            return clarified
        clarified["plan"] = asdict(PlanSkill()(clarified["answers"]))
        return clarified

    def run(self, request: str, answers: dict[str, Any] | None = None, inject_fault: str | None = None, selected_labs: list[int | str] | None = None) -> RunContext:
        planned = self.make_plan(request, answers)
        if not planned["complete"]:
            raise ValueError("Clarification required: " + " ".join(planned["questions"]))
        ctx = RunContext("run-" + uuid.uuid4().hex[:10], request, planned["plan"])
        ctx.source_snapshot = json.loads(json.dumps(self.connector.data))
        self.runtime.current = ctx
        self.runtime.audit("coordinator.plan_locked", {"request": request}, ctx.plan)
        self.runtime.checkpoint(ctx)
        if self.use_groq:
            from .groq_graph import GeminiLangGraphPipeline
            return GeminiLangGraphPipeline(self, llm=self.llm).execute(
                ctx, inject_fault, selected_labs
            )
        from .labs.pipeline import LabPipeline
        try:
            return LabPipeline(self).execute(ctx, inject_fault, selected_labs)
        except Exception as exc:
            ctx.status='FAILED'
            self.runtime.audit('workflow.failed', {}, {'error':str(exc)}, 'error')
            self.runtime.checkpoint(ctx)
            raise

    def resume(self, run_id):
        ctx = self.runtime.load_run(run_id)
        if ctx.status in {'PUBLISHED', 'AWAITING_APPROVAL', 'SELECTED_LABS_COMPLETED'}:
            return ctx
        if ctx.status not in {'RUNNING','FAILED'}:
            raise RuntimeError('This report requires corrected inputs and a new run; it cannot be resumed')
        if not ctx.source_snapshot:
            raise RuntimeError('Legacy run has no source snapshot and cannot safely resume')
        self.connector.data = ctx.source_snapshot
        self.runtime.current = ctx
        ctx.status = 'RUNNING'
        if self.use_groq:
            from .groq_graph import GeminiLangGraphPipeline
            return GeminiLangGraphPipeline(self, llm=self.llm).execute(ctx, selected_labs=ctx.requested_labs)
        from .labs.pipeline import LabPipeline
        return LabPipeline(self).execute(ctx, selected_labs=ctx.requested_labs)

    def review_duplicate(self, run_id, faculty_id, group, decision, reviewer):
        if decision not in {'confirmed', 'rejected'}:
            raise ValueError('Decision must be confirmed or rejected')
        ctx = self.runtime.load_run(run_id)
        if ctx.status != 'AWAITING_APPROVAL':
            raise ValueError('Only pending reports can be reviewed')
        for r in ctx.report['faculty_results']:
            if r['faculty']['faculty_id'] == faculty_id:
                for proposal in r['duplicate_proposals']:
                    if proposal['group'] == group:
                        if proposal.get('action')=='metadata_correction_required' and decision=='confirmed':
                            raise ValueError('Correct the missing DOI in source records and regenerate; this uncertain pair cannot be merged by an approval flag')
                        proposal.update(decision=decision, review_required=False, reviewed_by=reviewer, reviewed_at=now())
                        if decision == 'rejected':
                            # A rejected match requires corrected source associations and regeneration.
                            ctx.status = 'REQUIRES_CORRECTION'
                        self.runtime.checkpoint(ctx)
                        return asdict(ctx)
        raise KeyError('Duplicate proposal not found')

    def review_attribution(self, run_id, faculty_id, note, reviewer, checks=None):
        checklist = {
            'identity_checked': 'Checked the faculty profile or author ID and matched the name and affiliation',
            'publications_matched': 'Matched the listed publications to this faculty member',
            'conflicts_resolved': 'Checked for namesakes and found no unresolved ownership conflicts',
        }
        if checks is not None:
            if not isinstance(checks, dict) or set(checks) != set(checklist) or any(checks[k] is not True for k in checklist):
                raise ValueError('Complete all three attribution checks before confirming')
            note = 'Reviewer checklist: ' + '; '.join(checklist.values()) + '.'
        if len(str(note).strip()) < 12:
            raise ValueError('Provide an evidence note explaining faculty ownership of these publications')
        ctx = self.runtime.load_run(run_id)
        if ctx.status != 'AWAITING_APPROVAL':
            raise ValueError('Only pending reports can be reviewed')
        for r in ctx.report['faculty_results']:
            if r['faculty']['faculty_id'] == faculty_id:
                review={'reviewer':reviewer, 'note':note, 'time':now()}
                if checks is not None:
                    review['checks']=dict(checks)
                    review['check_labels']=checklist
                r.update(attribution_status='reviewer_confirmed', attribution_review=review)
                for p in r.get('publications', []):
                    p['attribution_status']='reviewer_confirmed'
                self.runtime.audit('review.attribution', {'faculty_id':faculty_id}, review)
                self.runtime.checkpoint(ctx)
                return asdict(ctx)
        raise KeyError('Faculty not found in report')

    def _repair(self, ctx: RunContext, report: ValidationReport):
        if "metric caveats are stated" in report.failing:
            for item in ctx.report["faculty_results"]:
                item["metrics"].setdefault("caveat", "Coverage may differ by source and retrieval date; human review required.")

    def approve(self, run_id: str, reviewer: str, role: str, edits=None, reviewer_id=None):
        ctx = self.runtime.load_run(run_id)
        return self.governance.publish(ctx, reviewer, role, edits,reviewer_id=reviewer_id)

    def rollback(self, version: int):
        return self.governance.rollback(version)

    def reset_runtime(self):
        if self.runtime.root.exists():
            shutil.rmtree(self.runtime.root)

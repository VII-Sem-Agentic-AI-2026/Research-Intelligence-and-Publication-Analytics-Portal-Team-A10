"""Genuine LangGraph orchestration with LangChain tools and the Gemini API."""

from __future__ import annotations

import os
import re
import json
from operator import add
from typing import Annotated

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .langchain_tools import build_research_tools
from .labs.contracts import LabExecution
from .labs.pipeline import LabPipeline
from .narrative import actual_source_coverage, unsupported_source_mentions, verified_fallback
from .ai_text import response_text


class GeminiPlan(BaseModel):
    """A constrained planning result; the LLM cannot change permissions or publish."""

    objective: str = Field(description="The publication-analysis objective")
    steps: list[str] = Field(description="Short ordered execution steps")
    risks: list[str] = Field(description="Data-quality or governance risks")


class WorkflowState(TypedDict, total=False):
    run_id: str
    request: str
    requested_labs: list[str]
    executed_labs: list[str]
    completed_labs: Annotated[list[str], add]
    groq_plan: dict
    groq_summary: str
    status: str


class GeminiLangGraphPipeline:
    """Run the existing lab implementations as nodes in a compiled StateGraph."""

    def __init__(self, orchestrator, llm=None):
        self.orchestrator = orchestrator
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        if llm is None:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is required for dashboard runs. Set it in the "
                    "environment; never place the key in source code."
                )
            llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=0,
                max_retries=2,
                google_api_key=api_key,
                vertexai=False,
                timeout=45,
                max_tokens=4096,
            )
        self.llm = llm
        self.tools = build_research_tools(orchestrator.connector)
        self.raw_connector = orchestrator.connector

    def _groq_plan(self, execution: LabExecution):
        deterministic_plan = execution.run.plan
        planner = self.llm.with_structured_output(GeminiPlan)
        plan = planner.invoke(
            [
                (
                    "system",
                    "You are a governed research-intelligence planning agent. "
                    "Use only the supplied plan. Do not invent faculty, publications, metrics, "
                    "permissions, API results, or approval. Return a short execution plan.",
                ),
                (
                    "human",
                    f"Request: {execution.run.request}\nValidated plan: {deterministic_plan}",
                ),
            ]
        )
        value = plan.model_dump()
        execution.run.lab_results["lab01"]["groq_plan"] = value
        execution.orchestrator.runtime.audit(
            "gemini.plan",
            {"model": self.model_name},
            {"objective": value["objective"], "step_count": len(value["steps"])},
        )
        execution.orchestrator.runtime.checkpoint(execution.run)
        return value

    def _groq_summary(self, execution: LabExecution):
        report = execution.run.report
        coverage=actual_source_coverage(report)
        report['actual_source_coverage']=coverage
        summary_payload = {
            "title": report.get("title"),
            "report_scope": {k:report.get('plan',{}).get(k) for k in ('department','reporting_year','metric_pack','scope')},
            'actual_source_coverage':coverage,
            "summary": report.get("summary"),
            "faculty_metrics": [
                {
                    "faculty_id": result.get("faculty", {}).get("faculty_id"),
                    "metrics": result.get("metrics", {}),
                }
                for result in report.get("faculty_results", [])
            ],
            "reporting_note": report.get("reporting_note"),
        }
        response = self.llm.invoke(
            [
                (
                    "system",
                    "Explain only the supplied verified research metrics. Never invent records, "
                    "citations, source coverage, or approval status. Name only sources listed in "
                    "sources_with_in_scope_records. queried_sources may include empty reads and must not "
                    "be described as contributing data. Never infer sources from a plan or from general "
                    "knowledge. Do not mention any other source, even as a negative statement. "
                    "Year-grouped citations are grouped by publication year, not the year citations were received. "
                    "Keep the response under 120 words.",
                ),
                ("human", f"Verified aggregate report data: {summary_payload}"),
            ]
        )
        summary = response_text(response)
        unexpected_sources=unsupported_source_mentions(summary,coverage)
        allowed_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', json.dumps(summary_payload)))
        numbers_valid=set(re.findall(r'\b\d+(?:\.\d+)?\b', summary)) <= allowed_numbers
        valid=not unexpected_sources and numbers_valid
        if not valid:
            reason='the model named sources without contributing records' if unexpected_sources else 'the model returned numbers absent from the validated metrics'
            summary=verified_fallback(report,coverage,reason)
        report['groq_explanation_validation']={'passed':valid,'unexpected_sources':unexpected_sources,'numbers_valid':numbers_valid,'fallback_used':not valid}
        summary = 'AI explanation; reviewer must check interpretation. ' + summary
        execution.run.report["groq_explanation"] = summary
        execution.run.lab_results["lab08"]["groq_explanation"] = summary
        execution.orchestrator.runtime.audit(
            "gemini.explain", {"model": self.model_name}, {"characters": len(summary),'validation':report['groq_explanation_validation']}
        )
        execution.orchestrator.runtime.checkpoint(execution.run)
        return summary

    def execute(self, run, inject_fault=None, selected_labs=None):
        from .mcp_connection import local_research_connection
        with local_research_connection(self.raw_connector) as connector:
            self.tools = build_research_tools(connector)
            result = self._execute(run, inject_fault, selected_labs)
            run.framework_evidence["mcp"] = {
                "connected": True,
                "transport": "stdio",
                "server": "Local Research Intelligence",
                "tools": sorted(connector.tool_names),
            }
            self.orchestrator.runtime.checkpoint(run)
            return result

    def _execute(self, run, inject_fault=None, selected_labs=None):
        requested, resolved = LabPipeline.resolve(selected_labs)
        run.requested_labs = [f"lab{x:02d}" for x in requested]
        run.executed_labs = [f"lab{x:02d}" for x in resolved]
        execution = LabExecution(self.orchestrator, run, inject_fault)
        from copy import deepcopy
        execution.artifacts.update(deepcopy(run.artifacts))
        if 'lab03' in execution.artifacts:
            from .core import ReportFormattingSkill
            execution.artifacts['lab03']['_formatter'] = ReportFormattingSkill()

        tools = self.tools
        raw = self.raw_connector
        class ToolConnector:
            data = raw.data
            def faculty_profiles(self, department):
                return tools['faculty_profiles'].invoke({'department': department})
            def publications(self, faculty, source):
                return tools['publications_for_faculty'].invoke({'faculty_id': faculty['faculty_id'], 'sources': [source]})
        self.orchestrator.connector = ToolConnector()

        graph = StateGraph(WorkflowState)

        for number in resolved:
            module = LabPipeline.MODULES[number - 1]

            def node(state, number=number, module=module):
                if f'lab{number:02d}' not in execution.artifacts:
                    module.execute(execution)
                update = {"completed_labs": [f"lab{number:02d}"]}
                if number == 1 and 'groq_plan' not in execution.run.lab_results['lab01']:
                    update["groq_plan"] = self._groq_plan(execution)
                if number == 2:
                    execution.run.lab_results["lab02"]["langchain_tool"] = {
                        "name": "faculty_profiles",
                        "returned": execution.run.lab_results['lab02']['faculty_count'],
                    }
                if number == 5:
                    execution.run.lab_results["lab05"]["langchain_tool"] = {
                        "name": "publications_for_faculty",
                        "usage": 'Consumed by faculty workers in Lab 08',
                    }
                if number == 11 and 'groq_explanation' not in execution.run.report:
                    update["groq_summary"] = self._groq_summary(execution)
                return update

            graph.add_node(f"lab{number:02d}", node)

        first = f"lab{resolved[0]:02d}"
        graph.add_edge(START, first)
        for previous, current in zip(resolved, resolved[1:]):
            graph.add_edge(f"lab{previous:02d}", f"lab{current:02d}")
        graph.add_edge(f"lab{resolved[-1]:02d}", END)

        compiled = graph.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": run.run_id}}
        try:
            final_state = compiled.invoke(
                {
                    "run_id": run.run_id,
                    "request": run.request,
                    "requested_labs": run.requested_labs,
                    "executed_labs": run.executed_labs,
                    "completed_labs": [],
                },
                config,
            )
        except Exception as exc:
            run.status = "FAILED"
            self.orchestrator.runtime.audit(
                "gemini.workflow_failed",
                {"model": self.model_name},
                {"error": str(exc)},
                status="error",
            )
            self.orchestrator.runtime.checkpoint(run)
            raise
        finally:
            self.orchestrator.connector = self.raw_connector
        run.framework_evidence = {
            "langchain": True,
            "langgraph": True,
            "llm_provider": "Gemini",
            "model": self.model_name,
            "compiled_graph": compiled.__class__.__name__,
            "completed_labs": final_state.get("completed_labs", []),
        }
        if 12 not in resolved:
            run.status = "SELECTED_LABS_COMPLETED"
        self.orchestrator.runtime.checkpoint(run)
        return run

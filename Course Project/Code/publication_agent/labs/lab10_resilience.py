"""Lab 10: diagnose and repair only failing output within retry budget."""

from dataclasses import asdict
from ..core import AcceptanceSuite

def execute(execution):
    execution.require("lab09", "grounded_publications")
    if execution.inject_fault == "missing_caveat":
        execution.run.report["faculty_results"][0]["metrics"].pop("caveat", None)
    suite = AcceptanceSuite(); report = suite.validate(execution.run.report)
    while not report.passed and execution.run.attempts < execution.orchestrator.max_attempts:
        execution.run.attempts += 1
        execution.orchestrator.runtime.audit("validation.failed", report.failing, report.diagnosis, "repairing")
        execution.orchestrator._repair(execution.run, report)
        report = suite.validate(execution.run.report)
    execution.run.validation = asdict(report)
    return execution.save("lab10", {
        "outcome": "validation faults diagnosed and repaired",
        "passed": report.passed,
        "attempts": execution.run.attempts,
        "failing": report.failing,
        "acceptance": report.passed,
    })


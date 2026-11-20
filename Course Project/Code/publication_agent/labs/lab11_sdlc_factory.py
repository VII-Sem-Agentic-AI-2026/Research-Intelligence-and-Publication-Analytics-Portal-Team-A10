"""Lab 11: treat locked plan as spec and acceptance suite as build gate."""

from ..core import AcceptanceSuite

def execute(execution):
    execution.require("lab10", "passed")
    report = AcceptanceSuite().validate(execution.run.report)
    if not report.passed:
        raise RuntimeError("Build gate failed: " + ", ".join(report.failing))
    return execution.save("lab11", {
        "outcome": "artifact passed the complete acceptance build",
        "checks": report.checks,
        "all_green": all(report.checks.values()),
        "acceptance": True,
    })


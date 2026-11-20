"""Lab 3: bind reusable plan and formatting skills."""

from ..core import ReportFormattingSkill

def execute(execution):
    execution.require("lab01", "plan")
    return execution.save("lab03", {
        "outcome": "case-independent skills bound",
        "skills": ["PlanSkill", "ReportFormattingSkill"],
        "_formatter": ReportFormattingSkill(),
        "acceptance": True,
    })


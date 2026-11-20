"""Lab 6: controlled runtime, audit budget and checkpoint."""

def execute(execution):
    execution.require("lab05", "sources")
    return execution.save("lab06", {
        "outcome": "governed runtime checkpoint created",
        "tool_budget": execution.orchestrator.runtime.tool_budget,
        "tool_calls": execution.run.tool_calls,
        "checkpoint": f"runs/{execution.run.run_id}.json",
        "acceptance": True,
    })


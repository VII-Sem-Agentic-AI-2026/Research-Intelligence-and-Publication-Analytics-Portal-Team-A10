"""Lab 4: separate current run state from approved historical memory."""

def execute(execution):
    plan = execution.require("lab01", "plan")
    prior = execution.orchestrator.governance.memory.retrieve(
        execution.run.request,
        {"department": plan["department"]},
    )
    return execution.save("lab04", {
        "outcome": "history retrieved without mixing it into run state",
        "prior_run_ids": [item["run_id"] for item in prior],
        "prior_count": len(prior),
        "acceptance": True,
    })


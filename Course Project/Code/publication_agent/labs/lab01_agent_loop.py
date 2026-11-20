"""Lab 1: clarify -> plan -> revise agent loop."""

def execute(execution):
    plan = execution.run.plan
    if plan.get("status") != "locked":
        raise RuntimeError("Lab 1 requires a locked plan")
    return execution.save("lab01", {
        "outcome": "locked publication analytics plan",
        "request": execution.run.request,
        "plan": plan,
        "acceptance": True,
    })


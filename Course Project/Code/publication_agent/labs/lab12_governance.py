"""Lab 12: human approval hard stop, versioning and rollback readiness."""

def execute(execution):
    execution.require("lab11", "all_green")
    execution.run.status = "AWAITING_APPROVAL"
    return execution.save("lab12", {
        "outcome": "validated draft stopped at human approval gate",
        "status": execution.run.status,
        "authorized_roles": ["HoD", "Research Dean", "Research Office"],
        "rollback_ready": True,
        "acceptance": True,
    })


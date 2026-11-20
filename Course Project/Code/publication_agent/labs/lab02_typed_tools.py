"""Lab 2: governed typed data reads and calculations."""

def execute(execution):
    plan = execution.require("lab01", "plan")
    faculty = execution.orchestrator.connector.faculty_profiles(plan["department"])
    if not faculty:
        raise ValueError("No consented faculty found for the selected department")
    return execution.save("lab02", {
        "outcome": "typed faculty lookup completed",
        "faculty_count": len(faculty),
        "faculty_ids": [item["faculty_id"] for item in faculty],
        "_faculty": faculty,
        "acceptance": True,
    })


"""Lab 13: verify the selected domain specialist is registered and checkable."""

from ..core import SpecialistRegistry

def execute(execution):
    execution.require("lab12", "status")
    selected = execution.run.plan["metric_pack"]
    specialist = SpecialistRegistry.get(selected)
    metrics = [item["metrics"] for item in execution.run.faculty_results]
    checkable = all(item.get("method") and item.get("caveat") for item in metrics)
    if not checkable:
        raise RuntimeError("Specialist output is not checkable")
    return execution.save("lab13", {
        "outcome": "domain specialist output verified",
        "selected_specialist": specialist.name,
        "available_specialists": list(SpecialistRegistry.names()),
        "checkable": True,
        "acceptance": True,
    })


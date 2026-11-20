"""Lab 14: integrate all prior outcomes into one dashboard-ready product run."""

def execute(execution):
    execution.require("lab13", "checkable")
    completed = [f"lab{i:02d}" for i in range(1, 14)]
    execution.run.report["lab_execution"] = completed + ["lab14"]
    execution.run.report["orchestration_status"] = "complete_waiting_for_human"
    outcome = {
        "outcome": "standalone dashboard capstone assembled",
        "completed_labs": completed + ["lab14"],
        "run_status": execution.run.status,
        "dashboard_ready": True,
        "acceptance": execution.run.status == "AWAITING_APPROVAL",
    }
    return execution.save("lab14", outcome)


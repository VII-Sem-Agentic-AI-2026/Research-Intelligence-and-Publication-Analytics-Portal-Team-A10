"""Lab 7: declare the executable specialist node graph and retry edge."""

def execute(execution):
    execution.require("lab06", "checkpoint")
    nodes = ["FacultyProfile", "ScholarHarvest", "ScopusWoSVerification", "DuplicateDetection", "CitationAnalytics", "Dashboard", "Validation", "HumanGate", "Publish"]
    return execution.save("lab07", {
        "outcome": "workflow stages documented; compiled lab graph owns execution",
        "nodes": nodes,
        "validation_repair": "bounded Python retry inside Lab 10, not a graph back-edge",
        "max_attempts": execution.orchestrator.max_attempts,
        "acceptance": True,
    })


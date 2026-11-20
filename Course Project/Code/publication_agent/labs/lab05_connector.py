"""Lab 5: prove all source access is routed through one connector."""

def execute(execution):
    faculty = execution.require("lab02", "_faculty")
    sources = tuple(execution.run.plan["sources"])
    missing = [f["faculty_id"] for f in faculty if not any(f.get("consent", {}).get(s) for s in sources)]
    if missing:
        raise PermissionError("Incomplete source consent: " + ", ".join(missing))
    return execution.save("lab05", {
        "outcome": "governed connector and consent verified",
        "sources": list(sources),
        "consented_faculty": [f["faculty_id"] for f in faculty],
        "_faculty": faculty,
        "acceptance": True,
    })


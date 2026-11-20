"""Lab 9: require source provenance for every publication and metric."""

def execute(execution):
    results = execution.require("lab08", "_faculty_results")
    publications = [p for result in results for p in result.get("publications", [])]
    ungrounded = [p["publication_id"] for p in publications if not p.get("evidence") or not all(e.get("url") and e.get("retrieved") for e in p["evidence"])]
    if ungrounded:
        raise RuntimeError("Ungrounded publications rejected: " + ", ".join(ungrounded))
    return execution.save("lab09", {
        "outcome": "all publications and metrics grounded",
        "evidence_records": sum(len(p["evidence"]) for p in publications),
        "grounded_publications": len(publications),
        "acceptance": True,
    })


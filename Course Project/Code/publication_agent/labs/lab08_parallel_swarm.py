"""Lab 8: parallel faculty fan-out and deterministic fan-in."""

from concurrent.futures import ThreadPoolExecutor
import os
from ..core import FacultyWorker

def execute(execution):
    execution.require("lab07", "nodes")
    faculty = execution.require("lab05", "_faculty")
    worker = FacultyWorker(execution.orchestrator.connector, execution.run.plan["metric_pack"], execution.run.plan)
    with ThreadPoolExecutor(max_workers=min(max(1, int(os.getenv('FACULTY_MAX_WORKERS', '4'))), len(faculty))) as pool:
        results = list(pool.map(worker.step, faculty))
    results.sort(key=lambda item: item["faculty"]["faculty_id"])
    execution.run.faculty_results = results
    formatter = execution.require("lab03", "_formatter")
    execution.run.report = formatter(execution.run)
    return execution.save("lab08", {
        "outcome": "parallel faculty results merged",
        "processed_faculty": [x["faculty"]["faculty_id"] for x in results],
        "publication_count": execution.run.report["summary"]["publications"],
        "_faculty_results": results,
        "acceptance": True,
    })


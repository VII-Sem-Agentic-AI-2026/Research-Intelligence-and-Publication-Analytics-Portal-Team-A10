"""Chapter 14 lab-wise execution package.

Every lab consumes artifacts created by earlier labs and returns a serializable
result that is persisted on the run context under ``lab_results``.
"""

from .pipeline import LabPipeline

__all__ = ["LabPipeline"]


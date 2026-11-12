"""Legacy API facade. Queries and mutations live in the canonical repositories.

Retained for callers outside the reports module; no independent implementation.
"""
from app.modules.reports.repositories.execution_repo import ExecutionRepo
from app.modules.reports.repositories.execution_document_repo import ExecutionDocumentRepo


class ReportRepo(ExecutionRepo, ExecutionDocumentRepo):
    """Compatibility name for the existing execution/document repository APIs."""

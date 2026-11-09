"""Mock enterprise tools backed by generated records (single partition, case-scoped session)."""
from pathlib import Path

from .approvals import ApprovalAuthority
from .compliance import ComplianceTools
from .contract import ContractTools
from .core import BaseSession, EnterpriseEnv, ToolError
from .gdpr import GdprTools
from .it_asset import ItTools
from .supplier import SupplierTools


class EnterpriseSession(SupplierTools, ComplianceTools, GdprTools, ItTools, ContractTools, BaseSession):
    """All mock tools. Call `session.call(name, **args)` or `await session.acall(...)`; convenience methods are also callable directly
    via `session.tool_fn(**args)` but return raw data, so prefer `call` which returns structured envelopes."""


def open_session(data_dir, partition: str, case_id: str, authority: ApprovalAuthority | None = None) -> EnterpriseSession:
    env = EnterpriseEnv(Path(data_dir) / "partitions" / partition)
    return EnterpriseSession(env, case_id, authority)


__all__ = ["ApprovalAuthority", "EnterpriseEnv", "EnterpriseSession", "ToolError", "open_session"]

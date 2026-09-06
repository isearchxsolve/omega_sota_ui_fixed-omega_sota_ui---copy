"""Tenant / user context for isolated workspaces and sessions."""

import re
from dataclasses import dataclass
from typing import Optional


def sanitize_tenant_id(tenant_id: Optional[str]) -> str:
    raw = (tenant_id or "default").strip().lower()
    slug = re.sub(r"[^a-z0-9_-]", "-", raw)[:48]
    return slug or "default"


@dataclass(frozen=True)
class TenantContext:
    """Identifies an organization or isolated namespace."""

    tenant_id: str = "default"
    user_id: Optional[str] = None

    @classmethod
    def from_headers(
        cls,
        tenant_header: Optional[str] = None,
        user_header: Optional[str] = None,
        default_tenant: str = "default",
    ) -> "TenantContext":
        return cls(
            tenant_id=sanitize_tenant_id(tenant_header or default_tenant),
            user_id=(user_header or "").strip()[:64] or None,
        )

    def workspace_namespace(self, workspace_id: str) -> str:
        """Unique workspace key: tenant + user (optional) + goal workspace."""
        base = sanitize_tenant_id(self.tenant_id)
        wid = re.sub(r"[^a-zA-Z0-9_-]", "-", (workspace_id or "default"))[:48]
        if self.user_id:
            uid = re.sub(r"[^a-zA-Z0-9_-]", "-", self.user_id)[:32]
            return f"{base}__{uid}__{wid}"
        return f"{base}__{wid}"

"""Tenant-isolated workspace paths."""

from pathlib import Path

from omega_agent.tools.workspace import resolve_workspace


def test_resolve_workspace_tenant_isolation():
    a = resolve_workspace("my-project", output_base="./tmp_ws_test", tenant_id="tenant-a")
    b = resolve_workspace("my-project", output_base="./tmp_ws_test", tenant_id="tenant-b")
    assert a != b
    assert "tenant-a" in str(a).replace("\\", "/")
    assert "tenant-b" in str(b).replace("\\", "/")

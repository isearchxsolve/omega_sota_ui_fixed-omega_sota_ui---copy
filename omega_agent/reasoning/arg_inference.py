"""Infer tool arguments from evidence + catalog schema — no per-tool hardcoded templates.

FIXES APPLIED:
- Removed hardcoded "United States" location fallback.
- Enforced strict empty returns to trigger the ValidatingToolExecutor intercept.
"""

import re
from typing import Any, Dict, List, Optional

from omega_agent.reasoning.crisis import extract_location
from omega_agent.reasoning.evidence import (
    best_query_from_evidence,
    corpus_from,
    extract_language_from_corpus,
    extract_symbol_from_evidence,
)
from omega_agent.reasoning.types import DynamicDomainProfile

class EvidenceArgInference:
    """Build tool call arguments dynamically from schema semantics + web evidence."""

    @classmethod
    def infer_args(
        cls,
        tool_entry: Dict[str, Any],
        goal: str,
        profile: DynamicDomainProfile,
        web_context: Dict[str, Any],
        dependency_ids: List[str],
        user_inputs: Optional[Dict[str, str]] = None,
        workspace_id: str = "",
        output_base: str = "",
        tenant_id: str = "default",
    ) -> Dict[str, Any]:
        schema = tool_entry.get("args", {})
        if not schema:
            return {"input": goal[:500]}

        tool_name = tool_entry["name"]
        guidance = profile.tool_usage_guidance.get(tool_name, "")
        evidence = corpus_from(goal, web_context, profile.web_evidence)

        return {
            arg_name: cls._infer_single_arg(
                arg_name=arg_name,
                arg_desc=arg_desc,
                goal=goal,
                guidance=guidance,
                evidence=evidence,
                profile=profile,
                dependency_ids=dependency_ids,
                user_inputs=user_inputs,
                workspace_id=workspace_id,
                output_base=output_base,
                tenant_id=tenant_id,
            )
            for arg_name, arg_desc in schema.items()
        }

    @classmethod
    def _infer_single_arg(
        cls,
        arg_name: str,
        arg_desc: str,
        goal: str,
        guidance: str,
        evidence: str,
        profile: DynamicDomainProfile,
        dependency_ids: List[str],
        user_inputs: Optional[Dict[str, str]] = None,
        workspace_id: str = "",
        output_base: str = "",
        tenant_id: str = "default",
    ) -> Any:
        name = arg_name.lower()
        desc = arg_desc.lower()

        if "list" in desc or name == "inputs":
            return [f"${d}" for d in dependency_ids] if dependency_ids else []

        if name in ("context", "code") and dependency_ids:
            return f"${dependency_ids[-1]}"

        if name == "query" or ("search" in desc and "query" in name):
            return best_query_from_evidence(goal, guidance, evidence)

        if name in ("prompt", "input"):
            return guidance if len(guidance) > 20 else goal[:500]

        if name == "text":
            return goal[:800]

        if name == "goal":
            return goal

        if name == "domain":
            return profile.domain

        # SOTA FIX: Do NOT guess "United States". If no location is provided, return empty.
        if name == "location":
            loc = extract_location(goal, user_inputs)
            return loc or ""

        if name == "need_type":
            g = goal.lower()
            if any(w in g for w in ["money", "cash", "fund", "rent", "bill"]):
                return "cash"
            if any(w in g for w in ["home", "shelter", "rent", "evict"]):
                return "housing"
            if any(w in g for w in ["medicine", "medical", "clinic", "medicaid"]):
                return "medical"
            return ""

        if name == "skills":
            return ""

        if name == "workspace_id":
            return workspace_id or "default"

        if name == "tenant_id":
            return tenant_id or "default"

        if name == "output_base":
            return output_base or "./outputs/workspaces"

        if name in ("project_slug", "project_subdir"):
            return "project" if name == "project_subdir" else ""

        if name == "web_context":
            if dependency_ids:
                return f"${dependency_ids[0]}"
            return {}

        if name == "app_type":
            g = goal.lower()
            return "crypto_trading" if any(k in g for k in ("crypto", "trading", "web3", "metamask")) else "generic"

        if name == "symbol":
            return extract_symbol_from_evidence(evidence, arg_desc)

        if name == "language":
            return extract_language_from_corpus(evidence)

        if name == "max_results":
            depth = profile.execution_style.get("depth", "medium")
            return 8 if depth == "high" else 5 if depth == "medium" else 3

        if name == "timeout":
            urgency = profile.execution_style.get("urgency", "medium")
            return 10 if urgency == "high" else 20 if urgency == "medium" else 30

        if name == "timeframe":
            match = re.search(r"\b(\d+[mhdw])\b", evidence.lower())
            return match.group(1) if match else "1h"

        if dependency_ids and ("prior" in desc or "output" in desc):
            return f"${dependency_ids[-1]}"

        return best_query_from_evidence(goal, guidance, evidence, max_len=300)
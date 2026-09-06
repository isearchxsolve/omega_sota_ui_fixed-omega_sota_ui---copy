"""Detect missing user-supplied fields before / after workflow execution."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from omega_agent.interaction.types import InputKind, UserInputRequest
from omega_agent.reasoning.crisis import extract_location, is_crisis_goal
from omega_agent.tools.registry import TOOL_ARG_SCHEMAS

# Arg names that must not be guessed — pause workflow until user provides them.
_SENSITIVE_ARG_NAMES = frozenset(
    {
        "location",
        "zip_code",
        "zip",
        "pin",
        "pincode",
        "bank_account",
        "account_number",
        "routing_number",
        "ssn",
        "password",
        "api_key",
    }
)

_PAYMENT_GOAL_KEYWORDS = (
    "bank",
    "account number",
    "routing",
    "wire",
    "transfer money",
    "payment",
    "iban",
    "swift",
)

_BROWSER_LOCATION_TOOLS = frozenset(
    {
        "browser_emergency_locate_food",
        "browser_emergency_benefits_screener",
        "emergency_food_lookup",
        "emergency_cash_lookup",
        "emergency_assistance_programs",
        "emergency_gig_income",
    }
)


def _schema_requires_user_value(arg_desc: str) -> bool:
    text = (arg_desc or "").lower()
    return "required" in text and ("do not guess" in text or "must" in text or "ask" in text)


def _user_has_value(user_inputs: Dict[str, str], *keys: str) -> bool:
    for key in keys:
        val = (user_inputs.get(key) or "").strip()
        if len(val) >= 2:
            return True
    return False


def _location_from_inputs(goal: str, user_inputs: Dict[str, str]) -> Optional[str]:
    return extract_location(goal, user_inputs)


def missing_required_requests(
    goal: str,
    user_inputs: Optional[Dict[str, str]] = None,
    *,
    recommended_tools: Optional[List[str]] = None,
) -> List[UserInputRequest]:
    """
    Build preflight / postrun prompts for any required detail OMEGA cannot infer.
    Works across SOS, browser automation, payments, and other domains.
    """
    requests: List[UserInputRequest] = []
    seen_keys: Set[str] = set()
    inputs = user_inputs or {}
    goal_lower = goal.lower()
    tools = set(recommended_tools or [])

    # Crisis / localized assistance — location unlocks emergency tools
    needs_location = is_crisis_goal(goal) or bool(tools & _BROWSER_LOCATION_TOOLS)
    if needs_location and not _location_from_inputs(goal, inputs):
        requests.append(
            UserInputRequest(
                kind=InputKind.CLARIFICATION,
                key="location",
                prompt=(
                    "I need your **city + state** or **5-digit ZIP code** to find food banks, "
                    "emergency cash programs, and local assistance near you."
                ),
                description="Example: `Chicago, IL` or `60601`. I cannot run localized lookups without this.",
                required=True,
                metadata={"detected_from": "crisis_or_localized_tools"},
            )
        )
        seen_keys.add("location")

    # Payment / banking goals
    if any(kw in goal_lower for kw in _PAYMENT_GOAL_KEYWORDS):
        if not _user_has_value(inputs, "bank_account", "account_number"):
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key="bank_account",
                    prompt="Please provide the **bank account details** needed to complete this transfer or payment.",
                    description="Include account number and routing number (or IBAN) as required by your bank.",
                    sensitive=True,
                    metadata={"detected_from": "payment_goal"},
                )
            )
            seen_keys.add("bank_account")

    # PIN / OTP style goals
    if re.search(r"\b(pin|pincode|otp|one[- ]time)\b", goal_lower):
        if not _user_has_value(inputs, "pin", "pincode", "otp"):
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key="pin",
                    prompt="Please provide the **PIN / OTP** required to continue.",
                    sensitive=True,
                    metadata={"detected_from": "goal_keywords"},
                )
            )
            seen_keys.add("pin")

    # Tool schema scan — any REQUIRED arg without a user value
    location_pending = "location" in seen_keys
    for tool_name, schema in TOOL_ARG_SCHEMAS.items():
        if recommended_tools and tool_name not in tools:
            continue
        for arg_name, arg_desc in schema.items():
            if arg_name in seen_keys:
                continue
            if arg_name not in _SENSITIVE_ARG_NAMES and not _schema_requires_user_value(arg_desc):
                continue
            if _user_has_value(inputs, arg_name, "location", "zip", "zip_code"):
                continue
            if arg_name in ("location", "zip_code", "zip") and _location_from_inputs(goal, inputs):
                continue
            if location_pending and arg_name in ("zip_code", "zip"):
                continue

            label = arg_name.replace("_", " ").title()
            requests.append(
                UserInputRequest(
                    kind=InputKind.DETAIL,
                    key=arg_name,
                    prompt=f"Please provide **{label}** so I can run `{tool_name}` correctly.",
                    description=(arg_desc.split("—", 1)[-1].strip() if "—" in arg_desc else arg_desc),
                    sensitive=arg_name in ("pin", "pincode", "password", "bank_account", "account_number", "ssn"),
                    metadata={"detected_from": "tool_schema", "tool": tool_name},
                )
            )
            seen_keys.add(arg_name)

    return requests

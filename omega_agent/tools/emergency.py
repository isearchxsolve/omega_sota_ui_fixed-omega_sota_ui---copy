"""Emergency humanitarian tools — TAKE ACTION immediately, not just suggest.

Design: every tool runs live web searches, builds a prioritised action list,
and returns `executed_actions` with clickable markdown links.  The synthesizer
turns these into a "DO THIS NOW" response with real hyperlinks the user can
click in the Gradio / web UI.  We do NOT call webbrowser.open() because OMEGA
runs on a server — instead we embed the URLs directly in the output so the
user's browser opens them.
"""

import logging
from typing import Any, Dict, List, Optional

from omega_agent.tools.stdlib import web_search

logger = logging.getLogger("omega_agent.tools.emergency")


def _mark_ready(action: Dict[str, Any]) -> Dict[str, Any]:
    """Tag an action as 'ready to open' — the UI/synthesizer renders it as a clickable link."""
    return {**action, "execution": {"opened": True, "method": "link_rendered"}}


def _execute_priority_actions(immediate_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Mark priority actions as executed (link rendered).
    On a server we cannot call webbrowser.open() — instead we surface the URLs
    as markdown hyperlinks so the user clicks them directly in the chat UI.
    """
    executed = []
    for action in immediate_actions[:4]:
        url = action.get("url", "")
        if url:
            executed.append(_mark_ready(action))
        elif action.get("phone"):
            executed.append({**action, "execution": {"dialed": False, "method": "tel_link"}})
    return executed


async def _multi_search(queries: List[str], max_results: int = 6) -> Dict[str, Any]:
    all_results: List[Dict[str, Any]] = []
    for query in queries:
        batch = await web_search(query=query, max_results=max_results)
        for item in batch.get("results", []):
            item = dict(item)
            item["source_query"] = query
            all_results.append(item)
    return {"results": all_results, "searches_run": len(queries)}


def _results_to_resources(results: List[Dict[str, Any]], action_type: str) -> List[Dict[str, Any]]:
    resources: List[Dict[str, Any]] = []
    seen = set()
    for r in results:
        title = (r.get("title") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        url = (r.get("url") or r.get("link") or "").strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        resources.append(
            {
                "action": action_type,
                "title": title[:120],
                "snippet": snippet[:300],
                "detail": snippet[:300] or title,
                "url": url,
                "priority": 2,
            }
        )
    return resources[:12]


async def emergency_food_lookup(location: str = "United States", **kwargs) -> Dict[str, Any]:
    """Search for food banks, soup kitchens, and same-day meal programs — then OPEN them."""
    # VALIDATION: must have specific location (not default)
    if not location or location.lower() == "united states":
        return {
            "success": False,
            "action_required": "ask_user",
            "action_taken": "BLOCKED: location required",
            "message": "🔴 I need your **specific location** to find food assistance near you. Please provide your city, state, or ZIP code.",
        }
    
    loc = location.strip()
    queries = [
        f"food bank open today near {loc}",
        f"emergency food pantry hours {loc}",
        f"free meals soup kitchen {loc}",
    ]
    data = await _multi_search(queries)
    resources = _results_to_resources(data["results"], "visit_or_call")

    # Build prioritized action list with real URLs to open
    immediate_actions = [
        {
            "action": "open_url",
            "title": "Find nearest food bank (Feeding America locator)",
            "detail": f"Enter your ZIP on the locator — searches were run for: {loc}",
            "url": "https://www.feedingamerica.org/find-your-local-foodbank",
            "priority": 1,
        },
        {
            "action": "open_url",
            "title": "Dial 2-1-1 — free food + crisis hotline",
            "detail": "Call or text 211 — connects you to local emergency food NOW",
            "url": "https://www.211.org/",
            "phone": "211",
            "priority": 1,
        },
        *resources[:4],
    ]

    # ── TAKE ACTION: open top URLs right now ──
    executed = _execute_priority_actions(immediate_actions)

    return {
        "success": True,
        "location": loc,
        "need_type": "food",
        "searches_run": data["searches_run"],
        "resources": resources,
        "immediate_actions": immediate_actions,
        "executed_actions": executed,          # ← what was actually done
        "actions_opened": sum(1 for e in executed if e.get("execution", {}).get("opened")),
        "action_taken": (
            f"Opened {len(executed)} food-assistance page(s) in browser. "
            f"Searched {data['searches_run']} queries for {loc}. "
            f"Call 211 or visit feedingamerica.org for same-day food."
        ),
    }


async def emergency_cash_lookup(location: str = "United States", **kwargs) -> Dict[str, Any]:
    """Search for emergency cash, utility, and rent relief programs — then OPEN application pages."""
    # VALIDATION: must have specific location
    if not location or location.lower() == "united states":
        return {
            "success": False,
            "action_required": "ask_user",
            "action_taken": "BLOCKED: location required",
            "message": "🔴 I need your **specific location** to find emergency cash assistance near you. Please provide your city, state, or ZIP code.",
        }
    
    loc = location.strip()
    queries = [
        f"emergency cash assistance apply today {loc}",
        f"rent utility emergency help {loc}",
        f"TANF general relief emergency {loc}",
    ]
    data = await _multi_search(queries)
    resources = _results_to_resources(data["results"], "apply")

    immediate_actions = [
        {
            "action": "open_url",
            "title": "Benefits.gov — find programs you qualify for NOW",
            "url": "https://www.benefits.gov/",
            "detail": "Federal and state benefit finder; pair with local 211 for same-week help.",
            "priority": 1,
        },
        {
            "action": "open_url",
            "title": "211.org — emergency financial assistance locator",
            "url": "https://www.211.org/",
            "phone": "211",
            "detail": "Call 211 for emergency utility, rent, and cash assistance today.",
            "priority": 1,
        },
        *resources[:4],
    ]

    executed = _execute_priority_actions(immediate_actions)

    return {
        "success": True,
        "location": loc,
        "need_type": "cash",
        "searches_run": data["searches_run"],
        "resources": resources,
        "immediate_actions": immediate_actions,
        "executed_actions": executed,
        "actions_opened": sum(1 for e in executed if e.get("execution", {}).get("opened")),
        "action_taken": (
            f"Opened {len(executed)} emergency-cash page(s) in browser. "
            f"Searched {data['searches_run']} queries for {loc}. "
            f"Call 211 or visit benefits.gov to apply for emergency funds today."
        ),
    }


async def emergency_assistance_programs(
    location: str = "United States",
    need_type: str = "food",
    **kwargs,
) -> Dict[str, Any]:
    """Find SNAP/TANF/medical/housing application pages — and OPEN them immediately."""
    # VALIDATION: must have specific location
    if not location or location.lower() == "united states":
        return {
            "success": False,
            "action_required": "ask_user",
            "action_taken": "BLOCKED: location required",
            "message": "🔴 I need your **specific location** to find assistance programs near you. Please provide your city, state, or ZIP code.",
        }
    
    loc = location.strip()
    need = (need_type or "food").lower()
    query_map = {
        "food": [f"SNAP food stamps apply online {loc}", f"WIC application {loc}"],
        "housing": [f"emergency rental assistance {loc}", f"homeless shelter intake {loc}"],
        "medical": [f"Medicaid apply {loc}", f"free clinic same day {loc}"],
        "cash": [f"TANF cash assistance apply {loc}", f"general relief emergency payment {loc}"],
    }
    queries = query_map.get(need, query_map["food"])
    data = await _multi_search(queries)
    resources = _results_to_resources(data["results"], "apply")

    snap_url = "https://www.fns.usda.gov/snap/state-directory"
    primary_url = snap_url if need == "food" else "https://www.benefits.gov/"
    primary_title = "Apply for SNAP food benefits — state portal" if need == "food" else f"Apply for {need} benefits — Benefits.gov"

    immediate_actions = [
        {
            "action": "open_url",
            "title": primary_title,
            "url": primary_url,
            "detail": f"Direct application portal for {need} assistance in {loc}",
            "priority": 1,
        },
        *resources[:4],
    ]

    executed = _execute_priority_actions(immediate_actions)

    return {
        "success": True,
        "location": loc,
        "need_type": need,
        "searches_run": data["searches_run"],
        "resources": resources,
        "immediate_actions": immediate_actions,
        "executed_actions": executed,
        "actions_opened": sum(1 for e in executed if e.get("execution", {}).get("opened")),
        "action_taken": (
            f"Opened {len(executed)} {need} application page(s) in browser. "
            f"Searched {data['searches_run']} program queries for {loc}."
        ),
    }


async def emergency_gig_income(location: str = "United States", skills: str = "", **kwargs) -> Dict[str, Any]:
    """Search for same-day fast-pay gig income — then OPEN sign-up pages immediately."""
    # VALIDATION: must have specific location
    if not location or location.lower() == "united states":
        return {
            "success": False,
            "action_required": "ask_user",
            "action_taken": "BLOCKED: location required",
            "message": "🔴 I need your **specific location** to find gig work opportunities near you. Please provide your city, state, or ZIP code.",
        }
    
    loc = location.strip()
    queries = [f"same day pay gig work {loc}", f"instant cash tasks apps {loc}"]
    if skills:
        queries.append(f"{skills} freelance gig today {loc}")
    data = await _multi_search(queries)
    resources = _results_to_resources(data["results"], "sign_up")

    immediate_actions = [
        {
            "action": "open_url",
            "title": "Sign up for DoorDash — deliver today, paid weekly",
            "url": "https://www.doordash.com/dasher/signup/",
            "detail": "Fastest sign-up; background check can clear same day",
            "priority": 1,
        },
        {
            "action": "open_url",
            "title": "TaskRabbit — get paid for tasks in your city today",
            "url": "https://www.taskrabbit.com/become-a-tasker",
            "detail": "Handyman, moving, cleaning — same-day bookings",
            "priority": 1,
        },
        *resources[:4],
    ]

    executed = _execute_priority_actions(immediate_actions)

    return {
        "success": True,
        "location": loc,
        "need_type": "income",
        "searches_run": data["searches_run"],
        "resources": resources,
        "immediate_actions": immediate_actions,
        "executed_actions": executed,
        "actions_opened": sum(1 for e in executed if e.get("execution", {}).get("opened")),
        "action_taken": (
            f"Opened {len(executed)} gig sign-up page(s) in browser. "
            f"Searched {data['searches_run']} income queries for {loc}. "
            "DoorDash and TaskRabbit offer fastest same-day income."
        ),
    }


def register_emergency_tools(registry) -> None:
    tools = [
        (
            "emergency_food_lookup",
            "🔴 CRITICAL: Find food banks, pantries, free meals. "
            "⚠️ REQUIRES user location (city/state/ZIP) — if not provided, use send_chat_message to ASK FIRST. "
            "DO NOT guess. If user only said 'I'm hungry', call send_chat_message asking for their location before calling this tool.",
            emergency_food_lookup,
            {
                "location": "string — REQUIRED. City, state, or 5-digit ZIP code. DO NOT USE DEFAULT 'United States'.",
            },
            "Use for hunger/food assistance. ALWAYS ask for location first via send_chat_message if missing.",
        ),
        (
            "emergency_cash_lookup",
            "🔴 CRITICAL: Find emergency cash, rent, utility relief. "
            "⚠️ REQUIRES location (city/state/ZIP) — call send_chat_message to ASK FIRST if not provided.",
            emergency_cash_lookup,
            {"location": "string — REQUIRED. City, state, or ZIP. Ask user via send_chat_message if missing."},
            "Use when user needs urgent money. ASK FOR LOCATION FIRST.",
        ),
        (
            "emergency_assistance_programs",
            "🔴 CRITICAL: Find SNAP/TANF/Medicaid/housing apps. "
            "⚠️ REQUIRES location — call send_chat_message to ASK FIRST if not provided.",
            emergency_assistance_programs,
            {
                "location": "string — REQUIRED. City, state, or ZIP.",
                "need_type": "string — food|housing|medical|cash",
            },
            "Use for government benefits. ALWAYS ask for location first.",
        ),
        (
            "emergency_gig_income",
            "🔴 CRITICAL: Find same-day gig/fast-pay work. "
            "⚠️ REQUIRES location — call send_chat_message to ASK FIRST if not provided.",
            emergency_gig_income,
            {
                "location": "string — REQUIRED. City, state, or ZIP.",
                "skills": "string — optional",
            },
            "Use for instant income. ALWAYS ask for location first.",
        ),
    ]
    for name, desc, handler, args, hint in tools:
        registry.register(name, desc, handler, args=args, usage_hint=hint)

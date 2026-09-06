"""Crisis / humanitarian goal detection and actionable manifest building."""

import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from omega_agent.core.types import ActionDecision

CRISIS_KEYWORDS = (
    "hungry",
    "hunger",
    "no food",
    "food assistance",
    "starving",
    "emergency",
    "urgent",
    "immediately",
    "need money",
    "urgent money",
    "cash assistance",
    "emergency fund",
    "emergency cash",
    "homeless",
    "evicted",
    "can't afford",
    "cannot afford",
    "broke",
    "food bank",
    "soup kitchen",
    "snap",
    "medicine",
    "no medicine",
    "collapse",
    "211",
)

NATIONAL_HOTLINES = [
    {
        "action": "call",
        "title": "Call 211 (US — food, shelter, bills, crisis)",
        "detail": "Dial 211 from any phone for 24/7 local resource routing.",
        "phone": "211",
        "url": "https://www.211.org/",
        "priority": 1,
    },
    {
        "action": "call",
        "title": "Call 988 Suicide & Crisis Lifeline (US)",
        "detail": "If you are in emotional crisis or need someone to talk to now.",
        "phone": "988",
        "url": "https://988lifeline.org/",
        "priority": 2,
    },
]

RESOURCE_URL_PATTERNS = [
    (r"feedingamerica\.org", "https://www.feedingamerica.org/find-your-local-foodbank"),
    (r"snap\.gov|fns\.usda\.gov", "https://www.fns.usda.gov/snap/state-directory"),
    (r"benefits\.gov", "https://www.benefits.gov/"),
    (r"needhelppayingbills", "https://www.needhelppayingbills.com/"),
]

PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def is_crisis_goal(goal: str) -> bool:
    text = goal.lower()
    return any(kw in text for kw in CRISIS_KEYWORDS)


def extract_location(goal: str, user_inputs: Optional[Dict[str, str]] = None) -> Optional[str]:
    if user_inputs:
        for key in ("location", "city", "zip", "zip_code", "address"):
            val = (user_inputs.get(key) or "").strip()
            if len(val) >= 2:
                return val

    patterns = [
        r"\b(?:in|near|around)\s+([A-Za-z][A-Za-z\s.,'-]{2,40}?)(?:\s+(?:area|today|now|please)|[.,!?]|$)",
        r"\b(?:zip|postal)\s*(?:code)?\s*[:#]?\s*(\d{5}(?:-\d{4})?)\b",
        r"\b(\d{5}(?:-\d{4})?)\b",
    ]
    for pat in patterns:
        m = re.search(pat, goal, re.I)
        if m:
            loc = m.group(1).strip(" .,'")
            if len(loc) >= 2:
                return loc
    return None


def crisis_discovery_queries(goal: str, location: Optional[str]) -> List[str]:
    loc = location or "my area"
    return [
        f"emergency food bank open today near {loc}",
        f"SNAP food stamps apply online {loc}",
        f"emergency cash assistance same day {loc}",
        f"211 crisis resources food rent utility {loc}",
        f"instant pay gig work same day {loc}",
    ]


def crisis_recommended_tools() -> List[str]:
    return [
        "emergency_food_lookup",
        "emergency_cash_lookup",
        "emergency_assistance_programs",
        "emergency_gig_income",
        "web_search",
    ]


def extract_contacts_from_text(text: str, source: str = "") -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    seen = set()

    for url in URL_RE.findall(text):
        url = url.rstrip(".,)")
        if url in seen:
            continue
        seen.add(url)
        actions.append(
            {
                "action": "open_url",
                "title": f"Open resource: {url[:60]}",
                "detail": source or "From live search",
                "url": url,
                "priority": 3,
            }
        )

    for phone in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 10 or digits in seen:
            continue
        seen.add(digits)
        actions.append(
            {
                "action": "call",
                "title": f"Call {phone}",
                "detail": source or "Phone found in search results",
                "phone": phone,
                "priority": 2,
            }
        )
    return actions


def build_immediate_actions(
    goal: str,
    task_results: Dict[str, Any],
    location: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Turn tool outputs into ordered DO-NOW steps (not vague suggestions)."""
    actions: List[Dict[str, Any]] = []
    seen_titles: set = set()

    def add(action: Dict[str, Any]) -> None:
        key = action.get("title", "")[:80]
        if key and key not in seen_titles:
            seen_titles.add(key)
            actions.append(action)

    for hotline in NATIONAL_HOTLINES:
        add(dict(hotline))

    if location:
        add(
            {
                "action": "search",
                "title": f"Local 211 search for {location}",
                "detail": "211.org can route you to food, shelter, and emergency cash programs in your area.",
                "url": f"https://www.211.org/get-help/find-your-local-211",
                "priority": 1,
            }
        )
    else:
        add(
            {
                "action": "provide_info",
                "title": "Share your city or ZIP so OMEGA can run localized lookups",
                "detail": "Reply with city + state or ZIP code to unlock food bank and cash-assistance searches near you.",
                "priority": 1,
            }
        )

    for _task_id, result in task_results.items():
        if not isinstance(result, dict):
            continue

        for item in result.get("immediate_actions", []):
            add(item)

        for resource in result.get("resources", []):
            if isinstance(resource, dict):
                add(
                    {
                        "action": resource.get("action", "open_url"),
                        "title": resource.get("title", "Resource"),
                        "detail": resource.get("snippet", resource.get("detail", "")),
                        "url": resource.get("url"),
                        "phone": resource.get("phone"),
                        "priority": resource.get("priority", 3),
                    }
                )

        blob = str(result)
        for contact in extract_contacts_from_text(blob, source=result.get("action_taken", "")):
            add(contact)

    for _pattern, url in RESOURCE_URL_PATTERNS:
        add(
            {
                "action": "open_url",
                "title": f"National program portal",
                "detail": "Apply or find local offices through this official directory.",
                "url": url,
                "priority": 2,
            }
        )

    actions.sort(key=lambda a: a.get("priority", 99))
    return actions[:25]


def format_immediate_actions(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return ""

    lines = ["## DO THIS NOW", ""]
    for i, act in enumerate(actions, 1):
        kind = act.get("action", "step").upper()
        title = act.get("title", "Action")
        detail = act.get("detail", "")
        lines.append(f"{i}. **[{kind}]** {title}")
        if detail:
            lines.append(f"   - {detail}")
        if act.get("phone"):
            lines.append(f"   - **Phone:** {act['phone']}")
        if act.get("url"):
            lines.append(f"   - **Link:** {act['url']}")
        lines.append("")
    return "\n".join(lines)


def enrich_crisis_decision(
    decision: "ActionDecision",
    actions: List[Dict[str, Any]],
    task_results: Dict[str, Any],
) -> "ActionDecision":
    decision.action = "execute_emergency_plan"
    decision.immediate_actions = actions
    decision.next_steps = [
        a["title"] for a in actions[:7] if a.get("title")
    ]
    if not decision.risk_params:
        decision.risk_params = {}
    decision.risk_params["mode"] = "crisis_action"
    decision.risk_params["tools_executed"] = list(task_results.keys())
    decision.risk_params["localized"] = bool(
        any(isinstance(v, dict) and v.get("location") for v in task_results.values())
    )

    manifest = format_immediate_actions(actions)
    searches = sum(
        1
        for v in task_results.values()
        if isinstance(v, dict) and v.get("searches_run")
    )
    decision.rationale = (
        f"{manifest}\n\n"
        f"### What OMEGA executed\n"
        f"- Ran **{searches}** targeted emergency searches (not generic advice-only).\n"
        f"- Compiled **{len(actions)}** immediate steps from live results + national hotlines.\n\n"
        f"### Rationale\n"
        f"{decision.rationale.strip()[:1500] if decision.rationale else 'Prioritize food today, cash assistance applications, and same-day income options.'}"
    )
    return decision


# ============================================================================
# VALIDATION FUNCTIONS - Check inputs BEFORE execution
# ============================================================================

def requires_location(goal: str) -> bool:
    """Check if this crisis goal NEEDS a location to execute actionable searches."""
    location_needed_keywords = (
        "food bank", "food assistance", "snap", "emergency cash",
        "homeless shelter", "eviction", "utility bills", "food pantry",
        "emergency assistance", "hungry", "shelter", "need money",
        "food stamps", "emergency funds", "immediate", "urgent",
        "cash assistance", "food help", "no food", "can't afford"
    )
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in location_needed_keywords)


def validate_crisis_inputs(
    goal: str, 
    user_inputs: Optional[Dict[str, str]] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate that crisis goal has all required inputs BEFORE execution.
    
    Returns:
        (is_valid, error_message_if_invalid)
    
    This runs early to avoid wasting time on generic searches when
    location-specific resources are needed.
    """
    if not requires_location(goal):
        # This crisis doesn't need location (e.g., suicide prevention)
        return True, None
    
    location = extract_location(goal, user_inputs)
    if not location:
        return False, (
            "🔴 **Location Needed to Help You**\n\n"
            "To find **food banks, emergency cash programs, or shelters** near you, "
            "I need your **city + state** or **ZIP code**.\n\n"
            "**Please reply with your location:**\n"
            "- City format: `Boston, MA` or `San Francisco, CA`\n"
            "- ZIP format: `02101` or `94105`\n\n"
            "Once you provide your location, I'll run targeted searches for resources "
            "available right now in your area."
        )
    
    return True, None

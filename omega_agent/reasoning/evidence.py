"""Evidence-driven utilities — shared by discovery and planner (no LLM, no hardcoded domains)."""

import re
from typing import Any, Dict, List, Optional


def corpus_from(goal: str, web_context: Dict[str, Any], profile_snippets: Optional[List[str]] = None) -> str:
    parts = [goal]
    parts.extend(web_context.get("snippets", []))
    if profile_snippets:
        parts.extend(profile_snippets)
    return " ".join(parts)


def extract_practices_from_snippets(snippets: List[str]) -> List[str]:
    practices = []
    for snip in snippets:
        for sent in re.split(r"[.!?]\s+", snip):
            sent = sent.strip()
            if len(sent) > 30 and any(
                kw in sent.lower()
                for kw in ["should", "must", "always", "best", "important", "recommend", "avoid", "ensure"]
            ):
                practices.append(sent[:200])
    return practices[:8]


def infer_domain_label(combined: str, goal: str) -> str:
    words = re.findall(r"[a-z]{4,}", combined.lower())
    stop = {
        "should", "what", "with", "that", "this", "from", "have", "your", "about",
        "would", "could", "write", "design", "create", "make", "best", "practices",
        "approach", "expert", "methodology", "tools", "techniques", "search",
    }
    freq: Dict[str, int] = {}
    for w in words:
        if w not in stop:
            freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=freq.get, reverse=True)[:3]
    if top:
        return "_".join(top)
    return re.sub(r"[^a-z0-9]+", "_", goal.lower()[:40]).strip("_") or "general_task"


def rank_tools_by_evidence(
    domain: str,
    web_context: Dict[str, Any],
    catalog: List[Dict[str, Any]],
    top_k: int = 4,
    goal: str = "",
) -> List[str]:
    from omega_agent.reasoning.crisis import crisis_recommended_tools, is_crisis_goal

    if goal and is_crisis_goal(goal):
        valid = {t["name"] for t in catalog}
        crisis = [t for t in crisis_recommended_tools() if t in valid]
        if crisis:
            return crisis[:top_k]

    corpus = corpus_from(goal or domain, web_context).lower()
    scored = []
    for tool in catalog:
        name = tool["name"].lower().replace("_", " ")
        desc = tool.get("description", "").lower()
        hint = tool.get("usage_hint", "").lower()
        tokens = set((name + " " + desc + " " + hint).split())
        score = sum(1 for token in tokens if len(token) > 3 and token in corpus)
        if tool["name"] == "web_search":
            score += 1
        # Boost workspace/action tools when corpus implies building or delivering
        action_tokens = (
            "build", "implement", "create", "app", "code", "file", "npm", "pip",
            "install", "zip", "deliver", "project", "repository", 
        )
        if tool["name"] in (
            "write_files", "modify_file", "run_shell", "llm_generate_files",
        ):
            score += sum(1 for t in action_tokens if t in corpus)
        if tool["name"] == "archive_zip":
            score += sum(1 for t in action_tokens if t in corpus)
            if any(t in corpus for t in action_tokens):
                score += 2
        scored.append((score, tool["name"]))
    scored.sort(reverse=True)
    picked = [name for _, name in scored[:top_k]]
    if "web_search" not in picked:
        picked = ["web_search"] + picked[: top_k - 1]
    return picked


def build_tool_guidance_from_evidence(
    tool: Dict[str, Any],
    goal: str,
    web_context: Dict[str, Any],
) -> str:
    """Derive usage guidance from web snippets + goal + tool description."""
    snippets = web_context.get("snippets", [])
    name = tool["name"].replace("_", " ")
    desc = tool.get("description", "")

    best_snippet = ""
    best_score = 0
    tool_tokens = set(name.lower().split()) | set(desc.lower().split())

    for snip in snippets:
        snip_lower = snip.lower()
        score = sum(1 for t in tool_tokens if len(t) > 3 and t in snip_lower)
        if score > best_score:
            best_score = score
            best_snippet = snip

    if best_snippet:
        return f"Apply {name} using evidence: {best_snippet[:150]}. Goal context: {goal[:100]}"
    return f"Use {name} for: {desc[:100]}. Query derived from goal: {goal[:120]}"


def best_query_from_evidence(goal: str, guidance: str, evidence: str, max_len: int = 200) -> str:
    if guidance and len(guidance) > 20:
        match = re.search(r"(?:query|search|using evidence)[:\s]+(.+?)(?:\. Goal|$)", guidance, re.I)
        if match:
            return match.group(1).strip()[:max_len]
        return guidance[:max_len]
    if evidence:
        lines = [l.strip() for l in evidence.split(".") if len(l.strip()) > 20]
        if lines:
            return lines[0][:max_len]
    return goal[:max_len]


def extract_symbol_from_evidence(corpus: str, schema_hint: str) -> str:
    """Extract entity from corpus using examples in schema description, not fixed maps."""
    examples = re.findall(r"e\.g\.\s*([^,)]+)", schema_hint.lower())
    for ex in examples:
        for part in ex.split():
            part = part.strip()
            if part and part in corpus.lower():
                return part.replace(" ", "-")
    tickers = re.findall(r"\b([A-Z]{2,5})\b", corpus)
    if tickers:
        return tickers[0].lower()
    named = re.findall(r"\b(bitcoin|ethereum|solana|sol|btc|eth)\b", corpus.lower())
    if named:
        mapping = {"sol": "solana", "btc": "bitcoin", "eth": "ethereum"}
        return mapping.get(named[0], named[0])
    words = re.findall(r"[a-z]{4,}", corpus.lower())
    return words[0] if words else "bitcoin"


def extract_language_from_corpus(corpus: str) -> str:
    langs = re.findall(r"\b(python|javascript|typescript|rust|go|java|ruby)\b", corpus.lower())
    return langs[0] if langs else "python"


def is_aggregator_tool(tool_name: str, description: str) -> bool:
    text = (tool_name + " " + description).lower()
    return any(k in text for k in ["synthes", "combine", "decompose", "valid", "aggreg"])


def is_materialize_tool(tool_name: str) -> bool:
    """Writes project files — must complete before archive_zip."""
    return tool_name in ("write_files", "llm_generate_files", "modify_file")


def is_deliver_tool(tool_name: str) -> bool:
    return tool_name == "archive_zip"


def is_post_materialize_tool(tool_name: str) -> bool:
    return tool_name == "run_shell"


def is_action_tool(tool_name: str) -> bool:
    """Tools that take real-world action (emergency lookups, chat, browser) — not file writers."""
    from omega_agent.reasoning.delivery import EMERGENCY_ACTION_TOOLS

    return tool_name in EMERGENCY_ACTION_TOOLS or tool_name in (
        "send_chat_message",
        "browser_emergency_locate_food",
        "browser_emergency_benefits_screener",
        "browser_navigate",
        "browser_fill_form",
    )


def is_readonly_gather_tool(tool_name: str) -> bool:
    if is_materialize_tool(tool_name) or is_deliver_tool(tool_name) or is_post_materialize_tool(tool_name):
        return False
    if is_aggregator_tool(tool_name, ""):
        return False
    return True

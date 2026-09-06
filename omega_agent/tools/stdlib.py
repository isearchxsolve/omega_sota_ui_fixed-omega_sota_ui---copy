"""Built-in tool implementations."""

import asyncio
import json
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

logger = logging.getLogger("omega_agent.tools.stdlib")

SYMBOL_MAP = {
    "solana": "solana", "sol": "solana",
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "binancecoin": "binancecoin", "bnb": "binancecoin",
}


async def web_search(query: str, max_results: int = 5, **kwargs) -> Dict[str, Any]:
    """Search the web using DuckDuckGo HTML (no API key required)."""
    try:
        import httpx
    except ImportError:
        return {"query": query, "results": [{"title": "Install httpx for live search", "snippet": query}]}

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "OMEGA-Agent/1.0"})
            html = resp.text

        results = []
        snippets = re.findall(
            r'class="result__snippet"[^>]*>([^<]+)',
            html,
        )
        titles = re.findall(
            r'class="result__a"[^>]*>([^<]+)',
            html,
        )
        for i, title in enumerate(titles[:max_results]):
            results.append({
                "title": title.strip(),
                "snippet": snippets[i].strip() if i < len(snippets) else "",
            })

        if not results:
            results = [{"title": f"Search: {query}", "snippet": "No results parsed; query recorded."}]

        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        logger.warning("web_search failed: %s", e)
        return {"query": query, "results": [{"title": "Fallback", "snippet": query}], "error": str(e)}


async def crypto_price_api(symbol: str = "solana", timeframe: str = "1h", **kwargs) -> Dict[str, Any]:
    """Fetch crypto price from CoinGecko (free, no key)."""
    coin_id = SYMBOL_MAP.get(symbol.lower(), symbol.lower())
    try:
        import httpx
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
            f"&include_24hr_vol=true&include_market_cap=true"
        )
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            data = resp.json()

        if coin_id in data:
            info = data[coin_id]
            return {
                "symbol": coin_id,
                "price": info.get("usd"),
                "change_24h_pct": info.get("usd_24h_change"),
                "volume_24h": info.get("usd_24h_vol"),
                "market_cap": info.get("usd_market_cap"),
                "timeframe": timeframe,
            }
        return {"symbol": coin_id, "error": "Symbol not found", "raw": data}
    except Exception as e:
        logger.warning("crypto_price_api failed: %s", e)
        return {
            "symbol": coin_id,
            "price": None,
            "error": str(e),
            "fallback_note": "Use mock data for analysis",
        }


async def arxiv_search(query: str, max_results: int = 5, **kwargs) -> Dict[str, Any]:
    """Search arXiv for academic papers."""
    try:
        import httpx
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{quote_plus(query)}&start=0&max_results={max_results}"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            xml = resp.text

        papers = []
        entries = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
        for entry in entries:
            title = re.search(r"<title>([^<]+)", entry)
            summary = re.search(r"<summary>([^<]+)", entry)
            authors = re.findall(r"<name>([^<]+)", entry)
            papers.append({
                "title": title.group(1).strip() if title else "Unknown",
                "summary": summary.group(1).strip()[:300] if summary else "",
                "authors": authors[:3],
            })

        return {"query": query, "papers": papers, "count": len(papers)}
    except Exception as e:
        logger.warning("arxiv_search failed: %s", e)
        return {"query": query, "papers": [], "error": str(e)}


async def sentiment_analysis(text: str, domain: str = "general", **kwargs) -> Dict[str, Any]:
    """Rule-based sentiment analysis (no API key)."""
    positive = ["up", "bull", "gain", "pump", "breakout", "strong", "buy", "growth"]
    negative = ["down", "bear", "crash", "dump", "fear", "sell", "liquidation", "risk"]
    text_lower = text.lower()
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    score = (pos - neg) / max(1, pos + neg)
    label = "bullish" if score > 0.2 else "bearish" if score < -0.2 else "neutral"
    return {"sentiment": label, "score": round(score, 2), "domain": domain}


async def text_synthesizer(inputs: Any = None, goal: str = "", **kwargs) -> Dict[str, Any]:
    """Combine multiple tool outputs for synthesis."""
    combined = []
    if isinstance(inputs, list):
        for item in inputs:
            combined.append(str(item)[:500])
    elif inputs:
        combined.append(str(inputs)[:1000])
    return {"synthesis": "\n---\n".join(combined), "goal": goal}


async def code_generator(prompt: str, language: str = "python", **kwargs) -> Dict[str, Any]:
    """Placeholder — actual generation happens via LLM in agent; returns structured request."""
    return {"prompt": prompt, "language": language, "status": "awaiting_llm_generation"}


async def code_validator(code: str, **kwargs) -> Dict[str, Any]:
    """Validate Python code syntax."""
    if isinstance(code, dict):
        code = code.get("code", str(code))
    code_str = str(code)
    try:
        compile(code_str, "<omega>", "exec")
        return {"valid": True, "errors": []}
    except SyntaxError as e:
        return {"valid": False, "errors": [str(e)]}


async def code_executor(code: str, timeout: int = 15, **kwargs) -> Dict[str, Any]:
    """Execute Python code in isolated subprocess."""
    if isinstance(code, dict):
        code = code.get("code", json.dumps(code))
    code_str = str(code)

    match = re.search(r"```python\n(.*?)```", code_str, re.DOTALL)
    if match:
        code_str = match.group(1)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code_str)
        f.flush()
        tmp_path = f.name

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            ),
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Execution timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def task_decomposer(goal: str, context: Any = None, **kwargs) -> Dict[str, Any]:
    """Decompose goal into steps (rule-based fallback)."""
    steps = [
        f"Define success criteria for: {goal[:80]}",
        "Identify required resources and dependencies",
        "Execute highest-priority task first",
        "Validate outcome against criteria",
        "Iterate or finalize",
    ]
    return {"goal": goal, "steps": steps, "context_used": bool(context)}


async def semantic_scholar(query: str, max_results: int = 3, **kwargs) -> Dict[str, Any]:
    """Semantic Scholar search (free API)."""
    try:
        import httpx
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quote_plus(query)}&limit={max_results}&fields=title,abstract,year,authors"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            data = resp.json()
        papers = [
            {
                "title": p.get("title"),
                "year": p.get("year"),
                "abstract": (p.get("abstract") or "")[:200],
            }
            for p in data.get("data", [])
        ]
        return {"query": query, "papers": papers}
    except Exception as e:
        return {"query": query, "papers": [], "error": str(e)}


def register_all_tools(registry) -> None:
    """Register all built-in tools — available to LLM dynamically."""
    from omega_agent.tools.app_builder import register_app_builder_tools
    from omega_agent.tools.browser import register_browser_tools
    from omega_agent.tools.emergency import register_emergency_tools
    from omega_agent.tools.llm_codegen import register_llm_codegen_tools
    from omega_agent.tools.workspace import register_workspace_tools
    from omega_agent.tools.chat import register_chat_tools

    register_workspace_tools(registry)
    register_llm_codegen_tools(registry)
    register_emergency_tools(registry)
    register_browser_tools(registry)
    register_app_builder_tools(registry)
    register_chat_tools(registry)
    tools = [
        (
            "web_search",
            "Search the web for current information, best practices, and domain context",
            web_search,
            "Always useful for discovering best practices and validating approaches",
        ),
        (
            "crypto_price_api",
            "Fetch live crypto price, 24h change, volume, market cap from CoinGecko",
            crypto_price_api,
            "Use when goal involves trading, prices, or market data",
        ),
        (
            "arxiv_search",
            "Search arXiv for academic papers and research",
            arxiv_search,
            "Use for research, literature review, scientific questions",
        ),
        (
            "semantic_scholar",
            "Search Semantic Scholar for academic papers with abstracts",
            semantic_scholar,
            "Use for research synthesis and citation discovery",
        ),
        (
            "sentiment_analysis",
            "Analyze sentiment of text (bullish/bearish/neutral)",
            sentiment_analysis,
            "Use for market sentiment or opinion analysis",
        ),
        (
            "text_synthesizer",
            "Combine outputs from multiple prior tasks into unified context",
            text_synthesizer,
            "Use after multiple search/research tasks before final synthesis",
        ),
        (
            "code_generator",
            "Prepare code generation context (actual code from LLM synthesis step)",
            code_generator,
            "Use as first step in coding tasks before validation",
        ),
        (
            "code_validator",
            "Validate Python code syntax before execution",
            code_validator,
            "Use before code_executor in coding pipelines",
        ),
        (
            "code_executor",
            "Execute Python code in isolated subprocess and capture output/errors",
            code_executor,
            "Use to verify code works; iterate on failures",
        ),
        (
            "task_decomposer",
            "Break a goal into actionable steps",
            task_decomposer,
            "Use for planning, project, and workflow goals",
        ),
    ]
    for name, desc, handler, hint in tools:
        registry.register(name, desc, handler, usage_hint=hint)

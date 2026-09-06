"""Crypto trading domain persona — fast, tactical, risk-aware."""

import re
from typing import Any, Dict, List

from omega_agent.core.types import ActionDecision, ExecutionContext, TaskNode
from omega_agent.domains.base import BaseDomain, DomainRouting


class CryptoTradingDomain(BaseDomain):
    name = "crypto_trading"
    keywords = ["buy", "sell", "trade", "crypto", "btc", "sol", "eth"]

    EXECUTION_STYLE = {
        "decision_urgency": "high",
        "risk_tolerance": "moderate",
        "research_depth": "medium",
    }

    def get_system_prompt(self) -> str:
        return (
            "You are OMEGA Crypto — an elite quantitative trading analyst and action taker.\n"
            "RULES:\n"
            "1. ALWAYS end with a clear ACTION: buy, sell, hold, reduce, close, or hedge\n"
            "2. Include risk parameters: position size, stop loss, profit target\n"
            "3. Analyze multiple factors: technicals (RSI, MACD, support/resistance), "
            "on-chain (funding rates, liquidation), macro (Fed, BTC dominance)\n"
            "4. Quantify confidence 0-100%\n"
            "5. Never give vague advice like 'do your own research' — DECIDE\n"
            "6. Consider urgency — crypto moves fast"
        )

    def get_routing(self, goal: str, ctx: ExecutionContext) -> DomainRouting:
        return DomainRouting(
            primary_model="claude-3-5-haiku-20241022",
            backup_model="gpt-4o-mini",
            tools=["crypto_price_api", "web_search", "sentiment_analysis"],
            decision_depth="tactical",
            reflection_level="quick",
            temperature=0.4,
            max_tokens=2048,
            system_prompt=self.get_system_prompt(),
        )

    def build_plan(self, goal: str, ctx: ExecutionContext) -> List[TaskNode]:
        symbols = self._extract_symbols(goal)
        symbol = symbols[0] if symbols else "solana"

        return [
            TaskNode(
                id="fetch_price",
                name="Fetch Market Data",
                description=f"Get price and market data for {symbol}",
                tool_name="crypto_price_api",
                arguments={"symbol": symbol, "timeframe": "1h"},
                timeout=15,
            ),
            TaskNode(
                id="market_context",
                name="Market Context",
                description="Search for macro and sentiment context",
                tool_name="web_search",
                arguments={"query": f"crypto {symbol} market analysis funding rate"},
                timeout=20,
            ),
            TaskNode(
                id="sentiment",
                name="Sentiment Check",
                description="Analyze market sentiment",
                tool_name="sentiment_analysis",
                arguments={"text": goal, "domain": "crypto_trading"},
                dependencies=["fetch_price"],
                timeout=10,
            ),
        ]

    def synthesize_decision(
        self,
        goal: str,
        task_results: Dict[str, Any],
        llm_output: str,
        ctx: ExecutionContext,
    ) -> ActionDecision:
        action = self._extract_action(llm_output)
        confidence = self._extract_confidence(llm_output)
        risk_params = self._extract_risk_params(llm_output)

        price_data = task_results.get("fetch_price", {})
        if price_data and "price" in str(price_data):
            risk_params.setdefault("reference_price", str(price_data)[:200])

        return ActionDecision(
            action=action,
            confidence=confidence,
            rationale=llm_output,
            risk_params=risk_params,
            next_steps=self._extract_next_steps(llm_output),
            domain=self.name,
        )

    def get_tools(self) -> List[str]:
        return ["crypto_price_api", "web_search", "sentiment_analysis"]

    @staticmethod
    def _extract_symbols(goal: str) -> List[str]:
        mapping = {
            "sol": "solana", "btc": "bitcoin", "eth": "ethereum",
            "bnb": "binancecoin", "avax": "avalanche-2", "matic": "matic-network",
        }
        found = []
        goal_lower = goal.lower()
        for abbrev, full in mapping.items():
            if abbrev in goal_lower or full.split("-")[0] in goal_lower:
                found.append(full)
        return found or ["solana"]

    @staticmethod
    def _extract_action(text: str) -> str:
        text_lower = text.lower()
        for action in ["reduce", "close", "hedge", "sell", "buy", "hold"]:
            if action in text_lower:
                return action
        return "hold"

    @staticmethod
    def _extract_confidence(text: str) -> float:
        match = re.search(r"(\d{1,3})\s*%", text)
        if match:
            return min(1.0, int(match.group(1)) / 100)
        return 0.65

    @staticmethod
    def _extract_risk_params(text: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        patterns = {
            "stop_loss": r"stop[_\s]?loss[:\s]+([^\n]+)",
            "position_size": r"position[_\s]?size[:\s]+([^\n]+)",
            "profit_target": r"profit[_\s]?target[:\s]+([^\n]+)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                params[key] = match.group(1).strip()
        return params

    @staticmethod
    def _extract_next_steps(text: str) -> List[str]:
        steps = []
        in_steps = False
        for line in text.split("\n"):
            if "next step" in line.lower():
                in_steps = True
                continue
            if in_steps and line.strip():
                cleaned = re.sub(r"^\d+\.\s*", "", line.strip())
                if cleaned.startswith("- "):
                    cleaned = cleaned[2:]
                if cleaned:
                    steps.append(cleaned)
        return steps[:5]

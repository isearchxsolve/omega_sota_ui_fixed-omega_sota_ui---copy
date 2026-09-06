"""Domain detection — delegates to dynamic discovery (no hardcoded domains)."""

import logging
from typing import List, Optional

from omega_agent.core.types import ExecutionContext

logger = logging.getLogger("omega_agent.domains.detector")


class DomainDetector:
    """
    Legacy compatibility wrapper.
    Domain detection is now fully dynamic via DynamicDiscoveryEngine + web search.
    """

    def detect(self, goal: str, ctx: ExecutionContext) -> str:
        if ctx.domain:
            return ctx.domain
        if ctx.dynamic_profile:
            return ctx.dynamic_profile.domain
        logger.info("Domain will be discovered dynamically via web search + LLM")
        return "pending_discovery"

    def list_domains(self) -> List[str]:
        return ["dynamic — discovered per goal via LLM + web search"]

    def get_domain_handler(self, domain: str):
        raise DeprecationWarning(
            "Hardcoded domain handlers removed. Use DynamicDiscoveryEngine + DynamicPlanner."
        )

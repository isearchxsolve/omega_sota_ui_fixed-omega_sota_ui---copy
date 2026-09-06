"""Pre-execution validation that runs BEFORE planning to catch missing inputs early."""

import logging
from typing import Dict, Optional, Tuple

from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator
from omega_agent.interaction.domain_requirements import (
    DomainRequirementsValidator,
    validate_domain_inputs
)
from omega_agent.reasoning.crisis import (
    is_crisis_goal,
    extract_location,
)

logger = logging.getLogger("omega_agent.pre_execution_validator")


def requires_location(goal: str) -> bool:
    """Check if this crisis goal NEEDS a location to execute."""
    location_needed_keywords = (
        "food bank", "food assistance", "snap", "emergency cash",
        "homeless shelter", "eviction", "utility bills", "food pantry",
        "emergency assistance", "hungry", "shelter", "need money",
        "food stamps", "emergency funds", "immediate", "urgent"
    )
    goal_lower = goal.lower()
    return any(kw in goal_lower for kw in location_needed_keywords)


class PreExecutionValidator:
    """
    Validates that a goal has all required inputs BEFORE planning/execution.
    
    This runs early in the workflow to catch missing information and ask the user
    before wasting compute cycles on planning and tool execution.
    """
    
    def __init__(self, config: Config, orchestrator: Optional[ModelOrchestrator] = None):
        self.config = config
        self.orchestrator = orchestrator
        self.validator = DomainRequirementsValidator()
    
    async def validate(
        self,
        goal: str,
        domain: str,
        user_inputs: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate goal has sufficient inputs for execution.
        
        Returns:
            (is_valid, error_message_if_invalid)
        
        If not valid, the error_message should be returned to the user asking for
        the missing information. Execution should NOT proceed.
        """
        user_inputs = user_inputs or {}
        
        logger.info(f"Pre-execution validation for domain={domain}, goal_length={len(goal)}")
        
        # Route to domain-specific validation
        if domain == "emergency-assistance":
            return await self._validate_sos(goal, user_inputs)
        elif domain == "coding":
            return await self._validate_coding(goal, user_inputs)
        elif domain == "crypto_trading":
            return await self._validate_crypto_trading(goal, user_inputs)
        elif domain == "research":
            return await self._validate_research(goal, user_inputs)
        elif domain == "planning":
            return await self._validate_planning(goal, user_inputs)
        else:
            # Generic domain - no validation
            logger.debug(f"No validation rules for domain={domain}")
            return True, None
    
    async def _validate_sos(
        self,
        goal: str,
        user_inputs: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Emergency assistance (SOS/humanitarian) requires location.
        
        Fails fast if no location is provided - don't waste time on generic searches.
        """
        logger.info("Validating SOS goal - requires location")
        
        # Check if this specific crisis needs a location
        if not requires_location(goal):
            logger.debug("SOS goal does not require location (e.g., suicide prevention)")
            return True, None
        
        # Try to extract location from goal or user_inputs
        location = extract_location(goal, user_inputs)
        
        if location:
            logger.info(f"SOS validation passed - location found: {location[:20]}")
            return True, None
        
        # No location found - ask for it
        error_msg = (
            "🔴 **Location Needed to Help You**\n\n"
            "To find **food banks, emergency cash programs, or shelters** near you, "
            "I need your **city + state** or **ZIP code**.\n\n"
            "**Please reply with your location:**\n"
            "- City format: `Boston, MA` or `San Francisco, CA`\n"
            "- ZIP format: `02101` or `94105`\n\n"
            "Once you provide your location, I'll run targeted searches for resources "
            "available right now in your area."
        )
        logger.warning("SOS validation failed - no location provided")
        return False, error_msg
    
    async def _validate_coding(
        self,
        goal: str,
        user_inputs: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Coding domain requires language/framework and project type.
        """
        logger.info("Validating coding goal")
        
        is_valid, error_msg = self.validator.get_missing_inputs("coding", user_inputs, goal)
        
        if not is_valid:
            logger.warning(f"Coding validation failed: {error_msg[:100]}")
        else:
            logger.info("Coding validation passed")
        
        return is_valid, error_msg
    
    async def _validate_crypto_trading(
        self,
        goal: str,
        user_inputs: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Crypto trading requires exchange, trading pair, and strategy.
        
        Also checks for sensitive fields and warns about API key security.
        """
        logger.info("Validating crypto trading goal")
        
        # Check for sensitive fields in user inputs
        sensitive_fields = self.validator.get_sensitive_fields("crypto_trading")
        if any(field in user_inputs for field in sensitive_fields):
            warning = (
                "⚠️ **SECURITY WARNING**\n\n"
                "Never paste API keys or credentials directly in messages! "
                "They should be stored securely using proper credential management. "
                "I can help you set up secure credential storage instead."
            )
            logger.warning("User provided sensitive field in message")
            return False, warning
        
        # Check for required inputs
        is_valid, error_msg = self.validator.get_missing_inputs("crypto_trading", user_inputs, goal)
        
        if not is_valid:
            logger.warning(f"Crypto trading validation failed: {error_msg[:100]}")
        else:
            logger.info("Crypto trading validation passed")
        
        return is_valid, error_msg
    
    async def _validate_research(
        self,
        goal: str,
        user_inputs: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Research domain requires a topic.
        
        Can usually infer topic from goal string, so less likely to fail.
        """
        logger.info("Validating research goal")
        
        # Try to infer topic from goal if not in user_inputs
        if "topic" not in user_inputs and len(goal.strip()) > 3:
            logger.debug("Inferring topic from goal string")
            return True, None
        
        is_valid, error_msg = self.validator.get_missing_inputs("research", user_inputs, goal)
        
        if not is_valid:
            logger.warning(f"Research validation failed: {error_msg[:100]}")
        else:
            logger.info("Research validation passed")
        
        return is_valid, error_msg
    
    async def _validate_planning(
        self,
        goal: str,
        user_inputs: Dict[str, str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Planning domain requires a clear objective.
        
        Usually inferred from goal string, so less likely to fail.
        """
        logger.info("Validating planning goal")
        
        # Try to infer objective from goal if not in user_inputs
        if "objective" not in user_inputs and len(goal.strip()) > 5:
            logger.debug("Inferring objective from goal string")
            return True, None
        
        is_valid, error_msg = self.validator.get_missing_inputs("planning", user_inputs, goal)
        
        if not is_valid:
            logger.warning(f"Planning validation failed: {error_msg[:100]}")
        else:
            logger.info("Planning validation passed")
        
        return is_valid, error_msg


# Singleton instance
_validator_instance: Optional[PreExecutionValidator] = None


def get_validator(config: Config, orchestrator: Optional[ModelOrchestrator] = None) -> PreExecutionValidator:
    """Get or create the global validator instance."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = PreExecutionValidator(config, orchestrator)
    return _validator_instance


async def quick_validate(
    goal: str,
    domain: str,
    config: Config,
    user_inputs: Optional[Dict[str, str]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Quick helper function for validation.
    
    Usage in omega.py:
        is_valid, error_msg = await quick_validate(goal, domain, self.config, user_inputs)
        if not is_valid:
            return AgentResult(
                success=False,
                action="AWAIT_INPUT",
                output=error_msg,
                domain=domain,
                # ...
            )
    """
    validator = get_validator(config)
    return await validator.validate(goal, domain, user_inputs)

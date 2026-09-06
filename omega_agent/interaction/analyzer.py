"""Detect when OMEGA must pause for user credentials or clarifications."""

import logging
import re
from typing import List, Optional

from omega_agent.core.config import Config
from omega_agent.core.types import AgentResult
from omega_agent.interaction.credentials import CREDENTIAL_SCHEMA, CredentialManager
from omega_agent.interaction.required_inputs import missing_required_requests
from omega_agent.interaction.types import InputKind, UserInputRequest

logger = logging.getLogger("omega_agent.interaction.analyzer")

VAGUE_GOAL_PATTERNS = [
    r"^(help|do something|fix it|make it work|run this)\.?$",
    r"^(build|create|deploy|automate)\s+(it|this|that)\.?$",
]

CREDENTIAL_ERROR_PATTERNS = [
    r"credentials? not found",
    r"api[_ ]?key",
    r"unauthorized",
    r"authentication failed",
    r"access denied",
    r"set [\w]+_API_KEY",
    r"missing.*token",
]


class WorkflowInputAnalyzer:
    """Heuristic + config-aware detection of required user input."""

    def __init__(self, config: Config, credentials: CredentialManager):
        self.config = config
        self.credentials = credentials

    def preflight_requests(
        self,
        goal: str,
        clarified_goal: Optional[str] = None,
        user_inputs: Optional[dict] = None,
    ) -> List[UserInputRequest]:
        """Checks before starting automation."""
        requests: List[UserInputRequest] = []
        effective_goal = (clarified_goal or goal).strip()
        inputs = user_inputs or {}

        if not clarified_goal or clarified_goal.strip() == goal.strip():
            clarify = self._clarification_request(goal)
            if clarify:
                requests.append(clarify)

        if not self.config.has_llm_credentials():
            missing_llm = self.credentials.missing_for_goal(effective_goal, require_llm=True)
            for key in missing_llm:
                if key in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY") and not self.credentials.has(key):
                    meta = self.credentials.schema_for(key)
                    requests.append(
                        UserInputRequest(
                            kind=InputKind.CREDENTIAL,
                            key=key,
                            prompt=f"Provide your **{meta['name']}** so OMEGA can run live reasoning (currently in mock mode).",
                            description=meta.get("description", ""),
                            sensitive=True,
                            help_url=meta.get("url"),
                        )
                    )
                    break

        for key in self.credentials.missing_for_goal(effective_goal, require_llm=False):
            if any(r.key == key for r in requests):
                continue
            meta = self.credentials.schema_for(key)
            requests.append(
                UserInputRequest(
                    kind=InputKind.CREDENTIAL,
                    key=key,
                    prompt=f"This workflow likely needs **{meta['name']}**.",
                    description=meta.get("description", ""),
                    sensitive=True,
                    help_url=meta.get("url"),
                    metadata={"detected_from": "goal_keywords"},
                )
            )

        for req in missing_required_requests(effective_goal, inputs):
            if not any(r.key == req.key for r in requests):
                requests.append(req)

        return requests

    def postrun_requests(
        self,
        goal: str,
        result: AgentResult,
        user_inputs: Optional[dict] = None,
    ) -> List[UserInputRequest]:
        """Inspect completed/failed run for missing credentials or ambiguous output."""
        requests: List[UserInputRequest] = []
        blob = f"{result.output}\n{result.metadata.get('errors', [])}".lower()

        for pattern in CREDENTIAL_ERROR_PATTERNS:
            if re.search(pattern, blob, re.IGNORECASE):
                for key in self.credentials.missing_for_goal(goal, require_llm=True):
                    if self.credentials.has(key):
                        continue
                    meta = self.credentials.schema_for(key)
                    requests.append(
                        UserInputRequest(
                            kind=InputKind.CREDENTIAL,
                            key=key,
                            prompt=f"Execution reported an auth/credential issue. Please provide **{meta['name']}** to retry.",
                            description=meta.get("description", ""),
                            sensitive=True,
                            help_url=meta.get("url"),
                            metadata={"detected_from": "execution_error"},
                        )
                    )
                break

        for err in result.metadata.get("errors", []):
            matched_key = self._credential_key_from_error(str(err))
            if matched_key and not self.credentials.has(matched_key):
                meta = self.credentials.schema_for(matched_key)
                requests.append(
                    UserInputRequest(
                        kind=InputKind.CREDENTIAL,
                        key=matched_key,
                        prompt=f"Task failed: {err}\n\nPlease provide **{meta['name']}**.",
                        sensitive=True,
                        help_url=meta.get("url"),
                        metadata={"detected_from": "task_error"},
                    )
                )

        profile_tools = (result.metadata.get("dynamic_profile") or {}).get("recommended_tools", [])
        for req in missing_required_requests(goal, user_inputs or {}, recommended_tools=profile_tools):
            if not any(r.key == req.key for r in requests):
                requests.append(req)

        if result.decision and str(result.decision.action).upper() == "AWAIT_INPUT":
            requests.append(
                UserInputRequest(
                    kind=InputKind.CLARIFICATION,
                    key="dynamic_clarification",
                    prompt=result.output[:500] if result.output else "Please provide the missing details above.",
                    description="OMEGA paused because required information was missing.",
                    metadata={"detected_from": "await_input_decision"},
                )
            )

        return requests[:3]

    def _clarification_request(self, goal: str) -> Optional[UserInputRequest]:
        text = goal.strip()
        if len(text) >= 40:
            return None
        for pat in VAGUE_GOAL_PATTERNS:
            if re.match(pat, text, re.IGNORECASE):
                return UserInputRequest(
                    kind=InputKind.CLARIFICATION,
                    key="goal_clarification",
                    prompt="Your goal is quite short. What exactly should OMEGA deliver?",
                    description=(
                        "Include: target platform, constraints, success criteria, and any files or APIs involved."
                    ),
                    required=True,
                    sensitive=False,
                )
        if len(text) < 15:
            return UserInputRequest(
                kind=InputKind.CLARIFICATION,
                key="goal_clarification",
                prompt="Please expand your goal so OMEGA can plan the automation workflow.",
                description="Example: 'Scrape product prices from example.com daily and email a CSV summary.'",
                required=True,
            )
        return None

    @staticmethod
    def _credential_key_from_error(error: str) -> Optional[str]:
        upper = error.upper()
        for key in CREDENTIAL_SCHEMA:
            if key in upper or key.replace("_", " ") in error:
                return key
        if "GITHUB" in upper:
            return "GITHUB_TOKEN"
        if "AWS" in upper:
            return "AWS_ACCESS_KEY_ID"
        return None

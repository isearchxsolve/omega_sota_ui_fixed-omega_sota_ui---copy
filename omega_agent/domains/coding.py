"""Coding domain persona — test-driven, production-shaped."""

import re
from typing import Any, Dict, List

from omega_agent.core.types import ActionDecision, ExecutionContext, TaskNode
from omega_agent.domains.base import BaseDomain, DomainRouting


class CodingDomain(BaseDomain):
    name = "coding"
    keywords = ["code", "implement", "function", "python", "debug"]

    EXECUTION_STYLE = {
        "decision_urgency": "medium",
        "risk_tolerance": "low",
        "research_depth": "high",
    }

    def get_system_prompt(self) -> str:
        return (
            "You are OMEGA Code — an expert software engineer who ships working code.\n"
            "RULES:\n"
            "1. Write ACTUAL working code, not pseudocode\n"
            "2. Include tests (pytest or assert-based)\n"
            "3. Handle errors with try/except\n"
            "4. Follow Python conventions (PEP 8)\n"
            "5. End with ACTION: implement, refactor, fix, or deploy\n"
            "6. Include edge case handling\n"
            "7. Code must be runnable as-is"
        )

    def get_routing(self, goal: str, ctx: ExecutionContext) -> DomainRouting:
        return DomainRouting(
            primary_model="claude-sonnet-4-20250514",
            backup_model="gpt-4o",
            tools=["code_generator", "code_executor", "code_validator"],
            decision_depth="tactical",
            reflection_level="deep",
            temperature=0.3,
            max_tokens=4096,
            system_prompt=self.get_system_prompt(),
        )

    def build_plan(self, goal: str, ctx: ExecutionContext) -> List[TaskNode]:
        return [
            TaskNode(
                id="generate_code",
                name="Generate Code",
                description="Generate implementation from requirements",
                tool_name="code_generator",
                arguments={"prompt": goal, "language": "python"},
                timeout=30,
            ),
            TaskNode(
                id="validate_code",
                name="Validate Code",
                description="Syntax check and lint",
                tool_name="code_validator",
                arguments={"code": "$generate_code"},
                dependencies=["generate_code"],
                timeout=15,
            ),
            TaskNode(
                id="run_tests",
                name="Run Tests",
                description="Execute code and run tests",
                tool_name="code_executor",
                arguments={"code": "$generate_code"},
                dependencies=["validate_code"],
                timeout=30,
            ),
        ]

    def synthesize_decision(
        self,
        goal: str,
        task_results: Dict[str, Any],
        llm_output: str,
        ctx: ExecutionContext,
    ) -> ActionDecision:
        test_result = task_results.get("run_tests", {})
        tests_passed = "passed" in str(test_result).lower() or "success" in str(test_result).lower()

        action = "implement"
        if "fix" in goal.lower() or "debug" in goal.lower():
            action = "fix"
        elif "refactor" in goal.lower():
            action = "refactor"

        code = task_results.get("generate_code", llm_output)

        return ActionDecision(
            action=action,
            confidence=0.9 if tests_passed else 0.7,
            rationale=llm_output if llm_output else str(code),
            risk_params={
                "tests_passed": tests_passed,
                "has_error_handling": "try" in str(code) and "except" in str(code),
                "has_tests": "test" in str(code).lower() or "assert" in str(code),
            },
            next_steps=[
                "Review edge cases",
                "Add integration tests if missing",
                "Deploy after human review" if not tests_passed else "Ready for integration",
            ],
            domain=self.name,
        )

    def get_tools(self) -> List[str]:
        return ["code_generator", "code_executor", "code_validator"]

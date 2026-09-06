"""
OMEGA Validation Integration - Orchestrator Pipeline Integration
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from omega_agent.validation.validation_framework import (
    ValidationOrchestrator,
    ValidationLevel,
    ValidationResult,
    ProjectType,
)

logger = logging.getLogger("omega_agent.validation.integration")

class ValidationGate:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM):
        self.workspace_path = workspace_path
        self.validation_level = validation_level
    
    async def validate_and_gate(self) -> Tuple[bool, ValidationResult]:
        orchestrator = ValidationOrchestrator(self.workspace_path, validation_level=self.validation_level)
        try:
            result = await orchestrator.run_validation()
            return result.validated, result
        except Exception as e:
            return False, ValidationResult(
                project_type=ProjectType.UNKNOWN, validated=False, validation_level=self.validation_level,
                checks_passed=0, checks_failed=1, checks_total=1, errors=[], warnings=[str(e)], execution_time_ms=0
            )

class ValidationErrorAnalyzer:
    @staticmethod
    def analyze(result: ValidationResult) -> Dict[str, Any]:
        if result.validated:
            return {"error_summary": "No errors", "root_causes": [], "suggested_fixes": [], "is_recoverable": True}
        
        root_causes = []
        for e in result.errors:
            if e.error_type == "dependency": root_causes.append(f"Dependency failure: {e.stderr[:100]}")
            if e.error_type == "syntax": root_causes.append(f"Syntax error: {e.stderr[:100]}")
            if e.error_type == "build": root_causes.append(f"Build failed: {e.stderr[:100]}")
            
        return {
            "error_summary": f"Validation failed with {len(result.errors)} issues.",
            "root_causes": root_causes,
            "suggested_fixes": ["Regenerate code addressing the specific build/syntax errors"],
            "is_recoverable": True,
        }

class RegenerationCoordinator:
    def __init__(self, llm_generate_files_fn=None):
        self.llm_generate_files_fn = llm_generate_files_fn
    
    async def attempt_recovery(self, goal: str, validation_result: ValidationResult, error_analysis: Dict[str, Any], max_attempts: int = 3, **llm_kwargs):
        if not self.llm_generate_files_fn or not error_analysis.get("is_recoverable"):
            return None
            
        recovery_context = f"\nVALIDATION FAILED. FIX THESE ISSUES:\n" + "\n".join(error_analysis["root_causes"])
        
        for attempt in range(max_attempts):
            try:
                regen_result = await self.llm_generate_files_fn(goal=goal + recovery_context, **llm_kwargs)
                if regen_result.get("success"):
                    return regen_result.get("files")
            except Exception as e:
                logger.warning(f"Recovery failed on attempt {attempt+1}: {e}")
        return None

class ValidationPipeline:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM, llm_generate_files_fn=None, max_recovery_attempts: int = 2):
        self.workspace_path = workspace_path
        self.gate = ValidationGate(workspace_path, validation_level)
        self.analyzer = ValidationErrorAnalyzer()
        self.recovery = RegenerationCoordinator(llm_generate_files_fn)
        self.max_recovery_attempts = max_recovery_attempts
    
    async def execute(self, goal: str, allow_recovery: bool = True, **llm_kwargs) -> Dict[str, Any]:
        passed, result = await self.gate.validate_and_gate()
        if passed:
            return {"success": True, "validation_result": result.to_dict(), "report": "✅ VALIDATION PASSED"}
            
        error_analysis = self.analyzer.analyze(result)
        recovery_successful = False
        
        if allow_recovery:
            regen_files = await self.recovery.attempt_recovery(goal, result, error_analysis, self.max_recovery_attempts, **llm_kwargs)
            recovery_successful = regen_files is not None
            
        return {
            "success": recovery_successful,
            "validation_result": result.to_dict(),
            "recovery_successful": recovery_successful,
            "report": f"{'✅ RECOVERED' if recovery_successful else '❌ FAILED'}\n{error_analysis['error_summary']}"
        }
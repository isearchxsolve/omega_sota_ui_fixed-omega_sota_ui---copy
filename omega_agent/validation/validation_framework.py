"""
OMEGA Validation Framework - Complete Post-Generation Verification
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("omega_agent.validation.framework")

class ProjectType(Enum):
    REACT = "react"
    VUE = "vue"
    ANGULAR = "angular"
    NEXT_JS = "nextjs"
    EXPRESS = "express"
    FASTAPI = "fastapi"
    DJANGO = "django"
    PYTHON_CLI = "python_cli"
    RUST = "rust"
    UNKNOWN = "unknown"

class ValidationLevel(Enum):
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3
    PARANOID = 4

@dataclass
class ValidationError:
    check_name: str
    command: Optional[str]
    returncode: Optional[int]
    stdout: str
    stderr: str
    error_type: str
    severity: str
    recoverable: bool = True

@dataclass
class ValidationResult:
    project_type: ProjectType
    validated: bool
    validation_level: ValidationLevel
    checks_passed: int
    checks_failed: int
    checks_total: int
    errors: List[ValidationError]
    warnings: List[str]
    execution_time_ms: float
    dependency_valid: Optional[bool] = None
    build_valid: Optional[bool] = None
    tests_valid: Optional[bool] = None
    syntax_valid: Optional[bool] = None
    recommendations: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_type": self.project_type.value,
            "validated": self.validated,
            "validation_level": self.validation_level.name,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_total": self.checks_total,
            "errors": [asdict(e) for e in self.errors],
            "warnings": self.warnings,
            "execution_time_ms": self.execution_time_ms,
            "dependency_valid": self.dependency_valid,
            "build_valid": self.build_valid,
            "tests_valid": self.tests_valid,
            "syntax_valid": self.syntax_valid,
            "recommendations": self.recommendations or [],
        }

class ProjectDetector:
    @staticmethod
    def detect_from_files(files: List[Dict[str, str]]) -> ProjectType:
        file_paths = {f.get("path", "") for f in files}
        contents = {f.get("path", ""): f.get("content", "") for f in files}
        
        for path, content in contents.items():
            if path == "package.json" or path.endswith("package.json"):
                try:
                    pkg = json.loads(content)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "react" in deps and "next" in deps: return ProjectType.NEXT_JS
                    if "react" in deps and "react-dom" in deps: return ProjectType.REACT
                    if "vue" in deps: return ProjectType.VUE
                    if "@angular/core" in deps: return ProjectType.ANGULAR
                    if "express" in deps or "fastify" in deps: return ProjectType.EXPRESS
                except json.JSONDecodeError:
                    pass
        
        if "requirements.txt" in file_paths or "pyproject.toml" in file_paths or "setup.py" in file_paths:
            for path, content in contents.items():
                if "requirements.txt" in path:
                    if "fastapi" in content or "starlette" in content: return ProjectType.FASTAPI
                    if "django" in content: return ProjectType.DJANGO
                    return ProjectType.PYTHON_CLI
                if "pyproject.toml" in path:
                    if "fastapi" in content: return ProjectType.FASTAPI
                    if "django" in content: return ProjectType.DJANGO
                    return ProjectType.PYTHON_CLI
        
        if "Cargo.toml" in file_paths: return ProjectType.RUST
        
        for path, content in contents.items():
            content_lower = content.lower()
            if "react" in content_lower: return ProjectType.REACT
            if "express" in content_lower: return ProjectType.EXPRESS
            if "fastapi" in content_lower: return ProjectType.FASTAPI
        
        return ProjectType.UNKNOWN
    
    @staticmethod
    def detect_from_workspace(workspace_path: Path) -> ProjectType:
        files = []
        for file_path in workspace_path.rglob("*"):
            if file_path.is_file() and not any(part.startswith(".") for part in file_path.parts):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    rel_path = file_path.relative_to(workspace_path)
                    files.append({"path": str(rel_path), "content": content[:5000]})
                except (UnicodeDecodeError, IOError):
                    pass
        return ProjectDetector.detect_from_files(files)

class ValidationChecks:
    @staticmethod
    def check_has_package_json(workspace_path: Path) -> Tuple[bool, str]:
        pkg_path = workspace_path / "package.json"
        if pkg_path.exists():
            try:
                json.loads(pkg_path.read_text())
                return True, "package.json found and valid"
            except json.JSONDecodeError as e:
                return False, f"package.json is invalid JSON: {e}"
        return False, "package.json not found"
    
    @staticmethod
    def check_has_requirements_txt(workspace_path: Path) -> Tuple[bool, str]:
        if (workspace_path / "requirements.txt").exists():
            return True, "requirements.txt found"
        return False, "requirements.txt not found"
    
    @staticmethod
    def check_package_json_syntax(workspace_path: Path) -> Tuple[bool, str]:
        pkg_path = workspace_path / "package.json"
        if not pkg_path.exists(): return True, "package.json not applicable"
        try:
            json.loads(pkg_path.read_text())
            return True, "package.json syntax valid"
        except json.JSONDecodeError as e:
            return False, f"package.json syntax error: {str(e)[:200]}"
    
    @staticmethod
    def check_no_syntax_errors_in_js(workspace_path: Path) -> Tuple[bool, str]:
        js_files = list(workspace_path.rglob("*.js")) + list(workspace_path.rglob("*.jsx"))
        if not js_files: return True, "No JavaScript files to check"
        errors = []
        for js_file in js_files[:20]:
            try:
                content = js_file.read_text()
                if content.count("{") != content.count("}"):
                    errors.append(f"{js_file.relative_to(workspace_path)}: Mismatched braces")
                if content.count("[") != content.count("]"):
                    errors.append(f"{js_file.relative_to(workspace_path)}: Mismatched brackets")
            except (UnicodeDecodeError, IOError):
                pass
        if errors: return False, f"Syntax errors found: {'; '.join(errors[:3])}"
        return True, "JavaScript syntax checks passed"
    
    @staticmethod
    def check_no_syntax_errors_in_python(workspace_path: Path) -> Tuple[bool, str]:
        import ast
        py_files = list(workspace_path.rglob("*.py"))
        if not py_files: return True, "No Python files to check"
        errors = []
        for py_file in py_files[:20]:
            try:
                ast.parse(py_file.read_text())
            except SyntaxError as e:
                errors.append(f"{py_file.relative_to(workspace_path)}: {str(e)[:100]}")
            except (UnicodeDecodeError, IOError):
                pass
        if errors: return False, f"Python syntax errors found: {'; '.join(errors[:3])}"
        return True, "Python syntax checks passed"

class ShellCommandValidator:
    def __init__(self, workspace_path: Path, timeout: int = 300):
        self.workspace_path = workspace_path
        self.timeout = timeout
    
    async def run_command(self, command: str) -> Dict[str, Any]:
        import subprocess
        logger.info(f"[VALIDATION] Executing: {command}")
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command, shell=True, cwd=str(self.workspace_path),
                    capture_output=True, text=True, timeout=self.timeout
                )
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[:8000],
                "stderr": (proc.stderr or "")[:4000],
                "command": command,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}
    
    async def validate_npm_dependencies(self) -> Tuple[bool, str, Optional[str]]:
        result = await self.run_command("npm ls --depth=0 2>&1")
        if result["success"]: return True, "npm dependencies valid", None
        stderr = result.get("stderr", "")
        if "ERR!" in stderr or "unmet" in stderr.lower():
            return False, "npm dependencies invalid", stderr[:500]
        dry_run = await self.run_command("npm install --dry-run 2>&1")
        if dry_run["success"]: return True, "npm install --dry-run succeeded", None
        return False, "npm dependencies validation failed", dry_run.get("stderr", "")[:500]
    
    async def validate_npm_build(self) -> Tuple[bool, str, Optional[str]]:
        for cmd in ["npm run build", "npm run build:prod", "npm run prod"]:
            result = await self.run_command(f"{cmd} 2>&1")
            if result["success"]: return True, f"{cmd} succeeded", None
        return False, "npm build failed for all scripts", result.get("stderr", result.get("stdout", ""))[:500]
    
    async def validate_python_imports(self) -> Tuple[bool, str, Optional[str]]:
        result = await self.run_command("python -m py_compile *.py 2>&1")
        if result["success"]: return True, "Python import compilation successful", None
        return False, "Python imports have errors", result.get("stderr", result.get("stdout", ""))[:500]

class ValidationOrchestrator:
    def __init__(self, workspace_path: Path, validation_level: ValidationLevel = ValidationLevel.MEDIUM, timeout: int = 300):
        self.workspace_path = workspace_path
        self.validation_level = validation_level
        self.detector = ProjectDetector()
        self.shell_validator = ShellCommandValidator(workspace_path, timeout)
    
    async def run_validation(self) -> ValidationResult:
        import time
        start_time = time.time()
        project_type = self.detector.detect_from_workspace(self.workspace_path)
        
        errors, warnings = [], []
        checks_passed, checks_failed = 0, 0
        
        syntax_valid = await self._validate_syntax(project_type, errors)
        checks_passed += 1 if syntax_valid else 0
        checks_failed += 0 if syntax_valid else 1
        
        dependency_valid = await self._validate_dependencies(project_type, errors)
        checks_passed += 1 if dependency_valid else 0
        checks_failed += 0 if dependency_valid else 1
        
        build_valid, tests_valid = True, True
        if self.validation_level.value >= ValidationLevel.MEDIUM.value:
            build_valid = await self._validate_build(project_type, errors)
            checks_passed += 1 if build_valid else 0
            checks_failed += 0 if build_valid else 1
            
        all_valid = syntax_valid and dependency_valid and build_valid
        recommendations = self._generate_recommendations(errors, project_type)
        
        return ValidationResult(
            project_type=project_type,
            validated=all_valid and len(errors) == 0,
            validation_level=self.validation_level,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            checks_total=checks_passed + checks_failed,
            errors=errors, warnings=warnings,
            execution_time_ms=(time.time() - start_time) * 1000,
            dependency_valid=dependency_valid, build_valid=build_valid,
            tests_valid=tests_valid, syntax_valid=syntax_valid,
            recommendations=recommendations,
        )
    
    async def _validate_syntax(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS, ProjectType.EXPRESS]:
            success, msg, detail = ValidationChecks.check_no_syntax_errors_in_js(self.workspace_path)
            if not success:
                errors.append(ValidationError("JavaScript Syntax", None, None, "", detail or "", "syntax", "critical"))
                return False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI]:
            success, msg, detail = ValidationChecks.check_no_syntax_errors_in_python(self.workspace_path)
            if not success:
                errors.append(ValidationError("Python Syntax", None, None, "", detail or "", "syntax", "critical"))
                return False
        return True
    
    async def _validate_dependencies(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS, ProjectType.EXPRESS]:
            success, msg, detail = await self.shell_validator.validate_npm_dependencies()
            if not success:
                errors.append(ValidationError("npm Dependencies", "npm ls", 1, "", detail or "", "dependency", "critical"))
                return False
        elif project_type in [ProjectType.FASTAPI, ProjectType.DJANGO, ProjectType.PYTHON_CLI]:
            success, msg, detail = await self.shell_validator.validate_python_imports()
            if not success:
                errors.append(ValidationError("Python Imports", "py_compile", 1, "", detail or "", "dependency", "critical"))
                return False
        return True
    
    async def _validate_build(self, project_type: ProjectType, errors: List[ValidationError]) -> bool:
        if project_type in [ProjectType.REACT, ProjectType.VUE, ProjectType.ANGULAR, ProjectType.NEXT_JS]:
            success, msg, detail = await self.shell_validator.validate_npm_build()
            if not success:
                errors.append(ValidationError("npm Build", "npm run build", 1, "", detail or "", "build", "critical"))
                return False
        return True
    
    def _generate_recommendations(self, errors: List[ValidationError], project_type: ProjectType) -> List[str]:
        if not errors: return ["✅ All validation checks passed successfully!"]
        recs = []
        error_types = {e.error_type for e in errors}
        if "dependency" in error_types:
            recs.append("🔧 Check package.json or requirements.txt for conflicts")
        if "syntax" in error_types:
            recs.append("🔍 Check for missing imports or syntax errors")
        return recs
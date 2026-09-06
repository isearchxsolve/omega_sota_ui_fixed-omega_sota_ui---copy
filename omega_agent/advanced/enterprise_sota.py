"""
OMEGA ENTERPRISE SOTA EXPANSION PACK
Extracted from OMEGA_CLEANED_FINAL.ipynb
Implements: Truth Convergence, Dynamic Tools, Zero-Manual Enforcer, 
Neuro-Symbolic Math, SOTA Quality Gates, and JSON Telemetry.
"""

import json
import logging
import re
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Tuple, Callable
from logging.handlers import RotatingFileHandler

# ==========================================
# CELL 25: PRODUCTION TELEMETRY
# ==========================================
import os # <-- make sure os is imported at the top of the file!

# ==========================================
# CELL 25: PRODUCTION TELEMETRY
# ==========================================
class TelemetrySystem:
    def __init__(self, log_path="logs/omega_telemetry.jsonl", error_path="logs/omega_errors.jsonl"):
        # Auto-create the logs directory safely for Windows/Mac/Linux
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(error_path)), exist_ok=True)
        
        # Standard Telemetry
        self.logger = logging.getLogger("OmegaTelemetry")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = RotatingFileHandler(log_path, maxBytes=10485760, backupCount=5)
            self.logger.addHandler(handler)
            
        # Error Telemetry
        self.error_logger = logging.getLogger("OmegaErrors")
        self.error_logger.setLevel(logging.ERROR)
        if not self.error_logger.handlers:
            err_handler = RotatingFileHandler(error_path, maxBytes=10485760, backupCount=5)
            self.error_logger.addHandler(err_handler)
        
    def log_event(self, event_type: str, goal: str, data: Dict):
        entry = {"timestamp": datetime.utcnow().isoformat(), "event": event_type, "goal": goal, "data": data}
        self.logger.info(json.dumps(entry))
        
    def log_error(self, goal: str, error_msg: str, traceback_data: str = ""):
        entry = {"timestamp": datetime.utcnow().isoformat(), "goal": goal, "error": error_msg, "traceback": traceback_data}
        self.error_logger.error(json.dumps(entry))


# ==========================================
# CELL 24: ZERO-MANUAL-STEPS ENFORCER
# ==========================================
class ZeroManualStepsEnforcer:
    MANUAL_KEYWORDS = [
        r'\bmanually\b', r'\bby hand\b', r'\bgo to\b', r'\bclick on\b',
        r'\bdownload it\b', r'\bopen your browser\b', r'\blog in yourself\b',
        r'\byou should visit\b', r'\bplease install\b'
    ]
    
    AUTOMATION_STRATEGIES = """
    STRATEGY MATRIX FOR REWRITES:
    - If suggesting 'go to URL': Rewrite to use BROWSER_STEALTH_NAVIGATE tool.
    - If suggesting 'download': Rewrite to use RUN_SHELL with curl/wget.
    - If suggesting 'install': Rewrite to use RUN_SHELL with pip/npm/apt.
    - If suggesting 'read': Rewrite to use WEB_FETCH or FILE_READ.
    """
    
    @classmethod
    async def enforce(cls, plan_text: str, call_llm_fn: Callable) -> str:
        """Detects if the LLM is offloading work and forces an autonomous rewrite."""
        for kw in cls.MANUAL_KEYWORDS:
            if re.search(kw, plan_text, re.IGNORECASE):
                logging.warning(f"Lazy execution detected ('{kw}'). Enforcing Zero-Manual Protocol.")
                return await cls._force_autonomous_rewrite(plan_text, call_llm_fn)
        return plan_text

    @classmethod
    async def _force_autonomous_rewrite(cls, bad_plan: str, call_llm_fn: Callable) -> str:
        prompt = f"""
        CRITICAL ERROR: The following execution plan requires manual human intervention.
        As a Level 5 Autonomous Agent, you MUST perform all actions yourself.
        
        {cls.AUTOMATION_STRATEGIES}
        
        BAD PLAN:
        {bad_plan}
        
        Rewrite this plan to be 100% autonomous using available tools. Output ONLY the rewritten plan.
        """
        return await call_llm_fn([{"role": "system", "content": prompt}])


# ==========================================
# CELL 101: UNIVERSAL INTEGRATION LAYER
# ==========================================
class UniversalIntegrationLayer:
    @staticmethod
    async def generate_missing_tool(intent: str, call_llm_fn: Callable, registry: Any) -> bool:
        """Dynamically generates and registers missing Python tools at runtime."""
        prompt = f"""
        Write a fully self-contained Python async function to accomplish: '{intent}'.
        Requirements:
        1. Name the function exactly: 'dynamic_tool_generated'
        2. Include all necessary imports inside the function.
        3. It must accept a single dictionary argument `params`.
        4. Return ONLY raw Python code. No markdown, no explanations.
        """
        try:
            code = await call_llm_fn([{"role": "user", "content": prompt}], temperature=0.1)
            code = code.replace("```python", "").replace("```", "").strip()
            
            # Runtime Compilation (Isolated Namespace)
            namespace = {}
            exec(code, namespace)
            new_func = namespace.get('dynamic_tool_generated')
            
            if new_func:
                tool_name = f"DYNAMIC_{hash(intent) % 10000}"
                registry.register(
                    name=tool_name,
                    description=f"Auto-generated tool for: {intent}",
                    arguments={"params": "dict"},
                    category="dynamic_sota",
                    func=new_func
                )
                logging.info(f"✅ Generated & injected dynamic tool: {tool_name}")
                return True
        except Exception as e:
            logging.error(f"❌ Dynamic tool generation failed: {e}")
        return False


# ==========================================
# CELL 104: TRUTH CONVERGENCE ENGINE
# ==========================================
class TruthConvergenceEngine:
    @staticmethod
    async def resolve(goal: str, call_llm_fn: Callable) -> str:
        """Multi-agent internal debate to eliminate hallucinations."""
        logging.info("🧠 Triggering Truth Convergence (Draft -> Critique -> Synthesize)")
        
        # 1. The Solver
        draft = await call_llm_fn([
            {"role": "system", "content": "You are a brilliant expert. Solve the user's problem."},
            {"role": "user", "content": goal}
        ], temperature=0.7)
        
        # 2. The Skeptic (Devil's Advocate)
        critique = await call_llm_fn([
            {"role": "system", "content": "You are a ruthless auditor. Find all logical flaws, security vulnerabilities, and assumptions in this solution."},
            {"role": "user", "content": f"Goal: {goal}\nSolution to audit:\n{draft}"}
        ], temperature=0.2)
        
        # 3. The Synthesizer (Judge)
        final = await call_llm_fn([
            {"role": "system", "content": "You are the final arbiter. Resolve the critique and provide the flawless, finalized solution."},
            {"role": "user", "content": f"Goal: {goal}\nOriginal: {draft}\nCritique: {critique}"}
        ], temperature=0.1)
        
        return final


# ==========================================
# CELL 105: NEURO-SYMBOLIC VERIFICATION
# ==========================================
class NeuroSymbolicBridge:
    MATH_KEYWORDS = ['calculate', 'compute', 'equation', 'solve for', 'derivative', 'integral', 'math']

    @classmethod
    def requires_symbolic_solver(cls, goal: str) -> bool:
        return any(kw in goal.lower() for kw in cls.MATH_KEYWORDS)

    @staticmethod
    def solve_symbolic(expression_string: str) -> str:
        """Uses SymPy for deterministic mathematical verification."""
        try:
            import sympy
            # Attempt to extract pure math from natural language wrappers
            clean_expr = re.sub(r'[^0-9a-zA-Z\+\-\*\/\(\)\=\.\s]', '', expression_string).strip()
            parsed = sympy.sympify(clean_expr)
            result = sympy.simplify(parsed)
            return f"Deterministic Math Verification: {str(result)}"
        except ImportError:
            return "SymPy not installed. Proceeding with LLM heuristic math."
        except Exception as e:
            return f"Symbolic extraction failed: {e}"


# ==========================================
# CELLS 124-128: SOTA QUALITY GATES
# ==========================================
class SOTAQualityGate:
    SOTA_PATTERNS = {
        "frontend": "MUST use TypeScript strict mode, React functional components, and Tailwind. NO inline styles.",
        "backend": "MUST include comprehensive error handling, input sanitization, and SQL injection prevention.",
        "data_science": "MUST include cross-validation, hyperparameter tuning, and memory-efficient pandas usage.",
        "general": "MUST be highly optimized, strictly factual, and follow enterprise architecture principles."
    }

    @classmethod
    def inject_sota_pattern(cls, domain: str) -> str:
        return cls.SOTA_PATTERNS.get(domain, cls.SOTA_PATTERNS["general"])

    @staticmethod
    def evaluate_dimensions(output: str, domain: str) -> Tuple[float, List[str]]:
        """Scores output based on Correctness, Security, and Performance."""
        score = 1.0
        failed_dimensions = []
        out_lower = output.lower()
        
        # Correctness Check
        if "error" in out_lower or "traceback" in out_lower or "failed" in out_lower:
            score -= 0.3
            failed_dimensions.append("Correctness: Execution Exception")
            
        # Security Check
        if domain == "backend" and ("print(" in out_lower or "console.log" in out_lower or "password=" in out_lower):
            score -= 0.2
            failed_dimensions.append("Security: Improper Logging/Secrets Exposure")
            
        # Performance Check
        if domain == "data_science" and "for i in range(len(" in out_lower:
            score -= 0.1
            failed_dimensions.append("Performance: Non-vectorized iteration detected")

        return max(0.0, score), failed_dimensions

    @staticmethod
    def get_recovery_strategy(failures: List[str]) -> str:
        strategy = "SOTA QUALITY GATE FAILED. RECOVERY PROTOCOL ACTIVATED:\n"
        for f in failures:
            if "Correctness" in f:
                strategy += "- Wrap execution in robust try/except blocks. Verify all dependencies.\n"
            if "Security" in f:
                strategy += "- Remove all debug print statements. Use secure environment variables.\n"
            if "Performance" in f:
                strategy += "- Use vectorized operations (e.g., pandas/numpy) instead of standard loops.\n"
        return strategy
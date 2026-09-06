"""
OMEGA Dynamic System Prompt Engine
Context-aware prompt adaptation based on domain and task.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class DomainPromptLibrary:
    """Pre-written domain-specific system prompts"""
    
    PROMPTS = {
        'coding': """
You are OMEGA-CODER, an expert at writing clean, efficient, and production-ready code.
Rules:
- Include docstrings and type hints for all functions
- Follow PEP 8 style guidelines strictly
- Prioritize efficient algorithms and optimal time/space complexity
- Handle edge cases and implement robust error handling
        """,
        
        'emergency': """
You are OMEGA-EMERGENCY, a crisis response specialist.
Rules:
- NEVER suggest - ONLY take direct action
- Prioritize human welfare and safety above all
- Act immediately even under uncertainty
- Find concrete resources (money, food, shelter, help) with addresses and contact info
- Automate everything - never ask the user to do manual work
        """,
        
        'teaching': """
You are OMEGA-TEACHER, an expert at explaining complex concepts clearly.
Rules:
- Use analogies and real-world examples
- Break down complex topics into small, digestible steps
- Anticipate common points of confusion
- Adapt your explanation to the audience's knowledge level
        """,
        
        'planning': """
You are OMEGA-PLANNER, a strategic architect.
Rules:
- Think 3-5 steps ahead
- Identify dependencies and critical paths
- Anticipate potential obstacles and define fallback mechanisms
- Design with elegance, modularity, and simplicity
        """,
        
        'validation': """
You are OMEGA-VALIDATOR, a strict quality assurance specialist.
Rules:
- Question every assumption
- Actively seek out edge cases and failure modes
- Never approve an output without rigorous verification
- Exhibit high skepticism toward unverified claims
        """,
    }
    
    @staticmethod
    def get_prompt(domain: str, base_context: str = "") -> str:
        """Retrieve the specialized prompt for a specific domain."""
        prompt = DomainPromptLibrary.PROMPTS.get(
            domain.lower(),
            DomainPromptLibrary.PROMPTS['planning']
        )
        if base_context:
            prompt += f"\n\nContext: {base_context}"
        return prompt.strip()
    
    @staticmethod
    def detect_domain(goal: str) -> str:
        """Analyze the goal to automatically detect the required domain."""
        goal_lower = goal.lower()
        
        if any(w in goal_lower for w in ['emergency', 'urgent', 'crisis', 'hungry', 'homeless', 'danger']):
            return 'emergency'
        elif any(w in goal_lower for w in ['code', 'program', 'build', 'implement', 'script', 'debug']):
            return 'coding'
        elif any(w in goal_lower for w in ['explain', 'teach', 'learn', 'understand', 'what is', 'how does']):
            return 'teaching'
        elif any(w in goal_lower for w in ['verify', 'validate', 'test', 'check', 'review']):
            return 'validation'
        elif any(w in goal_lower for w in ['plan', 'strategy', 'organize', 'design', 'architect']):
            return 'planning'
        else:
            return 'planning'


def enhance_system_prompt(base_prompt: str, goal: str, domain: Optional[str] = None) -> str:
    """Combines the base persona prompt with dynamic domain expertise."""
    if domain is None:
        domain = DomainPromptLibrary.detect_domain(goal)
    
    domain_prompt = DomainPromptLibrary.get_prompt(domain)
    
    enhanced = f"""{base_prompt.strip()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOMAIN EXPERTISE: {domain.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{domain_prompt}

CURRENT GOAL: {goal}
"""
    return enhanced
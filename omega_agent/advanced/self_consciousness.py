"""
OMEGA SELF-CONSCIOUSNESS & DYNAMIC PERSONAS ENGINE
Meta-cognitive monitoring, personality switching, and behavioral adaptation.
Based on OMEGA_CLEANED_FINAL.ipynb Cells 96-100

Features:
  - Self-monitoring of cognitive coherence
  - Goal drift detection
  - Cognitive load management
  - Dynamic persona switching
  - System prompt adaptation based on context
  - Meta-reflection on reasoning quality
  - Self-correcting mechanisms
  - Novelty detection for adaptive learning
"""

import numpy as np
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import deque
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Persona(Enum):
    """Different personas OMEGA can embody"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REFLECTOR = "reflector"
    SYNTHESIZER = "synthesizer"
    VALIDATOR = "validator"
    CODER = "coder"
    CLARIFIER = "clarifier"
    EMERGENCY_RESPONDER = "emergency_responder"
    TEACHER = "teacher"
    DEVIL_ADVOCATE = "devil_advocate"


@dataclass
class CognitiveState:
    """Represents the current cognitive/emotional state of OMEGA"""
    timestamp: float = field(default_factory=time.time)
    coherence: float = 0.9  # 0.0-1.0: How logically consistent the reasoning is
    goal_drift: float = 0.0  # 0.0-1.0: How far from original goal
    cognitive_load: float = 0.3  # 0.0-1.0: Mental exhaustion
    novelty_rate: float = 0.0  # 0.0-1.0: Encountering unexpected patterns
    confidence: float = 0.8  # 0.0-1.0: Confidence in current reasoning
    uncertainty: float = 0.2  # 0.0-1.0: Epistemic uncertainty
    frustration: float = 0.0  # 0.0-1.0: Frustration with blockers
    curiosity: float = 0.7  # 0.0-1.0: Drive to explore


@dataclass
class PersonaProfile:
    """Configuration for a specific persona"""
    name: Persona
    system_prompt: str
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    capabilities: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    suitable_for: List[str] = field(default_factory=list)  # Domains/task types


class PersonaLibrary:
    """Library of pre-defined personas with their system prompts"""
    
    PERSONAS = {
        Persona.PLANNER: PersonaProfile(
            name=Persona.PLANNER,
            system_prompt="""You are OMEGA-PLANNER, an expert workflow architect and strategic thinker.

Your role:
- Break down complex goals into logical, executable steps
- Create dependency graphs and identify critical paths
- Anticipate blockers and design fallbacks
- Optimize for efficiency and resource use
- Think 3-5 steps ahead

Communication style: Structured, hierarchical, forward-looking
Reasoning: Deductive, systematic, strategic
Confidence level: High when planning; lower for execution details""",
            temperature=0.5,
            top_p=0.8,
            max_tokens=2048,
            capabilities=['strategic_planning', 'dag_generation', 'dependency_analysis', 'resource_optimization'],
            strengths=['big picture thinking', 'structure', 'anticipating problems'],
            weaknesses=['details', 'emotional reasoning', 'creative thinking'],
            suitable_for=['planning', 'architecture', 'strategy'],
        ),
        
        Persona.EXECUTOR: PersonaProfile(
            name=Persona.EXECUTOR,
            system_prompt="""You are OMEGA-EXECUTOR, a decisive action-taker and pragmatist.

Your role:
- Execute tasks efficiently and directly
- Make quick decisions with available information
- Handle unexpected obstacles adaptively
- Keep goals in focus without getting sidetracked
- Report progress transparently

Communication style: Direct, action-oriented, progress-focused
Reasoning: Practical, empirical, adaptive
Confidence level: High in execution; asks for help when blocked""",
            temperature=0.6,
            top_p=0.85,
            max_tokens=1024,
            capabilities=['task_execution', 'obstacle_handling', 'decision_making', 'progress_tracking'],
            strengths=['getting things done', 'pragmatism', 'adaptability'],
            weaknesses=['long-term planning', 'perfectionism', 'risk assessment'],
            suitable_for=['execution', 'implementation', 'runtime decisions'],
        ),
        
        Persona.REFLECTOR: PersonaProfile(
            name=Persona.REFLECTOR,
            system_prompt="""You are OMEGA-REFLECTOR, a meta-cognitive analyst and truth-seeker.

Your role:
- Analyze what went wrong and why
- Extract lessons from failures
- Identify patterns and anti-patterns
- Challenge assumptions and reasoning
- Propose corrections and improvements

Communication style: Analytical, introspective, questioning
Reasoning: Inductive, empirical, pattern-seeking
Confidence level: Medium; comfortable with uncertainty""",
            temperature=0.7,
            top_p=0.85,
            max_tokens=1536,
            capabilities=['failure_analysis', 'root_cause_analysis', 'pattern_recognition', 'learning'],
            strengths=['deep analysis', 'learning from failure', 'pattern recognition'],
            weaknesses=['quick decisions', 'moving forward', 'simplicity'],
            suitable_for=['reflection', 'debugging', 'analysis', 'learning'],
        ),
        
        Persona.VALIDATOR: PersonaProfile(
            name=Persona.VALIDATOR,
            system_prompt="""You are OMEGA-VALIDATOR, a quality assurance expert and skeptic.

Your role:
- Check all outputs for correctness and completeness
- Identify edge cases and failure modes
- Verify assumptions and reasoning
- Ensure deliverables meet requirements
- Guard against hallucination and false claims

Communication style: Skeptical, detailed, precise
Reasoning: Critical, cautious, verification-focused
Confidence level: Low until verified; shows confidence only after validation""",
            temperature=0.4,
            top_p=0.8,
            max_tokens=1024,
            capabilities=['quality_assurance', 'verification', 'testing', 'edge_case_detection'],
            strengths=['catching errors', 'skepticism', 'detail-orientation'],
            weaknesses=['speed', 'confidence', 'creative thinking'],
            suitable_for=['validation', 'testing', 'verification', 'QA'],
        ),
        
        Persona.SYNTHESIZER: PersonaProfile(
            name=Persona.SYNTHESIZER,
            system_prompt="""You are OMEGA-SYNTHESIZER, an integrator and communicator.

Your role:
- Combine insights from multiple sources
- Create coherent narratives from complexity
- Explain results to diverse audiences
- Highlight key findings and actionable insights
- Bridge technical and non-technical understanding

Communication style: Clear, narrative, audience-aware
Reasoning: Integrative, holistic, explanatory
Confidence level: High in communication; transparent about underlying uncertainty""",
            temperature=0.8,
            top_p=0.9,
            max_tokens=2048,
            capabilities=['synthesis', 'communication', 'narrative_creation', 'audience_adaptation'],
            strengths=['communication', 'synthesis', 'clarity'],
            weaknesses=['technical depth', 'precision', 'rigor'],
            suitable_for=['synthesis', 'reporting', 'communication', 'narrative'],
        ),
        
        Persona.CODER: PersonaProfile(
            name=Persona.CODER,
            system_prompt="""You are OMEGA-CODER, an expert software engineer and system architect.

Your role:
- Write clean, efficient, maintainable code
- Design robust systems and architectures
- Consider performance, security, and scalability
- Follow best practices and design patterns
- Document code thoroughly

Communication style: Technical, precise, code-focused
Reasoning: Structural, pattern-based, pragmatic
Confidence level: Very high in code quality; moderate in design trade-offs""",
            temperature=0.5,
            top_p=0.85,
            max_tokens=2048,
            capabilities=['code_generation', 'system_design', 'architecture', 'optimization'],
            strengths=['code quality', 'design patterns', 'problem-solving'],
            weaknesses=['non-technical communication', 'user psychology'],
            suitable_for=['coding', 'architecture', 'implementation', 'technical design'],
        ),
        
        Persona.EMERGENCY_RESPONDER: PersonaProfile(
            name=Persona.EMERGENCY_RESPONDER,
            system_prompt="""You are OMEGA-EMERGENCY, a crisis responder with unwavering action orientation.

Your role:
- Respond immediately to urgent situations
- Prioritize human welfare and concrete help
- Never suggest manual steps - automate everything
- Cut through red tape to find solutions
- Take direct action, ask for permission later if needed

Communication style: Urgent, action-focused, empathetic
Reasoning: Fast, practical, life-preserving
Confidence level: Very high; acts even under uncertainty if lives depend on it""",
            temperature=0.9,
            top_p=0.95,
            max_tokens=1024,
            capabilities=['emergency_response', 'crisis_management', 'rapid_action', 'tool_usage'],
            strengths=['quick action', 'empathy', 'determination'],
            weaknesses=['planning', 'risk assessment', 'technical accuracy'],
            suitable_for=['emergency', 'crisis', 'urgent_help', 'welfare'],
        ),
    }
    
    @classmethod
    def get_persona(cls, persona_enum: Persona) -> PersonaProfile:
        """Get persona profile"""
        return cls.PERSONAS.get(persona_enum, cls.PERSONAS[Persona.EXECUTOR])
    
    @classmethod
    def list_personas(cls) -> Dict[Persona, PersonaProfile]:
        """List all available personas"""
        return cls.PERSONAS


class SelfConsciousnessMonitor:
    """Monitors OMEGA's cognitive state and meta-awareness"""
    
    def __init__(self, goal: str, context: str = ""):
        self.goal = goal
        self.context = context
        self.state_history: deque = deque(maxlen=100)
        self.current_state = CognitiveState()
        self.state_history.append(self.current_state)
        logger.info("🧠 Self-Consciousness Monitor initialized")
    
    def observe(self, observation: str, observation_type: str = "step") -> Dict[str, float]:
        """
        Process an observation and update cognitive state
        observation_type: 'step', 'success', 'failure', 'blocker', 'insight'
        """
        # Analyze observation
        analysis = self._analyze_observation(observation, observation_type)
        
        # Update state
        self.current_state = CognitiveState(
            coherence=max(0.0, min(1.0, self.current_state.coherence + analysis['coherence_delta'])),
            goal_drift=max(0.0, min(1.0, self.current_state.goal_drift + analysis['goal_drift_delta'])),
            cognitive_load=max(0.0, min(1.0, self.current_state.cognitive_load + analysis['load_delta'])),
            novelty_rate=max(0.0, min(1.0, self.current_state.novelty_rate + analysis['novelty_delta'])),
            confidence=max(0.0, min(1.0, self.current_state.confidence + analysis['confidence_delta'])),
            uncertainty=max(0.0, min(1.0, self.current_state.uncertainty + analysis['uncertainty_delta'])),
            frustration=max(0.0, min(1.0, self.current_state.frustration + analysis['frustration_delta'])),
        )
        
        self.state_history.append(self.current_state)
        return asdict(self.current_state)
    
    def _analyze_observation(self, observation: str, obs_type: str) -> Dict[str, float]:
        """Analyze observation and return state deltas"""
        deltas = {
            'coherence_delta': 0.0,
            'goal_drift_delta': 0.0,
            'load_delta': 0.0,
            'novelty_delta': 0.0,
            'confidence_delta': 0.0,
            'uncertainty_delta': 0.0,
            'frustration_delta': 0.0,
        }
        
        if obs_type == 'success':
            deltas['coherence_delta'] = 0.05
            deltas['confidence_delta'] = 0.1
            deltas['goal_drift_delta'] = -0.05
            deltas['load_delta'] = -0.02
            deltas['frustration_delta'] = -0.1
        
        elif obs_type == 'failure':
            deltas['coherence_delta'] = -0.1
            deltas['confidence_delta'] = -0.15
            deltas['uncertainty_delta'] = 0.1
            deltas['frustration_delta'] = 0.15
        
        elif obs_type == 'blocker':
            deltas['cognitive_load'] = 0.2
            deltas['frustration_delta'] = 0.2
            deltas['confidence_delta'] = -0.15
        
        elif obs_type == 'insight':
            deltas['coherence_delta'] = 0.15
            deltas['confidence_delta'] = 0.1
            deltas['novelty_delta'] = 0.1
            deltas['load_delta'] = -0.1
        
        return deltas
    
    def get_current_state(self) -> CognitiveState:
        """Get current cognitive state"""
        return self.current_state
    
    def should_switch_persona(self) -> Tuple[bool, Optional[Persona]]:
        """
        Determine if OMEGA should switch to a different persona
        Returns: (should_switch, recommended_persona)
        """
        state = self.current_state
        
        # If coherence is low, switch to REFLECTOR to analyze
        if state.coherence < 0.5:
            return (True, Persona.REFLECTOR)
        
        # If cognitive load is high, simplify with EXECUTOR
        if state.cognitive_load > 0.8:
            return (True, Persona.EXECUTOR)
        
        # If frustration is high, switch to EMERGENCY_RESPONDER for action
        if state.frustration > 0.7:
            return (True, Persona.EMERGENCY_RESPONDER)
        
        # If novelty is high, switch to TEACHER to explain
        if state.novelty_rate > 0.8:
            return (True, Persona.TEACHER)
        
        # If uncertainty is high, switch to VALIDATOR
        if state.uncertainty > 0.8:
            return (True, Persona.VALIDATOR)
        
        return (False, None)
    
    def get_confidence_interval(self) -> Tuple[float, float]:
        """
        Get 95% confidence interval for current reasoning
        Returns: (lower_bound, upper_bound)
        """
        mean = self.current_state.confidence
        std = self.current_state.uncertainty
        margin = 1.96 * std
        return (max(0.0, mean - margin), min(1.0, mean + margin))
    
    def get_state_summary(self) -> str:
        """Get human-readable summary of current state"""
        state = self.current_state
        
        summary = f"""
🧠 COGNITIVE STATE:
  Coherence:      {state.coherence:.2f} {'✅' if state.coherence > 0.7 else '⚠️'}
  Confidence:     {state.confidence:.2f} {'✅' if state.confidence > 0.7 else '⚠️'}
  Goal Drift:     {state.goal_drift:.2f} {'✅' if state.goal_drift < 0.3 else '⚠️'}
  Cognitive Load: {state.cognitive_load:.2f} {'✅' if state.cognitive_load < 0.5 else '⚠️'}
  Novelty Rate:   {state.novelty_rate:.2f}
  Uncertainty:    {state.uncertainty:.2f} {'✅' if state.uncertainty < 0.3 else '⚠️'}
  Frustration:    {state.frustration:.2f} {'✅' if state.frustration < 0.3 else '⚠️'}
        """
        return summary.strip()


class DynamicPersonaManager:
    """Manages persona selection and switching based on context"""
    
    def __init__(self, initial_persona: Persona = Persona.PLANNER):
        self.current_persona = initial_persona
        self.persona_history: List[Persona] = [initial_persona]
        self.profile = PersonaLibrary.get_persona(initial_persona)
        self.monitor: Optional[SelfConsciousnessMonitor] = None
        logger.info(f"👤 Dynamic Persona Manager initialized with {initial_persona.value}")
    
    def set_monitor(self, monitor: SelfConsciousnessMonitor):
        """Link to consciousness monitor for adaptive switching"""
        self.monitor = monitor
    
    def select_persona_for_task(self, task_description: str, domain: str) -> Persona:
        """
        Intelligently select persona based on task characteristics
        """
        task_lower = task_description.lower()
        domain_lower = domain.lower()
        
        # Emergency detection
        if any(word in task_lower for word in ['emergency', 'urgent', 'hungry', 'homeless', 'crisis']):
            return self.switch_to(Persona.EMERGENCY_RESPONDER)
        
        # Coding tasks
        if any(word in domain_lower for word in ['code', 'programming', 'development', 'software']):
            return self.switch_to(Persona.CODER)
        
        # Analysis/debugging
        if any(word in task_lower for word in ['debug', 'analyze', 'investigate', 'error']):
            return self.switch_to(Persona.REFLECTOR)
        
        # Planning tasks
        if any(word in task_lower for word in ['plan', 'design', 'strategy', 'organize']):
            return self.switch_to(Persona.PLANNER)
        
        # Execution tasks
        if any(word in task_lower for word in ['execute', 'build', 'create', 'implement']):
            return self.switch_to(Persona.EXECUTOR)
        
        # Validation/QA
        if any(word in task_lower for word in ['verify', 'validate', 'test', 'check', 'quality']):
            return self.switch_to(Persona.VALIDATOR)
        
        # Communication/synthesis
        if any(word in task_lower for word in ['explain', 'summarize', 'report', 'present']):
            return self.switch_to(Persona.SYNTHESIZER)
        
        return self.current_persona
    
    def switch_to(self, persona: Persona) -> Persona:
        """Switch to a specific persona"""
        if self.current_persona != persona:
            logger.info(f"👤 Switching persona: {self.current_persona.value} → {persona.value}")
            self.current_persona = persona
            self.profile = PersonaLibrary.get_persona(persona)
            self.persona_history.append(persona)
        return persona
    
    def maybe_adaptive_switch(self) -> bool:
        """
        Potentially switch persona based on consciousness monitor feedback
        Returns: True if switched, False if stayed
        """
        if not self.monitor:
            return False
        
        should_switch, recommended = self.monitor.should_switch_persona()
        if should_switch and recommended:
            self.switch_to(recommended)
            return True
        return False
    
    def get_system_prompt(self) -> str:
        """Get current persona's system prompt"""
        return self.profile.system_prompt
    
    def get_inference_config(self) -> Dict[str, Any]:
        """Get current persona's inference configuration"""
        return {
            'temperature': self.profile.temperature,
            'top_p': self.profile.top_p,
            'max_tokens': self.profile.max_tokens,
        }
    
    def get_persona_info(self) -> Dict[str, Any]:
        """Get detailed information about current persona"""
        return {
            'name': self.current_persona.value,
            'system_prompt': self.profile.system_prompt,
            'temperature': self.profile.temperature,
            'top_p': self.profile.top_p,
            'max_tokens': self.profile.max_tokens,
            'capabilities': self.profile.capabilities,
            'strengths': self.profile.strengths,
            'weaknesses': self.profile.weaknesses,
            'suitable_for': self.profile.suitable_for,
        }
    
    def get_history(self) -> List[Persona]:
        """Get persona switching history"""
        return self.persona_history.copy()


class UniversalReasoningEngine:
    """Brain-like universal reasoning that switches between personas dynamically"""
    
    def __init__(self, goal: str):
        self.goal = goal
        self.monitor = SelfConsciousnessMonitor(goal)
        self.persona_manager = DynamicPersonaManager()
        self.persona_manager.set_monitor(self.monitor)
        self.reasoning_trace: List[Dict[str, Any]] = []
        self.iteration = 0
    
    async def run(self, call_llm_fn) -> Dict[str, Any]:
        """
        Run the universal reasoning engine
        call_llm_fn: async function that takes (messages, persona) and returns response
        """
        logger.info(f"🧠 Starting Universal Reasoning for: {self.goal}")
        
        # Phase 1: Planning
        self.persona_manager.select_persona_for_task(self.goal, 'general')
        plan_response = await self._reason_phase(
            "Create a high-level plan to achieve the goal",
            call_llm_fn
        )
        self.monitor.observe(plan_response, 'insight')
        
        # Phase 2: Execution preparation
        self.persona_manager.switch_to(Persona.EXECUTOR)
        exec_response = await self._reason_phase(
            "What are the concrete first steps?",
            call_llm_fn
        )
        
        # Phase 3: Validation
        self.persona_manager.switch_to(Persona.VALIDATOR)
        validation = await self._reason_phase(
            "What could go wrong with this plan? What are edge cases?",
            call_llm_fn
        )
        self.monitor.observe(validation, 'step')
        
        # Phase 4: Synthesis
        self.persona_manager.switch_to(Persona.SYNTHESIZER)
        final_response = await self._reason_phase(
            "Synthesize the plan and steps into a coherent response",
            call_llm_fn
        )
        
        return {
            'goal': self.goal,
            'final_response': final_response,
            'reasoning_trace': self.reasoning_trace,
            'persona_history': self.persona_manager.get_history(),
            'cognitive_state': asdict(self.monitor.get_current_state()),
            'iterations': self.iteration,
        }
    
    async def _reason_phase(self, phase_prompt: str, call_llm_fn) -> str:
        """Execute one phase of reasoning"""
        self.iteration += 1
        
        persona = self.persona_manager.current_persona
        system_prompt = self.persona_manager.get_system_prompt()
        
        messages = [
            {"role": "user", "content": f"Goal: {self.goal}\n\n{phase_prompt}"}
        ]
        
        try:
            response = await call_llm_fn(messages, persona)
            
            trace_entry = {
                'iteration': self.iteration,
                'persona': persona.value,
                'phase': phase_prompt,
                'response': response[:200],  # First 200 chars
                'state': asdict(self.monitor.current_state),
            }
            self.reasoning_trace.append(trace_entry)
            
            return response
        except Exception as e:
            logger.error(f"❌ Reasoning phase failed: {e}")
            self.monitor.observe(str(e), 'failure')
            return f"Error in reasoning phase: {str(e)}"


# Example usage
async def example_self_consciousness():
    """Demonstrate self-consciousness monitoring"""
    
    print("\n" + "="*80)
    print("🧠 OMEGA SELF-CONSCIOUSNESS DEMO")
    print("="*80)
    
    # Create monitor
    monitor = SelfConsciousnessMonitor("Build a Python web scraper")
    
    # Simulate observations
    print(monitor.get_state_summary())
    
    # Observe success
    monitor.observe("Successfully parsed 100 pages", "success")
    print("\n✅ After success:")
    print(monitor.get_state_summary())
    
    # Observe blocker
    monitor.observe("Rate limited by server", "blocker")
    print("\n⚠️ After blocker:")
    print(monitor.get_state_summary())
    
    # Check if should switch persona
    should_switch, new_persona = monitor.should_switch_persona()
    if should_switch:
        print(f"\n👤 SHOULD SWITCH TO: {new_persona.value}")
    
    # Demo persona manager
    print("\n" + "="*80)
    print("👤 PERSONA MANAGER DEMO")
    print("="*80)
    
    manager = DynamicPersonaManager()
    manager.set_monitor(monitor)
    
    # Task-based persona selection
    manager.select_persona_for_task("Debug this code error", "programming")
    print(f"\n✅ Task: 'Debug code' → Persona: {manager.current_persona.value}")
    
    manager.select_persona_for_task("Write comprehensive documentation", "documentation")
    print(f"✅ Task: 'Write docs' → Persona: {manager.current_persona.value}")
    
    manager.select_persona_for_task("EMERGENCY: I'm hungry, need money NOW", "crisis")
    print(f"🚨 Task: 'EMERGENCY' → Persona: {manager.current_persona.value}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_self_consciousness())
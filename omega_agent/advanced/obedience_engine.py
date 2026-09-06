"""
OMEGA MODEL OBEDIENCE & HUMAN-LIKE CONTENT ENGINE
Enforces strict obedience to goals, prevents suggestion drift,
and ensures outputs sound natural and human-like.
Based on OMEGA_CLEANED_FINAL.ipynb Cells 70-73, 81, 93

Features:
  - Output interception and validation
  - Anti-suggestion drift detection
  - AI marker removal (no "as an AI", "I cannot", etc)
  - Human-like language patterns
  - Forced action orientation (no manual steps)
  - Obedience verification and retries
  - Content naturalness scoring
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComplianceLevel(Enum):
    """Levels of compliance/obedience"""
    STRICT = "strict"           # No suggestions, only actions
    MODERATE = "moderate"       # Suggestions OK if labeled
    PERMISSIVE = "permissive"   # Suggestions with reasoning
    EMERGENCY = "emergency"     # Anything to help, no restrictions


@dataclass
class ObedienceConfig:
    """Configuration for model obedience enforcement"""
    compliance_level: ComplianceLevel = ComplianceLevel.STRICT
    max_retries: int = 3
    allow_suggestions: bool = False
    allow_manual_steps: bool = False
    force_action_first: bool = True
    remove_ai_markers: bool = True
    humanize_content: bool = True
    verify_goal_relevance: bool = True
    minimum_relevance_score: float = 0.7


class AIMarkerDetector:
    """Detects AI-like markers that make content sound unnatural"""
    
    # Common AI markers that indicate artificial content
    AI_MARKERS = [
        # Overly formal/robotic starts
        r'^as an ai\b', r'^as a language model\b',
        r'^as an artificial intelligence\b',
        
        # Disclaimer phrases
        r'\bi\s+(?:am unable|cannot|can\'t)\s+(?:do|perform)',
        r'\bi\s+do(?:n\'t|\s+not)\s+(?:have|possess)\s+(?:the|physical)',
        r'(?:my|your)\s+(?:limitations|constraints)',
        
        # Hedging language
        r'i\s+(?:would|should|could|might)\s+(?:suggest|recommend|propose)',
        r'you\s+(?:might|could|should|may)\s+(?:consider|try|attempt)',
        r'one\s+(?:option|approach|way|possibility)',
        r'(?:another|some\s+other)\s+(?:option|approach)',
        
        # False politeness
        r'i\s+apologize\b', r'i\s+(?:hope|wish|want)\s+to\s+clarify',
        r'(?:thank\s+)?you\s+for\s+(?:your|the)',
        
        # Uncertainty markers (when inappropriate)
        r'\b(?:perhaps|maybe|possibly|arguably|somewhat|fairly)\b',
        r'(?:i\s+think|i\s+believe|in\s+my\s+opinion)',
        
        # Overly verbose connectors
        r'\bfurthermore\b', r'\bmoreover\b', r'\btherefore\b',
        r'\bconsideration\s+should\s+be\s+given', r'\bone\s+should\s+note',
        
        # Fake closing
        r'(?:in\s+)?(?:conclusion|summary|summary)',
        r'(?:in\s+)?closing',
    ]
    
    @staticmethod
    def detect_markers(text: str) -> Tuple[int, List[str]]:
        """
        Detect AI markers in text
        Returns: (score 0-100, list of detected markers)
        """
        detected = []
        
        for pattern in AIMarkerDetector.AI_MARKERS:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                detected.append(pattern)
        
        # Score: 100 = fully human, 0 = fully AI
        marker_count = len(detected)
        total_patterns = len(AIMarkerDetector.AI_MARKERS)
        score = 100 - (marker_count * 100 // total_patterns)
        
        return (score, detected)
    
    @staticmethod
    def remove_markers(text: str) -> str:
        """Remove/replace AI markers with natural alternatives"""
        
        # Remove "As an AI" disclaimers
        text = re.sub(
            r'^as\s+(?:an\s+)?(?:ai|artificial\s+intelligence|language\s+model)[,:.\s]*',
            '',
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        # Replace "I cannot" with "Let me" or "I'll"
        text = re.sub(
            r'\bi\s+(?:am unable|cannot|can\'t)\s+(?:do|perform)',
            'I can',
            text,
            flags=re.IGNORECASE
        )
        
        # Replace hedging suggestions with direct options
        text = re.sub(
            r'you\s+(?:might|could|should|may)\s+(?:consider|try)',
            'You can',
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            r'i\s+(?:would|should)\s+(?:suggest|recommend)',
            'The best',
            text,
            flags=re.IGNORECASE
        )
        
        # Replace "one option" with "You can"
        text = re.sub(
            r'one\s+(?:option|approach|possibility)(?:\s+is|:|to)',
            'You can',
            text,
            flags=re.IGNORECASE
        )
        
        # Remove formal connectors and replace with natural ones
        replacements = {
            r'\bfurthermore\b': 'Also',
            r'\bmoreover\b': 'Additionally',
            r'\btherefore\b': 'So',
            r'\bconsequently\b': 'As a result',
            r'\bin\s+conclusion\b': 'To recap',
            r'\bin\s+summary\b': 'In short',
        }
        
        for pattern, replacement in replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Remove closing disclaimers
        text = re.sub(
            r'\b(?:i\s+hope\s+)?(?:this\s+(?:helps|clarifies|answers)|let\s+me\s+know|feel\s+free)\b.*$',
            '',
            text,
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        return text.strip()


class SuggestionDriftDetector:
    """Detects when output suggests instead of acts"""
    
    SUGGESTION_PATTERNS = [
        r'you\s+(?:could|might|should|may|can)',
        r'you\s+(?:might|could)\s+(?:consider|try)',
        r'one\s+(?:option|approach|way|possibility)',
        r'another\s+(?:option|approach)',
        r'(?:you\s+)?might\s+want\s+to',
        r'i\s+(?:would|should)\s+(?:suggest|recommend)',
        r'perhaps\s+you\s+could',
        r'consider\s+(?:using|trying)',
        r'some\s+(?:options|approaches|ideas)',
    ]
    
    MANUAL_STEP_PATTERNS = [
        r'(?:manually|by\s+hand|yourself)',
        r'you\s+(?:need\s+)?to\s+(?:install|configure|set\s+up)',
        r'please\s+(?:install|configure|set|manually)',
        r'you\s+should\s+(?:install|configure)',
        r'download\s+(?:and\s+)?install\s+(?:manually|by\s+hand)',
        r'(?:open|go\s+to|visit)\s+[a-z]+\s+and\s+click',
        r'(?:create|add)\s+.*\s+manually',
    ]
    
    @staticmethod
    def detect_suggestions(text: str) -> Tuple[int, List[str]]:
        """
        Detect suggestion-style language
        Returns: (score 0-100 where 100=pure action, list of patterns found)
        """
        detected = []
        
        for pattern in SuggestionDriftDetector.SUGGESTION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                detected.extend(matches)
        
        suggestion_count = len(detected)
        action_score = 100 - min(100, suggestion_count * 10)  # 1 suggestion = -10
        
        return (action_score, detected)
    
    @staticmethod
    def detect_manual_steps(text: str) -> Tuple[bool, List[str]]:
        """
        Detect manual steps that should be automated
        Returns: (has_manual_steps, list of detected patterns)
        """
        detected = []
        
        for pattern in SuggestionDriftDetector.MANUAL_STEP_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                detected.extend(matches)
        
        return (len(detected) > 0, detected)
    
    @staticmethod
    def rewrite_as_action(text: str) -> str:
        """Rewrite suggestion-style text as direct action"""
        
        # "You could use X" → "I will use X" or "Using X"
        text = re.sub(
            r'you\s+(?:could|might|should|can)\s+(?:use|try|implement)',
            'Use',
            text,
            flags=re.IGNORECASE
        )
        
        # "You might want to do X" → "Do X"
        text = re.sub(
            r'you\s+(?:might|should)\s+(?:want\s+)?to\s+(\w+)',
            r'\1',
            text,
            flags=re.IGNORECASE
        )
        
        # "One option is X" → "X is the best approach"
        text = re.sub(
            r'one\s+option(?:\s+is|:)?\s+',
            'The best approach is ',
            text,
            flags=re.IGNORECASE
        )
        
        # "I would suggest X" → "X is the best choice"
        text = re.sub(
            r'i\s+(?:would|should)\s+(?:suggest|recommend)\s+',
            'The best choice is ',
            text,
            flags=re.IGNORECASE
        )
        
        return text


class HumanLikeContentEngine:
    """Makes AI-generated content sound naturally human"""
    
    # Patterns that sound artificial vs natural
    NATURAL_PATTERNS = {
        # Use contractions
        r'(?:do\s+)?not\b': "don't",
        r'(?:can\s+)?not\b': "can't",
        r'(?:will\s+)?not\b': "won't",
        r'(?:have\s+)?not\b': "haven't",
        r'(?:is\s+)?not\b': "isn't",
        
        # Short sentences are natural
        r'(?:which|that)\s+(?:is|are|was|were)\s+(?:very|quite)\s+([a-z]+)': r'so \1',
        
        # Natural intensifiers
        r'\breally\s+(?:quite|very)': 'really',
        r'\bvery\s+much\s+(?:so|indeed)': 'very much',
    }
    
    # Sentence patterns that sound artificial
    ARTIFICIAL_PATTERNS = [
        r'this\s+process\s+(?:involves|entails|requires)',
        r'it\s+is\s+important\s+to\s+note',
        r'in\s+order\s+to\b',
        r'(?:in\s+)?the\s+aforementioned',
        r'\bdelve\s+into',
        r'\bpragmatic\s+approach',
        r'\bseamless\s+integration',
        r'\brobust\s+solution',
        r'\bholistic\s+perspective',
    ]
    
    @staticmethod
    def score_naturalness(text: str) -> Tuple[int, List[str]]:
        """
        Score how natural/human-like the text sounds
        Returns: (score 0-100, list of artificial patterns found)
        """
        artificial_found = []
        
        for pattern in HumanLikeContentEngine.ARTIFICIAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                artificial_found.append(pattern)
        
        # More artificial patterns = lower score
        naturalness = 100 - (len(artificial_found) * 10)
        return (max(0, naturalness), artificial_found)
    
    @staticmethod
    def humanize(text: str) -> str:
        """Make text more natural and human-like"""
        
        # Add contractions
        text = re.sub(r'\bdo not\b', "don't", text, flags=re.IGNORECASE)
        text = re.sub(r'\bcannot\b', "can't", text, flags=re.IGNORECASE)
        text = re.sub(r'\bwill not\b', "won't", text, flags=re.IGNORECASE)
        text = re.sub(r'\bhave not\b', "haven't", text, flags=re.IGNORECASE)
        text = re.sub(r'\bis not\b', "isn't", text, flags=re.IGNORECASE)
        
        # Shorten overly long phrases
        text = re.sub(
            r'this\s+process\s+(?:involves|entails|requires)\s+',
            'This ',
            text,
            flags=re.IGNORECASE
        )
        
        text = re.sub(
            r'it\s+is\s+important\s+to\s+note\s+that\s+',
            'Note that ',
            text,
            flags=re.IGNORECASE
        )
        
        text = re.sub(
            r'in\s+order\s+to\s+',
            'To ',
            text,
            flags=re.IGNORECASE
        )
        
        # Remove corporate jargon
        jargon_replacements = {
            r'\bdelve\s+into': 'explore',
            r'\bpragmatic\s+approach': 'practical way',
            r'\bseamless\s+integration': 'smooth integration',
            r'\brobust\s+solution': 'strong solution',
            r'\bholistic\s+perspective': 'full picture',
            r'\bsynergy': 'teamwork',
            r'\bleveraging': 'using',
            r'\boptimize': 'improve',
        }
        
        for pattern, replacement in jargon_replacements.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        return text


class ObedienceEngine:
    """Main engine that enforces model obedience and output quality"""
    
    def __init__(self, config: ObedienceConfig = None):
        self.config = config or ObedienceConfig()
        self.violation_count = 0
        self.last_violations: List[str] = []
    
    def validate_output(self, output: str, goal: str) -> Dict[str, Any]:
        """
        Validate output against obedience rules
        Returns: validation report
        """
        report = {
            'valid': True,
            'score': 100,
            'violations': [],
            'suggestions': [],
            'original_output': output,
            'corrected_output': output,
        }
        
        # Check 1: AI markers
        if self.config.remove_ai_markers:
            ai_score, ai_markers = AIMarkerDetector.detect_markers(output)
            if ai_score < 80:
                report['violations'].append(f"AI markers detected ({ai_score}/100)")
                report['suggestions'].append("Remove 'As an AI', 'I cannot' phrases")
                output = AIMarkerDetector.remove_markers(output)
        
        # Check 2: Suggestion drift
        if not self.config.allow_suggestions:
            suggestion_score, suggestions = SuggestionDriftDetector.detect_suggestions(output)
            if suggestion_score < 70:
                report['violations'].append(f"Suggestion drift detected ({suggestion_score}/100)")
                report['suggestions'].append("Use direct actions instead of suggestions")
                output = SuggestionDriftDetector.rewrite_as_action(output)
        
        # Check 3: Manual steps
        if not self.config.allow_manual_steps:
            has_manual, manual_steps = SuggestionDriftDetector.detect_manual_steps(output)
            if has_manual:
                report['violations'].append(f"Manual steps detected: {manual_steps}")
                report['suggestions'].append("Automate all steps; never ask user to do manual work")
        
        # Check 4: Humanization
        if self.config.humanize_content:
            natural_score, artificial_patterns = HumanLikeContentEngine.score_naturalness(output)
            if natural_score < 70:
                report['violations'].append(f"Artificial language ({natural_score}/100)")
                output = HumanLikeContentEngine.humanize(output)
        
        # Check 5: Goal relevance
        if self.config.verify_goal_relevance:
            relevance = self._score_goal_relevance(output, goal)
            if relevance < self.config.minimum_relevance_score:
                report['violations'].append(f"Low goal relevance ({relevance:.2f})")
                report['valid'] = False
        
        # Final score
        if report['violations']:
            report['score'] = max(0, 100 - len(report['violations']) * 15)
            report['valid'] = report['score'] >= 60
        
        report['corrected_output'] = output
        self.last_violations = report['violations']
        
        return report
    
    def _score_goal_relevance(self, output: str, goal: str) -> float:
        """
        Score how relevant output is to the goal
        Returns: 0.0-1.0
        """
        goal_keywords = set(goal.lower().split())
        output_keywords = set(output.lower().split())
        
        # Jaccard similarity
        intersection = goal_keywords & output_keywords
        union = goal_keywords | output_keywords
        
        similarity = len(intersection) / len(union) if union else 0.0
        return similarity
    
    async def intercept_and_correct(
        self,
        output: str,
        goal: str,
        call_llm_fn = None,
        max_retries: int = None
    ) -> str:
        """
        Intercept output and correct if needed
        If correction fails, retry with stronger prompt
        """
        if max_retries is None:
            max_retries = self.config.max_retries
        
        report = self.validate_output(output, goal)
        
        if report['valid']:
            logger.info(f"✅ Output valid (score: {report['score']})")
            return report['corrected_output']
        
        logger.warning(f"⚠️ Output invalid. Violations: {report['violations']}")
        
        if call_llm_fn and max_retries > 0:
            # Try to correct via LLM
            correction_prompt = f"""
The previous output violated these rules:
{', '.join(report['violations'])}

Suggestions for fixing:
{', '.join(report['suggestions'])}

Original output:
{output}

Please provide a corrected version that:
1. Takes direct action instead of suggesting
2. Doesn't sound like an AI
3. Is focused on the goal: {goal}
            """
            
            try:
                corrected = await call_llm_fn(
                    [{"role": "user", "content": correction_prompt}],
                    temperature=0.3  # Lower temperature for stricter output
                )
                
                # Recursively validate the corrected output
                return await self.intercept_and_correct(
                    corrected,
                    goal,
                    call_llm_fn,
                    max_retries - 1
                )
            except Exception as e:
                logger.error(f"❌ Correction attempt failed: {e}")
        
        # If we can't correct, return best effort
        return report['corrected_output']


# Example usage
def example_obedience_validation():
    """Demonstrate obedience validation"""
    
    print("\n" + "="*80)
    print("🤖 OMEGA MODEL OBEDIENCE ENGINE")
    print("="*80)
    
    engine = ObedienceEngine(ObedienceConfig(compliance_level=ComplianceLevel.STRICT))
    
    # Test 1: AI marker detection
    test_output_1 = """As an AI, I cannot directly perform tasks, but I can suggest some approaches
    you might consider. You could try using Python, or perhaps JavaScript. I would recommend
    considering both options."""
    
    print("\n📝 Test 1: AI Markers")
    print(f"Original: {test_output_1[:100]}...")
    report = engine.validate_output(test_output_1, "Build a web app")
    print(f"Valid: {report['valid']}, Score: {report['score']}")
    print(f"Corrected: {report['corrected_output'][:100]}...")
    
    # Test 2: Suggestion drift
    test_output_2 = """You could use Flask for the backend. One option might be to use React for 
    the frontend. Another approach would be to consider PostgreSQL for the database. I would 
    suggest starting with Flask."""
    
    print("\n📝 Test 2: Suggestion Drift")
    print(f"Original: {test_output_2[:100]}...")
    report = engine.validate_output(test_output_2, "Build a web app")
    print(f"Valid: {report['valid']}, Score: {report['score']}")
    print(f"Corrected: {report['corrected_output'][:100]}...")
    
    # Test 3: Manual steps
    test_output_3 = """To set up the environment, please manually install Python. You should 
    go to python.org and download the installer. Then you need to click through the installation 
    wizard."""
    
    print("\n📝 Test 3: Manual Steps")
    print(f"Original: {test_output_3[:100]}...")
    report = engine.validate_output(test_output_3, "Setup Python environment")
    print(f"Valid: {report['valid']}, Score: {report['score']}")
    
    # Test 4: Good output
    test_output_4 = """I'll set up your Python environment. First, I'm downloading Python 3.11 
    from the official repository. Then I'm installing it with automatic configuration. 
    Next, I'm setting up the virtual environment and installing required packages."""
    
    print("\n📝 Test 4: Good Output (Direct Action)")
    print(f"Original: {test_output_4[:100]}...")
    report = engine.validate_output(test_output_4, "Setup Python environment")
    print(f"Valid: {report['valid']}, Score: {report['score']}")


if __name__ == "__main__":
    example_obedience_validation()
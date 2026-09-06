"""Types for dynamic LLM-driven reasoning."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DynamicDomainProfile:
    """LLM + web-search derived profile — nothing hardcoded."""

    domain: str
    sub_domain: str = ""
    confidence: float = 0.7
    best_practices: List[str] = field(default_factory=list)
    execution_style: Dict[str, str] = field(default_factory=dict)
    recommended_tools: List[str] = field(default_factory=list)
    tool_usage_guidance: Dict[str, str] = field(default_factory=dict)
    system_prompt: str = ""
    output_format: str = "action_decision"
    quality_criteria: List[str] = field(default_factory=list)
    web_evidence: List[str] = field(default_factory=list)
    model_priority: str = "accuracy"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "sub_domain": self.sub_domain,
            "confidence": self.confidence,
            "best_practices": self.best_practices,
            "execution_style": self.execution_style,
            "recommended_tools": self.recommended_tools,
            "tool_usage_guidance": self.tool_usage_guidance,
            "system_prompt": self.system_prompt,
            "output_format": self.output_format,
            "quality_criteria": self.quality_criteria,
            "web_evidence": self.web_evidence[:5],
            "model_priority": self.model_priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DynamicDomainProfile":
        return cls(
            domain=data.get("domain", "general"),
            sub_domain=data.get("sub_domain", ""),
            confidence=float(data.get("confidence", 0.7)),
            best_practices=data.get("best_practices", []) or [],
            execution_style=data.get("execution_style", {}) or {},
            recommended_tools=data.get("recommended_tools", []) or [],
            tool_usage_guidance=data.get("tool_usage_guidance", {}) or {},
            system_prompt=data.get("system_prompt", "") or "",
            output_format=data.get("output_format", "action_decision"),
            quality_criteria=data.get("quality_criteria", []) or [],
            web_evidence=data.get("web_evidence", []) or [],
            model_priority=data.get("model_priority", "accuracy"),
        )

"""Domain-specific input validation requirements and error messages."""

from typing import Dict, List, Optional, Tuple

DOMAIN_REQUIREMENTS = {
    "emergency-assistance": {
        "required_inputs": ["location"],
        "validation_rules": {
            "location": {
                "min_length": 2,
                "must_contain_city_or_zip": True,
                "examples": ["Boston, MA", "02101", "San Francisco", "94105"],
                "error_field_name": "location (city + state or ZIP code)"
            }
        },
        "error_message_template": (
            "🔴 **Location Needed to Help You**\n\n"
            "To find **food banks, emergency cash programs, or shelters** near you, "
            "I need your **city + state** or **ZIP code**.\n\n"
            "**Please reply with your location:**\n"
            "- City format: `Boston, MA` or `San Francisco, CA`\n"
            "- ZIP format: `02101` or `94105`"
        ),
        "sub_domains": ["food_assistance", "cash_emergency", "shelter", "utility_bills"]
    },
    
    "coding": {
        "required_inputs": ["language_or_framework", "project_type"],
        "validation_rules": {
            "language_or_framework": {
                "must_be_non_empty": True,
                "valid_options": [
                    "python", "javascript", "typescript", "java", "go", "rust",
                    "csharp", "php", "ruby", "swift", "kotlin", "scala",
                    "react", "vue", "angular", "fastapi", "django", "spring",
                    "nodejs", "express", "nextjs", "flutter", "react-native"
                ],
                "examples": ["Python", "React with TypeScript", "Go", "FastAPI"],
                "error_field_name": "language or framework"
            },
            "project_type": {
                "must_be_non_empty": True,
                "valid_options": [
                    "web_app", "api", "cli_tool", "library", "desktop_app",
                    "mobile_app", "data_pipeline", "ml_model", "game"
                ],
                "examples": ["Web API", "React frontend", "CLI tool", "Python library"],
                "error_field_name": "project type or description"
            }
        },
        "error_message_template": (
            "❓ **I need more details to help you code**\n\n"
            "Please tell me:\n"
            "1. **Language or framework:** Python, React + TypeScript, Go, FastAPI, etc.\n"
            "2. **Project type:** Web app, API, CLI tool, library, etc.\n\n"
            "**Example:** \"Build a Python FastAPI REST API for a todo app\""
        ),
        "sub_domains": ["web", "backend", "frontend", "mobile", "devops", "data"]
    },
    
    "crypto_trading": {
        "required_inputs": ["exchange_name", "trading_pair", "strategy"],
        "validation_rules": {
            "exchange_name": {
                "must_be_non_empty": True,
                "valid_options": ["binance", "coinbase", "kraken", "bybit", "kucoin"],
                "examples": ["Binance", "Coinbase", "Kraken"],
                "error_field_name": "exchange name"
            },
            "trading_pair": {
                "must_be_non_empty": True,
                "pattern": r"^[A-Z]{2,}\-?[A-Z]{2,}$",
                "examples": ["BTC-USD", "ETH-USDT", "BTC/USDT"],
                "error_field_name": "trading pair (e.g., BTC-USD)"
            },
            "strategy": {
                "must_be_non_empty": True,
                "valid_options": [
                    "grid_trading", "dca", "swing_trade", "scalping",
                    "mean_reversion", "momentum", "arbitrage"
                ],
                "examples": ["Grid trading", "Dollar-cost averaging (DCA)", "Swing trading"],
                "error_field_name": "trading strategy"
            }
        },
        "sensitive_fields": ["api_key", "secret_key", "password"],
        "warning_message": "⚠️ **NEVER share API keys in messages!** Use secure credential storage.",
        "error_message_template": (
            "❓ **Trading details needed**\n\n"
            "Please provide:\n"
            "1. **Exchange:** Binance, Coinbase, Kraken, etc.\n"
            "2. **Trading pair:** BTC-USD, ETH-USDT, etc.\n"
            "3. **Strategy:** Grid trading, DCA, Swing trade, etc.\n\n"
            "⚠️ **Never share API keys in chat!** Use secure credential management."
        ),
        "sub_domains": ["spot_trading", "futures", "options"]
    },
    
    "research": {
        "required_inputs": ["topic"],
        "validation_rules": {
            "topic": {
                "min_length": 3,
                "must_be_non_empty": True,
                "examples": ["machine learning", "climate change", "quantum computing"],
                "error_field_name": "research topic"
            }
        },
        "error_message_template": (
            "❓ **Research topic needed**\n\n"
            "What would you like me to research?\n\n"
            "**Example:** \"Latest breakthroughs in quantum computing\" or \"Climate change impacts on agriculture\""
        ),
        "sub_domains": ["academic", "news", "technical", "general"]
    },
    
    "planning": {
        "required_inputs": ["objective"],
        "validation_rules": {
            "objective": {
                "min_length": 5,
                "must_be_non_empty": True,
                "examples": ["Complete Q3 project", "Plan a wedding", "Organize team offsite"],
                "error_field_name": "planning objective"
            }
        },
        "error_message_template": (
            "❓ **Planning objective needed**\n\n"
            "What would you like to plan?\n\n"
            "**Example:** \"Plan a 3-day team offsite in Seattle\" or \"Organize weekly team meetings\""
        ),
        "sub_domains": ["project", "personal", "team", "event"]
    }
}


class DomainRequirementsValidator:
    """Validates inputs match domain-specific requirements."""
    
    @staticmethod
    def get_missing_inputs(
        domain: str,
        user_inputs: Dict[str, str],
        goal: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if all required inputs are provided for a domain.
        
        Returns:
            (is_valid, error_message_if_invalid)
        """
        if domain not in DOMAIN_REQUIREMENTS:
            # No requirements for this domain
            return True, None
        
        req = DOMAIN_REQUIREMENTS[domain]
        required = req.get("required_inputs", [])
        
        if not required:
            return True, None
        
        # Check if required inputs are present and non-empty
        missing_fields = []
        for field in required:
            val = user_inputs.get(field, "").strip()
            if not val:
                missing_fields.append(field)
        
        if missing_fields:
            # Build helpful error message with examples
            error_msg = req.get("error_message_template", "Missing required information.")
            
            # Add warning for sensitive fields if applicable
            if any(f in missing_fields for f in req.get("sensitive_fields", [])):
                warning = req.get("warning_message", "")
                if warning:
                    error_msg = f"{warning}\n\n{error_msg}"
            
            return False, error_msg
        
        return True, None
    
    @staticmethod
    def validate_field_format(
        domain: str,
        field_name: str,
        value: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a specific field matches domain requirements.
        
        Returns:
            (is_valid, error_message_if_invalid)
        """
        if domain not in DOMAIN_REQUIREMENTS:
            return True, None
        
        req = DOMAIN_REQUIREMENTS[domain]
        rules = req.get("validation_rules", {}).get(field_name, {})
        
        if not rules:
            return True, None
        
        value = str(value).strip()
        
        # Check minimum length
        min_len = rules.get("min_length", 0)
        if value and len(value) < min_len:
            return False, f"{field_name} must be at least {min_len} characters"
        
        # Check valid options
        valid_options = rules.get("valid_options", [])
        if valid_options:
            val_lower = value.lower()
            is_valid = any(opt.lower() in val_lower or val_lower in opt.lower() 
                          for opt in valid_options)
            if not is_valid:
                options_str = ", ".join(valid_options[:5])
                return False, f"{field_name} should be one of: {options_str}"
        
        # Check pattern/regex
        if "pattern" in rules:
            import re
            pattern = rules["pattern"]
            if not re.match(pattern, value, re.IGNORECASE):
                error_field = rules.get("error_field_name", field_name)
                examples = rules.get("examples", [])
                example_str = f" (e.g., {examples[0]})" if examples else ""
                return False, f"Invalid {error_field} format{example_str}"
        
        return True, None
    
    @staticmethod
    def get_domain_requirements_prompt(domain: str) -> str:
        """Get a user-friendly prompt for gathering domain inputs."""
        if domain not in DOMAIN_REQUIREMENTS:
            return "Please provide the necessary details to proceed."
        
        req = DOMAIN_REQUIREMENTS[domain]
        return req.get("error_message_template", "Please provide the required information.")
    
    @staticmethod
    def has_sensitive_fields(domain: str) -> bool:
        """Check if domain involves sensitive information."""
        if domain not in DOMAIN_REQUIREMENTS:
            return False
        
        req = DOMAIN_REQUIREMENTS[domain]
        return bool(req.get("sensitive_fields"))
    
    @staticmethod
    def get_sensitive_fields(domain: str) -> List[str]:
        """Get list of sensitive fields for a domain."""
        if domain not in DOMAIN_REQUIREMENTS:
            return []
        
        req = DOMAIN_REQUIREMENTS[domain]
        return req.get("sensitive_fields", [])


# Helper function for quick validation in main agent
async def validate_domain_inputs(
    domain: str,
    goal: str,
    user_inputs: Optional[Dict[str, str]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Quick validation function to check if domain-specific inputs are available.
    
    Usage in omega.py:
        is_valid, error_msg = await validate_domain_inputs(domain, goal, user_inputs)
        if not is_valid:
            # Return AWAIT_INPUT action
            return AgentResult(action="AWAIT_INPUT", output=error_msg, ...)
    """
    user_inputs = user_inputs or {}
    return DomainRequirementsValidator.get_missing_inputs(domain, user_inputs, goal)

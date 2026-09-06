"""Chat and messaging tools for user interaction."""

import logging
import time
from typing import Tuple, Dict, Any

logger = logging.getLogger("omega_agent.tools.chat")

async def send_chat_message(
    message: str,
    urgency: str = "normal",
    message_type: str = "prompt",
    **kwargs
) -> Tuple[Dict[str, Any], float]:
    """
    Send a message directly to the user via the UI.
    
    Used for:
    - Location/PIN prompts in emergency mode
    - Clarification questions
    - Status updates
    - Urgent notifications
    """
    start = time.time()
    
    # Construct the UI event
    event = {
        "type": "chat_message",
        "message": message,
        "urgency": urgency,
        "message_type": message_type,
        "timestamp": time.time(),
    }
    
    # Log that this was called
    logger.info(f"send_chat_message: {message[:50]}... (urgency={urgency})")
    
    return {
        "status": "sent",
        "message": message,
        "urgency": urgency,
    }, time.time() - start

def register_chat_tools(registry) -> None:
    """Register the chat messaging tool with the global ToolRegistry."""
    registry.register(
        "send_chat_message",
        (
            "ACT: Send a direct, conversational text message to the user in the Web UI. "
            "Use this tool when you need to explicitly ask the user for missing details "
            "(e.g., location, pincode, bank account info) before continuing a goal."
        ),
        send_chat_message,
        args={
            "message": "string — The complete message. MUST explicitly ask the user for missing details.",
            "urgency": "string — 'low', 'normal', or 'high' depending on message context.",
        }
    )
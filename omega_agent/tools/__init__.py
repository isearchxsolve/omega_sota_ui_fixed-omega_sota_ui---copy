import logging
from typing import Dict, Any

# --- ORIGINAL IMPORTS ---
from omega_agent.tools.registry import ToolRegistry
from omega_agent.tools.executor import ToolExecutor

logger = logging.getLogger(__name__)

# ==========================================
# ADVANCED INTEGRATED TOOLS
# ==========================================

async def tool_browser_stealth_navigate(agent_instance, url: str, interactions: list = None, screenshot: bool = False) -> Dict[str, Any]:
    """
    Navigate and interact with websites using stealth techniques to bypass Cloudflare, WAFs, and rate limits.
    """
    try:
        # Utilize the lazy-loader from the agent instance
        await agent_instance._initialize_stealth_browser()
        
        # Navigate to target
        if not await agent_instance.stealth_browser.navigate(url):
            return {'status': 'error', 'message': 'Stealth navigation failed.'}
        
        # Execute human-like interactions if provided
        if interactions:
            await agent_instance.stealth_browser.interact_with_form(interactions)
        
        # Capture screenshot if requested
        if screenshot:
            screenshot_path = '/tmp/stealth_screenshot.png'
            await agent_instance.stealth_browser.screenshot(screenshot_path)
            return {'status': 'success', 'screenshot': screenshot_path}
        
        # Return page content (trimmed to 5000 chars to avoid LLM context window blowouts)
        content = await agent_instance.stealth_browser.get_page_content()
        return {'status': 'success', 'content': content[:5000]}
        
    except Exception as e:
        if hasattr(agent_instance, 'logger'):
            agent_instance.logger.error(f"Stealth browser error: {e}")
        else:
            logger.error(f"Stealth browser error: {e}")
        return {'status': 'error', 'message': str(e)}


# ==========================================
# TOOL REGISTRATION
# ==========================================
# We safely bind the new stealth tool to your existing ToolRegistry class. 
# (Adjust the method name below from '.register' or '.add_tool' depending on your specific ToolRegistry setup).

try:
    if hasattr(ToolRegistry, 'register'):
        ToolRegistry.register(
            name='BROWSER_STEALTH_NAVIGATE',
            description='Navigate and interact with websites using stealth techniques to bypass Cloudflare, WAFs, and rate limits.',
            arguments={
                'url': 'string',
                'interactions': 'list of dicts with keys: selector, type (type/click/select), value',
                'screenshot': 'bool (default False)'
            },
            category='browser',
            func=tool_browser_stealth_navigate
        )
    elif hasattr(ToolRegistry, 'add_tool'):
        ToolRegistry.add_tool(
            name='BROWSER_STEALTH_NAVIGATE',
            description='Navigate and interact with websites using stealth techniques.',
            func=tool_browser_stealth_navigate
        )
except Exception as e:
    logger.debug(f"Could not auto-register stealth tool (manual registration may be required in your registry file): {e}")

# Maintain original exports, plus the new tool if needed elsewhere
__all__ = ["ToolRegistry", "ToolExecutor", "tool_browser_stealth_navigate"]
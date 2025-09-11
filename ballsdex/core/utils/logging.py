import logging
import asyncio
from typing import Optional
import discord
from discord import Webhook
import aiohttp

from ballsdx.core.bot import BallsDexBot
from ballsdx.settings import settings


class DiscordWebhookHandler(logging.Handler):
    """Custom logging handler that sends log messages via Discord webhook"""
    
    def __init__(self, webhook_url: str, level=logging.NOTSET):
        super().__init__(level)
        self.webhook_url = webhook_url
        self.webhook: Optional[Webhook] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_webhook(self):
        """Ensure webhook and session are initialized"""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        if self.webhook is None:
            self.webhook = Webhook.from_url(self.webhook_url, session=self._session)
    
    def emit(self, record):
        """Emit a log record by sending it to Discord webhook"""
        try:
            # Format the log message
            message = self.format(record)
            
            # Schedule the coroutine to send the webhook message
            asyncio.create_task(self._send_webhook(message))
        except Exception:
            self.handleError(record)
    
    async def _send_webhook(self, message: str):
        """Send message via webhook"""
        try:
            await self._ensure_webhook()
            if self.webhook:
                # Truncate message if too long for Discord
                if len(message) > 2000:
                    message = message[:1997] + "..."
                await self.webhook.send(content=message)
        except Exception as e:
            # Fallback to console logging if webhook fails
            print(f"Failed to send webhook message: {e}")
            print(f"Message: {message}")
    
    async def close(self):
        """Clean up resources"""
        if self._session:
            await self._session.close()


# Create logger for admin actions
admin_logger = logging.getLogger("ballsdx.admin_actions")
admin_logger.setLevel(logging.INFO)

# Add console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
admin_logger.addHandler(console_handler)

# Add Discord webhook handler if webhook URL is configured
if hasattr(settings, 'webhook_url') and settings.webhook_url:
    webhook_handler = DiscordWebhookHandler(settings.webhook_url, logging.INFO)
    webhook_formatter = logging.Formatter('%(message)s')  # Simple format for Discord
    webhook_handler.setFormatter(webhook_formatter)
    admin_logger.addHandler(webhook_handler)


async def log_action(message: str, bot: Optional[BallsDexBot] = None):
    """
    Log an admin action using the configured logging handlers.
    This will automatically log to console and send to Discord webhook if configured.
    
    Args:
        message: The message to log
        bot: Bot instance (kept for backward compatibility, not used)
    """
    admin_logger.info(message)


# Backward compatibility
log = logging.getLogger("ballsdx.packages.admin.cog")
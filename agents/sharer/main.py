#!/usr/bin/env python
"""
Sharer Agent - Main Module
Responsible for sharing high-importance articles to social media platforms.
"""
import os
import asyncio
import json
import requests
from datetime import datetime

from agents._core._base import BaseAgent
from agents._core._rpc import Router
from _core.secrets import SecretsManager

class SharerAgent(BaseAgent):
    """Agent for sharing articles to social media."""

    def __init__(self):
        super().__init__("sharer")
        self.router = Router(self.bus)
        self.secrets_manager = SecretsManager(self.logger)
        self.linkedin_config = {}

    async def share_to_linkedin(self, article_title: str, article_url: str):
        """Shares a given article to LinkedIn."""
        if not all(k in self.linkedin_config for k in ['author_urn', 'access_token']):
            self.logger.error("LinkedIn config is incomplete. Missing author_urn or access_token.")
            return

        author_urn = self.linkedin_config['author_urn']
        access_token = self.linkedin_config['access_token']

        post_url = "https://api.linkedin.com/v2/ugcPosts"

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0'
        }

        post_data = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": f"{article_title}\n\n#AI #Technology #Innovation #AIRadar"
                    },
                    "shareMediaCategory": "ARTICLE",
                    "media": [
                        {
                            "status": "READY",
                            "originalUrl": article_url
                        }
                    ]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        try:
            response = requests.post(post_url, headers=headers, json=post_data)
            response.raise_for_status()  # Raise an exception for bad status codes
            self.logger.info(f"Successfully shared '{article_title}' to LinkedIn. Post ID: {response.json().get('id')}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to post to LinkedIn: {e}")
            if e.response:
                self.logger.error(f"LinkedIn API Response: {e.response.text}")

    async def setup(self):
        """Initializes the agent, retrieves secrets, and sets up subscriptions."""
        self.logger.info("Setting up sharer agent...")
        await self.bus.connect()
        
        # Retrieve LinkedIn credentials from Vault
        self.linkedin_config = self.secrets_manager.get_linkedin_config()
        if not self.linkedin_config:
            self.logger.error("LinkedIn configuration not found in Vault. Sharing will be disabled.")

        @self.router.on("tasks.share")
        async def handle_share_request(payload, subject, reply):
            self.logger.info(f"Received share request for article ID: {payload.get('article_id')}")
            title = payload.get('title')
            url = payload.get('url')
            if title and url:
                await self.share_to_linkedin(title, url)
            else:
                self.logger.warning("Share request received with missing title or url.")

        await self.router.start()
        self.logger.info("Sharer agent setup complete and listening for tasks.")

    async def run(self):
        """Runs the agent's main loop."""
        try:
            await self.setup()
            while True:
                await asyncio.sleep(3600)  # Agent stays alive
        except Exception as e:
            self.logger.critical(f"Sharer agent failed critically: {e}", exc_info=True)

async def main():
    agent = SharerAgent()
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())

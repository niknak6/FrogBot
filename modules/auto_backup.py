# modules.auto_backup

from datetime import datetime, time, timedelta, timezone
from modules.utils.database import DATABASE_FILE
from core import Config, CONFIG_FILE
from disnake.ext import commands
from disnake import Embed, Color
from typing import Optional
import asyncio
import logging
import aiohttp
import random
import base64
import os

REPO_NAME = 'FrogBot_DB_Backup'
DB_FILENAME = os.path.basename(DATABASE_FILE)

class GitHubBackup:
    def __init__(self, token: str, owner: str):
        self.token = token
        self.owner = owner
        self.repo = 'FrogBot_DB_Backup'
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.db_file = 'user_points.db'
        
    async def backup(self) -> bool:
        try:
            with open(self.db_file, 'rb') as f:
                content = base64.b64encode(f.read()).decode()
            async with aiohttp.ClientSession() as session:
                url = f'https://api.github.com/repos/{self.owner}/{self.repo}/contents/{self.db_file}'
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        current_file = await resp.json()
                        sha = current_file.get('sha')
                    else:
                        sha = None
                data = {
                    'message': f'Backup {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}',
                    'content': content
                }
                if sha:
                    data['sha'] = sha
                async with session.put(url, headers=self.headers, json=data) as resp:
                    if resp.status == 200 or resp.status == 201:
                        logging.info("Backup successful")
                        return True
                    else:
                        error_msg = await resp.text()
                        logging.error(f"Backup failed with status {resp.status}: {error_msg}")
                        return False
        except Exception as e:
            logging.error(f"Backup failed: {str(e)}")
            return False

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        config = Config(CONFIG_FILE).read()
        self.backup_handler = GitHubBackup(
            token=config['GITHUB_TOKEN'],
            owner=config['GITHUB_USERNAME']
        )

    @commands.slash_command(name="backup")
    @commands.is_owner()
    async def backup(self, inter):
        await inter.response.defer()
        success = await self.backup_handler.backup()
        await inter.followup.send(
            f"Backup {'successful' if success else 'failed'}"
        )

def setup(bot):
    bot.add_cog(BackupCog(bot))

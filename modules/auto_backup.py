# modules.auto_backup

from datetime import datetime, timedelta, timezone
from modules.utils.database import DATABASE_FILE
from core import Config, CONFIG_FILE
from disnake.ext import commands
from disnake import Embed, Color
import asyncio
import logging
import aiohttp
import base64

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
        self.backup_task = self.bot.loop.create_task(self.scheduled_backup())
        logging.info("Scheduled daily backup task initialized")

    async def create_backup_embed(self, success: bool, scheduled: bool = False) -> Embed:
        if success:
            embed = Embed(
                title="✅ Backup Successful",
                description="Database has been successfully backed up to GitHub.",
                color=Color.green()
            )
        else:
            embed = Embed(
                title="❌ Backup Failed",
                description="Failed to backup database to GitHub. Check logs for details.",
                color=Color.red()
            )
        embed.add_field(
            name="Timestamp", 
            value=f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
            inline=True
        )
        embed.add_field(
            name="Type",
            value="Scheduled" if scheduled else "Manual",
            inline=True
        )
        embed.add_field(
            name="Repository",
            value=f"[{self.backup_handler.repo}](https://github.com/{self.backup_handler.owner}/{self.backup_handler.repo})",
            inline=True
        )
        return embed

    async def scheduled_backup(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            target = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            wait_time = (target - now).total_seconds()
            logging.info(f"Next scheduled backup in {wait_time/3600:.2f} hours")
            await asyncio.sleep(wait_time)
            try:
                success = await self.backup_handler.backup()
                logging.info(f"Scheduled backup {'successful' if success else 'failed'}")
            except Exception as e:
                logging.error(f"Error during scheduled backup: {str(e)}")

    def cog_unload(self):
        if hasattr(self, 'backup_task'):
            self.backup_task.cancel()

    @commands.slash_command(name="backup")
    @commands.is_owner()
    async def backup(self, inter):
        await inter.response.defer()
        success = await self.backup_handler.backup()
        embed = await self.create_backup_embed(success, scheduled=False)
        await inter.followup.send(embed=embed)

def setup(bot):
    bot.add_cog(BackupCog(bot))

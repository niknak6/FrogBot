# modules.auto_backup

from modules.utils.database import DATABASE_FILE
from datetime import datetime, time, timedelta
from dropbox.exceptions import ApiError
from core import Config, CONFIG_FILE
from disnake.ext import commands
import calendar
import asyncio
import logging
import dropbox
import os

class DatabaseBackup:
    def __init__(self, dropbox_token):
        self.dropbox_token = dropbox_token
        self.dbx = dropbox.Dropbox(self.dropbox_token)
        
    async def backup_database(self):
        try:
            with open(DATABASE_FILE, 'rb') as f:
                file_content = f.read()
            date_str = datetime.now().strftime('%Y-%m-%d')
            backup_path = f'/backups/user_points_{date_str}/user_points.db'
            self.dbx.files_upload(
                file_content,
                backup_path,
                mode=dropbox.files.WriteMode.overwrite
            )
            logging.info(f"Database backup created successfully at {backup_path}")
            return True
        except ApiError as e:
            logging.error(f"Dropbox API error: {e}")
            return False
        except Exception as e:
            logging.error(f"Backup failed: {e}")
            return False

    async def cleanup_backups(self):
        try:
            result = self.dbx.files_list_folder('/backups')
            folders = sorted(
                [entry for entry in result.entries if entry.name.startswith('user_points_')],
                key=lambda entry: entry.name,
                reverse=True
            )
            if not folders:
                return
            newest_folder = folders[0]
            new_path = f'/monthly_backups/{newest_folder.name}'
            try:
                self.dbx.files_get_metadata('/monthly_backups')
            except ApiError:
                self.dbx.files_create_folder('/monthly_backups')
            self.dbx.files_move(newest_folder.path_display, new_path)
            for folder in folders[1:]:
                self.dbx.files_delete(folder.path_display)
            logging.info(f"Cleanup completed. Moved {newest_folder.name} to monthly backups and deleted {len(folders)-1} old backups")
            return True
        except ApiError as e:
            logging.error(f"Dropbox API error during cleanup: {e}")
            return False
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")
            return False

    async def sync_database(self):
        try:
            latest_backup = None
            try:
                result = self.dbx.files_list_folder('/backups')
                folders = sorted(
                    [entry for entry in result.entries if entry.name.startswith('user_points_')],
                    key=lambda entry: entry.name,
                    reverse=True
                )
                if folders:
                    latest_backup = self.dbx.files_download(f"{folders[0].path_display}/user_points.db")
            except ApiError as e:
                logging.warning(f"No existing backup found: {e}")
            local_exists = os.path.exists(DATABASE_FILE)
            if not local_exists and latest_backup:
                with open(DATABASE_FILE, 'wb') as f:
                    f.write(latest_backup[1].content)
                logging.info("Downloaded database from cloud backup")
            elif local_exists and latest_backup:
                local_time = os.path.getmtime(DATABASE_FILE)
                cloud_time = latest_backup[1].server_modified.timestamp()
                if local_time > cloud_time:
                    await self.backup_database()
                    logging.info("Local database newer than cloud - backed up")
                elif cloud_time > local_time:
                    with open(DATABASE_FILE, 'wb') as f:
                        f.write(latest_backup[1].content)
                    logging.info("Cloud database newer than local - downloaded")
            elif local_exists and not latest_backup:
                await self.backup_database()
                logging.info("No cloud backup found - created initial backup")
            else:
                logging.error("No database file found locally or in cloud!")
                return False
            return True
        except Exception as e:
            logging.error(f"Database sync failed: {e}")
            return False

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_task = None
        self.config = Config(CONFIG_FILE)
        self.dropbox_token = self.config.read().get('DROPBOX_TOKEN')
        if not self.dropbox_token:
            logging.error("Dropbox token not found in config")
            return
        self.backup_handler = DatabaseBackup(self.dropbox_token)

    def cog_unload(self):
        if self.backup_task:
            self.backup_task.cancel()

    async def schedule_backup(self):
        while True:
            now = datetime.now()
            target_time = time(hour=0, minute=0)
            next_run = datetime.combine(now.date(), target_time)
            if now.time() >= target_time:
                next_run = datetime.combine(now.date(), target_time) + timedelta(days=1)
            sleep_seconds = (next_run - now).total_seconds()
            await asyncio.sleep(sleep_seconds)
            await self.backup_handler.backup_database()
            _, last_day = calendar.monthrange(now.year, now.month)
            if now.day == last_day:
                await self.backup_handler.cleanup_backups()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.backup_task:
            await self.backup_handler.sync_database()
            self.backup_task = self.bot.loop.create_task(self.schedule_backup())
            logging.info("Database backup scheduler started")

    @commands.slash_command()
    @commands.is_owner()
    async def backup_now(self, inter):
        await inter.response.defer()
        success = await self.backup_handler.backup_database()
        if success:
            await inter.followup.send("Database backup completed successfully!")
        else:
            await inter.followup.send("Database backup failed. Check logs for details.")

    @commands.slash_command()
    @commands.is_owner()
    async def cleanup_backups(self, inter):
        await inter.response.defer()
        success = await self.backup_handler.cleanup_backups()
        if success:
            await inter.followup.send("Backup cleanup completed successfully!")
        else:
            await inter.followup.send("Backup cleanup failed. Check logs for details.")

    @commands.slash_command()
    @commands.is_owner()
    async def sync_database(self, inter):
        await inter.response.defer()
        success = await self.backup_handler.sync_database()
        if success:
            await inter.followup.send("Database sync completed successfully!")
        else:
            await inter.followup.send("Database sync failed. Check logs for details.")

def setup(bot):
    bot.add_cog(BackupCog(bot))
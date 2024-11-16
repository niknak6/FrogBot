# modules.auto_backup

from datetime import datetime, time, timedelta, timezone
from modules.utils.database import DATABASE_FILE
from dropbox.files import FolderMetadata
from dropbox.exceptions import ApiError
from core import Config, CONFIG_FILE
from typing import Optional, List
from disnake.ext import commands
from functools import lru_cache
import calendar
import asyncio
import logging
import dropbox
import hashlib
import os

class DatabaseBackup:
    def __init__(self, dropbox_token: str):
        self.dropbox_token = dropbox_token
        self.dbx = dropbox.Dropbox(
            self.dropbox_token,
            max_retries_on_error=3,
            max_retries_on_rate_limit=3
        )
        self._folder_cache = {}
        self._cache_timeout = 300

    @lru_cache(maxsize=32)
    async def _get_folder_listing(self, path: str) -> List[FolderMetadata]:
        try:
            result = self.dbx.files_list_folder(path)
            return sorted(
                [entry for entry in result.entries if entry.name.startswith('user_points_')],
                key=lambda entry: entry.name,
                reverse=True
            )
        except ApiError as e:
            logging.error(f"Failed to list folder {path}: {e}")
            return []

    async def backup_database(self) -> bool:
        try:
            chunk_size = 4 * 1024 * 1024
            with open(DATABASE_FILE, 'rb') as f:
                file_content = f.read(chunk_size)
            date_str = datetime.now().strftime('%Y-%m-%d')
            backup_path = f'/backups/user_points_{date_str}/user_points.db'
            if len(file_content) > chunk_size:
                session = self.dbx.files_upload_session_start(file_content)
                cursor = dropbox.files.UploadSessionCursor(
                    session.session_id,
                    offset=len(file_content)
                )
                commit = dropbox.files.CommitInfo(
                    path=backup_path,
                    mode=dropbox.files.WriteMode.overwrite
                )
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.dbx.files_upload_session_append_v2(chunk, cursor)
                    cursor.offset += len(chunk)
                self.dbx.files_upload_session_finish(b'', cursor, commit)
            else:
                self.dbx.files_upload(
                    file_content,
                    backup_path,
                    mode=dropbox.files.WriteMode.overwrite
                )
            self._get_folder_listing.cache_clear()
            return True
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

    async def sync_database(self) -> bool:
        try:
            folders = await self._get_folder_listing('/backups')
            if not folders:
                return await self.backup_database()
            latest_backup = None
            try:
                latest_backup = self.dbx.files_download(f"{folders[0].path_display}/user_points.db")
            except ApiError:
                return await self.backup_database()
            if not os.path.exists(DATABASE_FILE):
                with open(DATABASE_FILE, 'wb') as f:
                    f.write(latest_backup[1].content)
                return True
            with open(DATABASE_FILE, 'rb') as f:
                local_hash = hashlib.md5()
                cloud_hash = hashlib.md5()
                while True:
                    local_chunk = f.read(8192)
                    if not local_chunk:
                        break
                    local_hash.update(local_chunk)
                cloud_hash.update(latest_backup[1].content)
                if local_hash.hexdigest() == cloud_hash.hexdigest():
                    logging.info("Files are identical, no sync needed")
                    return True
            local_exists = os.path.exists(DATABASE_FILE)
            if not local_exists and latest_backup:
                with open(DATABASE_FILE, 'wb') as f:
                    f.write(latest_backup[1].content)
                logging.info("Downloaded database from cloud backup")
            elif local_exists and latest_backup:
                with open(DATABASE_FILE, 'rb') as f:
                    local_hash = hashlib.md5(f.read()).hexdigest()
                cloud_hash = hashlib.md5(latest_backup[1].content).hexdigest()
                logging.info(f"Local hash: {local_hash}")
                logging.info(f"Cloud hash: {cloud_hash}")
                if local_hash == cloud_hash:
                    logging.info("Files are identical (same hash), no sync needed")
                    return True
                local_time = datetime.fromtimestamp(os.path.getmtime(DATABASE_FILE), timezone.utc)
                cloud_time = latest_backup[0].server_modified.replace(tzinfo=timezone.utc)
                logging.info(f"Local last modified (UTC): {local_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                logging.info(f"Cloud last modified (UTC): {cloud_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                diff_seconds = abs((local_time - cloud_time).total_seconds())
                hours = int(diff_seconds // 3600)
                minutes = int((diff_seconds % 3600) // 60)
                seconds = int(diff_seconds % 60)
                logging.info(f"Time difference: {hours}h {minutes}m {seconds}s")
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
            logging.error(f"Sync failed: {e}")
            return False

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_task: Optional[asyncio.Task] = None
        self.config = Config(CONFIG_FILE)
        self.dropbox_token = self.config.read().get('DROPBOX_TOKEN')
        if not self.dropbox_token:
            logging.error("Dropbox token not found in config")
            return
        self.backup_handler = DatabaseBackup(self.dropbox_token)
        self._last_backup_time = None

    def cog_unload(self):
        if self.backup_task:
            self.backup_task.cancel()

    async def schedule_backup(self):
        while True:
            try:
                now = datetime.now()
                target_time = time(hour=0, minute=0)
                next_run = datetime.combine(now.date(), target_time)
                if now.time() >= target_time:
                    next_run += timedelta(days=1)
                sleep_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                if (self._last_backup_time and 
                    self._last_backup_time.date() == now.date()):
                    continue
                await self.backup_handler.backup_database()
                self._last_backup_time = now
                _, last_day = calendar.monthrange(now.year, now.month)
                if now.day == last_day:
                    await self.backup_handler.cleanup_backups()
            except Exception as e:
                logging.error(f"Backup schedule error: {e}")
                await asyncio.sleep(300)

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
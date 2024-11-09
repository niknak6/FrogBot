# core

from modules.utils.commons import is_admin_or_privileged
from concurrent.futures import ThreadPoolExecutor
from disnake.ext import commands
from pathlib import Path
import importlib.util
import subprocess
import logging
import asyncio
import disnake
import yaml
import sys
import os
from functools import wraps
from typing import Optional

CONFIG_FILE = 'config.yaml'

class Config:
    def __init__(self, filename='config.yaml'):
        self.filename = filename
        
    def read(self):
        config_path = Path(self.filename)
        return yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    
    def write(self, config):
        with open(self.filename, 'w') as file:
            yaml.safe_dump(config, file)
    
    def update(self, key, value):
        config = self.read()
        config[key] = value
        self.write(config)

config = Config(CONFIG_FILE)

class GitManager:
    @staticmethod
    async def run_command(*args) -> tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        except Exception as e:
            return -1, "", str(e)

    @staticmethod
    def get_version():
        try:
            version = config.read().get('version', 'unknown-version')
            branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
            return f"{version} {branch} {commit}"
        except subprocess.CalledProcessError:
            return "unknown-version"

class ModuleLoader:
    @staticmethod
    def load_single_module(client: commands.Bot, file_path: Path, name: str) -> None:
        try:
            spec = importlib.util.spec_from_file_location(name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Failed to load spec for {name}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                    client.add_cog(attr(client))
                    logging.info(f"Successfully loaded cog: {attr.__name__}")
        except Exception as e:
            logging.error(f"Error loading module {name}: {e}", exc_info=True)

    @staticmethod
    def load_all_modules(client: commands.Bot, cogs_dir: str = "modules") -> None:
        for root, _, files in os.walk(cogs_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    module_name = f"{Path(root).name}.{file[:-3]}"
                    ModuleLoader.load_single_module(client, file_path, module_name)

intents = disnake.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.guild_messages = True
intents.reactions = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False

client = commands.Bot(command_prefix='//||', intents=intents, command_sync_flags=command_sync_flags, test_guilds=[698205243103641711, 1137853399715549214])

async def run_subprocess(*args):
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
    except Exception as e:
        return -1, "", str(e)

async def run_git_command(*cmd):
    return await run_subprocess("git", *cmd)

async def restart_bot(ctx):
    try:
        message = await ctx.original_response()
        config.update('restart_message_id', str(message.id))
        config.update('restart_channel_id', str(ctx.channel.id))
        await ctx.edit_original_response(content="Restarting...")
        await asyncio.sleep(1)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'core.py')])
        await client.close()
    except Exception as e:
        await ctx.edit_original_response(content=f"Error restarting the bot: {e}")
        logging.error(f"Error restarting the bot: {e}")

async def update_bot(ctx, branch: str):
    git = GitManager()
    try:
        current_branch = await git.run_command("rev-parse", "--abbrev-ref", "HEAD")
        if current_branch[0] != 0:
            raise Exception("Failed to get current branch.")
            
        if current_branch[1] != branch:
            checkout_result = await git.run_command("checkout", branch)
            if checkout_result[0] != 0:
                raise Exception(f"Git checkout failed: {checkout_result[2]}")
                
        stash_result = await git.run_command("stash")
        if stash_result[0] != 0:
            raise Exception(f"Git stash failed: {stash_result[2]}")
            
        pull_result = await git.run_command("pull", "origin", branch)
        if pull_result[0] != 0:
            raise Exception(f"Git pull failed: {pull_result[2]}")
            
        await ctx.edit_original_response(content='Update process completed.')
    except Exception as e:
        await ctx.edit_original_response(content=f"Error updating the bot: {e}")
        logging.error(f"Error updating the bot: {e}")
        raise

@client.slash_command(description="Update and optionally restart the bot.")
@is_admin_or_privileged(user_id=126123710435295232)
async def update(ctx, branch: str = "beta", restart: bool = False, reload: bool = False):
    await ctx.response.defer(ephemeral=True)
    message = await ctx.original_response()
    try:
        await update_bot(ctx, branch)
        await message.edit(content="Update completed.")
        if reload:
            await asyncio.sleep(0.5)
            await message.edit(content="Reloading plugins...")
            await reload_plugins(ctx, message)
        if restart:
            await asyncio.sleep(0.5)
            await restart_bot(ctx)
        elif not restart:
            await message.edit(content="Update and reload process completed.")
    except Exception as e:
        await message.edit(content=f"Error during update process: {str(e)}")
        logging.error(f"Error during update process: {e}")

@client.slash_command(name="reload_plugins", description="Reload all plugins")
@is_admin_or_privileged(user_id=126123710435295232)
async def reload_plugins(ctx, message=None):
    if not message:
        await ctx.response.defer(ephemeral=True)
        message = await ctx.original_response()
    try:
        await message.edit(content="Reloading plugins...")
        existing_commands = client.all_commands.copy()
        for cog_name in list(client.cogs.keys()):
            client.remove_cog(cog_name)
        ModuleLoader.load_all_modules(client)
        for cmd_name, cmd in existing_commands.items():
            if cmd_name not in client.all_commands:
                client.add_application_command(cmd)
        await message.edit(content="All plugins have been reloaded successfully!")
    except Exception as e:
        logging.error(f"Error reloading plugins: {e}")
        await message.edit(content=f"An error occurred while reloading plugins: {str(e)}")

@client.slash_command(description="Restart the bot.")
@is_admin_or_privileged(user_id=126123710435295232)
async def restart(ctx):
    await ctx.response.defer()
    await restart_bot(ctx)

@client.slash_command(description="Shut down the bot.")
@is_admin_or_privileged(user_id=126123710435295232)
async def shutdown(ctx):
    class ShutdownView(disnake.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        @disnake.ui.button(label="Yes", style=disnake.ButtonStyle.danger)
        async def confirm(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
            await inter.response.edit_message(content="Shutting down...", view=None)
            logging.info("Bot shutdown initiated by user.")
            await client.close()
        @disnake.ui.button(label="No", style=disnake.ButtonStyle.secondary)
        async def cancel(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
            await inter.response.edit_message(content="Shutdown cancelled.", view=None)
    await ctx.response.send_message("Are you sure you want to shut down the bot?", view=ShutdownView(), ephemeral=True)

@client.event
async def on_ready():
    await client.change_presence(activity=disnake.Game(name=f"/help | {GitManager.get_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        restart_channel_id = config.read().get('restart_channel_id')
        restart_message_id = config.read().get('restart_message_id')
        if restart_channel_id and restart_message_id:
            channel = client.get_channel(int(restart_channel_id))
            if channel:
                try:
                    message = await channel.fetch_message(int(restart_message_id))
                    await message.edit(content="I'm back online!")
                except disnake.NotFound:
                    await channel.send("I'm back online!")
        config.update('restart_channel_id', '')
        config.update('restart_message_id', '')
    except Exception as e:
        logging.error(f"Error in on_ready: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ModuleLoader.load_all_modules(client)
    try:
        token = config.read().get('DISCORD_TOKEN')
        if not token:
            raise ValueError("Discord token not found in config")
        client.run(token)
    except Exception as e:
        logging.error(f"Failed to start bot: {e}", exc_info=True)

'''Kaofui was here uwu'''
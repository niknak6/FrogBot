# core

from modules.utils.database import initialize_database
from modules.utils.commons import is_admin_or_user
from concurrent.futures import ThreadPoolExecutor
from modules.roles import check_user_points
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

CONFIG_FILE = 'config.yaml'

def read_config():
    config_path = Path(CONFIG_FILE)
    return yaml.safe_load(config_path.read_text()) if config_path.exists() else {}

def write_config(config):
    with open(CONFIG_FILE, 'w') as file:
        yaml.safe_dump(config, file)

def update_config(key, value):
    config = read_config()
    config[key] = value
    write_config(config)

intents = disnake.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.guild_messages = True
intents.reactions = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = True

client = commands.Bot(command_prefix='//||', intents=intents, command_sync_flags=command_sync_flags, test_guilds=[698205243103641711])

def get_git_version():
    try:
        version = read_config().get('version', 'unknown-version')
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
        return f"{version} {branch} {commit}"
    except subprocess.CalledProcessError:
        return "unknown-version"

def load_module(file_path, name):
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        spec = importlib.util.spec_from_file_location(name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                client.add_cog(attr(client))
    except Exception as e:
        logging.error(f"Error loading module {name}: {e}")

def load_modules():
    cogs_dir = "modules"
    with ThreadPoolExecutor() as executor:
        for root, _, files in os.walk(cogs_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    executor.submit(load_module, file_path, f"{Path(root).name}.{file[:-3]}")

@client.slash_command(name="reload_plugins", description="Reload all plugins")
@is_admin_or_user()
async def reload_plugins(ctx):
    await ctx.response.defer(ephemeral=True)
    try:
        for cog in list(client.cogs):
            client.remove_cog(cog)
        load_modules()
        await ctx.edit_original_response(content="All plugins have been reloaded successfully!")
    except Exception as e:
        logging.error(f"Error reloading plugins: {e}")
        await ctx.edit_original_response(content=f"An error occurred while reloading plugins: {str(e)}")

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
        update_config('restart_message_id', str(message.id))
        update_config('restart_channel_id', str(ctx.channel.id))
        await ctx.edit_original_response(content="Restarting...")
        await asyncio.sleep(1)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'core.py')])
        await client.close()
    except Exception as e:
        await ctx.edit_original_response(content=f"Error restarting the bot: {e}")
        logging.error(f"Error restarting the bot: {e}")

async def update_bot(ctx, branch: str):
    try:
        current_branch = await run_git_command("rev-parse", "--abbrev-ref", "HEAD")
        if current_branch[0] != 0:
            raise Exception("Failed to get current branch.")
        if current_branch[1] != branch:
            checkout_result = await run_git_command("checkout", branch)
            if checkout_result[0] != 0:
                raise Exception(f"Git checkout failed: {checkout_result[2]}")
        stash_result = await run_git_command("stash")
        if stash_result[0] != 0:
            raise Exception(f"Git stash failed: {stash_result[2]}")
        pull_result = await run_git_command("pull", "origin", branch)
        if pull_result[0] != 0:
            raise Exception(f"Git pull failed: {pull_result[2]}")
        await ctx.edit_original_response(content='Update process completed.')
    except Exception as e:
        await ctx.edit_original_response(content=f"Error updating the bot: {e}")
        logging.error(f"Error updating the bot: {e}")
        raise

@client.slash_command(description="Update and optionally restart the bot.")
@is_admin_or_user()
async def update(ctx, branch: str = "beta", restart: bool = False, reload: bool = False):
    await ctx.response.defer()
    try:
        await update_bot(ctx, branch)
        if reload:
            await reload_plugins(ctx)
        if restart:
            await asyncio.sleep(0.5)
            await restart_bot(ctx)
    except Exception:
        pass

@client.slash_command(description="Restart the bot.")
@is_admin_or_user()
async def restart(ctx):
    await ctx.response.defer()
    await restart_bot(ctx)

@client.slash_command(description="Shut down the bot.")
@is_admin_or_user()
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
    await initialize_database()
    await check_user_points(client)
    await client.change_presence(activity=disnake.Game(name=f"/help | {get_git_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        config = read_config()
        restart_channel_id = config.get('restart_channel_id')
        restart_message_id = config.get('restart_message_id')
        if restart_channel_id and restart_message_id:
            channel = client.get_channel(int(restart_channel_id))
            if channel:
                try:
                    message = await channel.fetch_message(int(restart_message_id))
                    await message.edit(content="I'm back online!")
                except disnake.NotFound:
                    await channel.send("I'm back online!")
        update_config('restart_channel_id', '')
        update_config('restart_message_id', '')
    except Exception as e:
        logging.error(f"Error in on_ready: {e}")

if __name__ == "__main__":
    load_modules()
    try:
        client.run(read_config().get('DISCORD_TOKEN'))
    except Exception as e:
        logging.error(f"An error occurred while trying to run the Discord client: {e}")

'''Kaofui was here uwu'''
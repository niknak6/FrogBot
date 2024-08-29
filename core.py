# core.py

from modules.utils.database import initialize_database
from modules.utils.commons import is_admin_or_user
from concurrent.futures import ThreadPoolExecutor
from modules.roles import check_user_points
from disnake.ext import commands
from pathlib import Path
import importlib.util
import subprocess
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
command_sync_flags.sync_commands_debug = False

client = commands.Bot(command_prefix='//||', intents=intents, command_sync_flags=command_sync_flags)

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
                print(f"Imported cog: {attr.__name__}")
    except Exception as e:
        print(f"Error loading module {name}: {e}")

def load_modules():
    cogs_dir = "modules"
    with ThreadPoolExecutor() as executor:
        for root, _, files in os.walk(cogs_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    executor.submit(load_module, file_path, f"{Path(root).name}.{file[:-3]}")

async def run_subprocess(*args):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

async def restart_bot(ctx, message_id, channel_id):
    try:
        update_config('restart_message_id', str(message_id))
        update_config('restart_channel_id', str(channel_id))
        await asyncio.sleep(3)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'core.py')])
        await ctx.bot.close()
        sys.exit(0)
    except Exception as e:
        await ctx.edit_original_response(content=f"Error restarting the bot: {e}")

@client.slash_command(description="Restart the bot.")
@is_admin_or_user()
async def restart(ctx):
    try:
        await ctx.response.defer()
        message = await ctx.original_response()
        await restart_bot(ctx, message.id, ctx.channel.id)
    except Exception as e:
        await ctx.edit_original_response(content=f"An error occurred while trying to restart the bot: {e}")

@client.slash_command(description="Update the bot from the Git repository.")
@is_admin_or_user()
async def update(ctx, branch="beta", restart=False):
    try:
        await ctx.response.defer()
        returncode, current_branch, _ = await run_subprocess("git", "rev-parse", "--abbrev-ref", "HEAD")
        if returncode != 0:
            await ctx.edit_original_response(content="Failed to get current branch.")
            return
        if current_branch != branch:
            returncode, _, stderr = await run_subprocess("git", "checkout", branch)
            if returncode != 0:
                await ctx.edit_original_response(content=f"Git checkout failed: {stderr}")
                return
        returncode, _, stderr = await run_subprocess("git", "stash")
        if returncode != 0:
            await ctx.edit_original_response(content=f"Stashing changes failed: {stderr}")
            return
        returncode, _, stderr = await run_subprocess("git", "pull", "origin", branch)
        if returncode != 0:
            await ctx.edit_original_response(content=f"Git pull failed: {stderr}")
            return
        await ctx.edit_original_response(content='Update process completed.')
        if restart:
            await asyncio.sleep(0.5)
            message = await ctx.original_response()
            await restart_bot(ctx, message.id, ctx.channel.id)
    except Exception as e:
        await ctx.edit_original_response(content=f"Error updating the script: {e}")

@client.slash_command(description="Shut down the bot.")
@is_admin_or_user()
async def shutdown(ctx):
    buttons = [
        disnake.ui.Button(label="Yes", style=disnake.ButtonStyle.success, custom_id="shutdown_yes"),
        disnake.ui.Button(label="No", style=disnake.ButtonStyle.danger, custom_id="shutdown_no"),
    ]
    await ctx.response.send_message(
        "Are you sure you want to shut down the bot?",
        components=buttons,
        ephemeral=True
    )

@client.listen("on_button_click")
@is_admin_or_user()
async def shutdown_listener(inter):
    if inter.component.custom_id == "shutdown_yes":
        await inter.response.edit_message(content="Shutting down...", components=[])
        await inter.bot.close()
        sys.exit(0)
    elif inter.component.custom_id == "shutdown_no":
        await inter.response.edit_message(content="Bot shutdown canceled.", components=[])

def get_git_version():
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
        return f"v2.7 {branch} {commit}"
    except subprocess.CalledProcessError:
        return "unknown-version"

@client.event
async def on_ready():
    await initialize_database()
    await check_user_points(client)
    await client.change_presence(activity=disnake.Game(name=f"/help | {get_git_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        config = read_config()
        restart_channel_id = int(config.get('restart_channel_id', 0))
        restart_message_id = int(config.get('restart_message_id', 0))
        if restart_channel_id and restart_message_id:
            channel = client.get_channel(restart_channel_id)
            if channel:
                message = await channel.fetch_message(restart_message_id)
                if message:
                    await message.delete()
                    await channel.send("I'm back online!")
        update_config('restart_channel_id', '')
        update_config('restart_message_id', '')
    except Exception as e:
        print(f"Error sending restart message: {e}")

if __name__ == "__main__":
    load_modules()
    try:
        client.run(read_config().get('DISCORD_TOKEN'))
    except Exception as e:
        print(f"An error occurred while trying to run the Discord client: {e}")

'''Kaofui was here uwu'''
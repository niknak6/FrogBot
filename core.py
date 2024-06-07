# core.py

from modules.utils.database import initialize_database
from modules.utils.commons import is_admin_or_user
from concurrent.futures import ThreadPoolExecutor
from modules.roles import check_user_points
from disnake.ext import commands
from dotenv import load_dotenv
from pathlib import Path
import importlib.util
import subprocess
import asyncio
import disnake
import sys
import os
load_dotenv()

'''This Python code initializes a Discord bot with specific intents, and uses the ModuleLoader instance to dynamically load modules from the 'modules' directory into the bot.'''
intents = disnake.Intents(
    members=True,
    guilds=True,
    messages=True,
    message_content=True,
    guild_messages=True,
    reactions=True
)

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False
client = commands.Bot(command_prefix='//', intents=intents, command_sync_flags=command_sync_flags, test_guilds=[698205243103641711, 1137853399715549214])

'''Loads all the cogs from the 'modules' directory into the bot.'''
if __name__ == "__main__":
    def load_module(file_path, name):
        spec = importlib.util.spec_from_file_location(name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                client.add_cog(attr(client))
                print(f"Imported cog: {attr.__name__}")

    cogs_dir = "modules"
    with ThreadPoolExecutor() as executor:
        for item in os.listdir(cogs_dir):
            item_path = os.path.join(cogs_dir, item)
            if os.path.isdir(item_path):
                for file in os.listdir(item_path):
                    if file.endswith('.py'):
                        file_path = os.path.join(item_path, file)
                        executor.submit(load_module, file_path, f"{item}.{file[:-3]}")
            elif item.endswith('.py'):
                executor.submit(load_module, item_path, item[:-3])

'''This code defines commands for the bot to restart, shutdown, and update itself, including switching branches and pulling from a Git repository, with error handling for each operation.'''
root_dir = Path(__file__).resolve().parent
core_script = root_dir / 'core.py'

@client.slash_command(description = "Restart the bot.")
@is_admin_or_user()
async def restart(ctx):
    try:
        await restart_bot(ctx)
    except PermissionError:
        await ctx.send("Bot does not have permission to perform the restart operation.")
    except FileNotFoundError:
        await ctx.send("Could not find the core.py script.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to restart the bot: {e}")

@client.slash_command(description="Update the bot from the Git repository.")
@is_admin_or_user()
async def update(ctx: disnake.ApplicationCommandInteraction, branch="beta", restart=False):
    try:
        current_branch_proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--abbrev-ref", "HEAD", stdout=asyncio.subprocess.PIPE)
        stdout, _ = await current_branch_proc.communicate()
        current_branch = stdout.strip().decode()
        if current_branch != branch:
            switch_proc = await asyncio.create_subprocess_exec("git", "checkout", branch)
            await switch_proc.communicate()
        stash_proc = await asyncio.create_subprocess_exec("git", "stash", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stash_stdout, stash_stderr = await stash_proc.communicate()
        if stash_proc.returncode != 0:
            error_msg = stash_stderr.decode()
            await ctx.send(f'Stashing changes failed: {error_msg}')
            return
        pull_proc = await asyncio.create_subprocess_exec('git', 'pull', 'origin', branch, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        pull_stdout, pull_stderr = await pull_proc.communicate()
        if pull_proc.returncode != 0:
            error_msg = pull_stderr.decode()
            await ctx.send(f'Git pull failed: {error_msg}')
            return
        await pull_proc.wait()
        await ctx.send('Update process completed.')
        if restart:
            await asyncio.sleep(0.5)
            await restart_bot(ctx)
    except Exception as e:
        await ctx.send(f'Error updating the script: {e}')

async def restart_bot(ctx):
    global restart_channel_id
    try:
        await ctx.send("Restarting bot, please wait...")
        restart_channel_id = ctx.channel.id
        with open('restart_channel_id.txt', 'w') as f:
            f.write(str(restart_channel_id))
        for cmd in list(ctx.bot.all_commands.keys()):
            ctx.bot.remove_command(cmd)
        await asyncio.sleep(3)
        subprocess.Popen([sys.executable, str(core_script)])
        await asyncio.sleep(2)
        await ctx.bot.close()
        sys.exit(0)
    except Exception as e:
        await ctx.send(f"Error restarting the bot: {e}")

'''This code defines the core functionality of the bot, including event handlers for when the bot is ready, when a message is received, when a reaction is added, and when a command error occurs, as well as a method to process commands.'''
def get_git_version():
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
        return f"v2.5 {branch} {commit}"
    except subprocess.CalledProcessError:
        return "unknown-version"

@client.event
async def on_ready():
    global restart_channel_id
    await initialize_database()
    await check_user_points(client)
    await client.change_presence(activity=disnake.Game(name=f"/help | {get_git_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        with open('restart_channel_id.txt', 'r') as f:
            content = f.read().strip()
            if content:
                restart_channel_id = int(content)
            else:
                restart_channel_id = None
    except FileNotFoundError:
        restart_channel_id = None
    try:
        if restart_channel_id:
            channel = client.get_channel(restart_channel_id)
            if channel:
                await channel.send("I'm back online!")
            with open('restart_channel_id.txt', 'w') as f:
                f.write('')
    except Exception as e:
        print(f"Error sending restart message: {e}")

'''This code attempts to run the Discord client with a token retrieved from the environment variables.'''
try:
    client.run(os.getenv("DISCORD_TOKEN"))
except Exception as e:
    print(f"An error occurred while trying to run the Discord client: {e}")

'''Kaofui was here uwu'''
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

intents = disnake.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.guild_messages = True
intents.reactions = True

command_sync_flags = commands.CommandSyncFlags.default()
command_sync_flags.sync_commands_debug = False

client = commands.Bot(command_prefix='/', intents=intents, command_sync_flags=command_sync_flags)

def load_module(file_path, name):
    try:
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

@client.slash_command(description="Restart the bot.")
@is_admin_or_user()
async def restart(ctx):
    try:
        await restart_bot(ctx)
    except Exception as e:
        await ctx.send(f"An error occurred while trying to restart the bot: {e}")

@client.slash_command(description="Update the bot from the Git repository.")
@is_admin_or_user()
async def update(ctx, branch="beta", restart=False):
    try:
        current_branch_proc = await asyncio.create_subprocess_exec("git", "rev-parse", "--abbrev-ref", "HEAD", stdout=asyncio.subprocess.PIPE)
        stdout, _ = await current_branch_proc.communicate()
        current_branch = stdout.strip().decode()
        if current_branch != branch:
            await asyncio.create_subprocess_exec("git", "checkout", branch)

        stash_proc = await asyncio.create_subprocess_exec("git", "stash", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stash_stdout, stash_stderr = await stash_proc.communicate()
        if stash_proc.returncode != 0:
            await ctx.send(f'Stashing changes failed: {stash_stderr.decode()}')
            return

        pull_proc = await asyncio.create_subprocess_exec('git', 'pull', 'origin', branch, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        pull_stdout, pull_stderr = await pull_proc.communicate()
        if pull_proc.returncode != 0:
            await ctx.send(f'Git pull failed: {pull_stderr.decode()}')
            return

        await ctx.send('Update process completed.')
        if restart:
            await asyncio.sleep(0.5)
            await restart_bot(ctx)
    except Exception as e:
        await ctx.send(f'Error updating the script: {e}')

@client.slash_command(description="Shut down the bot.")
@is_admin_or_user()
async def shutdown(ctx):
    await ctx.response.send_message(
        "Are you sure you want to shut down the bot?",
        components=[
            disnake.ui.Button(label="Yes", style=disnake.ButtonStyle.success, custom_id="shutdown_yes"),
            disnake.ui.Button(label="No", style=disnake.ButtonStyle.danger, custom_id="shutdown_no"),
        ],
        ephemeral=True
    )

@client.listen("on_button_click")
@is_admin_or_user()
async def shutdown_listener(inter):
    if inter.component.custom_id == "shutdown_yes":
        await inter.response.send_message("Shutting down...", ephemeral=True)
        await inter.bot.close()
    elif inter.component.custom_id == "shutdown_no":
        await inter.response.send_message("Bot shutdown canceled.", ephemeral=True)

async def restart_bot(ctx):
    try:
        await ctx.send("Restarting bot, please wait...")
        with open('restart_channel_id.txt', 'w') as f:
            f.write(str(ctx.channel.id))
        await asyncio.sleep(3)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'core.py')])
        await ctx.bot.close()
        sys.exit(0)
    except Exception as e:
        await ctx.send(f"Error restarting the bot: {e}")

def get_git_version():
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:7]
        return f"v2.6 {branch} {commit}"
    except subprocess.CalledProcessError:
        return "unknown-version"

@client.event
async def on_ready():
    await initialize_database()
    await check_user_points(client)
    await client.change_presence(activity=disnake.Game(name=f"/help | {get_git_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        with open('restart_channel_id.txt', 'r') as f:
            restart_channel_id = int(f.read().strip() or 0)
        if restart_channel_id:
            channel = client.get_channel(restart_channel_id)
            if channel:
                await channel.send("I'm back online!")
        with open('restart_channel_id.txt', 'w') as f:
            f.write('')
    except Exception as e:
        print(f"Error sending restart message: {e}")

if __name__ == "__main__":
    load_modules()

try:
    client.run(os.getenv("DISCORD_TOKEN"))
except Exception as e:
    print(f"An error occurred while trying to run the Discord client: {e}")

'''Kaofui was here uwu'''

# core

from typing import Optional, Tuple, Any
from disnake.ext import commands
from pathlib import Path
import importlib.util
import subprocess
import logging
import asyncio
import disnake
import yaml
import sys

CONFIG = {
    'VERSION': 'v2.9',
    'CONFIG_FILE': Path('config.yaml'),
    'COGS_DIR': Path("modules"),
    'TEST_GUILDS': [698205243103641711, 1137853399715549214],
    'ADMIN_USER_ID': 126123710435295232,
}

class Config:
    DEFAULT_FIELDS = {
        'DISCORD_TOKEN': ('Enter your Discord bot token: ', True),
        'DATABASE_FILE': ('Enter your database filename (optional, with .db extension): ', False),
        'OPENAI_API_KEY': ('Enter your OpenAI API key (optional): ', False)
    }

    def __init__(self, filename: Path = CONFIG['CONFIG_FILE']):
        self._config_path = Path(filename)
        
    def read(self) -> dict[str, Any]: 
        return yaml.safe_load(self._config_path.read_text()) if self._config_path.exists() else {}
    
    def write(self, config: dict[str, Any]): self._config_path.write_text(yaml.safe_dump(config))
    def update(self, key: str, value: Any): self.write({**self.read(), key: value})

    def setup_config(self):
        if self._config_path.exists(): return
        config_data = {'modules': {}}
        for field, (prompt, required) in self.DEFAULT_FIELDS.items():
            if value := input(f"\n{prompt}" if not required else prompt).strip():
                config_data[field] = f"{value}.db" if field == 'DATABASE_FILE' and not value.endswith('.db') else value
            elif required:
                print(f"{field} is required. Please enter a value.")
                return self.setup_config()
        base_dir = Path(__file__).parent
        for dir_path in ["modules", "utils", "logs"]:
            (base_dir / dir_path).mkdir(exist_ok=True)
        (base_dir / "modules" / "__init__.py").touch()
        self.write(config_data)

config = Config()

class GitManager:
    @staticmethod
    async def run_cmd(*args) -> Tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        except Exception as e:
            return -1, "", str(e)

    @staticmethod
    def get_version() -> str:
        try:
            branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()[:7]
            return f"{CONFIG['VERSION']} {branch} {commit}"
        except subprocess.CalledProcessError:
            return f"{CONFIG['VERSION']}-unknown"

    @staticmethod
    async def get_branches() -> list[str]:
        try:
            code, stdout, stderr = await GitManager.run_cmd("git", "branch", "-r")
            if code != 0:
                raise Exception(f"Failed to get branches: {stderr}")
            branches = [b.strip().replace('origin/', '') for b in stdout.split('\n') if 'HEAD' not in b]
            return sorted(branches)
        except Exception as e:
            logging.error(f"Error getting git branches: {e}")
            return ["main", "beta"]

class BotManager:
    def __init__(self, client: commands.Bot):
        self.client = client

    async def restart_bot(self, inter: disnake.MessageInteraction) -> None:
        try:
            config.update('restart_channel_id', str(inter.channel.id))
            config.update('restart_message_id', str(inter.message.id))
            await inter.response.edit_message(content="Restarting...")
            subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
            await self.client.close()
        except Exception as e:
            resp = inter.response.send_message if not inter.response.is_done() else inter.edit_original_message
            await resp(content=f"Error restarting: {e}", ephemeral=True)
            logging.error(f"Restart error: {e}")

    async def update_bot(self, ctx: commands.Context, branch: str) -> None:
        try:
            for cmd in [
                ["rev-parse", "--abbrev-ref", "HEAD"],
                ["checkout", branch] if (await GitManager.run_cmd("git", "rev-parse", "--abbrev-ref", "HEAD"))[1] != branch else None,
                ["pull", "origin", branch]
            ]:
                if cmd and (code := (await GitManager.run_cmd(*cmd))[0]) != 0:
                    raise Exception(f"Git command failed: {cmd[0]}")
            await ctx.edit_original_response(content='Update complete.')
        except Exception as e:
            await ctx.edit_original_response(content=f"Update error: {e}")
            logging.error(f"Update error: {e}")
            raise

    async def handle_restart_message(self):
        try:
            config_data = config.read()
            if (channel_id := config_data.get('restart_channel_id')) and (message_id := config_data.get('restart_message_id')):
                if channel := self.client.get_channel(int(channel_id)):
                    try: 
                        message = await channel.fetch_message(int(message_id))
                        await message.edit(content="I'm back online!")
                    except disnake.NotFound: 
                        await channel.send("I'm back online!")
            config.update('restart_channel_id', '')
            config.update('restart_message_id', '')
        except Exception as e: 
            logging.error(f"Error handling restart message: {e}", exc_info=True)

def is_admin_or_privileged(user_id: Optional[int] = None, rank_id: Optional[int] = None):
    async def predicate(ctx):
        return (
            ctx.author.guild_permissions.administrator or
            (user_id and ctx.author.id == user_id) or
            (rank_id and any(role.id == rank_id for role in ctx.author.roles))
        )
    return commands.check(predicate)

intents = disnake.Intents.default()
intents.members = intents.messages = intents.message_content = intents.guild_messages = intents.reactions = True

client = commands.Bot(
    command_prefix='//||',
    intents=intents,
    command_sync_flags=commands.CommandSyncFlags.default(),
    test_guilds=CONFIG['TEST_GUILDS']
)
bot_manager = BotManager(client)

class ModuleLoader:
    @staticmethod
    def get_available_modules(cogs_dir: Path = CONFIG['COGS_DIR']) -> dict[str, bool]:
        modules = {}
        cogs_path = Path(cogs_dir)
        if not cogs_path.exists():
            cogs_path.mkdir(parents=True)
            (cogs_path / "__init__.py").touch()
        for file_path in cogs_path.rglob("*.py"):
            if file_path.stem == "__init__": continue
            relative_parts = file_path.relative_to(cogs_path).parts
            module_name = (
                f"modules.{'.'.join(relative_parts[:-1])}.{file_path.stem}" 
                if len(relative_parts) > 1 
                else f"modules.{file_path.stem}"
            )
            modules[module_name] = True
            logging.info(f"Found installed module: {module_name}")
        return modules

    @staticmethod
    def load_single_module(client: commands.Bot, file_path: Path, name: str) -> None:
        if not config.read().get('modules', {}).get(name, True):
            logging.info(f"Skipping disabled module: {name}")
            return
        try:
            spec = importlib.util.spec_from_file_location(name, file_path)
            if not spec or not spec.loader:
                raise ImportError(f"Failed to load spec for {name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                    client.add_cog(attr(client))
                    logging.info(f"Loaded cog: {attr.__name__}")
        except Exception as e:
            logging.error(f"Error loading module {name}: {e}", exc_info=True)

    @classmethod
    def load_all_modules(cls, client: commands.Bot, cogs_dir: Path = CONFIG['COGS_DIR']) -> None:
        current_modules = cls.get_available_modules(cogs_dir)
        config_data = config.read()
        if 'modules' not in config_data:
            config_data['modules'] = current_modules
            config.write(config_data)
        for file_path in Path(cogs_dir).rglob("*.py"):
            if file_path.stem == "__init__": continue
            module_name = f"{file_path.parent.name}.{file_path.stem}"
            if config_data['modules'].get(module_name, True):
                cls.load_single_module(client, file_path, module_name)

class BranchSelect(disnake.ui.Select):
    def __init__(self, branches: list[str]):
        options = [
            disnake.SelectOption(
                label=branch, 
                description=f"Update to {branch} branch",
                default=(branch == "beta")
            )
            for branch in branches
        ]
        super().__init__(
            placeholder="Select branch to update to...",
            options=options,
            custom_id="branch_select_menu"
        )

class UpdateView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(disnake.ui.Button(
            label="Back",
            style=disnake.ButtonStyle.danger,
            custom_id="update_view_back"
        ))
        self.add_item(disnake.ui.Button(
            label="Update & Restart",
            style=disnake.ButtonStyle.success,
            custom_id="update_and_restart",
            emoji="🔄"
        ))

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        try:
            if inter.component.custom_id == "update_view_back":
                await inter.response.edit_message(
                    content=f"🤖 {client.user.display_name} Control Panel",
                    view=ControlPanelView()
                )
            elif inter.component.custom_id == "update_and_restart":
                await inter.response.edit_message(content="Updating and restarting...", view=None)
                await bot_manager.update_bot(inter, inter.message.components[0].children[0].values[0])
                await bot_manager.restart_bot(inter)
            elif inter.component.type == disnake.ComponentType.select:
                await inter.response.edit_message(content="Updating...", view=None)
                await bot_manager.update_bot(inter, inter.values[0])
                await inter.edit_original_message(
                    content="Update complete! Use restart if needed.",
                    view=None
                )
            return True
        except Exception as e:
            if not inter.response.is_done():
                await inter.response.edit_message(content=f"An error occurred: {str(e)}")
            logging.error(f"Error in UpdateView interaction: {e}")
            return False

class ControlPanelView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        BUTTONS = [
            ("Update Bot", disnake.ButtonStyle.success, "panel_update", "⬆️"),
            ("Restart Bot", disnake.ButtonStyle.secondary, "panel_restart", "🔄"),
            ("Shutdown", disnake.ButtonStyle.danger, "panel_shutdown", "⛔")
        ]
        for label, style, cid, emoji in BUTTONS:
            self.add_item(disnake.ui.Button(
                label=label,
                style=style,
                custom_id=cid,
                emoji=emoji
            ))

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        try:
            handlers = {
                "panel_update": self.show_update_options,
                "panel_restart": self.confirm_restart,
                "panel_shutdown": self.confirm_shutdown
            }
            cid = inter.component.custom_id
            if handler := handlers.get(cid):
                await handler(inter)
            return True
        except Exception as e:
            if not inter.response.is_done():
                await inter.response.edit_message(content=f"An error occurred: {str(e)}")
            logging.error(f"Error in ControlPanelView interaction: {e}")
            return False

    async def show_update_options(self, inter: disnake.MessageInteraction):
        branches = await GitManager.get_branches()
        update_view = UpdateView()
        update_view.add_item(BranchSelect(branches))
        await inter.response.edit_message(content="⬆️ Update Options", view=update_view)

    async def confirm_restart(self, inter: disnake.MessageInteraction):
        class ConfirmView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(disnake.ui.Button(label="Confirm Restart", style=disnake.ButtonStyle.danger, custom_id="confirm_restart_yes", emoji="✅"))
                self.add_item(disnake.ui.Button(label="Cancel", style=disnake.ButtonStyle.secondary, custom_id="confirm_restart_no", emoji="❌"))

            async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
                try:
                    if inter.component.custom_id == "confirm_restart_yes":
                        await bot_manager.restart_bot(inter)
                    else:
                        await inter.response.edit_message(content=f"🤖 {client.user.display_name} Control Panel", view=ControlPanelView())
                    return True
                except Exception as e:
                    if not inter.response.is_done():
                        await inter.response.send_message(content=f"An error occurred: {str(e)}", ephemeral=True)
                    logging.error(f"Error in ConfirmView interaction: {e}")
                    return False
        await inter.response.edit_message(content=f"⚠️ Are you sure you want to restart {client.user.display_name}?", view=ConfirmView())

    async def confirm_shutdown(self, inter: disnake.MessageInteraction):
        class ConfirmView(disnake.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(disnake.ui.Button(label="Confirm Shutdown", style=disnake.ButtonStyle.danger, custom_id="confirm_shutdown_yes", emoji="✅"))
                self.add_item(disnake.ui.Button(label="Cancel", style=disnake.ButtonStyle.secondary, custom_id="confirm_shutdown_no", emoji="❌"))

            async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
                if inter.component.custom_id == "confirm_shutdown_yes":
                    await inter.response.edit_message(content="Shutting down...", view=None)
                    await client.close()
                else:
                    await inter.response.edit_message(content=f"🤖 {client.user.display_name} Control Panel", view=ControlPanelView())
                return True
        await inter.response.edit_message(content=f"⚠️ Are you sure you want to shut down {client.user.display_name}?", view=ConfirmView())

@client.slash_command(name="control_panel", description="Open the bot's control panel")
@is_admin_or_privileged(user_id=CONFIG['ADMIN_USER_ID'])
async def control_panel(ctx): 
    await ctx.send(f"🤖 {client.user.display_name} Control Panel", view=ControlPanelView(), ephemeral=True)

@client.event
async def on_ready():
    await client.change_presence(activity=disnake.Game(name=f"/help | {GitManager.get_version()}"))
    print(f'Logged in as {client.user.name}')
    try:
        config_data = config.read()
        if (channel_id := config_data.get('restart_channel_id')) and (message_id := config_data.get('restart_message_id')):
            if channel := client.get_channel(int(channel_id)):
                try: message = await channel.fetch_message(int(message_id)); await message.edit(content="I'm back online!")
                except disnake.NotFound: await channel.send("I'm back online!")
        config.update('restart_channel_id', ''); config.update('restart_message_id', '')
    except Exception as e: logging.error(f"Error in on_ready: {e}", exc_info=True)

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler('logs/bot.log'), logging.StreamHandler()])
    try:
        config.setup_config()
        if not (token := config.read().get('DISCORD_TOKEN')): raise ValueError("Discord token not found in config")
        if db_file := config.read().get('DATABASE_FILE'): Path(db_file).touch(exist_ok=True); logging.info(f"Database file ready: {db_file}")
        ModuleLoader.load_all_modules(client)
        client.run(token)
    except KeyboardInterrupt: print("\nSetup cancelled. Please run the bot again to complete setup."); sys.exit(1)
    except Exception as e: logging.error(f"Failed to start bot: {e}", exc_info=True); sys.exit(1)

if __name__ == "__main__": main()

'''Kaofui was here uwu'''

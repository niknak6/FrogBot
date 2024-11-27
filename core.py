# core

from typing import Optional, Tuple, Any
from disnake.ext import commands
from pathlib import Path
import importlib.util
import subprocess
import logging
import asyncio
import disnake
import aiohttp
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
        'DATABASE_FILE': ('Enter your database filename (optional): ', False),
        'OPENAI_API_KEY': ('Enter your OpenAI API key (optional): ', False),
        'GITHUB_TOKEN': ('Enter your GitHub personal access token (optional): ', False)
    }

    def __init__(self, filename: Path = CONFIG['CONFIG_FILE']):
        self._config_path = Path(filename)
        
    def read(self) -> dict[str, Any]: 
        return yaml.safe_load(self._config_path.read_text()) if self._config_path.exists() else {}
    
    def write(self, config: dict[str, Any]) -> None:
        self._config_path.write_text(yaml.safe_dump(config))
    def update(self, key: str, value: Any): self.write({**self.read(), key: value})

    def setup_config(self):
        if self._config_path.exists(): return
        config_data = {}
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
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode, stdout.decode().strip(), stderr.decode().strip()
        except Exception as e:
            return -1, "", str(e)

    @staticmethod
    async def get_current_branch() -> str:
        try:
            code, stdout, stderr = await GitManager.run_cmd("git", "rev-parse", "--abbrev-ref", "HEAD")
            if code != 0:
                logging.warning(f"Failed to get current branch: {stderr}")
                return "beta"
            return stdout.strip() or "beta"
        except Exception as e:
            logging.error(f"Error getting current branch: {e}")
            return "beta"

    @staticmethod
    async def get_branches() -> list[str]:
        try:
            code, stdout, stderr = await GitManager.run_cmd("git", "branch", "-r")
            if code != 0:
                logging.warning(f"Failed to get branches: {stderr}")
                return ["beta"]
            branches = [b.strip().replace('origin/', '') for b in stdout.split('\n') if 'HEAD' not in b]
            return sorted(branches) if branches else ["beta"]
        except Exception as e:
            logging.error(f"Error getting git branches: {e}")
            return ["beta"]

    @staticmethod
    async def get_remote_modules() -> dict[str, dict]:
        try:
            headers = {}
            if github_token := config.read().get('GITHUB_TOKEN'):
                headers['Authorization'] = f'token {github_token}'
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.github.com/repos/idontneedonetho/FrogBot/contents/modules',
                    headers=headers
                ) as response:
                    if response.status != 200:
                        raise Exception(f"GitHub API error: {response.status}")
                    contents = await response.json()
                modules = {'root': {}}
                for item in contents:
                    if item['type'] == 'file' and item['name'].endswith('.py') and item['name'] != '__init__.py':
                        modules['root'][item['name']] = item['download_url']
                    elif item['type'] == 'dir':
                        category = item['name']
                        modules[category] = {}
                        async with session.get(item['url'], headers=headers) as response:
                            if response.status == 200:
                                category_contents = await response.json()
                                for file in category_contents:
                                    if file['name'].endswith('.py') and file['name'] != '__init__.py':
                                        modules[category][file['name']] = file['download_url']
            return modules
        except Exception as e:
            logging.error(f"Error fetching remote modules: {e}")
            return {}

class BotManager:
    def __init__(self, client: commands.Bot):
        self.client = client

    async def restart_bot(self, inter: disnake.MessageInteraction) -> None:
        try:
            config.update('restart_channel_id', str(inter.channel.id))
            if inter.message:
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
            current_modules = ModuleLoader.get_available_modules()
            current_branch = await GitManager.get_current_branch()
            
            commands = [
                ["git", "fetch", "origin"],  # First fetch updates
                ["git", "checkout", branch] if current_branch != branch else None,
                ["git", "pull", "origin", branch]
            ]
            
            for cmd in commands:
                if cmd:  # Skip None commands
                    code, stdout, stderr = await GitManager.run_cmd(*cmd)
                    if code != 0:
                        raise Exception(f"Git command failed: {' '.join(cmd)}, Error: {stderr}")
            
            remote_modules = await GitManager.get_remote_modules()
            for category, modules in remote_modules.items():
                for module_name, url in modules.items():
                    module_id = (
                        f"modules.{module_name[:-3]}" 
                        if category == "root" 
                        else f"modules.{category}.{module_name[:-3]}"
                    )
                    if module_id in current_modules:
                        await ModuleLoader.download_module(url, category, module_name)
            
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
            logging.error(f"Error handling restart message: {e}")

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
            relative_parts = file_path.relative_to(cogs_dir).parts
            module_name = (
                f"modules.{'.'.join(relative_parts[:-1])}.{file_path.stem}" 
                if len(relative_parts) > 1 
                else f"modules.{file_path.stem}"
            )
            modules[module_name] = True
        return modules

    @staticmethod
    def load_single_module(client: commands.Bot, file_path: Path, name: str) -> None:
        try:
            spec = importlib.util.spec_from_file_location(name, file_path)
            if not spec or not spec.loader:
                raise ImportError(f"Failed to load spec for {name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                del sys.modules[name]
                raise e
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, commands.Cog) and attr is not commands.Cog:
                    client.add_cog(attr(client))
        except Exception as e:
            if name in sys.modules:
                del sys.modules[name]
            logging.error(f"Error loading module {name}: {e}", exc_info=True)

    @classmethod
    def load_all_modules(cls, client: commands.Bot, cogs_dir: Path = CONFIG['COGS_DIR']) -> None:
        for file_path in Path(cogs_dir).rglob("*.py"):
            if file_path.stem == "__init__": continue
            relative_parts = file_path.relative_to(cogs_dir).parts
            module_name = (
                f"modules.{'.'.join(relative_parts[:-1])}.{file_path.stem}" 
                if len(relative_parts) > 1 
                else f"modules.{file_path.stem}"
            )
            cls.load_single_module(client, file_path, module_name)

    @staticmethod
    async def download_module(url: str, category: str, filename: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        if category == "root":
                            module_path = CONFIG['COGS_DIR'] / filename
                        else:
                            module_dir = CONFIG['COGS_DIR'] / category
                            module_dir.mkdir(exist_ok=True)
                            (module_dir / '__init__.py').touch()
                            module_path = module_dir / filename
                        module_path.write_text(await response.text(), encoding='utf-8')
                        return True
            return False
        except Exception as e:
            logging.error(f"Error downloading module: {e}")
            return False

    @staticmethod
    def uninstall_module(category: str, filename: str) -> bool:
        try:
            if category == "root":
                module_path = CONFIG['COGS_DIR'] / filename
            else:
                module_path = CONFIG['COGS_DIR'] / category / filename
            if module_path.exists():
                module_path.unlink()
            return True
        except Exception as e:
            logging.error(f"Error uninstalling module: {e}")
            return False

class ModuleCategoryView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(disnake.ui.Button(
            label="Back",
            style=disnake.ButtonStyle.danger,
            custom_id="module_category_back"
        ))

    async def add_category_buttons(self, categories: list[str]):
        for category in categories:
            self.add_item(disnake.ui.Button(
                label=category.title(),
                style=disnake.ButtonStyle.primary,
                custom_id=f"category_{category}"
            ))

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        try:
            if inter.component.custom_id == "module_category_back":
                await inter.response.edit_message(
                    content=f"🤖 {client.user.display_name} Control Panel",
                    view=ControlPanelView()
                )
            elif inter.component.custom_id.startswith("category_"):
                category = inter.component.custom_id.replace("category_", "")
                module_view = ModuleListView(category)
                await module_view.refresh_module_buttons(inter)
            return True
        except Exception as e:
            if not inter.response.is_done():
                await inter.response.send_message(content=f"An error occurred: {str(e)}", ephemeral=True)
            logging.error(f"Error in ModuleCategoryView interaction: {e}")
            return False

class ModuleListView(disnake.ui.View):
    def __init__(self, category: str):
        super().__init__(timeout=300)
        self.category = category
        back_button = disnake.ui.Button(
            label="Back",
            style=disnake.ButtonStyle.danger,
            custom_id="module_list_back",
            row=4
        )
        apply_button = disnake.ui.Button(
            label="Apply Changes",
            style=disnake.ButtonStyle.success,
            custom_id="apply_modules",
            emoji="💾",
            row=4
        )
        self.add_item(back_button)
        self.add_item(apply_button)

    async def refresh_module_buttons(self, inter: disnake.MessageInteraction):
        remote_modules = await GitManager.get_remote_modules()
        current_modules = ModuleLoader.get_available_modules()
        category_modules = remote_modules.get(self.category, {})
        current_row = 0
        buttons_in_row = 0
        max_buttons_per_row = 5
        for module_name in category_modules:
            module_id = (
                f"modules.{module_name[:-3]}" 
                if self.category == "root" 
                else f"modules.{self.category}.{module_name[:-3]}"
            )
            is_installed = module_id in current_modules
            if buttons_in_row >= max_buttons_per_row:
                current_row += 1
                buttons_in_row = 0
            self.add_item(disnake.ui.Button(
                label=module_name,
                style=disnake.ButtonStyle.green if is_installed else disnake.ButtonStyle.gray,
                custom_id=f"toggle_module_{module_name}",
                emoji="✅" if is_installed else "❌",
                row=current_row
            ))
            buttons_in_row += 1
        if not inter.response.is_done():
            await inter.response.edit_message(
                content=f"🧩 Module Manager - {self.category.title()}",
                view=self
            )
        else:
            await inter.edit_original_message(
                content=f"🧩 Module Manager - {self.category.title()}",
                view=self
            )

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        try:
            if inter.component.custom_id == "module_list_back":
                category_view = ModuleCategoryView()
                await category_view.add_category_buttons(
                    (await GitManager.get_remote_modules()).keys()
                )
                await inter.response.edit_message(
                    content="🧩 Module Manager",
                    view=category_view
                )
            elif inter.component.custom_id == "apply_modules":
                await inter.response.edit_message(
                    content="Applying changes...",
                    view=None
                )
                selected_modules = [
                    btn.label for btn in self.children 
                    if isinstance(btn, disnake.ui.Button) 
                    and btn.style == disnake.ButtonStyle.green
                    and btn.custom_id.startswith("toggle_module_")
                ]
                remote_modules = await GitManager.get_remote_modules()
                if not remote_modules:
                    remote_modules = {self.category: {}}
                current_modules = ModuleLoader.get_available_modules()
                for module_name, url in remote_modules.get(self.category, {}).items():
                    module_id = (
                        f"modules.{module_name[:-3]}" 
                        if self.category == "root" 
                        else f"modules.{self.category}.{module_name[:-3]}"
                    )
                    is_selected = module_name in selected_modules
                    is_installed = module_id in current_modules
                    if is_selected and not is_installed and url:
                        await ModuleLoader.download_module(url, self.category, module_name)
                    elif not is_selected and is_installed:
                        ModuleLoader.uninstall_module(self.category, module_name)
                for cog in list(client.cogs.keys()):
                    client.remove_cog(cog)
                ModuleLoader.load_all_modules(client)
                await inter.edit_original_message(
                    content="Modules updated successfully!",
                    view=None
                )
            elif inter.component.custom_id.startswith("toggle_module_"):
                button = [b for b in self.children if b.custom_id == inter.component.custom_id][0]
                button.style = (
                    disnake.ButtonStyle.gray 
                    if button.style == disnake.ButtonStyle.green 
                    else disnake.ButtonStyle.green
                )
                button.emoji = "❌" if button.style == disnake.ButtonStyle.gray else "✅"
                await inter.response.edit_message(view=self)
            return True
        except Exception as e:
            if not inter.response.is_done():
                await inter.response.send_message(content=f"An error occurred: {str(e)}", ephemeral=True)
            logging.error(f"Error in ModuleListView interaction: {e}")
            return False

class BranchSelect(disnake.ui.Select):
    def __init__(self, branches: list[str]):
        options = [
            disnake.SelectOption(
                label=branch,
                default=(branch == "beta")
            ) 
            for branch in branches
        ]
        super().__init__(
            placeholder="Select branch",
            options=options,
            min_values=1,
            max_values=1
        )

class UpdateView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.branch = "beta"
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
                await bot_manager.update_bot(inter, self.branch)
                await bot_manager.restart_bot(inter)
            elif inter.component.type == disnake.ComponentType.select:
                self.branch = inter.values[0]
                await inter.response.edit_message(
                    content=f"Selected branch: {self.branch}",
                    view=self
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
            ("Modules", disnake.ButtonStyle.primary, "panel_modules", "🧩"),
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
                "panel_modules": self.show_module_options,
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
        update_view = UpdateView()
        branches = await GitManager.get_branches()
        if branches:  # Only add select if we got branches
            update_view.add_item(BranchSelect(branches))
        await inter.response.edit_message(
            content="⬆️ Update Options (default: beta)",
            view=update_view
        )

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

    async def show_module_options(self, inter: disnake.MessageInteraction):
        try:
            remote_modules = await GitManager.get_remote_modules()
            if not remote_modules:
                if not inter.response.is_done():
                    await inter.response.edit_message(
                        content="Failed to fetch modules from GitHub",
                        view=self
                    )
                return
            category_view = ModuleCategoryView()
            await category_view.add_category_buttons(remote_modules.keys())
            if not inter.response.is_done():
                await inter.response.edit_message(
                    content="🧩 Module Manager",
                    view=category_view
                )
            else:
                await inter.edit_original_message(
                    content="🧩 Module Manager",
                    view=category_view
                )
        except Exception as e:
            if not inter.response.is_done():
                await inter.response.send_message(
                    content=f"An error occurred: {str(e)}",
                    ephemeral=True
                )
            logging.error(f"Error in show_module_options: {e}")

@client.slash_command(name="control_panel", description="Open the bot's control panel")
@is_admin_or_privileged(user_id=CONFIG['ADMIN_USER_ID'])
async def control_panel(ctx): 
    await ctx.send(f"🤖 {client.user.display_name} Control Panel", view=ControlPanelView(), ephemeral=True)

@client.event
async def on_ready():
    await client.change_presence(activity=disnake.Game(name=f"/help | {GitManager.get_version()}"))
    print(f'Logged in as {client.user.name}')
    await bot_manager.handle_restart_message()

def main():
    try:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        config.setup_config()
        if not (token := config.read().get('DISCORD_TOKEN')): 
            raise ValueError("Discord token not found in config")
        if db_file := config.read().get('DATABASE_FILE'): 
            Path(db_file).touch(exist_ok=True)
        ModuleLoader.load_all_modules(client)
        client.run(token)
    except KeyboardInterrupt: 
        print("\nSetup cancelled. Please run the bot again to complete setup.")
        sys.exit(1)
    except Exception as e: 
        print(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__": main()
from disnake import TextInputStyle, ui, ApplicationCommandInteraction, NotFound, Forbidden, Message, Embed, Color
from core import is_admin_or_privileged
from disnake.ext import commands
import asyncio

CREATE_TIMEOUT = 1200
EDIT_TIMEOUT = 600

class WhiteboardCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.privileged_role_id = 1198482895342411846

    @commands.slash_command()
    async def whiteboard(self, inter: ApplicationCommandInteraction):
        """Whiteboard command group"""
        pass

    @whiteboard.sub_command(name="create")
    @is_admin_or_privileged(rank_id=1198482895342411846)
    async def create_whiteboard(self, inter: ApplicationCommandInteraction):
        """Create a new whiteboard message"""
        await self._handle_whiteboard(inter)

    @whiteboard.sub_command(name="edit")
    async def edit_by_id(self, inter: ApplicationCommandInteraction, message_id: str):
        """Edit whiteboard by message ID"""
        try:
            message = await inter.channel.fetch_message(int(message_id))
            if not await self._can_edit_whiteboard(inter, message):
                await inter.response.send_message("You don't have permission to edit this whiteboard.", ephemeral=True)
                return
            await self._handle_whiteboard(inter, message)
        except Exception as e:
            await inter.response.send_message(str(e), ephemeral=True)

    @commands.message_command(name="Edit Whiteboard")
    async def edit_whiteboard(self, inter: ApplicationCommandInteraction, message: Message):
        """Edit whiteboard via message context"""
        if not await self._can_edit_whiteboard(inter, message):
            await inter.response.send_message("You don't have permission to edit this whiteboard.", ephemeral=True)
            return
        await self._handle_whiteboard(inter, message)

    async def _can_edit_whiteboard(self, inter: ApplicationCommandInteraction, message: Message) -> bool:
        if not message.embeds or message.author.id != self.client.user.id:
            return False
            
        # Check if user is admin or has privileged role
        if inter.author.guild_permissions.administrator or any(role.id == self.privileged_role_id for role in inter.author.roles):
            return True

        # Check if user is authorized editor
        maintainer_section = message.embeds[0].description.split("**Whiteboard Maintainer(s):**")
        if len(maintainer_section) > 1:
            return f"<@{inter.author.id}>" in maintainer_section[1]
        
        return False

    async def _handle_whiteboard(self, inter: ApplicationCommandInteraction, message: Message = None):
        embed = message.embeds[0] if message else None
        modal = ui.Modal(
            title="Whiteboard",
            custom_id="whiteboard_modal",
            components=[
                ui.TextInput(
                    label="Title", 
                    custom_id="title", 
                    style=TextInputStyle.short,
                    value=embed.title if embed else "Whiteboard"
                ),
                ui.TextInput(
                    label="Content", 
                    custom_id="content", 
                    style=TextInputStyle.paragraph,
                    value=embed.description.split("\n\n**Whiteboard")[0] if embed else None
                ),
                ui.TextInput(
                    label="Authorized Editor ID (Optional)", 
                    custom_id="editor_id", 
                    style=TextInputStyle.short,
                    required=False,
                    value=None
                )
            ]
        )
        
        await inter.response.send_modal(modal)

        try:
            modal_inter = await inter.client.wait_for(
                'modal_submit',
                check=lambda i: i.custom_id == modal.custom_id and i.author.id == inter.author.id,
                timeout=EDIT_TIMEOUT if message else CREATE_TIMEOUT
            )

            content = modal_inter.text_values['content']
            editor_id = modal_inter.text_values['editor_id']
            
            maintainers = []
            # Add admins and privileged users
            for member in inter.guild.members:
                if member.guild_permissions.administrator or any(role.id == self.privileged_role_id for role in member.roles):
                    maintainers.append(f"<@{member.id}>")
            
            # Add specific editor if provided
            if editor_id:
                try:
                    editor_id = int(editor_id)
                    if editor_id not in [int(m.strip("<@>")) for m in maintainers]:
                        maintainers.append(f"<@{editor_id}>")
                except ValueError:
                    pass

            maintainer_text = "\n\n**Whiteboard Maintainer(s):**\n" + ", ".join(maintainers)
            
            embed = Embed(
                title=modal_inter.text_values['title'],
                description=f"{content}{maintainer_text}",
                color=Color.blue()
            )

            if message:
                await message.edit(embed=embed)
                await modal_inter.response.send_message("Updated successfully!", ephemeral=True)
            else:
                await modal_inter.channel.send(embed=embed)
                await modal_inter.response.send_message("Created successfully!", ephemeral=True)

        except asyncio.TimeoutError:
            await inter.followup.send("Operation timed out!", ephemeral=True)

def setup(client):
    client.add_cog(WhiteboardCog(client))
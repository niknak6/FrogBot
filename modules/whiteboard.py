from disnake import TextInputStyle, ui, ApplicationCommandInteraction, NotFound, Forbidden, Message, Embed, Color
from core import is_admin_or_privileged
from disnake.ext import commands
import asyncio

TIMEOUT = 300

class WhiteboardCog(commands.Cog):
    def __init__(self, client):
        self.client = client

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
    @is_admin_or_privileged(rank_id=1198482895342411846)
    async def edit_by_id(self, inter: ApplicationCommandInteraction, message_id: str):
        """Edit whiteboard by message ID"""
        try:
            message = await inter.channel.fetch_message(int(message_id))
            if not self._is_valid_whiteboard(message):
                await inter.response.send_message("Invalid whiteboard message.", ephemeral=True)
                return
            await self._handle_whiteboard(inter, message)
        except Exception as e:
            await inter.response.send_message(str(e), ephemeral=True)

    @commands.message_command(name="Edit Whiteboard")
    @is_admin_or_privileged(rank_id=1198482895342411846)
    async def edit_whiteboard(self, inter: ApplicationCommandInteraction, message: Message):
        """Edit whiteboard via message context"""
        if not self._is_valid_whiteboard(message):
            await inter.response.send_message("Invalid whiteboard message.", ephemeral=True)
            return
        await self._handle_whiteboard(inter, message)

    def _is_valid_whiteboard(self, message: Message) -> bool:
        return message.embeds and message.author.id == self.client.user.id

    async def _handle_whiteboard(self, inter: ApplicationCommandInteraction, message: Message = None):
        embed = message.embeds[0] if message else None
        modal = ui.Modal(
            title="Whiteboard",
            custom_id="whiteboard_modal",
            components=[
                ui.TextInput(label="Title", custom_id="title", style=TextInputStyle.short, 
                           value=embed.title if embed else "Whiteboard"),
                ui.TextInput(label="Content", custom_id="content", style=TextInputStyle.paragraph, 
                           value=embed.description if embed else None)
            ]
        )
        
        await inter.response.send_modal(modal)

        try:
            modal_inter = await inter.client.wait_for(
                'modal_submit',
                check=lambda i: i.custom_id == modal.custom_id and i.author.id == inter.author.id,
                timeout=TIMEOUT
            )

            embed = Embed(title=modal_inter.text_values['title'],
                         description=modal_inter.text_values['content'],
                         color=Color.blue())

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
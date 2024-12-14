from disnake import TextInputStyle, ui, ApplicationCommandInteraction, NotFound, Forbidden, Message, Embed, Color, Permissions
from core import is_admin_or_privileged
from disnake.ext import commands
import asyncio

TIMEOUT = 300
WHITEBOARD_MODAL_ID = 'whiteboard_modal'

class WhiteboardCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command()
    @is_admin_or_privileged(rank_id=1198482895342411846)
    async def whiteboard(self, inter: ApplicationCommandInteraction):
        """Create a new whiteboard message"""
        await self._show_whiteboard_modal(inter)

    @commands.message_command(name="Edit Whiteboard", default_member_permissions=Permissions(administrator=True))
    @is_admin_or_privileged(rank_id=1198482895342411846)
    async def edit_whiteboard(self, inter: ApplicationCommandInteraction, message: Message):
        """Edit an existing whiteboard message"""
        if not message.embeds or message.embeds[0].title != "Whiteboard":
            await inter.response.send_message("This message was not created using whiteboard.", ephemeral=True)
            return
        await self._show_whiteboard_modal(inter, message)

    async def _show_whiteboard_modal(self, inter: ApplicationCommandInteraction, target_message: Message = None):
        """Shared modal handling logic for both create and edit operations"""
        components = [
            ui.TextInput(
                label="Content",
                placeholder="Type your content here",
                custom_id="content",
                style=TextInputStyle.paragraph,
                required=True,
                value=target_message.embeds[0].description if target_message else None
            ),
            ui.TextInput(
                label="Action",
                placeholder="'append' or 'clear' (default: append)",
                custom_id="action",
                style=TextInputStyle.single_line,
                required=False
            )
        ]
        
        if not target_message:
            components.insert(0, ui.TextInput(
                label="Message ID",
                placeholder="Enter message ID (optional)",
                custom_id="message_id",
                style=TextInputStyle.single_line,
                required=False
            ))

        modal_id = f"{WHITEBOARD_MODAL_ID}_edit" if target_message else WHITEBOARD_MODAL_ID
        
        await inter.response.send_modal(
            title="Whiteboard",
            custom_id=modal_id,
            components=components
        )

        try:
            modal_inter = await inter.client.wait_for(
                'modal_submit',
                check=lambda i: i.custom_id == modal_id and i.author.id == inter.author.id,
                timeout=TIMEOUT
            )

            content = modal_inter.text_values['content']
            action = modal_inter.text_values.get('action', 'append').lower()

            if target_message:
                message = target_message
            else:
                message_id = modal_inter.text_values.get('message_id', '')
                if message_id:
                    try:
                        message = await inter.channel.fetch_message(int(message_id))
                    except (ValueError, NotFound, Forbidden) as e:
                        await self._handle_message_error(modal_inter, e)
                        return
                else:
                    embed = self._create_whiteboard_embed(content)
                    await modal_inter.response.send_message(embed=embed)
                    return

            embed = self._create_whiteboard_embed(
                content,
                previous_content=message.embeds[0].description if action == 'append' else None
            )
            await message.edit(embed=embed)
            await modal_inter.response.send_message("Updated successfully!", ephemeral=True)

        except asyncio.TimeoutError:
            if target_message:
                await inter.followup.send("Edit timed out!", ephemeral=True)

    def _create_whiteboard_embed(self, content: str, previous_content: str = None) -> Embed:
        """Create a whiteboard embed with optional previous content"""
        description = f"{previous_content}\n\n{content}" if previous_content else content
        return Embed(
            title="Whiteboard",
            description=description,
            color=Color.blue()
        )

    async def _handle_message_error(self, inter, error):
        """Handle message-related errors with appropriate responses"""
        if isinstance(error, ValueError):
            await inter.response.send_message("Invalid message ID.", ephemeral=True)
        elif isinstance(error, NotFound):
            await inter.response.send_message("Message not found.", ephemeral=True)
        elif isinstance(error, Forbidden):
            await inter.response.send_message("Insufficient permissions to edit the message.", ephemeral=True)

def setup(client):
    client.add_cog(WhiteboardCog(client))
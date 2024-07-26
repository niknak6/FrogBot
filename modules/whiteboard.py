# modules.whiteboard

from modules.utils.commons import is_admin_or_rank
from disnake import TextInputStyle, ui
from disnake.ext import commands
import asyncio
import disnake

TIMEOUT = 300
WHITEBOARD_MODAL_ID = 'whiteboard_modal'

class WhiteboardCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command()
    @is_admin_or_rank()
    async def whiteboard(self, inter: disnake.ApplicationCommandInteraction):
        await inter.response.send_modal(
            title="Whiteboard",
            custom_id=WHITEBOARD_MODAL_ID,
            components=[
                ui.TextInput(
                    label="Message ID",
                    placeholder="Enter the message ID here (optional)",
                    custom_id="message_id",
                    style=TextInputStyle.single_line,
                    value="None",
                ),
                ui.TextInput(
                    label="Content",
                    placeholder="Type your content here",
                    custom_id="content",
                    style=TextInputStyle.paragraph,
                    value="",
                ),
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('interaction', check=lambda i: i.custom_id == WHITEBOARD_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            content = '>>> ' + modal_inter.text_values.get('content', '')
            message_id = modal_inter.text_values.get('message_id', None)
            if message_id and message_id != "None":
                try:
                    message_id = int(message_id)
                except ValueError:
                    await inter.channel.send(content='Invalid message ID.')
                    return
                try:
                    message = await inter.channel.fetch_message(message_id)
                    await message.edit(content=content)
                except disnake.NotFound:
                    await inter.channel.send(content='Message not found.')
                except disnake.Forbidden:
                    await inter.channel.send(content='Insufficient permissions to edit the message.')
            else:
                await inter.channel.send(content=content)
            await modal_inter.response.defer()
            await modal_inter.delete_original_message()

        except asyncio.TimeoutError:
            return

def setup(client):
    client.add_cog(WhiteboardCog(client))
# modules.whiteboard

from disnake import TextInputStyle, ui, ApplicationCommandInteraction, NotFound, Forbidden
from modules.utils.commons import is_admin_or_rank
from disnake.ext import commands
import asyncio

TIMEOUT = 300
WHITEBOARD_MODAL_ID = 'whiteboard_modal'

class WhiteboardCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command()
    @is_admin_or_rank()
    async def whiteboard(self, inter: ApplicationCommandInteraction):
        await inter.response.send_modal(
            title="Whiteboard",
            custom_id=WHITEBOARD_MODAL_ID,
            components=[
                ui.TextInput(label="Message ID", placeholder="Enter message ID (optional)", custom_id="message_id", style=TextInputStyle.single_line, required=False),
                ui.TextInput(label="Content", placeholder="Type your content here", custom_id="content", style=TextInputStyle.paragraph, required=True),
                ui.TextInput(label="Action", placeholder="'append' or 'clear' (default: append)", custom_id="action", style=TextInputStyle.single_line, required=False),
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('interaction', check=lambda i: i.custom_id == WHITEBOARD_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            content = f"> {modal_inter.text_values['content']}"
            message_id = modal_inter.text_values.get('message_id', '')
            action = modal_inter.text_values.get('action', 'append').lower()
            if message_id:
                try:
                    message = await inter.channel.fetch_message(int(message_id))
                    new_content = f"{message.content}\n{content}" if action == 'append' else content
                    await message.edit(content=new_content)
                except ValueError:
                    await inter.channel.send("Invalid message ID.")
                except NotFound:
                    await inter.channel.send("Message not found.")
                except Forbidden:
                    await inter.channel.send("Insufficient permissions to edit the message.")
            else:
                await inter.channel.send(content=content)
            await modal_inter.response.defer()
            await modal_inter.delete_original_message()
        except asyncio.TimeoutError:
            pass

def setup(client):
    client.add_cog(WhiteboardCog(client))
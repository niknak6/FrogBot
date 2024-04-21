# modules.on_thread_create.py

from disnake import Button, ButtonStyle, ActionRow, Interaction, Embed
from modules.utils.GPT import process_message_with_llm
from disnake.ui import Button, ActionRow
import asyncio

EMOJI_MAP = {
    1162100167110053888: ["🐞", "📜", "📹", "✅"],
    1167651506560962581: ["💡", "🧠", "✅"],
    1160318669839147259: ["💡", "🧠", "✅"],
}

async def add_reaction(message, emoji):
    try:
        await message.add_reaction(emoji)
    except Exception as e:
        print(f"Error adding reaction {emoji}: {e}")

async def on_thread_create(thread):
    try:
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        if emojis_to_add:
            async for message in thread.history(limit=1):
                for emoji in emojis_to_add:
                    await add_reaction(message, emoji)
                    await asyncio.sleep(0.5)
                if thread.parent_id == 1162100167110053888:
                    await send_bot_assistance_message(thread.guild.me, message, message.author.id)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

async def send_bot_assistance_message(bot, message, original_poster_id):
    print(f"Sending bot assistance message for user {original_poster_id}")
    channel = message.channel
    thread_id = message.thread.id
    embed = Embed(title="Bot Assistance",
                  description="Do you want the bot to assist you with this?",
                  color=0x3498db)
    embed.set_footer(text="Selecting 'Yes' will trigger bot assistance. Selecting 'No' will ignore.")
    yes_button = Button(style=ButtonStyle.success, label="Yes")
    no_button = Button(style=ButtonStyle.danger, label="No")
    action_row = ActionRow(yes_button, no_button)
    bot_assistance_message = await channel.send(embed=embed, components=[action_row], ephemeral=True)
    
    def check(interaction: Interaction):
        return interaction.message.id == bot_assistance_message.id and interaction.user.id == original_poster_id

    interaction = await bot.wait_for("interaction", check=check)
    print(f"Interaction received from user {interaction.user.id}")
    if interaction.component.label == "Yes":
        await interaction.response.send_message("The bot will now attempt to assist you.", ephemeral=True)
        first_message = await fetch_first_message_in_thread(bot, thread_id)
        await process_message_with_llm(first_message, bot)
    else:
        await interaction.response.send_message("No bot assistance will be provided, unless you tag it.", ephemeral=True)

async def fetch_first_message_in_thread(bot, thread_id):
    thread = bot.get_channel(thread_id)
    messages = await thread.history(limit=1).flatten()
    return messages[0]

def setup(client):
    client.event(on_thread_create)

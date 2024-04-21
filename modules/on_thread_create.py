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
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error adding reaction {emoji}: {e}")
        await asyncio.sleep(2)

async def on_thread_create(bot, thread):
    try:
        await asyncio.sleep(1)
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        if emojis_to_add:
            async for message in thread.history(limit=1):
                for emoji in emojis_to_add:
                    await add_reaction(message, emoji)
                    await asyncio.sleep(0.5)
                if thread.parent_id == 1162100167110053888:
                    await send_bot_assistance_message(bot, message, message.author.id)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

async def send_bot_assistance_message(bot, message, original_poster_id):
    print(f"Sending bot assistance message for user {original_poster_id}")
    channel = message.channel
    embed = Embed(title="Bot Assistance",
                  description="Do you want the bot to assist you with this?",
                  color=0x3498db)
    embed.set_footer(text="Selecting 'Yes' will trigger bot assistance. Selecting 'No' will ignore.")
    yes_button = Button(style=ButtonStyle.success, label="Yes")
    no_button = Button(style=ButtonStyle.danger, label="No")
    action_row = ActionRow(yes_button, no_button)
    bot_assistance_message = await channel.send(embed=embed, components=[action_row])
    print("Bot assistance message sent")
    
    def check(interaction: Interaction):
        result = interaction.message.id == bot_assistance_message.id and interaction.user.id == original_poster_id
        print(f"Checked interaction from message {interaction.message.id}, user {interaction.user.id}: {result}")
        return result

    print("Waiting for interaction...")
    interaction = await bot.wait_for("interaction", check=check)
    print(f"Interaction received from user {interaction.user.id}")
    if interaction.component.label == "Yes":
        await interaction.response.send_message("The bot will now attempt to assist you.", ephemeral=True)
    else:
        await interaction.response.send_message("No bot assistance will be provided, unless you tag it.", ephemeral=True)
    await bot_assistance_message.delete()

async def fetch_first_message_in_thread(bot, thread_id):
    thread = bot.get_channel(thread_id)
    messages = await thread.history(limit=100).flatten()
    first_message = sorted(messages, key=lambda m: m.created_at)[0]
    return first_message

def setup(client):
    client.add_listener(on_thread_create)
# modules.emoji

from disnake import Button, ButtonStyle, ActionRow, Interaction, Embed, ChannelType
from modules.utils.database import db_access_with_retry, update_points
from modules.roles import check_user_points
from disnake.ui import Button, ActionRow
from datetime import datetime, timedelta
import disnake
import asyncio
import sqlite3

bot_replies = {}

emoji_actions = {
    "✅": "handle_checkmark_reaction",
    "👍": "handle_thumbsup_reaction",
    "👎": "handle_thumbsdown_reaction"
}

emoji_points = {
    "🐞": 250,
    "📜": 250,
    "📹": 500,
    "💡": 100,
    "🧠": 250,
    "❤️": 100
}

emoji_responses = {
    "🐞": "their bug report",
    "📜": "submitting an error log",
    "📹": "including footage",
    "💡": "a feature request",
    "🧠": "making sure it was well-thought-out",
    "❤️": "being a good frog"
}

async def handle_thumbsup_reaction(bot, payload):
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    if message.author != bot.user:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    required_rank_id = 1198482895342411846
    if not any(role.id >= required_rank_id for role in member.roles):
        return
    print(f"Thumbs up reaction received from user {payload.user_id}")
    await message.reply("Thank you for your positive feedback!")

async def handle_thumbsdown_reaction(bot, payload):
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    if message.author != bot.user:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    required_rank_id = 1198482895342411846
    if not any(role.id >= required_rank_id for role in member.roles):
        return
    print(f"Thumbs down reaction received from user {payload.user_id}")
    await message.reply("We're sorry to hear that. We'll strive to do better.")
    
async def process_close(bot, payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id is None:
        return
    emoji_name = str(payload.emoji)
    if emoji_name not in emoji_actions:
        return
    message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
    if emoji_name == "✅" and ChannelType.forum and (payload.member.guild_permissions.administrator or payload.user_id == 126123710435295232):
        await handle_checkmark_reaction(bot, payload, message.author.id)

conn = sqlite3.connect('reminders.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        channel_id INTEGER,
        message_id INTEGER,
        reminder_time TEXT
    )
''')

def load_reminders_on_start(bot):
    print("Starting to load reminders...")
    bot.loop.create_task(handle_checkmark_reaction(bot, None, None, load_only=True))

async def handle_checkmark_reaction(bot, payload, original_poster_id, load_only=False):
    async def send_reminder_with_delay(user_id, channel_id, message_id, delay):
        await asyncio.sleep(delay)
        channel = bot.get_channel(channel_id)
        await channel.send(f"<@{user_id}>, please select an option.")

    async def load_reminders():
        print("Loading reminders...")
        c = conn.cursor()
        now = datetime.now()
        c.execute('SELECT user_id, channel_id, message_id, reminder_time FROM reminders')
        reminders = c.fetchall()
        for reminder in reminders:
            user_id, channel_id, message_id, reminder_time = reminder
            reminder_time = datetime.fromisoformat(reminder_time)
            if reminder_time > now:
                delay = (reminder_time - now).total_seconds()
                print(f"Creating reminder for user {user_id} in channel {channel_id} with message {message_id}")
                asyncio.create_task(send_reminder_with_delay(user_id, channel_id, message_id, delay))

    if load_only:
        await load_reminders()
        return

    print(f"Handling checkmark reaction for user {original_poster_id}")
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    thread_id = message.thread.id
    guild = bot.get_guild(payload.guild_id)
    embed = Embed(title="Resolution of Request/Report",
                  description=f"<@{original_poster_id}>, your request or report is considered resolved. Are you satisfied with the resolution?",
                  color=0x3498db)
    embed.set_footer(text="Selecting 'Yes' will close and delete this thread. Selecting 'No' will keep the thread open.")
    yes_button = Button(style=ButtonStyle.success, label="Yes")
    no_button = Button(style=ButtonStyle.danger, label="No")
    action_row = ActionRow(yes_button, no_button)
    satisfaction_message = await channel.send(embed=embed, components=[action_row])

    def check(interaction: Interaction):
        return interaction.message.id == satisfaction_message.id and interaction.user.id == original_poster_id

    async def send_reminder():
        await asyncio.sleep(43200)
        await channel.send(f"<@{original_poster_id}>, please select an option.")
    reminder_time = datetime.now() + timedelta(seconds=43200)
    c.execute('''
        INSERT INTO reminders (user_id, channel_id, message_id, reminder_time)
        VALUES (?, ?, ?, ?)
    ''', (original_poster_id, payload.channel_id, satisfaction_message.id, reminder_time.isoformat()))
    conn.commit()
    print(f"Added reminder for user {original_poster_id} in channel {payload.channel_id} with message {satisfaction_message.id}")

    reminder_task = asyncio.create_task(send_reminder())

    try:
        interaction = await bot.wait_for("interaction", timeout=86400, check=check)
        reminder_task.cancel()
        c.execute('''
            DELETE FROM reminders
            WHERE user_id = ? AND channel_id = ? AND message_id = ?
        ''', (original_poster_id, payload.channel_id, satisfaction_message.id))
        conn.commit()
        print(f"Deleted reminder for user {original_poster_id} in channel {payload.channel_id} with message {satisfaction_message.id}")
        print(f"Interaction received from user {interaction.user.id}")
        if interaction.component.label == "Yes":
            await interaction.response.send_message("Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
            thread = disnake.utils.get(guild.threads, id=thread_id)
            if thread is not None:
                await thread.delete()
            else:
                await channel.send(f"No thread found with ID {thread_id}.")
        else:
            await interaction.response.send_message("We're sorry to hear that. We'll strive to do better.")
    except asyncio.TimeoutError:
        reminder_task.cancel()
        c.execute('''
            DELETE FROM reminders
            WHERE user_id = ? AND channel_id = ? AND message_id = ?
        ''', (original_poster_id, payload.channel_id, satisfaction_message.id))
        conn.commit()
        print(f"Deleted reminder for user {original_poster_id} in channel {payload.channel_id} with message {satisfaction_message.id}")
        await channel.send(f"<@{original_poster_id}>, you did not select an option within 24 hours. This thread will now be closed.")
        thread = disnake.utils.get(guild.threads, id=thread_id)
        if thread is not None:
            await thread.delete()
        else:
            await channel.send(f"No thread found with ID {thread_id}.")

async def process_emoji_reaction(bot, payload):
    guild = bot.get_guild(payload.guild_id)
    reactor = guild.get_member(payload.user_id)
    if not reactor.guild_permissions.administrator:
        return
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    user_id = message.author.id
    user_points = get_user_points(user_id)
    points_to_add = emoji_points[str(payload.emoji)]
    new_points = user_points + points_to_add
    if await update_points(user_id, new_points):
        await check_user_points(bot)
    await manage_bot_response(bot, payload, points_to_add, str(payload.emoji))

async def process_reaction(bot, payload):
    if payload.guild_id is None:
        return
    emoji_name = str(payload.emoji)
    if emoji_name in emoji_points:
        await process_emoji_reaction(bot, payload)
    elif emoji_name in emoji_actions:
        if emoji_name == "✅":
            await process_close(bot, payload)
        else:
            function_name = emoji_actions[emoji_name]
            function = globals()[function_name]
            await function(bot, payload)

def get_user_points(user_id):
    user_points_dict = db_access_with_retry('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
    return user_points_dict[0][1] if user_points_dict else 0

async def manage_bot_response(bot, payload, points_to_add, emoji_name):
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    bot_reply_info = bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
    if emoji_responses[emoji_name] not in bot_reply_info['reasons']:
        bot_reply_info['reasons'].append(emoji_responses[emoji_name])
    total_points = bot_reply_info['total_points'] + points_to_add
    embed = create_points_embed(message.author, total_points, bot_reply_info['reasons'], emoji_name)
    if bot_reply_info['reply_id']:
        try:
            bot_reply_message = await channel.fetch_message(bot_reply_info['reply_id'])
            await bot_reply_message.edit(embed=embed)
        except disnake.NotFound:
            bot_reply_info['reply_id'] = None
    if not bot_reply_info['reply_id']:
        bot_reply_message = await message.reply(embed=embed)
        bot_reply_info['reply_id'] = bot_reply_message.id
    bot_replies[message.id] = {'reply_id': bot_reply_message.id, 'total_points': total_points, 'reasons': bot_reply_info['reasons']}

def create_points_embed(user, total_points, reasons, emoji_name):
    title = f"Points Updated: {emoji_name}"
    description = f"{user.display_name} was awarded points for:"
    reason_to_emoji = {reason: emoji for emoji, reason in emoji_responses.items()}
    reasons_text = "\n".join([f"{reason_to_emoji.get(reason, '❓')} for {reason}" for reason in reasons])
    embed = disnake.Embed(
        title=title,
        description=description,
        color=disnake.Color.green()
    )
    embed.add_field(name="Reasons", value=reasons_text, inline=False)
    embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
    embed.set_footer(text=f"Updated on {datetime.datetime.now().strftime('%Y-%m-%d')} | '/check_points' for more info.")
    return embed

def setup(client):
    @client.event
    async def on_raw_reaction_add(payload):
        await process_reaction(client, payload)

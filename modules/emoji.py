# modules.emoji

from modules.utils.database import db_access_with_retry, update_points
from disnake import Button, ButtonStyle, Embed
from modules.roles import check_user_points
from disnake.ext import commands
import datetime
import disnake
import asyncio

class EmojiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_replies = {}
        self.emoji_actions = {
            "✅": self.handle_checkmark_reaction,
            "👍": self.handle_thumbsup_reaction,
            "👎": self.handle_thumbsdown_reaction
        }
        self.emoji_points = {
            "🐞": 250, "📜": 250, "📹": 500, 
            "💡": 100, "🧠": 250, "❤️": 100
        }
        self.emoji_responses = {
            "🐞": "their bug report", "📜": "submitting an error log", 
            "📹": "including footage", "💡": "a feature request", 
            "🧠": "making sure it was well-thought-out", "❤️": "being a good frog"
        }

    async def handle_reaction(self, payload, reply_message):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message.author != self.bot.user:
            return
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        required_rank_id = 1198482895342411846
        if not any(role.id >= required_rank_id for role in member.roles):
            return
        print(f"Reaction received from user {payload.user_id}")
        await message.reply(reply_message)

    async def handle_thumbsup_reaction(self, payload):
        await self.handle_reaction(payload, "Thank you for your positive feedback!")

    async def handle_thumbsdown_reaction(self, payload):
        await self.handle_reaction(payload, "We're sorry to hear that. We'll strive to do better.")

    async def handle_checkmark_reaction(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        thread = message.thread
        original_poster_id = message.author.id
        if thread:
            embed = Embed(
                title="Resolution of Request/Report",
                description=f"<@{original_poster_id}>, your request or report is considered resolved. Are you satisfied with the resolution?\nThis thread will be closed in 24 hours.",
                color=0x3498db
            )
            embed.set_footer(text="Selecting 'Yes' will close and delete this thread. Selecting 'No' will keep the thread open.")
            action_row = disnake.ui.ActionRow(
                disnake.ui.Button(style=ButtonStyle.green, label="Yes", custom_id=f"yes_{thread.id}"),
                disnake.ui.Button(style=ButtonStyle.red, label="No", custom_id=f"no_{thread.id}")
            )
            satisfaction_message = await channel.send(embed=embed, components=[action_row])
            db_access_with_retry(
                "INSERT INTO interactions (message_id, user_id, thread_id, satisfaction_message_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                (message.id, original_poster_id, thread.id, satisfaction_message.id, payload.channel_id)
            )
            await self.schedule_reminder(channel, original_poster_id)
            try:
                interaction = await self.bot.wait_for(
                    "interaction", timeout=86400, 
                    check=lambda i: i.user.id == original_poster_id
                )
                await self.process_interaction(interaction, thread)
            except asyncio.TimeoutError:
                await self.close_thread(channel, thread, original_poster_id)

    async def schedule_reminder(self, channel, user_id):
        await asyncio.sleep(43200)
        await channel.send(f"<@{user_id}>, please select an option. If you don't respond within 12 hours from now, the thread will be closed.")

    async def process_interaction(self, interaction, thread):
        if interaction.component.label == "Yes" and thread:
            await thread.delete()
        else:
            await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
            await interaction.message.delete()

    async def close_thread(self, channel, thread, user_id):
        await channel.send(f"<@{user_id}>, you did not select an option within 24 hours. This thread will now be closed.")
        if thread:
            await thread.delete()

    async def process_emoji_reaction(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user_id = message.author.id
        points_to_add = self.emoji_points[str(payload.emoji)]
        new_points = self.get_user_points(user_id) + points_to_add
        if await update_points(user_id, new_points):
            await check_user_points(self.bot)
        await self.manage_bot_response(payload, points_to_add, str(payload.emoji))

    async def process_reaction(self, payload):
        if payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        if emoji_name in self.emoji_points:
            await self.process_emoji_reaction(payload)
        elif emoji_name in self.emoji_actions:
            await self.emoji_actions[emoji_name](payload)

    def get_user_points(self, user_id):
        user_points = db_access_with_retry('SELECT points FROM user_points WHERE user_id = ?', (user_id,))
        return user_points[0][0] if user_points else 0

    async def manage_bot_response(self, payload, points_to_add, emoji_name):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        bot_reply_info = self.bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        if self.emoji_responses[emoji_name] not in bot_reply_info['reasons']:
            bot_reply_info['reasons'].append(self.emoji_responses[emoji_name])
        total_points = bot_reply_info['total_points'] + points_to_add
        embed = self.create_points_embed(message.author, total_points, bot_reply_info['reasons'], emoji_name)
        if bot_reply_info['reply_id']:
            try:
                bot_reply_message = await channel.fetch_message(bot_reply_info['reply_id'])
                await bot_reply_message.edit(embed=embed)
            except disnake.NotFound:
                bot_reply_info['reply_id'] = None
        if not bot_reply_info['reply_id']:
            bot_reply_message = await message.reply(embed=embed)
            bot_reply_info['reply_id'] = bot_reply_message.id
        self.bot_replies[message.id] = {
            'reply_id': bot_reply_info['reply_id'], 
            'total_points': total_points, 
            'reasons': bot_reply_info['reasons']
        }

    def create_points_embed(self, user, total_points, reasons, emoji_name):
        title = f"Points Updated: {emoji_name}"
        description = f"{user.display_name} was awarded points for:"
        reasons_text = "\n".join([f"{emoji_name} for {reason}" for reason in reasons])
        embed = disnake.Embed(
            title=title,
            description=description,
            color=disnake.Color.green()
        )
        embed.add_field(name="Reasons", value=reasons_text, inline=False)
        embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
        embed.set_footer(text=f"Updated on {datetime.datetime.now().strftime('%Y-%m-%d')} | '/check_points' for more info.")
        return embed

    async def load_interaction_states(self):
        interaction_states = db_access_with_retry(
            "SELECT message_id, user_id, thread_id, satisfaction_message_id, channel_id FROM interactions"
        )
        for state in interaction_states:
            asyncio.create_task(self.resume_interaction(*state))

    async def resume_interaction(self, message_id, user_id, thread_id, satisfaction_message_id, channel_id):
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        try:
            satisfaction_message = await channel.fetch_message(satisfaction_message_id)
        except disnake.NotFound:
            return
        try:
            interaction = await self.bot.wait_for(
                "interaction", timeout=86400,
                check=lambda i: i.message.id == satisfaction_message_id and i.user.id == user_id
            )
            thread = disnake.utils.get(self.bot.get_guild(interaction.guild.id).threads, id=thread_id)
            await self.process_interaction(interaction, thread)
        except asyncio.TimeoutError:
            thread = disnake.utils.get(self.bot.get_guild(interaction.guild.id).threads, id=thread_id)
            await self.close_thread(channel, thread, user_id)
        except Exception as e:
            print(f"Error resuming interaction: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_interaction_states()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.process_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        emoji_name = str(payload.emoji)
        if emoji_name in self.emoji_points:
            await self.process_emoji_reaction(payload, removing=True)
        elif emoji_name in self.emoji_actions:
            await self.emoji_actions[emoji_name](payload)
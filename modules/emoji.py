# modules.emoji

from modules.utils.database import db_access_with_retry, update_points
from disnake.ext import commands
from typing import Dict, List
from disnake import Embed
import disnake

REQUIRED_RANK_ID = 1198482895342411846

EMOJI_ACTIONS = {
    "👍": "handle_thumbsup_reaction",
    "👎": "handle_thumbsdown_reaction"
}

EMOJI_POINTS = {
    "🐞": 250, "📜": 250, "📹": 500,
    "💡": 100, "🧠": 250, "❤️": 100
}

EMOJI_RESPONSES = {
    "🐞": "their bug report",
    "📜": "submitting an error log",
    "📹": "including footage",
    "💡": "a feature request",
    "🧠": "making sure it was well-thought-out",
    "❤️": "being a good frog"
}

class EmojiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_replies: Dict[int, Dict] = {}

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=False)

    async def process_reaction(self, payload: disnake.RawReactionActionEvent, is_add: bool):
        if payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        if emoji_name in EMOJI_POINTS:
            await self.process_emoji_points(payload, is_add)
        elif emoji_name in EMOJI_ACTIONS and is_add:
            await getattr(self, EMOJI_ACTIONS[emoji_name])(payload)

    async def process_emoji_points(self, payload: disnake.RawReactionActionEvent, is_add: bool):
        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)
        if not reactor.guild_permissions.administrator:
            return
        message = await self.fetch_message(payload)
        user_id = message.author.id
        new_points = await self.update_user_points(user_id, payload.emoji, is_add)
        await self.update_bot_reply(message, new_points, str(payload.emoji), is_add)

    async def update_user_points(self, user_id: int, emoji: disnake.PartialEmoji, is_add: bool) -> int:
        emoji_name = str(emoji)
        points_to_change = EMOJI_POINTS[emoji_name]
        user_points = await self.get_user_points(user_id)
        new_points = user_points + points_to_change if is_add else user_points - points_to_change
        if await update_points(user_id, new_points):
            return new_points

    async def fetch_message(self, payload: disnake.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        return await channel.fetch_message(payload.message_id)

    async def update_bot_reply(self, message: disnake.Message, total_points: int, emoji: str, is_add: bool):
        reply_info = self.bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        reason = EMOJI_RESPONSES[emoji]
        reason_tuple = (emoji, reason)
        if is_add:
            if reason_tuple not in reply_info['reasons']:
                reply_info['reasons'].append(reason_tuple)
            reply_info['total_points'] += EMOJI_POINTS[emoji]
        else:
            if reason_tuple in reply_info['reasons']:
                reply_info['reasons'].remove(reason_tuple)
            reply_info['total_points'] -= EMOJI_POINTS[emoji]
        embed = self.create_points_embed(message.author, reply_info['total_points'], reply_info['reasons'])
        await self.edit_or_create_reply(message, reply_info, embed)

    async def edit_or_create_reply(self, message: disnake.Message, reply_info: Dict, embed: Embed):
        channel = message.channel
        if reply_info['reply_id']:
            try:
                reply_message = await channel.fetch_message(reply_info['reply_id'])
                await reply_message.edit(embed=embed)
            except disnake.NotFound:
                reply_info['reply_id'] = None
        if not reply_info['reply_id']:
            reply_message = await message.reply(embed=embed)
            reply_info['reply_id'] = reply_message.id
        self.bot_replies[message.id] = reply_info

    def create_points_embed(self, user: disnake.User, total_points: int, reasons: List[tuple]) -> Embed:
        title = "Points Updated"
        description = f"{user.display_name} was awarded points for:"
        reasons_text = "\n".join([f"{emoji} for {reason}" for emoji, reason in reasons])
        embed = disnake.Embed(
            title=title,
            description=description,
            color=disnake.Color.green()
        )
        embed.add_field(name="Reasons", value=reasons_text, inline=False)
        embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
        embed.set_footer(text=f"Updated on {disnake.utils.utcnow().strftime('%Y-%m-%d')} | '/check_points' for more info.")
        return embed

    async def get_user_points(self, user_id: int) -> int:
        user_points_dict = await db_access_with_retry('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
        return user_points_dict[0][1] if user_points_dict else 0
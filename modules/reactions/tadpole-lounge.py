# modules.reactions.tadpole-lounge

from datetime import datetime, timedelta, timezone
from disnake.ext import commands
import disnake

class TadpoleLoungeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def add_role(self, member, role, channel):
        try:
            await member.add_roles(role)
        except Exception as e:
            print(f"Error adding role {role.name} to member {member.name}: {e}")
        try:
            await channel.send(f"Hello {member.mention}, welcome to {member.guild.name}! You have been assigned the {role.mention} role. Please read the rules and enjoy your stay! You will gain full server access in a little while. If you have any questions feel free to ask them here.")
        except Exception as e:
            print(f"Error sending message to member {member.name} in {member.guild.name} tadpole lounge channel: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            role = disnake.utils.get(member.guild.roles, name="tadpole")
            channel = member.guild.get_channel(1208256502645657611)
            utcnow_aware = datetime.utcnow().replace(tzinfo=timezone.utc)
            if utcnow_aware - member.created_at < timedelta(days=2):
                await self.add_role(member, role, channel)
        except Exception as e:
            print(f"Error in on_member_join: {e}")

def setup(bot):
    bot.add_cog(TadpoleLoungeCog(bot))

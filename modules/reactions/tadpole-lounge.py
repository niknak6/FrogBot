# modules.reactions.tadpole-lounge

from datetime import datetime, timedelta, timezone
from disnake.ext import commands
import disnake

class TadpoleLoungeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def add_role(self, member, role, channel):
        try:
            if role is not None:
                await member.add_roles(role)
                role_name = role.name
            else:
                role_name = "None"
        except Exception as e:
            print(f"Error adding role {role_name} to member {member.name if member else 'None'}: {e}")

        try:
            if member and channel:
                await channel.send(f"Hello {member.mention}, welcome to {member.guild.name}! You have been assigned the {role.mention if role else 'None'} role. Please read the rules and enjoy your stay! You will gain full server access in a little while. If you have any questions feel free to ask them here.")
            else:
                print(f"Cannot send message, member or channel is None. Member: {member}, Channel: {channel}")
        except Exception as e:
            print(f"Error sending message to member {member.name if member else 'None'} in {member.guild.name if member else 'None'} tadpole lounge channel: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            if member is None:
                print("Error: member is None")
                return

            role = disnake.utils.get(member.guild.roles, name="tadpole")
            channel = member.guild.get_channel(1208256502645657611)
            utcnow_aware = datetime.now(datetime.UTC).replace(tzinfo=timezone.utc)
            if utcnow_aware - member.created_at < timedelta(days=2):
                await self.add_role(member, role, channel)
            else:
                print(f"Member {member.name} joined but does not meet the account age requirement.")
        except Exception as e:
            print(f"Error in on_member_join: {e}")

def setup(bot):
    bot.add_cog(TadpoleLoungeCog(bot))
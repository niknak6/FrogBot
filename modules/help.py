# modules.help

from disnake import Option, OptionType, OptionChoice
from disnake.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        description="Shows help information",
        options=[
            Option(
                name="category",
                description="The category of help you want",
                type=OptionType.string,
                required=False,
                choices=[
                    OptionChoice(name="Points", value="points"),
                    OptionChoice(name="General", value="general"),
                    OptionChoice(name="Advanced", value="advanced")
                ]
            )
        ]
    )
    async def help(self, ctx, category: str = "general"):
        bot_name = ctx.me.display_name
        if category.lower() == "points":
            await self.points_help(ctx)
        elif category.lower() == "advanced":
            await self.advanced_help(ctx)
        else:
            await self.general_help(ctx, bot_name)

    async def advanced_help(self, ctx):
        help_message = (
            ">>> ## __**Advanced Help**__\n"
            "### *For commands below, the user must have admin privileges.*\n\n"
            "--------\n\n"
            "**`whiteboard`**\n"
            "Open's a whiteboard that users can type in. You can edit messages sent by whiteboard by copying the message ID and pasting it in the Message ID field.\n\n"
            "**`restart`**\n"
            "Restart the bot.\n\n"
            "**`update`**\n"
            "Update the bot.\n\n"
            "**`add [amount] [user]`**\n"
            "Add points to a user.\n\n"
            "**`remove [amount] [user]`**\n"
            "Remove points from a user.\n\n"
            "**`check points [user]`**\n"
            "Check points for a user.\n\n"
            "**`shutdown`**\n"
            "Shutdown the bot, needs confirmation.\n"
        )
        await ctx.send(help_message)

    async def points_help(self, ctx):
        help_message = (
            '>>> ## __**Points work as follows:**__\n\n'
            '1,000 points - Tadpole Trekker\n'
            '2,500 points - Puddle Pioneer\n'
            '5,000 points - Jumping Junior\n'
            '10,000 points - Croaking Cadet\n'
            '25,000 points - Ribbit Ranger\n'
            '50,000 points - Frog Star\n'
            '100,000 points - Lily Legend\n'
            '250,000 points - Froggy Monarch\n'
            '500,000 points - Never Nourished Fat Frog\n'
            '1,000,000 points - Frog Daddy\n\n'
            'Bug report = 250 points\n'
            'Error log included = 250 points\n'
            'Video included = 500 points\n\n'
            'Feature request = 100 points\n'
            'Detailed/thought out = 250 points\n\n'
            'Testing a PR/feature = 1000 points\n'
            'Submitting a PR = 1000 points\n'
            'PR gets merged = 2500 points\n\n'
            'Helping someone with a question = 100 points\n'
        )
        await ctx.send(help_message)

    async def general_help(self, ctx, bot_name):
        help_message = (
            ">>> ## __**General Help**__\n"
            "### *Keywords for bot reactions will not be listed*\n\n"
            "--------\n\n"
            f"**`@{bot_name} [question]`**\n"
            "Ask ChatGPT a question. To continue conversations, you must reply to the bot's message.\n\n"
            "**`help points`**\n"
            "Displays the points help message.\n\n"
            "**`check_points`**\n"
            "Check your points and rank.\n\n"
            "**`tictactoe`**\n"
            "Initiates a game of Tic-Tac-Toe between User 1 and User 2. If the bot is tagged, you will play against it.\n\n"
            "**`help`**\n"
            "Display this help message.\n\n"
            "--------\n\n"
            "*Commands below need Admin permissions*\n\n"
            "**`help advanced`**\n"
            "Displays advanced commands.\n"
        )
        await ctx.send(help_message)

def setup(client):
    client.add_cog(HelpCog(client))
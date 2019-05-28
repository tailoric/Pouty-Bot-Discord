import random
from discord.ext import commands
from discord.ext.commands import Bot
from .utils.dataIO import DataIO

class Penis(commands.Cog):
    """cog for finding the 100% accurate penis length of a user"""
    def __init__(self, bot:Bot, allowed_channels):
        self.bot = bot
        self.allowed_channel = None
        for channel_id in allowed_channels:
            channel = bot.get_channel(channel_id)
            if channel:
                self.allowed_channel = channel
                break

    @commands.command(pass_context=True)
    async def penis(self, ctx, *, users: str = None):
        """accurately measure a user's penis size or compare the penis size of multiple users"""
        if ctx.message.channel is not self.allowed_channel:
            await ctx.send(f"Please use the following channel: <#{self.allowed_channel.id}>")
            return
        if users is None:
            message = ctx.message
            seed = message.author.id
            random.seed(seed)
            length = random.randint(0, 20)
            await ctx.send("**{0}'s size:**\n8{1}D".format(message.author.name, "=" * length))
        else:
            user_list = users.split()
            length_list = []
            message_string = ""
            for user in user_list:
                converter = commands.UserConverter()
                current_user = await converter.convert(ctx=ctx, argument=user)
                random.seed(current_user.id)
                length = random.randint(0, 20)
                length_list.append({"username": current_user.name, "length": length})
            for entry in length_list:
                message_string += "**{0}'s size:**\n8{1}D\n".format(entry["username"], "=" * entry["length"])
            await ctx.send(message_string)


def setup(bot):
    data_io = DataIO()
    allowed_channels = data_io.load_json("bot_channels")
    bot.add_cog(Penis(bot, allowed_channels))

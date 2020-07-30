from discord.ext import commands
import discord

class Chazz(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bucket = commands.CooldownMapping.from_cooldown(
                1,
                3600,
                commands.BucketType.guild
                )

    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.bucket.update_rate_limit(message) and "chazz" in message.content.lower():
            await message.channel.send("https://tenor.com/view/confused-white-persian-guardian-why-gif-14053524")

def setup(bot: commands.Bot):
    bot.add_cog(Chazz(bot))

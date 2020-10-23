from discord.ext import commands
import discord

import re


class April(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bucket = commands.CooldownMapping.from_cooldown(
                1,
                60 * 15,
                commands.BucketType.channel)

    async def uwuify_name(self, username: str):
        replace_map = {
                    r"(?:r|l)": r"w",
                    r"(?:R|L)": r"W",
                    r"n([aeiou])": r"ny\1",
                    r"N([aeiou])": r"Ny\1",
                    r"N([AEIOU])": r"NY\1",
                    r"th": r"d",
                    r"ove": "uv",
                    r"ge": "gy",
                    r"rs": "s",
                }
        sub_num = 0
        for k, v in replace_map.items():
            current_pattern = re.compile(k)
            username, replacements = current_pattern.subn(v, username)
            sub_num += replacements
        return username, sub_num

    @commands.Cog.listener()
    async def on_message(self, message):
        message_low = message.content.lower()
        if not ("uwu" in message_low or "owo" in message_low):
            return
        if not message.guild:
            return
        new_username, sub_num = await self.uwuify_name(
                message.author.display_name)
        if sub_num == 0 and not message.author.display_name.lower().startswith("daddy") :
            new_username = "Daddy " + new_username
        try:
            await message.author.edit(nick=new_username)
        except discord.errors.Forbidden:
            pass
        if not self.bucket.update_rate_limit(message):
            daddy_check = message.author.display_name.lower().startswith("daddy")
            await message.channel.send(f"*nuzzles my new {'' if daddy_check else 'daddy '}{new_username}*")


def setup(bot: commands.Bot):
    bot.add_cog(April(bot))

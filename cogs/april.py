from datetime import timedelta, timezone, datetime
import random
from discord.ext import commands, tasks
import discord
import re
import random

from discord.mentions import AllowedMentions

ZOOMER_REGEX = re.compile(r"\b(ong|(fr)+|cap(ping)?|rizz)\b", flags=re.IGNORECASE)

ZOOMER_EMOJI = [
        '\N{SKULL}',
        '\N{FIRE}',
        '\N{ROLLING ON THE FLOOR LAUGHING}',
        '\N{AUBERGINE}',
        '\N{PEACH}',
        '\N{SPLASHING SWEAT SYMBOL}',
        '\N{HUNDRED POINTS SYMBOL}',
        '\N{OK HAND SIGN}',
        '\N{BILLED CAP}',
        '\N{FACE WITH PLEADING EYES}',
        '\N{FREEZING FACE}',
        '\N{OVERHEATED FACE}',
        '\N{PILE OF POO}',
        '\N{FACE MASSAGE}\N{ZERO WIDTH JOINER}\N{FEMALE SIGN}\N{VARIATION SELECTOR-16}',
        '\U0001fae6', # biting lip
        '\N{FACE WITH TEARS OF JOY}'
        ]
class April(commands.Cog):

    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.excluded_channels = [
                366659034410909717,
                463597797342445578,
                191536772352573440,
                695675889991811142,
                426174461637689344,
                363758396698263563,
                595585060909088774
                ]

    @commands.Cog.listener("on_message")
    async def zoomer_reply(self, message: discord.Message):
        if message.author == self.bot.user \
                or message.channel.id in self.excluded_channels \
                or not message.guild:
            return

        content = message.content
        chance = random.random()
        me = message.guild.me
        channel = message.channel
        match =ZOOMER_REGEX.search(content)
        all_terms = ZOOMER_REGEX.findall(content)
        if any('cap' in term[0] for term in all_terms):
            return await message.channel.send(content="\N{BILLED CAP}",
                    reference=message,
                    allowed_mentions=AllowedMentions.none())

        if channel.permissions_for(me).send_messages \
                and (match or chance <= 0.01):
            return await message.channel.send(content=random.choice(ZOOMER_EMOJI),
                    reference=message,
                    allowed_mentions=AllowedMentions.none()
                    )



async def setup(bot: commands.Bot):
    await bot.add_cog(April(bot))

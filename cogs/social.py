from discord.ext import commands
import discord.ext.commands
import random
import json
import asyncio
import os
import functools

def find_file(command):
    with open('data/social/{}.json'.format(command), 'r') as f:
        return json.load(f)




class Social(commands.Cog):
    """
    Cog for interacting with other users or the bot
    """
    def make_social_command(self, file):
        async def social_command(ctx, *, user=None):
            mentioned_users = ctx.message.mentions
            file_name = file.replace(".json", "")
            images = find_file(file_name)
            if mentioned_users or not user:
                await ctx.send(random.choice(images))
            else:
                user = user.replace("\"", "")
                found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
                fmt = '{0}\n{1}'
                await ctx.send(fmt.format(found_user.mention, random.choice(images)))
        return social_command

    def __init__(self, bot):
        self.bot = bot
        files = os.listdir("data/social/")
        for file in files:
            description = f"send a {file.replace('.json', '')} to a user or to yourself"
            new_command = commands.Command(self.make_social_command(file), name=file.replace(".json", ""),
                                           hidden=False, description=description, help=description)
            bot.add_command(new_command)


    @commands.command(name="iloveyou", aliases=['ily'])
    async def iloveyou(self, ctx):
        """Confess your love to the bot"""
        await ctx.send(f"I love you too, {ctx.author.mention} \N{HEAVY BLACK HEART}")

    @commands.command()
    async def love(self, ctx, member: discord.Member):
        """accurately calculate of how much love you are possible of giving to the other user"""
        lover = ctx.author
        love_capability = random.randint(0, 100)
        love_message_string = (f"**{lover.display_name}** is capable of loving "
                               f"**{member.display_name}** a whooping {love_capability}%")
        love_message = await ctx.send(love_message_string)
        def sad_reaction_check(reaction: discord.Reaction, user):
            if isinstance(reaction.emoji, str):
                return False
            reaction_name = reaction.emoji.name
            return 'sad' in reaction_name.lower() \
                   and (user.id == lover.id or user.id == member.id) and love_capability < 60 \
                   and reaction.message.channel.id == ctx.channel.id
        try:
            await self.bot.wait_for('reaction_add', timeout=20.0, check=sad_reaction_check)
        except asyncio.TimeoutError:
            return
        love_bonus = random.randint(0, 100-love_capability)
        love_capability = min(love_capability+love_bonus, 100)
        await love_message.edit(content="\N{SPARKLING HEART} love booster activated recalculating the score"
                                        "\N{SPARKLING HEART}")
        await asyncio.sleep(3)
        await love_message.edit(content=f"**{lover.display_name}** is capable of loving "
                                        f"**{member.display_name}** a whooping {love_capability}% "
                                        f"(with a love boost of {love_bonus}%)")

async def setup(bot):
    await bot.add_cog(Social(bot))

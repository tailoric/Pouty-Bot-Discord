import discord
from discord.ext import commands
from .utils.dataIO import DataIO
import aiohttp
class GithubIssues(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        dataIO = DataIO()
        self.github_data= dataIO.load_json('github')
        self.token = self.github_data['p_access_token']
        self.session = aiohttp.ClientSession()

    @commands.command(aliases=['suggest', 'suggestion'])
    async def proposal(self, ctx, *, title):
        """creates a track able issue on github so the bot creator can easily list and work with suggestions for the
        bot"""
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent' : 'PoutyBot Discord Issue Cog',
            'Authorization' : f'token {self.token}'

        }
        data = {
            'title': title,
            'labels': ['todo', 'suggestion']
        }
        reactions = {
            'yes' : '\N{HEAVY CHECK MARK}',
            'no': '\N{CROSS MARK}'
        }

        def message_check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
        await ctx.send("Please write a description for your suggestion\n"
                       "refer to this guide for the formatting\n"
                       "<https://guides.github.com/features/mastering-markdown/>")
        message = await self.bot.wait_for('message', check=message_check)
        data['body'] = message.content
        embed = discord.Embed(title=title, description=message.content)
        react_mes = await ctx.send(content="This will be the created issue on github, do you want to send?",
                                   embed=embed)
        await react_mes.add_reaction('\N{HEAVY CHECK MARK}')
        await react_mes.add_reaction('\N{CROSS MARK}')

        def reaction_check(r, user):
            return user.id == ctx.author.id and isinstance(r.emoji, str) and (r.emoji == reactions['yes'] or
                                                                              r.emoji == reactions['no'])
        reaction, user = await self.bot.wait_for('reaction_add', check=reaction_check)
        if reaction.emoji == reactions['no']:
            await ctx.send("alright I won't send this suggestion")
            return
        async with self.session.post(url='https://api.github.com/repos/tailoric/Pouty-Bot-Discord/issues',
                                     headers=headers, json=data) as resp:
            if resp.status == 201:
                await ctx.send("issue was created")
            else:
                await ctx.send(resp.status)



def setup(bot):
    bot.add_cog(GithubIssues(bot))
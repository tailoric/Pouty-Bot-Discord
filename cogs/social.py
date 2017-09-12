from discord.ext import commands
import random
import json


class Social:

    def __init__(self, bot):
        self.bot = bot


    async def find_file(self, command, mention):
        with open('data/social/{}.json'.format(command), 'r') as f:
            data = json.load(f)
        if mention:
            await self.bot.say("{}\n{}".format(mention.mention,random.choice(data)))
        else:
            await self.bot.say(random.choice(data))

    @commands.command(hidden=False, pass_context=True)
    async def pout(self,ctx, mood="none"):
        """ 
        usage: .pout 
        """
        mood_list = ('angry','sad','embarrassed')
        file_name = 'pouts'
        if mood in mood_list:
            file_name = '{}_pouts'.format(mood)
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await  self.find_file(file_name,mentioned_users[0])
        else:
            await  self.find_file(file_name,ctx.message.author)



    @commands.command(hidden=False,pass_context=True)
    async def hug(self,ctx):
        """
            usage: .hug (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('hug', mentioned_users[0])
        else:
            await  self.find_file('hug',ctx.message.author)

    @commands.command(hidden=False, pass_context=True)
    async def smug(self, ctx):
        """
            usage: .smug (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('smug',mentioned_users[0])
        else:
            await  self.find_file('smug',ctx.message.author)
    @commands.command(hidden=False, pass_context=True)
    async def cuddle(self, ctx):
        """
            usage: .cuddle (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('cuddle',mentioned_users[0])
        else:
            await self.find_file('cuddle',ctx.message.author)


    @commands.command(hidden=False, pass_context=True)
    async def lewd(self, ctx):
        """
            usage: .lewd (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('lewd',mentioned_users[0])
        else:
            await self.find_file('lewd',ctx.message.author)


    @commands.command(hidden=False, pass_context=True)
    async def pat(self,ctx):
        """
            usage: .pat (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('pat',mentioned_users[0])
        else:
            await self.find_file('pat',ctx.message.author)

    @commands.command(hidden=False, pass_context=True)
    async def bully(self,ctx):
        """
            usage: .bully (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('bully',mentioned_users[0])
        else:
            await self.find_file('bully',ctx.message.author)
    @commands.command(hidden=False, pass_context=True)
    async def nobully(self,ctx):
        """
            usage: .nobully
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('nobullys',mentioned_users[0])
        else:
            await self.find_file('nobullys',ctx.message.author)
    @commands.command(hidden=False, pass_context=True)
    async def slap(self,ctx):
        """
            usage: .slap (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('slaps',mentioned_users[0])
        else:
            await self.find_file('slaps',ctx.message.author)

    @commands.command(hidden=False, pass_context=True)
    async def kiss(self,ctx):
        """
            usage: .kiss (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('kiss',mentioned_users[0])
        else:
            await self.find_file('kiss',ctx.message.author)

    @commands.command(hidden=False, pass_context=True)
    async def blush(self,ctx):
        """
            usage: .blush (at) user
        """
        mentioned_users = ctx.message.mentions
        if mentioned_users and len(mentioned_users) == 1:
            await self.find_file('Blush',mentioned_users[0])
        else:
            await self.find_file('Blush', ctx.message.author)

def setup(bot):
    bot.add_cog(Social(bot))
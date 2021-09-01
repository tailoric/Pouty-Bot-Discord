import discord
from discord.ext import commands, tasks
from logging import getLogger

class ThreadConversionException(commands.BadArgument):
    pass

class ThreadFetch(commands.ThreadConverter):

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Thread:
        try:
            return await super().convert(ctx, argument)
        except:
            try:
                thread_id = int(argument)
                return await ctx.guild.fetch_channel(thread_id)
            except ValueError:
                raise ThreadConversionException("could not fetch thread")
class ThreadJoinView(discord.ui.View):

    def __init__(self, thread: discord.Thread):
        self.thread = thread
        super().__init__(timeout=None)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.primary)
    async def join_thread(self, button : discord.ui.Button, interaction: discord.Interaction):
        if interaction.user:
            if self.thread.archived:
                await self.thread.edit(archived=False, locked=False)
            await self.thread.add_user(interaction.user)



class Thread(commands.Cog):
    """
    A cog for creating "Thread" channels for spoiler discussions etc.
    """
    thread_rule = """
    This channel is for the topic `{}`.
    You don't need to spoiler tag anything that was revealed up to the episode or chapter provided by the topic.
    However spoiler tag everything that is from a different franchise or story or was not covered yet by the current episode/chapter
    """
    topic = """
    Feel free to discuss spoilers or other topics without needing spoiler tags,
    (if this channel was created for an episode/chapter, then only untagged spoilers up to that episode/chapter).
    if someone is not behaving then report it to the moderators.
    """
    def __init__(self, bot):
        self.bot = bot
        self.logger= getLogger("PoutyBot")
        self.admin_cog = self.bot.get_cog("Admin")


    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def thread(self, ctx: commands.Context, *, topic):
        """
        create a new private thread with open invite 
        """
        thread_type = discord.ChannelType.public_thread
        if ctx.guild.premium_tier >= 2:
            thread_type = discord.ChannelType.private_thread

        thread = await ctx.channel.create_thread(name=topic,type=thread_type)
        view = ThreadJoinView(thread)
        embed = discord.Embed(title=topic, description="Click the join button to join the private thread", colour=discord.Colour.blurple())
        await ctx.send(embed=embed, view=view)

    @thread.command(name="invite")
    async def thread_post_invite(self, ctx, thread: ThreadFetch):
        """
        post a new invite to an existing thread
        """
        view = ThreadJoinView(thread)
        embed = discord.Embed(title=thread.name, description="Click the join button to join the private thread", colour=discord.Colour.blurple())
        await ctx.send(embed=embed, view=view)

    @commands.guild_only()
    @thread.command(name="close")
    async def thread_close(self, ctx: commands.Context, thread: ThreadFetch):
        """
        Close a thread channel before its livetime is over
        """
        await thread.edit(archived=True, locked=True)
        await ctx.message.add_reaction("\N{OK HAND SIGN}")

def setup(bot):
    bot.add_cog(Thread(bot))

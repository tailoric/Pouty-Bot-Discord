from discord.ext import commands, tasks
import discord
from typing import Union, Optional
from wordcloud import WordCloud, STOPWORDS
from io import BytesIO
from functools import partial
import asyncio
import re
class Wordcloud(commands.Cog):

    def __init__(self, bot):
        self.bot= bot
        self.create_table = self.bot.loop.create_task(self.init_table())
        self.url_regex = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
        self.spoiler_regex = re.compile(r"\|\|.+?\|\|")
        self.clean_db.start()

    def cog_unload(self):
        self.clean_db.stop()

    async def init_table(self):
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("""
                CREATE TABLE IF NOT EXISTS wc_messages(
                    user_id BIGINT,
                    message_id BIGINT ,
                    message_content TEXT NOT NULL,
                    message_time TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, message_id)
                )
                """)
                await con.execute("""
                CREATE TABLE IF NOT EXISTS wc_consent(
                    user_id BIGINT PRIMARY KEY
                )
                """)
    ###################
    # Listener
    ###################
    @commands.Cog.listener("on_message")
    async def record_message(self, message):
        if not message.guild:
            return
        await asyncio.wait_for(self.create_table, timeout=None)
        context = await self.bot.get_context(message)
        if context and context.command:
            return
        consent = await self.bot.db.fetchrow("SELECT user_id FROM wc_consent where user_id = $1", message.author.id)
        if not consent:
            return
        clean_message = self.url_regex.sub("", message.clean_content)
        clean_message = self.spoiler_regex.sub("", clean_message)
        if clean_message:
            await self.bot.db.execute("""
            INSERT INTO wc_messages (user_id, message_id, message_content, message_time) VALUES ($1, $2, $3, $4)
            """, message.author.id, message.id, clean_message, message.created_at)

    @tasks.loop(hours=1)
    async def clean_db(self):
        await asyncio.wait_for(self.create_table, timeout=None)
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                user_ids = await con.fetch("SELECT * FROM wc_consent")
                user_ids = [(u.get('user_id'),) for u in user_ids]
                await con.executemany("""
                DELETE FROM wc_messages
                WHERE message_id not in (
                    select message_id 
                    from wc_messages
                    where user_id = $1
                    group by message_id, message_time
                    order by message_time desc
                    limit 100
                )
                AND user_id = $1
                """, user_ids)

    ##################
    # Commands
    ##################
    @commands.group(invoke_without_command=True,aliases=["wc"], name="wordcloud", usage="[user|channel]")
    @commands.max_concurrency(3, per=commands.BucketType.default, wait=True)
    async def word_cloud(self, ctx, *,target: Union[discord.Member, discord.TextChannel, None]):
        """
        generate a word cloud from the last 100 messages of a user or a channel. 
        for users it only applies to messages the bot recorded after getting your consent for recording messages, see `wc consent`
        """
        text = ""
        if target is None:
            target = ctx.author
        if isinstance(target, discord.TextChannel):
            permissions = target.permissions_for(ctx.author)
            if not permissions.read_messages:
                return await ctx.send("Can't create wordcloud since you don't have the permission to view that channel")
            messages = await target.history(limit=300).flatten()
            text = "\n".join([self.url_regex.sub("", m.clean_content) for m in messages])
            text = self.spoiler_regex.sub("", text)
            print(text)
        if isinstance(target, discord.Member):
            consent = await self.bot.db.fetchrow("SELECT user_id FROM wc_consent where user_id = $1", ctx.author.id)

            if not consent:
                if not ctx.author == target:
                    return await ctx.send("This user has not consented to recording their messages, I can't create a word cloud")
                else:
                    return await ctx.send(f"Please first consent to having your messages recorded. using `{ctx.prefix}wc consent`")
            messages = await self.bot.db.fetch("""
            SELECT message_content from wc_messages WHERE user_id = $1 LIMIT 100 
            """, target.id)
            text = " ".join([m['message_content'] for m in messages])

        gen_file = partial(self.generate_file_from_text, text)
        await ctx.trigger_typing()
        f = await ctx.bot.loop.run_in_executor(None, gen_file)
        await ctx.send(file=f)

    @word_cloud.command(name="consent")
    async def word_cloud_consent(self, ctx):
        """
        Give the bot your consent for recording your messages across all channels (except DMs) starting now, you can remove the consent any time
        using `wc delete`
        """
        consent_message = await ctx.send("I will record any message you send from now on even deleted once, "
                "I only keep your last 100 messages (I won't record DMs either). You can remove your consent any time (using `wc delete`) "
                "react with \N{THUMBS UP SIGN} to confirm or \N{THUMBS DOWN SIGN} to decline")
        await consent_message.add_reaction("\N{THUMBS UP SIGN}")
        await consent_message.add_reaction("\N{THUMBS DOWN SIGN}")
        def check(reaction, user):
            return reaction.message == consent_message and user == ctx.author and reaction.emoji in ('\N{THUMBS UP SIGN}','\N{THUMBS DOWN SIGN}')
        reaction, user = await self.bot.wait_for("reaction_add", check=check)
        if reaction.emoji == "\N{THUMBS UP SIGN}":
            await self.bot.db.execute("INSERT INTO wc_consent VALUES ($1) ON CONFLICT DO NOTHING", ctx.author.id)
            await consent_message.edit(content="consent given, wait a bit"
                    " until I have enough messages collected to create a word cloud for you")
        else:
            await consent_message.edit(content="No consent for recording messages, you won't be able to create a word cloud")

    @word_cloud.command(name="delete")
    async def word_cloud_delete(self, ctx):
        """
        remove yourself from the word cloud message storage and remove your message recording consent
        """
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("DELETE FROM wc_consent WHERE user_id = $1", ctx.author.id)
                await con.execute("DELETE FROM wc_messages WHERE user_id = $1", ctx.author.id)
        await ctx.send("Consent removed, all your recorded messages were deleted")

    def generate_file_from_text(self, text):
        wc = WordCloud(width=800, height=800)
        wc.generate(text)
        im = wc.to_image()
        img_buf = BytesIO()
        im.save(img_buf, format='png')
        img_buf.seek(0)
        return discord.File(img_buf, "wc.png")

def setup(bot):
    bot.add_cog(Wordcloud(bot))

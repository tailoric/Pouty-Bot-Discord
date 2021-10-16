"""
Create a contest mode command suite for moderators
stuff that should be done in here
Start command
    1. Create a channel for the contest that only allows posts from people with a certain role
    2. create the "contestant" role that mods can give to people participating in the contest
While the contest is going:
    3. when a contestant posts something in that channel immediately react with a vote reaction
    4. save user id, username, message id and vote number in the database
    when a reaction is happening:
        check if it is the contest channel and the vote emoji
        get the entry via the message id
        set the vote count to the new reaction number
(depending on how the contest is supposed to go)
    5. allow X entries
    6. delete follow up entries
"""
from builtins import hasattr

import discord
import io
import os.path
import asyncpg
import aiohttp
import asyncio
import logging
import mimetypes as mime
import typing
from discord.ext import commands
from .utils.checks import is_owner_or_moderator
class Contest(commands.Cog):

    def contestant_check(self, ctx):
        guild = self.contest_channel.guild
        member_author = guild.get_member(ctx.author.id)
        return self.contestant_role in member_author.roles

    def __init__(self, bot):
        self.bot = bot
        self.contestant_role = None
        self.contest_channel = None
        self.session = aiohttp.ClientSession()
        self.bot.loop.create_task(self.setup_database())
        self.bot.loop.create_task(self.load_settings())

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def load_settings(self):
        await asyncio.sleep(1)
        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                settings = await connection.fetchrow("SELECT * FROM contest_settings LIMIT 1")
                if settings:
                    guild = self.bot.get_guild(settings["contest_guild_id"])
                    self.contest_channel = guild.get_channel(settings["contest_channel_id"])
                    self.contestant_role = guild.get_role(settings["contest_role_id"])

    async def setup_database(self):
        async with self.bot.db.acquire() as connection:
            query = ("CREATE TABLE IF NOT EXISTS contest ("
                     "user_id BIGINT,"
                     "message_id BIGINT PRIMARY KEY);"
                     "CREATE TABLE IF NOT EXISTS contest_votes ("
                     "user_id BIGINT,"
                     "message_id BIGINT references contest(message_id) ON DELETE CASCADE ,"
                     "PRIMARY KEY (user_id, message_id));"
                     "CREATE TABLE IF NOT EXISTS contest_settings("
                     "contest_role_id BIGINT,"
                     "contest_channel_id BIGINT,"
                     "contest_guild_id BIGINT);"
                     "CREATE TABLE IF NOT EXISTS contest_disqualified("
                     "user_id BIGINT primary key )")
            async with connection.transaction():
                await connection.execute(query)

    async def save_settings(self, contest_role_id, contest_channel_id, guild_id):
        async with self.bot.db.acquire() as connection:
            query = ("INSERT INTO contest_settings values ($1, $2, $3)")
            statement = await connection.prepare(query)
            async with connection.transaction():
                await statement.fetch(contest_role_id, contest_channel_id, guild_id)

    async def empty_table(self):
        async with self.bot.db.acquire() as connection:
            query = ("DELETE FROM contest;"
                     "DELETE FROM contest_settings;"
                     "DELETE FROM contest_votes;"
                     "DELETE FROM contest_disqualified;")
            async with connection.transaction():
                await connection.execute(query)

    async def add_contest_entry(self, contestant_id, message,):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("INSERT INTO contest VALUES ($1,$2)")
            async with connection.transaction():
                await statement.fetch(contestant_id, message.id)

    async def add_vote_to_entry(self, user_id, entry_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("INSERT INTO contest_votes values ($1, $2)")
            async with connection.transaction():
                return await statement.fetchval(user_id, entry_id)

    async def remove_vote_from_entry(self, user_id, entry_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("DELETE FROM contest_votes WHERE user_id = $1 AND message_id = $2"
                                                 " RETURNING message_id")
            async with connection.transaction():
                return await statement.fetchval(user_id, entry_id)

    async def check_contestant_entries(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT count(message_id) as number_of_entries from contest "
                                                 "WHERE user_id = $1 GROUP BY user_id")
            async with connection.transaction():
                return await statement.fetchval(user_id)

    async def list_contest_entries(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT message_id from contest "
                                                 "WHERE user_id = $1")
            async with connection.transaction():
                return await statement.fetch(user_id)

    async def get_entry_by_message(self, message_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT user_id, message_id from contest "
                                                 "WHERE message_id = $1")
            async with connection.transaction():
                return await statement.fetchrow(message_id)

    async def remove_entry_from_database(self, message_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("DELETE FROM contest "
                                                 "WHERE message_id = $1")
            async with connection.transaction():
                return await statement.fetchrow(message_id)

    async def get_number_of_votes(self, message_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT count(message_id) as votes FROM contest_votes "
                                                 "WHERE message_id = $1")
            async with connection.transaction():
                return await statement.fetchval(message_id)

    async def contestant_disqualified(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("DELETE FROM contest "
                                                 "WHERE user_id = $1")
            statement_dq = await connection.prepare("INSERT INTO contest_disqualified values ($1)")
            async with connection.transaction():
                await statement_dq.fetchval(user_id)
                return await statement.fetchval(user_id)
    async def contestant_qualify(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("DELETE FROM contest_disqualified "
                                                 "WHERE user_id = $1")
            async with connection.transaction():
                return await statement.fetchrow(user_id)
    async def get_votes_of_user(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT user_id, message_id FROM contest_votes "
                                                 "WHERE user_id = $1")
            async with connection.transaction():
                return await statement.fetch(user_id)


    async def fetch_disqualified(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT user_id FROM contest_disqualified "
                                                 "WHERE user_id = $1")
            async with connection.transaction():
                return await statement.fetchval(user_id)
    async def get_top_entries(self):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare("SELECT DISTINCT contest.user_id, contest.message_id ,count(cv.message_id) as vote_count FROM contest "
                                                 "LEFT OUTER JOIN contest_votes cv on contest.message_id = cv.message_id "
                                                 "GROUP BY contest.user_id, contest.message_id "
                                                 "ORDER BY vote_count DESC "
                                                 )
            async with connection.transaction():
                return await statement.fetch()


    @commands.command(name="lentries", aliases=["list_entries", "myentries"], hidden=True)
    @commands.dm_only()
    async def list_entries(self, ctx):
        """show all entries of mine"""
        entries = await self.list_contest_entries(ctx.author.id)
        entry_list = ""
        for entry in entries:
            message = await self.contest_channel.fetch_message(entry["message_id"])
            entry_list += f"<{message.attachments[0].url}>\n"

        if entry_list:
            await ctx.send(entry_list)
        else:
            await ctx.send("no entries yet")

    @commands.command(name="gentry", aliases=["get_entry"])
    @is_owner_or_moderator()
    async def get_entry(self, ctx, message: discord.Message):
        """get the entry specified by jump_url or message id"""
        entry = await self.get_entry_by_message(message.id)
        votes = await self.get_number_of_votes(message.id)
        submission_image = message.attachments[0].url
        member = ctx.guild.get_member(entry["user_id"])
        embed = discord.Embed(color=member.color, title=member.display_name, url=message.jump_url,
                              description=f"submitted the following entry: [Jump]({message.jump_url})")
        embed.add_field(name="#Votes", value=votes)
        embed.set_thumbnail(url=member.avatar.url)
        embed.set_image(url=submission_image)
        await ctx.send(embed=embed)

    @commands.command(name="winner", aliases=["get_winner"])
    @is_owner_or_moderator()
    async def get_winner(self, ctx):
        """list the top 10 contestants by vote"""
        all_entries = await self.get_top_entries()
        embed = discord.Embed(title="Contest Winner:")
        winners = []
        counter = 1
        for entry in all_entries:
            if counter > 10:
                break
            if entry["user_id"] in winners:
                continue
            contestant = self.contest_channel.guild.get_member(entry["user_id"])
            submission = await self.contest_channel.fetch_message(entry["message_id"])
            embed.add_field(name=f"#{counter}", value=f"{contestant.mention} with the [following entry]({submission.jump_url})"
                                                    f" and a total number of {entry['vote_count']} votes")
            counter += 1
            winners.append(contestant.id)
        await ctx.send(embed=embed)

    @commands.command(name="rentry", aliases=["remove_entry"])
    @is_owner_or_moderator()
    async def remove_entry(self, ctx, message: discord.Message):
        """remove an entry"""
        await message.delete()
        await self.remove_entry_from_database(message.id)
        await ctx.send("Entry was deleted")

    @commands.command(name="disqualify")
    @is_owner_or_moderator()
    async def disqualify(self, ctx, member: discord.Member):
        """removes all entries of a user and makes them unable to join the contest again"""
        entries = await self.list_contest_entries(member.id)

        def check(m):
            return m.id in [entry["message_id"] for entry in entries]

        await member.remove_roles(self.contestant_role)
        await self.contest_channel.purge(check=check)
        await self.contestant_disqualified(member.id)
        await ctx.send(f"{member.display_name} has been disqualified.")
    @commands.command(name="qualify")
    @is_owner_or_moderator()
    async def qualify(self, ctx: commands.Context, member: discord.Member):
        """removes user from disqualification list"""
        await self.contestant_qualify(member.id)
        await ctx.send(f"{member.display_name} has been qualified again")

    @commands.command(name="my_votes")
    async def my_votes(self, ctx: commands.Context):
        """gives you a list of all images you have voted on"""
        votes = await self.get_votes_of_user(ctx.author.id)
        if not votes:
            await ctx.send("You haven't voted yet")
        paginator = commands.Paginator(prefix=None, suffix=None)
        paginator.add_line("You have voted for the following entries: ")
        for vote in votes:
            paginator.add_line(f"https://discordapp.com/channels/{self.contest_channel.guild.id}/{self.contest_channel.id}/{vote['message_id']}")
        for page in paginator.pages:
            await ctx.send(page)


    @commands.command(name="submit", hidden=True)
    @commands.dm_only()
    async def contest_submit(self, ctx, url : typing.Optional[str]):
        """
        allows you to submit to the contest
        """
        if os.path.exists("data/.contest_closed"):
            await ctx.send("contest is closed")
            return
        if not self.contestant_check(ctx):
            await ctx.send("you are not a contestant")
            return
        number_of_entries = await self.check_contestant_entries(ctx.author.id)
        if number_of_entries and number_of_entries >= 3:
            await ctx.send("you already have 3 entries")
            return
        else:
            attachment = ctx.message.attachments[0] if ctx.message.attachments else None
            if attachment:
                submission = io.BytesIO(await attachment.read())
                contest_entry = await self.contest_channel.send(file=discord.File(submission, attachment.filename))
            else:
                file_ext = mime.guess_type(url)[0].split("/")[1]
                if mime.guess_type(url)[0].split("/")[0] == "image":
                    async with self.session.get(url) as resp:
                        image_bytes = await resp.read()
                        submission = io.BytesIO(image_bytes)
                        try:
                            contest_entry = await self.contest_channel.send(
                                file=discord.File(submission, "submission."+file_ext))
                        except discord.HTTPException as e:
                            if e.status == 413:
                                await ctx.send("File too big")
                            return

                else:
                    await ctx.send("Please only send images")
                    return
            await contest_entry.add_reaction("\N{THUMBS UP SIGN}")
            await contest_entry.add_reaction("\N{CROSS MARK}")
            await self.add_contest_entry(ctx.author.id, contest_entry)
            await ctx.send("your entry has been submitted")

    @commands.command(name="enter", hidden=True)
    @commands.dm_only()
    async def enter_contest(self, ctx):
        """
        allows you to enter the contest
        """
        disqualified = await self.fetch_disqualified(ctx.author.id)
        if disqualified:
            await ctx.send("you have been disqualified you are not allowed to enter the contest")
        else:
            member = self.contest_channel.guild.get_member(ctx.author.id)
            await member.add_roles(self.contestant_role)
            await ctx.send("congratulations you have entered the contest")


    @commands.Cog.listener("on_raw_reaction_add")
    async def on_picture_vote(self, payload):
        if payload.channel_id != self.contest_channel.id or str(payload.emoji) != "\N{THUMBS UP SIGN}"\
                or payload.user_id == self.bot.user.id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        message_entry = await self.contest_channel.fetch_message(payload.message_id)
        member = guild.get_member(payload.user_id)
        try:
            if self.contestant_role in member.roles:
                entries = await self.list_contest_entries(user_id=member.id)
                if message_entry.id in [entry["message_id"] for entry in entries]:
                    await message_entry.remove_reaction("\N{THUMBS UP SIGN}", member)
                    await member.send("don't vote on your own entries dummy :T")
                    return
            await message_entry.remove_reaction("\N{THUMBS UP SIGN}", member)
            await self.add_vote_to_entry(payload.user_id, payload.message_id)
            await member.send(f"you have successfully voted on the following entry: {message_entry.jump_url}")
        except asyncpg.PostgresError as e:
            logger = logging.getLogger('PoutyBot')
            logger.error(e)
        except discord.Forbidden:
            pass

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_picture_unvote(self, payload):
        if payload.channel_id != self.contest_channel.id or str(payload.emoji) != "\N{CROSS MARK}" \
                or payload.user_id == self.bot.user.id:
            return
        try:
            message_entry = await self.contest_channel.fetch_message(payload.message_id)
            member = self.contest_channel.guild.get_member(payload.user_id)
            deleted = await self.remove_vote_from_entry(payload.user_id, payload.message_id)
            await message_entry.remove_reaction("\N{CROSS MARK}", member)
            if deleted:
                await member.send(f"vote removed for the following entry: {message_entry.jump_url}")
        except asyncpg.PostgresError as e:
            logger = logging.getLogger('PoutyBot')
            logger.error(e)
        except discord.Forbidden:
            pass

    def is_setup_complete(self):
        return self.contestant_role and self.contest_channel

    @commands.group(name="contest", invoke_without_command=True)
    async def contest(self, ctx: commands.context):
        pass

    @contest.command(name="start")
    @is_owner_or_moderator()
    async def contest_start(self, ctx):
        """creates the contest channel and role and sets their permissions"""
        if os.path.exists("data/.contest_closed"):
            try:
                os.remove("data/.contest_closed")
            except OSError:
                await ctx.send("could not delete contest closed file")
        current_guild = ctx.guild
        overwrite_memester = self.set_memester_permission(current_guild)
        overwrite_contestant = self.set_contestant_permission(current_guild)
        overwrite_everyone = self.set_default_permission(current_guild)
        everyone = current_guild.default_role
        memester = current_guild.get_role(514884001417134110)
        self.contestant_role = await current_guild.create_role(name="contestant")
        await self.contestant_role.edit(position=memester.position)
        self.contest_channel = await current_guild.create_text_channel(name="contest-channel")
        await self.contest_channel.set_permissions(target=self.contestant_role, overwrite=overwrite_contestant)
        await self.contest_channel.set_permissions(target=memester, overwrite=overwrite_memester)
        await self.contest_channel.set_permissions(target=everyone, overwrite=overwrite_everyone)
        await self.save_settings(self.contestant_role.id, self.contest_channel.id, ctx.guild.id)
        await ctx.send("contest has been started")


    @contest.command(name="cleanup")
    @is_owner_or_moderator()
    async def cleanup_contest(self, ctx):
        """small help command for resetting before contest"""
        await self.contestant_role.delete()
        await self.contest_channel.delete()
        await self.empty_table()
        self.contestant_role = None
        self.contest_channel = None
        await ctx.send("contest reset")

    @contest.command(name="close")
    @is_owner_or_moderator()
    async def close_contest(self, ctx: commands.Context):
        """close the contest"""
        try:
            with open("data/.contest_closed", 'x') as f:
                pass
        except OSError:
            await ctx.send("contest already closed")
            return
        await ctx.send("contest closed")

    def set_default_permission(self, current_guild):
        overwrite_everyone = discord.PermissionOverwrite()
        overwrite_everyone.read_messages = False
        return overwrite_everyone

    def set_memester_permission(self, current_guild):
        overwrite_memester = discord.PermissionOverwrite()
        overwrite_memester.send_messages = False
        overwrite_memester.read_messages = False
        return overwrite_memester

    def set_contestant_permission(self, current_guild):
        overwrite_contestant = discord.PermissionOverwrite()
        overwrite_contestant.send_messages = False
        overwrite_contestant.read_messages = False
        return overwrite_contestant


def setup(bot):
    bot.add_cog(Contest(bot))


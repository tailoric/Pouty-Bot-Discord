from typing import Optional
from discord.ext import commands
from .utils import checks
from .utils.dataIO import DataIO
from discord import Member, Embed, Role, utils
import discord
from datetime import datetime,timedelta
import time
import re
from typing import Union
import json


class Userinfo(commands.Cog):
    """show infos about the current or other users"""
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.create_name_tables())

    @commands.command(pass_context=True)
    async def userinfo(self,ctx, *, member: Member=None):
        """shows the info about yourself or another user"""
        if member is None:
            member = ctx.message.author
        join_date = member.joined_at
        created_at = member.created_at
        user_color = member.color
        user_roles = member.roles.copy()
        server = ctx.message.guild
        if member.nick:
            nick = member.nick
        else:
            nick = member.name
        time_fmt = "%d %b %Y %H:%M"
        joined_number_of_days_diff = (datetime.utcnow() - join_date).days
        created_number_of_days_diff = (datetime.utcnow() - created_at).days
        member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
        embed = Embed(description="[{0.name}#{0.discriminator} - {1}]({2})".format(member, nick, member.avatar_url), color=user_color)
        if member.avatar_url:
            embed.set_thumbnail(url=member.avatar_url)
        else:
            embed.set_thumbnail(url=member.default_avatar_url)
        embed.add_field(name="Joined Discord on",
                        value="{}\n({} days ago)".format(member.created_at.strftime(time_fmt),
                                                        created_number_of_days_diff),
                        inline=True)
        embed.add_field(name="Joined Server on",
                        value="{}\n({} days ago)".format(member.joined_at.strftime(time_fmt),
                                                        joined_number_of_days_diff),
                        inline=True)


        user_roles.pop(0)
        if user_roles:
            embed.add_field(name="Roles", value=", ".join([x.mention for x in user_roles]), inline=True)
        embed.set_footer(text="Member #{} | User ID: {}".format(member_number, member.id))
        await ctx.send(embed=embed)

    @commands.command(aliases=["avi", "profile_pic"])
    async def pfp(self, ctx, member: Union[discord.Member, str] = None):
        """
        makes the bot post the pfp of a member
        """
        if isinstance(member, discord.Member):
            await ctx.send(member.avatar_url_as(static_format="png"))
        elif isinstance(member, str):
            pattern = re.compile(r'(<@!?)?(\d{17,})>?')
            match = pattern.match(member)
            if match and match.group(2):
                user = await self.bot.fetch_user(int(match.group(2)))
                if user:
                    await ctx.send(user.avatar_url_as(static_format="png"))
            else:
                await ctx.send("Not a valid user ID or mention")

        else:
            await ctx.send(ctx.author.avatar_url_as(static_format="png"))

    @commands.command(pass_context=True)
    async def serverinfo(self, ctx):
        """shows info about the current server"""
        server = ctx.message.guild
        time_fmt = "%d %b %Y %H:%M"
        creation_time_diff = int(time.time() - time.mktime(server.created_at.timetuple())) // (3600 * 24)
        users_total = len(server.members)
        users_online = len([m for m in server.members if m.status == discord.Status.online or
                            m.status == discord.Status.idle])
        colour = server.me.colour
        if server.icon:
            embed = Embed(description="[{}]({})\nCreated {} ({} days ago)"
                          .format(server.name, server.icon_url, server.created_at.strftime(time_fmt), creation_time_diff),
                          color=colour)
            embed.set_thumbnail(url=server.icon_url)
        else:
            embed = Embed(description="{}\nCreated {} ({} days ago)"
                          .format(server.name, server.created_at.strftime(time_fmt), creation_time_diff))
        embed.add_field(name="Region", value=str(server.region))
        embed.add_field(name="Users", value="{}/{}".format(users_online, users_total))
        embed.add_field(name="Text Channels", value="{}"
                        .format(len([x for x in server.channels if type(x) == discord.TextChannel])))
        embed.add_field(name="Voice Channels", value="{}"
                        .format(len([x for x in server.channels if type(x) == discord.VoiceChannel])))
        embed.add_field(name="Roles", value="{}".format(len(server.roles)))
        embed.add_field(name="Owner", value=str(server.owner))
        embed.set_footer(text="Server ID: {}".format(server.id))

        await ctx.send(embed=embed)

    @commands.command()
    async def roleinfo(self, ctx, role=None):
        """shows information about the server roles"""
        role_converter = commands.RoleConverter()
        server = ctx.message.guild
        roles = server.roles
        embed = Embed()
        embed.set_thumbnail(url=server.icon_url)
        if not role:
            for role in roles:
                if role.name == "@everyone":
                    continue
                member_with_role = [member for member in server.members if role in member.roles]
                embed.add_field(name=role.name, value="{} Member(s)".format(len(member_with_role)))
        else:
            role = await role_converter.convert(ctx=ctx, argument=role)
            member_with_role = [member for member in server.members if role in member.roles]
            embed.add_field(name=role.name, value="{} Member(s)".format(len(member_with_role)))
        await ctx.send(embed=embed)

    async def fetch_names(self, member):
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare('''
                SELECT *
                FROM (
                    SELECT DISTINCT ON (name) *
                    from names
                    where user_id = $1
                 ) p
                ORDER BY change_date DESC
                LIMIT 20
            ''')
            return await stmt.fetch(member.id)

    async def fetch_nicknames(self, member):
        async with self.bot.db.acquire() as con:
            stmt = await con.prepare('''
                SELECT *
                FROM (
                    SELECT DISTINCT ON (nickname) *
                    from nicknames
                    where user_id = $1
                 ) p
                ORDER BY change_date DESC
                LIMIT 20
            ''')
            return await stmt.fetch(member.id)

    async def create_name_tables(self):
        query = '''
                CREATE TABLE IF NOT EXISTS names(
                    user_id BIGINT,
                    name varchar(32),
                    change_date timestamp
                );
                CREATE TABLE IF NOT EXISTS nicknames(
                    user_id BIGINT,
                    nickname varchar(32),
                    change_date timestamp
                );
        '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query)

    @commands.is_owner()
    @commands.command()
    async def lnames(self, ctx):
        data_io = DataIO()
        entries = data_io.load_json('names')
        for entry in entries:
            names = entries[entry].get("names", [])
            nicknames = entries[entry].get("nicknames", [])

            async with self.bot.db.acquire() as con:
                for name in names:
                    stmt = await con.prepare('''
                                   INSERT INTO names VALUES ($1,$2,current_timestamp)
                                   RETURNING *
                               ''')
                    async with con.transaction():
                        await stmt.fetch(int(entry), name)
                for nickname in nicknames:
                    stmt = await con.prepare('''
                                   INSERT INTO nicknames VALUES ($1,$2,current_timestamp)
                                   RETURNING *
                               ''')
                    async with con.transaction():
                        await stmt.fetch(int(entry), nickname)

    @commands.command()
    async def names(self, ctx, member: Member=None):
        """
        lists the past 20 names and nicknames of a user
        """
        if not member:
            member = ctx.message.author
        data_names = await self.fetch_names(member)
        data_nicknames = await self.fetch_nicknames(member)
        nickname_list = []
        names_list = []
        for entry in data_names:
            names_list.append(entry['name'])
        for entry in data_nicknames:
            nickname_list.append(entry['nickname'])
        if member.name not in names_list:
            names_list.insert(0, member.name)
        if member.nick not in nickname_list and member.nick:
            nickname_list.insert(0, member.nick)
        message_fmt = "**Past 20 names:**\n{}\n" \
                      "**Past 20 nicknames:**\n{}"
        names_list_str = discord.utils.escape_markdown(", ".join(names_list))
        display_names_list_str = discord.utils.escape_markdown(", ".join(nickname_list))
        await ctx.send(message_fmt.format(names_list_str, display_names_list_str))

    @commands.Cog.listener("on_member_update")
    async def save_nickname_change(self, before, after):
        forbidden_word_regex = re.compile(r'(trap|nigg(a|er)|fag(got)?)')
        if forbidden_word_regex.search(before.display_name) or forbidden_word_regex.search(after.display_name):
            return
        if before.nick != after.nick and after.nick:
            async with self.bot.db.acquire() as con:
                stmt = await con.prepare('''
                               INSERT INTO nicknames VALUES ($1,$2,current_timestamp)
                               RETURNING *
                           ''')
                async with con.transaction():
                    new_row = await stmt.fetch(after.id, after.nick)

    @commands.Cog.listener("on_user_update")
    async def save_username_change(self, before, after):
        forbidden_word_regex = re.compile(r'(trap|nigg(a|er)|fag(got)?)')
        if forbidden_word_regex.search(before.name) or forbidden_word_regex.search(after.name):
            return
        if before.name != after.name:
            async with self.bot.db.acquire() as con:
                stmt = await con.prepare('''
                    INSERT INTO names VALUES ($1,$2,current_timestamp)
                    RETURNING *
                ''')
                async with con.transaction():
                    new_row = await stmt.fetch(after.id, after.name)








def setup(bot):
    bot.add_cog(Userinfo(bot=bot))

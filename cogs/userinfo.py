from typing import Optional
from discord.ext import commands
from .utils import checks
from .utils.dataIO import DataIO
from discord import Member, User, Embed, Role, utils, ActivityType
import discord
from datetime import datetime,timedelta, timezone
import time
import re
from typing import Union, Optional
import json

snowflake_regex = re.compile(r"(\d{17,19})")
class ShowAllAvatars(discord.ui.View):

    def __init__(self, member: Union[discord.Member, discord.User]):
        super().__init__()
        self.member = member
        self.add_item(discord.ui.Button(label="Default avatar", url=member.default_avatar.url)) 
        if member.avatar:
            self.add_item(discord.ui.Button(label="User avatar",url=member.avatar.url))
        if isinstance(member, discord.Member) and member.guild_avatar:
            self.add_item(discord.ui.Button(label="Server avatar", url=member.guild_avatar.url)) 

class ShowUserAvatarView(discord.ui.View):

    def __init__(self, member: discord.Member, timeout=180):
        super().__init__(timeout=timeout)
        if member.avatar:
            self.add_item(discord.ui.Button(url=member.avatar.url, label="User Avatar"))

class ObjectConversionError(commands.CheckFailure):
    pass

class CustomMemberOrUserConverter(commands.MemberConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except (commands.CommandError, commands.BadArgument):
            return await ctx.bot.fetch_user(argument)

class ObjectConverter(commands.Converter):
    async def convert(self, ctx, argument):
        if(match := snowflake_regex.search(argument)):
            return discord.Object(int(match.group(1)))
        else:
            raise ObjectConversionError("Invalid Discord Id passed")

def format_dt(dt: datetime, /, style: str=None) -> str:
    if not style:
        style="f"
    return f"<t:{int(dt.timestamp())}:{style}>"

class Userinfo(commands.Cog):
    """show infos about the current or other users"""
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.loop.create_task(self.create_name_tables())

    @commands.command()
    async def userinfo(self,ctx, *, member: Optional[CustomMemberOrUserConverter]):
        """shows the info about yourself or another user"""
        if member is None:
            member = ctx.message.author

        avatar_url = member.display_avatar.url
        if isinstance(member, discord.User):
            embed = Embed(description="[{0}]({1})".format(member, avatar_url))
            embed.add_field(name="Joined Discord on",
                            value=f"{format_dt(member.created_at)}({format_dt(member.created_at, 'R')})")
            embed.add_field(name="Mention", value=member.mention)
            embed.add_field(name="ID", value=member.id)
            embed.set_thumbnail(url=avatar_url)
            return await ctx.send(embed=embed)
        join_date = member.joined_at
        user_color = member.color
        user_roles = member.roles.copy()
        if member.nick:
            nick = member.nick
        else:
            nick = member.name
        member_number = 1
        if ctx.guild:
            server = ctx.message.guild
            member_number = sorted(server.members, key=lambda m: m.joined_at).index(member) + 1
        embed = Embed(description="[{0} - {1}]({2})".format(member, nick, avatar_url), color=user_color)
        embed.set_thumbnail(url=avatar_url)
        try:
            user = await self.bot.fetch_user(member.id)
            embed.set_image(url=user.banner.url)
        except:
            pass

        embed.add_field(name="Joined Discord on",
                value=f"{format_dt(member.created_at)}({format_dt(member.created_at, style='R')})",
                inline=True)
        embed.add_field(name="Joined Server on",
                value=f"{format_dt(member.joined_at)}({format_dt(member.joined_at, style='R')})",
                inline=True)
        user_roles.pop(0)
        if member.activity:
            activity = member.activity
            field_value = '\u200b'
            if isinstance(activity, discord.Game):
                field_value = activity.name
            elif isinstance(activity, discord.Streaming):
                field_value = f'On {activity.platform}: [**{activity.name}**]({activity.url})'
            elif isinstance(activity, discord.CustomActivity):
                if activity.emoji and activity.emoji.is_unicode_emoji(): 
                    field_value = f'{activity.emoji.name} '
                field_value += f'{activity.name}'
            elif isinstance(activity, discord.Spotify):
                field_value = f'{activity.title} - {activity.artist}'
            elif isinstance(activity, discord.Activity):
                since = ''
                if activity.start:
                    time_diff = datetime.now(timezone.utc).replace(microsecond=0) - activity.start.replace(microsecond=0)
                    since = f'For {time_diff}'

                field_value = f'**{activity.name}**: {activity.details}\n{since}'
            else:
                pass
            if activity.type:
                title = activity.type.name.title()
                if activity.type == discord.ActivityType.custom:
                    title = "Status"
                embed.add_field(name=title, value=field_value, inline=False)
            else:
                embed.add_field(name="Status", value=field_value, inline=False)

        if user_roles:
            embed.add_field(name="Roles", value=", ".join([x.mention for x in user_roles]), inline=False)
        embed.set_footer(text="Member #{} | User ID: {}".format(member_number, member.id))
        await ctx.send(embed=embed, view=ShowUserAvatarView(member=member))

    @commands.command(aliases=["avi", "profile_pic"])
    async def pfp(self, ctx, *, member: Union[discord.Member, discord.User] = None):
        """
        makes the bot post the pfp of a member
        """
        if not member:
            member = ctx.author
        embeds = []
        view = None
        if member.avatar:
            user_embed = discord.Embed(title=f"{member}'s user avatar",colour=member.colour).set_image(url=member.avatar.url)
            embeds.append(user_embed)
        if isinstance(member, discord.Member) and member.guild_avatar:
            server_embed = discord.Embed(title=f"{member}'s server avatar",colour=member.colour).set_image(url=member.guild_avatar.url)
            embeds.append(server_embed)
        if len(embeds) == 0:
            embeds.append(discord.Embed(url=member.default_avatar, colour=member.colour).set_image(url=member.default_avatar))
        view = ShowAllAvatars(member)
        await ctx.send(embeds=embeds, view=view)

    @commands.command()
    async def serverinfo(self, ctx):
        """shows info about the current server"""
        guild = ctx.message.guild
        time_fmt = "%d %b %Y %H:%M"
        users_total = len(guild.members)
        users_online = len([m for m in guild.members if m.status == discord.Status.online or
                            m.status == discord.Status.idle])
        colour = guild.me.colour
        embed = Embed(description="[{}]({})\nCreated {} ({})"
                      .format(guild.name, guild.icon, format_dt(guild.created_at), format_dt(guild.created_at,'R')),
                      color=colour)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Users", value="{}/{}".format(users_online, users_total))
        embed.add_field(name="Text Channels", value="{}"
                        .format(len([x for x in guild.channels if type(x) == discord.TextChannel])))
        embed.add_field(name="Voice Channels", value="{}"
                        .format(len([x for x in guild.channels if type(x) == discord.VoiceChannel])))
        embed.add_field(name="Roles", value="{}".format(len(guild.roles)))
        embed.add_field(name="Owner", value=guild.owner.mention)
        embed.set_footer(text="Guild ID: {}".format(guild.id))

        await ctx.send(embed=embed)

    @commands.command(name="created", aliases=["age"])
    async def created_at(self, ctx, discord_id: ObjectConverter):
        """
        Provide a mention or id of an discord object (channel, user, message, emote) to find out when it was created
        """
        embed = discord.Embed(title="Age of Discord Object", description=f"This discord object was created at {discord.utils.format_dt(discord_id.created_at)} ({discord.utils.format_dt(discord_id.created_at, 'R')})", colour=ctx.guild.me.colour)
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
    async def names(self, ctx, member: Union[Member, User]=None):
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
        if not isinstance(member, User) and member.nick and member.nick not in nickname_list:
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








async def setup(bot):
    await bot.add_cog(Userinfo(bot=bot))

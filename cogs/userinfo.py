from discord.ext import commands
from .utils import checks
from .utils.dataIO import DataIO
from discord import Member, Embed, Role, utils
import discord
from datetime import datetime,timedelta
import time


class Userinfo(commands.Cog):
    """show infos about the current or other users"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    async def userinfo(self,ctx, member: Member=None):
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
        joined_number_of_days_diff = (datetime.now() - join_date).days
        created_number_of_days_diff = (datetime.now() - created_at).days
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
            embed.add_field(name="Roles", value=", ".join([x.name for x in user_roles]), inline=True)
        embed.set_footer(text="Member #{} | User ID: {}".format(member_number, member.id))
        await ctx.send(embed=embed)

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

    @checks.is_owner_or_moderator()
    @commands.command(pass_context=True)
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

    @commands.command()
    async def names(self, ctx, member: Member=None):
        """
        lists the past 20 names and nicknames of a user
        """
        dataIO = DataIO()
        if member:
            member_id = member.id
        else:
            member = ctx.message.author
            member_id = member.id
        data = dataIO.load_json("names")
        member_name_data = data.get(str(member_id), {})
        nickname_list = member_name_data.get("nicknames", [])
        names_list = member_name_data.get("names", [])
        if member.name not in names_list:
            names_list.append(member.name)
        if member.display_name not in nickname_list:
            nickname_list.append(member.display_name)
        message_fmt = "**Past 20 names:**\n{}\n" \
                      "**Past 20 nicknames:**\n{}"
        await ctx.send(message_fmt.format(", ".join(names_list), ", ".join(nickname_list)))

    @commands.Cog.listener("on_member_update")
    async def save_nickname_change(self, before, after):
        if before.display_name != after.display_name:
            dataIO = DataIO()
            data = dataIO.load_json("names")
            member_name_info = data.get(str(before.id), {})
            nickname_list = member_name_info.get("nicknames", [])
            if before.display_name not in nickname_list:
                nickname_list.append(before.display_name)
            nickname_list.append(after.display_name)
            if len(nickname_list) > 20:
                nickname_list.pop(0)
            member_name_info["nicknames"] = nickname_list
            data[str(before.id)] = member_name_info
            dataIO.save_json("names", data)

    @commands.Cog.listener("on_user_update")
    async def save_username_change(self, before, after):
        if before.name != after.name:
            dataIO = DataIO()
            data = dataIO.load_json("names")
            member_name_info = data.get(str(before.id), {})
            name_list = member_name_info.get("names", [])
            if before.display_name not in name_list:
                name_list.append(before.name)
            name_list.append(after.name)
            if len(name_list) > 20:
                name_list.pop(0)
            member_name_info["names"] = name_list
            data[str(before.id)] = member_name_info
            dataIO.save_json("names", data)








def setup(bot):
    bot.add_cog(Userinfo(bot=bot))

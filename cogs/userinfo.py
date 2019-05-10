from discord.ext import commands
from .utils import checks
from discord import Member, Embed, Role, utils
import discord
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
        joined_number_of_days_diff = int((time.time() - time.mktime(join_date.timetuple())) // (3600 * 24))
        created_number_of_days_diff = int((time.time() - time.mktime(created_at.timetuple())) // (3600 * 24))
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

def setup(bot):
    bot.add_cog(Userinfo(bot=bot))

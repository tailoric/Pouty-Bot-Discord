from discord.ext import commands
from discord.utils import find
import json
import discord
from os import path



def is_owner_check(message):
    with open('data/credentials.json', 'r') as f:
        credentials = json.load(f)
        return message.author.id == int(credentials['owner'])


def is_owner():
    return commands.check(lambda ctx: is_owner_check(ctx.message))


def is_owner_or_admin_check(message):
    if is_owner_check(message):
        return True
    if not message.guild:
        return False
    return message.author.guild_permissions.administrator 


def is_owner_or_moderator_check(message):
    if is_owner_or_admin_check(message):
        return True
    if not message.guild:
        raise commands.CheckFailure("This command can only be used in servers/guilds")
    for role in message.author.roles:
        if role.name == "Discord-Senpai" or role.name == "Moderators":
            return True
        else:
            raise commands.CheckFailure("This command is only for Moderators")


def is_owner_or_admin():
    return commands.check(lambda ctx: is_owner_or_admin_check(ctx.message))


def is_owner_or_moderator():
    return commands.check(lambda ctx: is_owner_or_moderator_check(ctx.message))


def channel_only(*channels):
    def predicate(ctx):
        if not ctx.guild:
            return True
        if ctx.channel.id in channels or ctx.channel.name in channels:
            return True
        if ctx.guild:
            channel_mentions= [f"<#{ch.id}>" for ch in ctx.guild.text_channels
                               if ch.id in channels or ch.name in channels]
            if not channel_mentions:
                raise commands.CheckFailure("You can't use the command on this server.")
            raise commands.CheckFailure(f"Please use the command only in the following channels:\n"
                                        f"{' '.join(channel_mentions)}")
        raise commands.CheckFailure("Can't use  this command in DMs")
    return commands.check(predicate)

def user_is_in_whitelist_server(bot: commands.Bot, user: discord.User):
    if not path.exists('data/server_whitelist.json'):
        f = open('data/server_whitelist.json', 'w')
        json.dump([], f)
        f.close()
    with open('data/server_whitelist.json') as f:
        server_whitelist = json.load(f)
        for server_id in server_whitelist:
            server = bot.get_guild(server_id)
            if server:
                member = find(lambda m: m.id == user.id, server.members)
                if member:
                    return True
        return False


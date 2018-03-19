from discord.ext import commands
import json


def is_owner_check(message):
    with open('data/credentials.json', 'r') as f:
        credentials = json.load(f)
        return message.author.id == credentials['owner']

def is_owner():
    return commands.check(lambda ctx: is_owner_check(ctx.message))


def is_owner_or_admin_check(message):
   return message.author.server_permissions.administrator or is_owner_check(message)


def is_owner_or_moderator_check(message):
    if is_owner_or_admin_check(message):
        return True
    for role in message.author.roles:
        if role.name == "Discord-Senpai":
            return True


def is_owner_or_admin():
    return commands.check(lambda ctx: is_owner_or_admin_check(ctx.message))


def is_owner_or_moderator():
    return commands.check(lambda ctx: is_owner_or_moderator_check(ctx.message))

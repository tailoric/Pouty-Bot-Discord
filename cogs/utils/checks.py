from discord.ext import commands
import discord.utils

def is_owner_check(message):
    return message.author.id == '134310073014026242'

def is_shadow_check(message):
    return message.author.id == '191782132002193410'

def is_shadow():
    return commands.check(lambda ctx: is_shadow_check(ctx.message))

def is_owner():
    return commands.check(lambda ctx: is_owner_check(ctx.message))

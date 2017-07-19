import discord
from discord.ext import commands
import json
import random
description = 'a very pouty bot'

bot = commands.Bot(command_prefix=['!','.'], description=description)


def load_credentials():
    with open('data/credentials.json') as f:
        return json.load(f)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('-'*8)
@bot.event
async def on_command_error(error,ctx):
    if isinstance(error, commands.CommandNotFound):
        if not ctx.message.content.startswith('..'):
            await bot.send_message(ctx.message.channel, "This command does not exist")


if __name__ == '__main__':
    credentials = load_credentials()
    init_extensions = [
        'cogs.owner',
        'cogs.social',
        'cogs.wolfram',
        'cogs.youtube',
        'cogs.image_search',
        'cogs.waifu2x',
        'cogs.wuxia'
        ]
    try:
        for extension in init_extensions:
            bot.load_extension(extension)
    except Exception as e:
        print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
    bot.client_id = credentials['client-id']
    token = credentials['token']
    bot.run(token)

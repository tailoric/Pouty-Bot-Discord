import discord
from discord.ext import commands
import json
import logging
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
      logger.log(logging.INFO,error)


if __name__ == '__main__':
    credentials = load_credentials()
    init_extensions = [
        'cogs.owner',
        'cogs.image_search',
        'cogs.social',
        'cogs.playlist',
        'cogs.wolfram',
        'cogs.danbooru'
        ]
    try:
        for extension in init_extensions:
            bot.load_extension(extension)
    except Exception as e:
        print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))
    bot.client_id = credentials['client-id']
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    token = credentials['token']
    bot.run(token)

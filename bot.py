import discord
from discord.ext import commands
import json
import logging
from cogs.utils.formatter import CustomHelpFormatter
import sys
from cogs.utils import checks

description = 'Pouty Bot MKII by Saikimo'

bot = commands.Bot(command_prefix=['!','.'], description=description, formatter=CustomHelpFormatter())


def load_credentials():
    with open('data/credentials.json') as f:
        return json.load(f)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('-'*8)
    with open('data/initial_cogs.json') as f:
        init_extensions = json.load(f)
    try:
        for extension in init_extensions:
            bot.load_extension(extension)
        print(discord.utils.oauth_url(credentials['client-id']))
    except Exception as e:
        print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))

@bot.event
async def on_command_error(error, ctx):
  if isinstance(error, commands.CommandNotFound):
      logger.log(logging.INFO, error)

@bot.event
async def on_message(message):
    if bot.get_cog("Owner"):
        global_ignores = bot.get_cog("Owner").global_ignores
        if not message.author.id in global_ignores or checks.is_owner_check(message):
            await bot.process_commands(message)
    else:
        await bot.process_commands(message)
async def shutdown(bot, *,restart=False):
    """Gracefully quits bot with exit code 0"""
    await bot.logout()
    exit(0)

if __name__ == '__main__':
    credentials = load_credentials()
    bot.client_id = credentials['client-id']
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    token = credentials['token']
    try:
        bot.run(token)
    except KeyboardInterrupt:
        print("Keyboard interrupt exiting with error code 0")
        sys.exit(0)

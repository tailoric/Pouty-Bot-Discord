import discord
import os
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
    error_message_sent = False
    if isinstance(error, commands.CheckFailure):
        await bot.send_message(ctx.message.channel, "You don't have permission to use this command")
        error_message_sent = True
    if not isinstance(error, commands.CommandNotFound) and not error_message_sent:
        await bot.send_message(ctx.message.channel, error)
        if ctx.command.help is not None:
            await bot.send_message(ctx.message.channel, "```\n{}\n```".format(ctx.command.help))
    logger.log(logging.INFO, error)

@bot.event
async def on_message(message):
    server = message.server
    owner_cog = bot.get_cog("Owner")
    if owner_cog:
        global_ignores = owner_cog.global_ignores
        message_split = message.content[1:].split(" ")
        if len(message.content) == 0 or not message_split or message.content[0] not in bot.command_prefix:
            return
        invoked_command = bot.get_command(message_split[0])
        if not invoked_command:
            return
        if server is None:
            if checks.user_is_in_whitelist_server(bot, message.author):
                await bot.process_commands(message)
                return
            else:
                if str(invoked_command) in [dc['command'] for dc in owner_cog.disabled_commands]:
                    await bot.send_message(message.channel, "command disabled")
                    return
                else:
                    await bot.process_commands(message)
        disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands if dc["server"] == server.id]
        if str(invoked_command) in disabled_commands:
            await bot.send_message(message.channel, "command disabled")
            return
        if message.author.id in global_ignores and not checks.is_owner_check(message):
            return
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

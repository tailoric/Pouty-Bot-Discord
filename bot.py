import discord
from discord.ext import commands
from cogs.utils.dataIO import DataIO
import logging
import sys
from cogs.utils import checks
import pdb


description = 'Pouty Bot MKII by Saikimo'

data_io = DataIO()
bot = commands.Bot(command_prefix=['!', '.'], description=description)


def load_credentials():
    return data_io.load_json("credentials")



@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('-'*8)
    try:
        init_extensions = data_io.load_json("initial_cogs")
        for extension in init_extensions:
            bot.load_extension(extension)
        print(discord.utils.oauth_url(credentials['client-id']))
    except Exception as e:
        print('Failed to load extension {}\n{}: {}'.format(extension, type(e).__name__, e))


@bot.event
async def on_command_error(ctx, error):
    error_message_sent = False
    if isinstance(error, commands.CheckFailure):
        await ctx.message.channel.send("You don't have permission to use this command")
        error_message_sent = True
    if not isinstance(error, commands.CommandNotFound) and not error_message_sent:
        await ctx.message.channel.send(error)
        if ctx.command.help is not None:
            await ctx.message.channel.send( "```\n{}\n```".format(ctx.command.help))
    logger.log(logging.INFO, error)


@bot.event
async def on_message(message):
    server = message.guild
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
                    await message.channel.send("command disabled")
                    return
                else:
                    await bot.process_commands(message)
                    return
        disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands if dc["server"] == int(server.id)]
        if str(invoked_command) in disabled_commands:
            await message.channel.send("command disabled")
            return
        if message.author.id in global_ignores and not checks.is_owner_check(message):
            return
        await bot.process_commands(message)
    else:
        await bot.process_commands(message)


async def shutdown(bot, *, restart=False):
    """Gracefully quits bot with exit code 0"""
    await bot.logout()
    if restart:
        exit(1)
    else:
        exit(0)


if __name__ == '__main__':
    credentials = load_credentials()
    bot.client_id = credentials['client-id']
    logger = logging.getLogger('PoutyBot')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    token = credentials['token']

    try:
        bot.run(token)
    except KeyboardInterrupt:
        print("Keyboard interrupt exiting with error code 0")
        sys.exit(0)

import discord
from discord.ext import commands
from cogs.utils.formatter import CustomHelpCommand
from cogs.utils.dataIO import DataIO
from cogs.utils.exceptions import DisabledCommandException
import logging
import sys
from cogs.utils import checks
import pdb


description = 'Pouty Bot MKII by Saikimo'

data_io = DataIO()
bot = commands.Bot(command_prefix=['!', '.'], description=description, help_command=CustomHelpCommand())


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
    if isinstance(error, DisabledCommandException):
        await ctx.message.channel.send("Command is disabled")
        error_message_sent = True
    if isinstance(error, commands.CheckFailure) and not error_message_sent:
        await ctx.message.channel.send("You don't have permission to use this command")
        error_message_sent = True
    if not isinstance(error, commands.CommandNotFound) and not error_message_sent:
        await ctx.message.channel.send(error)
        if ctx.command.help is not None:
            await ctx.message.channel.send("```\n{}\n```".format(ctx.command.help))
    logger.log(logging.INFO, error)


@bot.check
async def check_for_black_list_user(ctx):
    owner_cog = bot.get_cog("Owner")
    if owner_cog:
        return ctx.author.id not in owner_cog.global_ignores
    return True


@bot.check
async def check_disabled_command(ctx):
    owner_cog = bot.get_cog("Owner")
    if owner_cog:
        current_guild = ctx.guild
        disabled_commands = [dc["command"] for dc in owner_cog.disabled_commands if dc["server"] == current_guild.id]
        if ctx.command.name in disabled_commands and not checks.user_is_in_whitelist_server(bot, ctx.author):
            raise DisabledCommandException()
    return True




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

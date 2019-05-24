from discord.ext import commands
from cogs.utils.dataIO import DataIO
import logging
import sys


description = 'Pouty Bot MKII by Saikimo'

data_io = DataIO()
bot = commands.Bot(command_prefix=['!', '.'], description=description)


def load_credentials():
    return data_io.load_json("credentials")


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
        bot.load_extension("cogs.default")
        bot.run(token)
    except KeyboardInterrupt:
        print("Keyboard interrupt exiting with error code 0")
        sys.exit(0)

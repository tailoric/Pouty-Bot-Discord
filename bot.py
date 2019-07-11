from discord.ext import commands
from cogs.utils.dataIO import DataIO
import logging
import asyncpg
import sys
import asyncio

if 'win32' in sys.platform:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

description = 'Pouty Bot MKII by Saikimo'

data_io = DataIO()
bot = commands.Bot(command_prefix=['!', '.'], description=description, owner_id=134310073014026242)


def load_credentials():
    return data_io.load_json("credentials")

async def connect_db_and_start_bot():
    token = credentials['token']
    db_info = data_io.load_json("postgres")
    bot.db = await asyncpg.create_pool(database=db_info['dbname'], user=db_info['user'], password=db_info["password"],
                                       host="127.0.0.1")

    try:
        bot.load_extension("cogs.default")
        await bot.start(token)
    except KeyboardInterrupt:
        print("closing connection")
        await bot.db.close()
        await bot.logout()

if __name__ == '__main__':
    credentials = load_credentials()
    bot.client_id = credentials['client-id']
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect_db_and_start_bot())


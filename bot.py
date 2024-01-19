from discord.ext import commands
from discord import Intents
import discord
from cogs.utils.dataIO import DataIO
import logging
from logging.handlers import RotatingFileHandler
import asyncpg
import sys
import asyncio
import aiohttp

description = 'Pouty Bot MKII by Saikimo'

data_io = DataIO()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=['!', '.'], description=description,
                   owner_id=134310073014026242, case_insensitive=True, intents=intents)
LOG_SIZE = 200 * 1024 * 1024


def load_credentials():
    return data_io.load_json("credentials")


async def connect_db_and_start_bot():
    token = credentials['token']
    db_info = data_io.load_json("postgres")
    bot.db = await asyncpg.create_pool(database=db_info['dbname'],
                                       user=db_info['user'],
                                       password=db_info["password"],
                                       host=db_info["hostaddr"])

    try:
        async with aiohttp.ClientSession() as session, bot:
            bot.loop.create_task(bot.load_extension("cogs.default"))
            bot.session = session
            await bot.start(token)
    except KeyboardInterrupt:
        print("closing connection")
        await bot.db.close()
        await bot.logout()

if __name__ == '__main__':
    credentials = load_credentials()
    handler = RotatingFileHandler(filename='discord.log',
                                  encoding='utf-8',
                                  mode='a',
                                  maxBytes=LOG_SIZE,
                                  backupCount=2)
    discord.utils.setup_logging(handler=handler, level=logging.INFO, root=False)
    logging.getLogger('discord').addHandler(logging.StreamHandler())
    asyncio.run(connect_db_and_start_bot())

import discord
from discord.ext import commands
from typing import Optional
from datetime import timedelta, datetime
from .utils import checks 
from logging import getLogger
from itertools import filterfalse
import re

text_channel_regex = re.compile(r"<#(\d+)>")
class StarError(commands.CheckAnyFailure):
    pass

def requires_starboard(func):
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        cog = ctx.bot.get_cog("Starboard")
        ctx.starboard = await cog.get_starboard(ctx.guild.id)
        if ctx.starboard.channel is None:
            raise StarError("Starboard channel not found")
        return True


class Starboard(commands.Cog):
    
    async def get_starboard(self, guild_id):
        async with self.bot.db.acquire() as con:
            return await con.fetchrow("SELECT * FROM starboard_config WHERE guild_id = $1", guild_id)

    async def fetch_starboard_entry(self, message_id, guild_id):
        return await self.bot.db.fetchrow("""
        SELECT *
        FROM starboard_entries 
        WHERE (message_id = $1 OR bot_message_id = $1)
        AND guild_id = $2
        """, message_id, guild_id)

    async def initialize_db(self):
        query_conf = ("""
            CREATE TABLE IF NOT EXISTS starboard_config(
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT UNIQUE,
                    threshold INTEGER DEFAULT 5 NOT NULL,
                    is_locked BOOLEAN DEFAULT false,
                    max_age INTERVAL DEFAULT '7 days'::interval
                )""")
        query_entries = ("""
            CREATE TABLE IF NOT EXISTS starboard_entries(
                    id SERIAL PRIMARY KEY,
                    bot_message_id BIGINT,
                    channel_id BIGINT,
                    message_id BIGINT,
                    author_id BIGINT,
                    guild_id BIGINT REFERENCES starboard_config(guild_id)
                    )"""
                )
        async with self.bot.db.acquire() as con:
            await con.execute(query_conf)
            await con.execute(query_entries)

    def __init__(self, bot):
        self.bot = bot
        self.star_emoji = "\N{WHITE MEDIUM STAR}"
        self.bot.loop.create_task(self.initialize_db())
        self.logger = getLogger("PoutyBot")

    
    def convert_string_timedelta(self, string):
            try:
                number, units = string.split()
                if not units.endswith('s'): units + 's'
                td_kwarg = {units: int(number)}
                return timedelta(**td_kwarg)
            except TypeError:
                raise commands.CommandError("could not convert interval please write it in the form `{number} {unit}s` for example `7 days` (always plural)")

    @commands.group(aliases=['sb'], invoke_without_command=True)
    @checks.is_owner_or_moderator()
    async def starboard(self, ctx, channel: discord.TextChannel, threshold: Optional[int] = 5, *, max_age: Optional[str] = '7 days'):
        """
        commands for configuring and managing the starboard
        """
        starboard_config = await self.get_starboard(ctx.guild.id)
        async with self.bot.db.acquire() as con:
            max_age = self.convert_string_timedelta(max_age)
            if starboard_config:
                await con.execute("""
                    UPDATE starboard_config SET (channel_id, threshold, max_age) = ($2, $3, $4) WHERE guild_id = $1
                """, ctx.guild.id, channel.id, threshold, max_age)
            else: 
                await con.execute("""
                    INSERT INTO starboard_config(guild_id, channel_id, threshold, is_locked, max_age) 
                    VALUES ($1, $2, $3, $4, $5)
                """, ctx.guild.id, channel.id, threshold, False, max_age)
            await ctx.send(f"Set starboard to {channel.mention} with a vote threshold of {threshold} and a max message age of {max_age}")

    @starboard.command(name="info")
    @checks.is_owner_or_moderator()
    async def sb_info(self, ctx):
        starboard = await self.get_starboard(ctx.guild.id)
        if not starboard:
            return await ctx.send("No starboard configured on this server")
        embed = discord.Embed(title="Starboard Info",colour=discord.Colour(0xffac33))
        sb_message_count = await self.bot.db.fetchval("""
        SELECT COUNT(*) as star_counts FROM starboard_entries WHERE guild_id = $1
        """, ctx.guild.id)
        sb_channel = self.bot.get_channel(starboard.get("channel_id"))
        embed.add_field(name="Channel",value=sb_channel.mention)
        embed.add_field(name="Threshold",value=starboard.get("threshold"))
        embed.add_field(name="Max age",value=starboard.get("max_age"))
        embed.add_field(name="Starred Messages Count", value=sb_message_count)
        await ctx.send(embed=embed)
    @starboard.command(name="channel")
    @checks.is_owner_or_moderator()
    async def sb_channel(self, ctx, channel: discord.TextChannel):
        """
        set the starboard channel
        """
        if not await self.get_starboard(ctx.guild.id):
            return await ctx.send(f"no starboard config found please set it up with `{ctx.prefix}{self.starboard.name}`")
        await self.bot.db.execute("UPDATE starboard_config SET channel_id = $1 WHERE guild_id = $2", channel.id, ctx.guild.id)
        await ctx.send(f"Set the starboard channel to {channel.mention}")

    @starboard.command(name="threshold")
    @checks.is_owner_or_moderator()
    async def sb_threshold(self, ctx, threshold: int):
        """
        set the vote threshold 
        """
        if not await self.get_starboard(ctx.guild.id):
            return await ctx.send(f"no starboard config found please set it up with `{ctx.prefix}{self.starboard.name}`")
        await self.bot.db.execute("UPDATE starboard_config SET threshold = $1 WHERE guild_id = $2", threshold, ctx.guild.id)
        await ctx.send(f"Set the vote threshold to {threshold}")
    
    @starboard.command(name="age")
    @checks.is_owner_or_moderator()
    async def sb_message_age(self, ctx, *, max_age):
        """
        set the maximum age for starred messages (bot won't repost star messages older than this interval)
        """
        if not await self.get_starboard(ctx.guild.id):
            return await ctx.send(f"no starboard config found please set it up with `{ctx.prefix}{self.starboard.name}`")
        max_age = self.convert_string_timedelta(max_age)
        await self.bot.db.execute("UPDATE starboard_config SET max_age = $1 WHERE guild_id = $2", max_age, ctx.guild.id)
        await ctx.send(f"Set the max message age to {max_age}")
    @starboard.command(name="lock")
    @checks.is_owner_or_moderator()
    async def sb_lock(self, ctx):
        """
        lock the starboard so that no new messages will get starred
        """
        if not await self.get_starboard(ctx.guild.id):
            return await ctx.send(f"no starboard config found please set it up with `{ctx.prefix}{self.starboard.name}`")
        await self.bot.db.execute("UPDATE starboard_config SET is_locked = true WHERE guild_id = $1", ctx.guild.id)
        await ctx.send(f"Starboard was locked")

    @starboard.command(name="unlock")
    @checks.is_owner_or_moderator()
    async def sb_unlock(self, ctx):
        """
        unlock the starboard
        """
        if not await self.get_starboard(ctx.guild.id):
            return await ctx.send(f"no starboard config found please set it up with `{ctx.prefix}{self.starboard.name}`")
        await self.bot.db.execute("UPDATE starboard_config SET is_locked = false WHERE guild_id = $1", ctx.guild.id)
        await ctx.send(f"Starboard was unlocked")

    async def get_star_emoji_number(self, reacted_message, starboard_message=None):
        star_react_orig = discord.utils.get(reacted_message.reactions, emoji=self.star_emoji)
        users_who_reacted = set()
        if star_react_orig:
            async for user in star_react_orig.users():
                users_who_reacted.add(user.id)
        if starboard_message:
            star_react_sb = discord.utils.get(starboard_message.reactions, emoji=self.star_emoji)
            if star_react_sb:
                async for user in star_react_sb.users():
                    users_who_reacted.add(user.id)
        users_who_reacted.discard(reacted_message.author.id)
        return len(users_who_reacted)

    async def create_starboard_embed(self, message, starboard_message=None):
        embed = discord.Embed(description=message.content, colour=discord.Colour(0xffac33))
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar_url_as(format="png"))
        embed.add_field(name="Original", value=f"[Jump!]({message.jump_url})", inline=False)
        if message.attachments:
            file = message.attachments[0]
            spoiler = file.is_spoiler()
            is_nsfw = message.channel.is_nsfw()
            if not spoiler and not is_nsfw and file.url.lower().endswith(('png', 'jpg', 'jpeg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            elif spoiler and not is_nsfw:
                embed.add_field(name="Attachment", value=f"|| [{file.filename}]({file.url}) ||", inline=False)
            elif is_nsfw:
                embed.add_field(name="Attachment", value=f"[**(NSFW)** {file.filename}]({file.url})", inline=False)
            else:
                embed.add_field(name="Attachment", value=f"[{file.filename}]({file.url})", inline=False)

        embed.add_field(name="Count", value=f"{await self.get_star_emoji_number(message, starboard_message)} {self.star_emoji}")
        embed.add_field(name="Channel", value=message.channel.mention)
        return embed

    @commands.Cog.listener('on_raw_reaction_add')
    async def listen_to_star_emotes(self, payload):
        if not payload.guild_id or payload.emoji == self.star_emoji:
            return
        starboard = await self.get_starboard(payload.guild_id)
        if not starboard:
            self.logger.warn("No starboard configuration found")
            return
        if starboard.get("is_locked"):
            return
        guild = self.bot.get_guild(starboard.get("guild_id"))
        sb_channel = guild.get_channel(starboard.get("channel_id"))
        reaction_channel = guild.get_channel(payload.channel_id)
        message = None
        try:
            message = await reaction_channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.HTTPException) as e:
            self.logger.error("error while fetching starred message: %s",e, exc_info=True)
            return
        starboard_entry = await self.fetch_starboard_entry(payload.message_id, payload.guild_id)
        if not starboard_entry:
            time_diff = datetime.utcnow() -  message.created_at 
            star_num = await self.get_star_emoji_number(message)
            if  star_num < starboard.get("threshold") or time_diff > starboard.get("max_age"):
                return
            embed = await self.create_starboard_embed(message)       
            bot_message = await sb_channel.send(embed=embed)
            async with self.bot.db.acquire() as con:
                await con.execute("""
                    INSERT INTO starboard_entries (bot_message_id, guild_id, channel_id, message_id, author_id)
                    VALUES ($1, $2, $3, $4, $5)
                    """, 
                    bot_message.id,
                    payload.guild_id,
                    payload.channel_id,
                    message.id,
                    message.author.id
                )
        else:
            if sb_channel == reaction_channel:
                original = None
                try:
                    original_channel = guild.get_channel(starboard_entry.get("channel_id"))
                    original = await original_channel.fetch_message(starboard_entry.get("message_id"))
                except (discord.NotFound, discord.HTTPException) as e:
                    self.logger.error("error while fetching original starboard message: %s",e)
                    return
                embed = await self.create_starboard_embed(original, message)
                await message.edit(embed=embed)
            else:
                sb_message = None
                try:
                    sb_message = await sb_channel.fetch_message(starboard_entry.get("bot_message_id"))
                except (discord.NotFound, discord.HTTPException) as e:
                    self.logger.error("error while fetching bot starboard message: %s",e)
                    return
                embed = await self.create_starboard_embed(message, sb_message)
                await sb_message.edit(embed=embed)

    @commands.Cog.listener('on_raw_reaction_remove')
    async def listen_to_star_emotes_remove(self, payload):
        if not payload.guild_id or payload.emoji == self.star_emoji:
            return
        starboard = await self.get_starboard(payload.guild_id)
        if not starboard:
            self.logger.warn("No starboard configuration found")
            return
        if starboard.get("is_locked"):
            return
        guild = self.bot.get_guild(starboard.get("guild_id"))
        sb_channel = guild.get_channel(starboard.get("channel_id"))
        reaction_channel = guild.get_channel(payload.channel_id)
        starboard_entry = await self.fetch_starboard_entry(payload.message_id, payload.guild_id)
        if not starboard_entry:
            return
        message = None
        bot_message = None
        try:
            original_channel = self.bot.get_channel(starboard_entry.get("channel_id"))
            message = await original_channel.fetch_message(starboard_entry.get("message_id"))
            bot_message = await sb_channel.fetch_message(starboard_entry.get("bot_message_id"))
        except (discord.NotFound, discord.HTTPException) as e:
            self.logger.error("error while fetching starred message: %s", e, exc_info=True)
            return
        star_num = await self.get_star_emoji_number(message, bot_message)
        if star_num < starboard.get("threshold"):
            await bot_message.delete()
            await self.bot.db.execute("""
                DELETE FROM starboard_entries WHERE message_id = $1
                """, message.id)
        else:
            embed = await self.create_starboard_embed(message, bot_message)
            await bot_message.edit(embed=embed)





    @commands.Cog.listener('on_raw_message_delete')
    async def check_for_deleted_star_messages(self, payload):
        if not payload.guild_id:
            return
        starboard = await self.get_starboard(payload.guild_id)
        if not starboard:
            return
        starboard_entry = await self.fetch_starboard_entry(payload.message_id, payload.guild_id)
        if not starboard_entry:
            return
        if payload.message_id == starboard_entry.get("message_id"):
            starboard_channel = self.bot.get_channel(starboard.get("channel_id"))
            sb_message = starboard_channel.get_partial_message(starboard_entry.get("bot_message_id"))
            if sb_message:
                await sb_message.delete()
        await self.bot.db.execute("""
            DELETE FROM starboard_entries WHERE bot_message_id = $1 or message_id = $1
            """, payload.message_id)

    @commands.Cog.listener('on_raw_bulk_message_delete')
    async def check_for_deleted_bulk_star_messages(self, payload):
        if not payload.guild_id:
            return
        starboard = await self.get_starboard(payload.guild_id)
        if not starboard:
            return
        for message_id in payload.message_ids:
            starboard_entry = await self.fetch_starboard_entry(message_id, payload.guild_id)
            if message_id == starboard_entry.get("message_id"):
                starboard_channel = self.bot.get_channel(starboard.get("channel_id"))
                sb_message = starboard_channel.get_partial_message(starboard_entry.get("bot_message_id"))
                if sb_message:
                    await sb_message.delete()
            if not starboard_entry:
                continue
            await self.bot.db.execute("""
                DELETE FROM starboard_entries WHERE bot_message_id = $1 OR message_id = $1
                """, message_id)
def setup(bot):
    bot.add_cog(Starboard(bot))

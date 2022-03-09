from datetime import time
from typing import Any, Dict, Optional, Union
import discord
import time
from discord.ext import commands
from discord import app_commands
from discord.mentions import AllowedMentions

async def commands_sync(bot: commands.Bot, tree: app_commands.CommandTree):
    for guild in bot.guilds:
        await tree.sync(guild=guild)
    await tree.sync()

def setup(bot: commands.Bot):
    tree = app_commands.CommandTree(bot)

    cooldowns : Dict[Union[discord.User, discord.Member], commands.Cooldown] = {}

    def update_cooldown(user: Union[discord.User, discord.Member]):
        dead_cooldowns = [k for k,v in cooldowns.items() if time.time() > v._last + v.per]
        for k in dead_cooldowns:
            del cooldowns[k]
        if user not in cooldowns:
            cooldowns[user] = commands.Cooldown(rate=1, per=60)
        return cooldowns[user].update_rate_limit()
    
    @tree.command(name="at", description="A command for pinging roles")
    @app_commands.describe(role="The role you want to ping")
    @app_commands.describe(message="Optional message to accompany with the ping")
    async def at_role_ping(interaction: discord.Interaction, role: discord.Role, message: Optional[str]):
        """
        """
        can_ping = await bot.db.fetchval("""
        SELECT pingable FROM role_info WHERE role_id = $1
        """, role.id)
        if not can_ping:
            await interaction.response.send_message(content="can't ping this role", ephemeral=True)
            return
        if wait := update_cooldown(interaction.user):
            await interaction.response.send_message(f"please wait for {int(wait)}s before using this command again", ephemeral=True)
            return
        try:
            await role.edit(mentionable=True)
            await interaction.response.send_message(f"{role.mention} {message if message else ''}", ephemeral=False, allowed_mentions=AllowedMentions(roles=[role],everyone=False, users=False, replied_user=False))
            await role.edit(mentionable=False)
        except discord.Forbidden:
            await interaction.response.send_message(content="I am not allowed to edit this role", ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(content="Command failed unexpectedly", ephemeral=True)
            raise e

    for guild in bot.guilds:
        tree.add_command(at_role_ping, guild=guild)
    bot.loop.create_task(commands_sync(bot, tree))

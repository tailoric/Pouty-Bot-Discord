from dataclasses import dataclass
import textwrap
from typing import List, Optional, TypedDict, Union
from discord import Interaction, Member, User, Embed
from discord.app_commands import Choice, Transform, default_permissions
from discord.ext import commands
from discord import ui
from discord import app_commands
from thefuzz import fuzz, process
import re
import json

class PlatformTransformError(app_commands.AppCommandError):
    pass
@dataclass()
class Platform:
    platform_id: int
    name: str
    example: str

class PlatformTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: int) -> Platform:
        platform_id = 0
        try:
            platform_id = int(value)
        except ValueError:
            raise PlatformTransformError("Only select from the autocompletion, if the platform is not in the list ask a moderator to create it")
        if platform_id not in interaction.client.friend_codes:
            row = await interaction.client.db.fetchrow("""
                SELECT * FROM friend_code.platform WHERE platform_id = $1
            """, platform_id)
            if row:
                platform = Platform(**row)
                interaction.client.friend_codes[platform_id] = platform
                return platform
            raise PlatformTransformError("Could not find the provided platform.")
        else:
            return interaction.client.friend_codes[platform_id]
    
    async def autocomplete(self, interaction: Interaction, current: str) -> List[Choice[str]]:
        
        platforms = list(interaction.client.friend_codes.values())
        choices = [Choice(name=p.name, value=str(p.platform_id)) for p in platforms[:25]]
        if current:
            choices = [app_commands.Choice(name=p.name, value=str(p.platform_id))
                        for p in platforms 
                        if fuzz.partial_ratio(current.lower(), p.name.lower()) > 70 or
                        current.lower() in p.name.lower()
                    ]
        return choices[:25]


class FriendCodes(commands.GroupCog, group_name="friend-codes"):
    """
    Get Friend codes for various games of other users or set your own
    """
    def __init__(self, bot) -> None:
        self.bot = bot
        super().__init__()

    async def cog_unload(self) -> None:
        await self.connection.close()
        return await super().cog_unload()
    async def cog_load(self) -> None:
        await self.bot.db.execute("""
        CREATE SCHEMA IF NOT EXISTS friend_code;
        CREATE TABLE IF NOT EXISTS friend_code.platform (
                platform_id bigint GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                example TEXT DEFAULT NULL
            );
        CREATE TABLE IF NOT EXISTS friend_code.user (
                entry_id bigint GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                user_id bigint NOT NULL,
                account TEXT NOT NULL,
                platform bigint 
                    REFERENCES friend_code.platform (platform_id) ON DELETE CASCADE,
                UNIQUE (user_id, platform)
            );
        """)
        if not hasattr(self.bot, 'friend_codes'):
            self.bot.friend_codes = {
                    f.get('platform_id'): Platform(**f) for f in 
                    await self.bot.db.fetch("""
                        SELECT * FROM friend_code.platform;
                    """)
            }
        self.connection = await self.bot.db.acquire()
        async def refresh_cache(connection, pid, channel, payload):
            self.bot.friend_codes = {
                    f.get('platform_id'): Platform(**f) for f in 
                    await self.bot.db.fetch("""
                        SELECT * FROM friend_code.platform;
                    """)
            }
        await self.connection.add_listener('friend_code.platforms', refresh_cache)
        

    @app_commands.command(name="set", description="set your friend code for a game")
    @app_commands.describe(
                platform="The game or platform you are setting the code for",
                account="The friend code, url, username or other identifier for that platform"
            )
    async def friend_code_set(self, interaction: Interaction, 
            platform: Transform[Platform, PlatformTransformer], 
            account: str
            ):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute("""
            INSERT INTO friend_code."user" (user_id, account, platform)
                VALUES ($1,$2,$3) ON CONFLICT (user_id, platform) DO UPDATE SET account = EXCLUDED.account;
        """, interaction.user.id, account, platform.platform_id)
        await interaction.followup.send(f"Account {account} for platform {platform.name} stored.")

    @app_commands.command(name="remove", description="set your friend code for a game")
    @app_commands.describe(
                platform="The game or platform you are setting the code for"
            )
    async def friend_code_remove(self, interaction: Interaction, 
            platform: Transform[Platform, PlatformTransformer]
            ):
        await interaction.response.defer(ephemeral=True)
        account = await self.bot.db.fetchval("""
            DELETE FROM friend_code."user" WHERE user_id = $1 AND platform = $2
            RETURNING account;
        """, interaction.user.id, platform.platform_id)
        if account:
            await interaction.followup.send(f"Account {account} for platform {platform.name} deleted.")
        else:
            await interaction.followup.send(f"You didn't have an account for platform {platform.name} stored.")

    @app_commands.command(name="get", description="get your own or others friend codes or accounts")
    @app_commands.describe(
            user="The optional user to search for, if not used will display your codes",
            platform="The platform to show your account on, if not used will show all"
            )
    async def friend_code_get(self, interaction: Interaction,
            user: Optional[Union[Member, User]], 
            platform: Optional[Transform[Platform, PlatformTransformer]]
            ):
        friend_codes = self.bot.friend_codes
        if not user:
            user = interaction.user
        if platform:
            rows = await self.bot.db.fetch("""
            SELECT account, platform FROM friend_code."user" WHERE platform = $1 AND user_id = $2
            """, platform.platform_id, user.id)
        else:
            rows = await self.bot.db.fetch("""
            SELECT account, platform FROM friend_code."user" WHERE user_id = $1
            """, user.id)
        if not rows:
            for_platform = f" for {platform.name}" if platform else ""
            return await interaction.response.send_message(f"This user has no accounts{for_platform} linked", ephemeral=True)
        embed = Embed(title="User Accounts")
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        count_rows = 0
        embed_too_big = False
        for row in rows[:25]:
            if len(embed) + len(friend_codes[row["platform"]].name) + len(row["account"]) > 5945:
                embed_too_big = True
                break
            count_rows += 1
            embed.add_field(name=friend_codes[row["platform"]].name, value=row["account"], inline=False)
        if len(rows) > 25 or embed_too_big:
            embed.set_footer(text=f"Only the first {count_rows}, too many accounts too show")
        await interaction.response.send_message(embed=embed)


class PlatformEditForm(ui.Modal):
    name = ui.TextInput(label="Platform/Game/Website Name", placeholder="Cool Game")
    example = ui.TextInput(label="Example Account Name", placeholder="USER#1234")
    def __init__(self, bot, old_platform: Platform) -> None:
        self.bot = bot
        self.platform = old_platform
        self.example.default = self.platform.example
        self.name.default = self.platform.name
        super().__init__(title=textwrap.shorten(f"Edit Platform {self.platform.name}", 45), timeout=None)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        async with self.bot.db.acquire() as con, con.transaction():
            await con.execute("""
            UPDATE friend_code.platform  
            SET name = $1,
                example = $2
            WHERE platform_id = $3
            """, self.name.value, self.example.value, self.platform.platform_id)
            await con.execute("""
            SELECT pg_notify('friend_code.platforms', 'edit');
            """)
        await interaction.followup.send(f"Edited platform \"{self.platform.name}\" \N{RIGHTWARDS ARROW} \"{self.name.value}\" with new example `{self.example.value}`")
        self.stop()
class PlatformCreationForm(ui.Modal):
    name = ui.TextInput(label="Platform/Game/Website Name", placeholder="Cool Game")
    example = ui.TextInput(label="Example Account Name", placeholder="USER#1234")
    def __init__(self, bot) -> None:
        self.bot = bot
        super().__init__(title="Create New Platform", timeout=None)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        async with self.bot.db.acquire() as con, con.transaction():
            await con.execute("""
            INSERT INTO friend_code.platform (name, example)
                VALUES ($1, $2)
            """, self.name.value, self.example.value)
            await con.execute("""
            SELECT pg_notify('friend_code.platforms', 'add');
            """)
        await interaction.followup.send(f"New platform \"{self.name.value}\" created")
        self.stop()

@default_permissions(manage_roles=True)
class FriendCodesManager(commands.GroupCog, group_name="manage-friend-codes"):
    """
    For managing friend-codes / user account platforms
    """
    def __init__(self, bot) -> None:
        self.bot = bot
        super().__init__()

    
    @app_commands.command(name="create")
    async def manager_create(self, interaction: Interaction):
        """
        Open a form for creating a new platform for the friend-code command 
        """
        await interaction.response.send_modal(PlatformCreationForm(self.bot))

    @app_commands.command(name="edit")
    @app_commands.describe(
            platform="The platform to edit, can change name and example"
            )
    async def manager_edit(self, interaction: Interaction, platform: Transform[Platform, PlatformTransformer]):
        """
        Open a form for editing an existing platform for the friend-code command 
        """
        await interaction.response.send_modal(PlatformEditForm(self.bot, platform))
    @app_commands.command(name="delete")
    @app_commands.describe(
            platform="The platform to delete."
            )
    async def manager_delete(self,
            interaction: Interaction,
            platform: Transform[Platform, PlatformTransformer]):
        """
        Delete an existing platform from the command
        """
        await interaction.response.defer()
        async with self.bot.db.acquire() as con, con.transaction():
            await con.execute("""
                DELETE FROM friend_code.platform WHERE platform_id = $1
            """, platform.platform_id)
            await con.execute("""
                SELECT pg_notify('friend_code.platforms', 'delete');
            """)
        await interaction.followup.send(f"Friend code platform {platform.name} deleted")

async def setup(bot):
    await bot.add_cog(FriendCodes(bot))
    await bot.add_cog(FriendCodesManager(bot))

from discord.ext import commands, menus
from .utils import checks, views
import discord

class TagList(menus.ListPageSource):
    def __init__(self, data, *args, **kwargs):
        super().__init__(data,*args, **kwargs)

    def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        embed = discord.Embed(title="Found tags", description="", colour=discord.Colour.blurple())
        for index, tag in enumerate(entries, start=offset):
            embed.description += f"`{index+1}. {tag}`\n"
        return embed

class Tags(commands.Cog):
    """Create, Edit, Delete and Search tags created by moderators"""

    def __init__(self, bot):
        self.bot = bot
        self.init_task = bot.loop.create_task(self.init_database())

    async def init_database(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS tag(
                tag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                UNIQUE (guild_id, name)
            );
        """)
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS tag_alias(
                alias_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                name TEXT,
                guild_id BIGINT NOT NULL,
                tag_id BIGINT REFERENCES tag(tag_id) ON DELETE CASCADE
            );
        """)
    @commands.group(invoke_without_command=True)
    async def tag(self, ctx, *, name):
        """
        Command for posting a tag into the current channel
        usable by everyone
        """
        result = await self.bot.db.fetchval("""
            SELECT content
            FROM tag_alias  
            INNER JOIN  tag ON tag.tag_id = tag_alias.tag_id
            WHERE tag_alias.name=$1
            AND tag_alias.guild_id=$2
        """, name, ctx.guild.id)
        if result:
            await ctx.send(result, allowed_mentions=discord.AllowedMentions.none())
        else:
            await ctx.send(f"no tag with name or alias `{name}` found")

    @tag.command(name="add")
    @checks.is_owner_or_moderator()
    async def tag_add(self, ctx, name, *, content):
        """
        Add a new tag to the database
        """
        if name in ("add", "search", "alias", "remove", "rm", "delete", "update", "edit", "update"):
            return await ctx.send(f"the name `{name}` is a reserved name of a tag subcommand please use a different name.")
        result = await self.bot.db.fetchval("""
            SELECT name FROM tag_alias WHERE name=$1 AND guild_id=$2
        """, name, ctx.guild.id)
        if result:
            await ctx.send("tag already exists choose a different name")
        else:
            await self.bot.db.execute("""
            WITH tag_insert AS (
                    INSERT INTO tag(guild_id, name, content) 
                    VALUES ($1, $2, $3)
                    RETURNING tag_id
                )
            INSERT INTO tag_alias(guild_id, name, tag_id) VALUES ($1, $2, (SELECT tag_id FROM tag_insert))
            """, ctx.guild.id, name, content)
            await ctx.send(f"tag `{name}` created.")

    @tag.command(name="edit", aliases=["update"])
    @checks.is_owner_or_moderator()
    async def tag_update(self, ctx, name, *, content):
        """
        Edit a tag to change its content
        """
        result = await self.bot.db.fetchval("""
            SELECT t.tag_id 
            FROM tag_alias 
            INNER JOIN tag t ON t.tag_id = tag_alias.tag_id 
            WHERE tag_alias.name=$1 AND tag_alias.guild_id=$2
        """, name, ctx.guild.id)
        if result:
            await self.bot.db.execute("""
            UPDATE tag SET content=$1 WHERE tag_id=$2 AND guild_id = $3
            """, content, result, ctx.guild.id)
            await ctx.send(f"tag `{name}` edited.")
        else:
            await ctx.send(f"tag {name} doesn't exist")

    @tag.command(name="remove", aliases=["rm", "delete"])
    @checks.is_owner_or_moderator()
    async def tag_remove(self, ctx, name):
        """
        Delete a tag, can be deleted via name or alias
        """
        tag_id = await self.bot.db.fetchval("""
            WITH tag_search AS (
                SELECT t.tag_id FROM tag t INNER JOIN tag_alias ta ON ta.tag_id = t.tag_id WHERE ta.name=$2 AND ta.guild_id = $1
            )
            DELETE FROM tag WHERE tag_id=(SELECT tag_id FROM tag_search)
            RETURNING tag_id
        """, ctx.guild.id , name)
        if tag_id:
            await ctx.send(f"tag `{name}` deleted")
        else:
            await ctx.send(f"tag `{name}` not found")

    @tag.command(name="search")
    async def tag_search(self, ctx, query):
        """
        Search for a tag, query must be contained inside the tag name 
        for example `.tag search test` will find `test` and `testtest` and `detestable`
        """
        results = await self.bot.db.fetch("""
            SELECT t.name
            FROM tag_alias t 
            WHERE name LIKE $1
            AND guild_id = $2
            LIMIT 100;
        """, f"%{query}%", ctx.guild.id)
        entries = []
        for result in results:
            entries.append(result.get('name'))
        if entries:
            source = TagList(entries, per_page=10)
            view = views.PaginatedView(source)
            await view.start(ctx)
        else:
            await ctx.send("nothing found")



    @tag.group(name="alias", invoke_without_command=True)
    @checks.is_owner_or_moderator()
    async def tag_alias(self, ctx, name, *, alias):
        """
        Add an alias to a tag.
        """
        tag = await self.bot.db.fetchrow("""
            SELECT tag_id FROM tag WHERE name=$1 AND guild_id=$2
        """, name, ctx.guild.id)
        if not tag:
            return await ctx.send(f"tag with name `{name}` not found.")

        result = await self.bot.db.fetchrow("""
            SELECT name FROM tag_alias WHERE name = $1 AND guild_id = $2
        """, alias, ctx.guild.id)
        if result:
            return await ctx.send("tag alias or name already exists choose a different alias")
        await self.bot.db.execute("""
            INSERT INTO tag_alias (name, tag_id, guild_id) VALUES ($1, $2, $3)
        """, alias, tag.get("tag_id"), ctx.guild.id)
        await ctx.send(f"tag `{name}` now has the alias `{alias}`")


    @tag_alias.group(name="remove", aliases=["rm", "delete"])
    @checks.is_owner_or_moderator()
    async def tag_alias_remove(self, ctx, alias):
        """
        delete an alias.
        CAREFUL the tag name is also in the alias list 
        so deleting the real name can result in problems
        if you do delete the tag name instead of an alias 
        add it back in with the alias command.
        """
        tag_id = await self.bot.db.fetchval("""
            DELETE FROM tag_alias WHERE name=$2 AND guild_id=$1
            RETURNING tag_id
        """, ctx.guild.id , alias)
        if tag_id:
            await ctx.send(f"tag alias `{alias}` deleted")
        else:
            await ctx.send(f"tag alias `{alias}` not found")

def setup(bot):
    bot.add_cog(Tags(bot))
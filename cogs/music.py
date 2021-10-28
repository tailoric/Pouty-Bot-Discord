"""
This is an example cog that shows how you would make use of Lavalink.py.
This example cog requires that you have python 3.6 or higher due to the
f-strings.
"""
import math
import re

import discord
import lavalink
from discord.ext import commands
from discord.ext import menus
from .utils import checks
from typing import List
import asyncio
import logging

url_rx = re.compile('https?:\\/\\/(?:www\\.)?.+')  # noqa: W605

class LavalinkVoiceClient(discord.VoiceProtocol):

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.connect_event = asyncio.Event()

    async def on_voice_server_update(self, data):
        lavalink_data = {
                't': 'VOICE_SERVER_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        lavalink_data = {
                't': 'VOICE_STATE_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)


    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        await self.channel.guild.change_voice_state(channel=self.channel)
        try:
            self.lavalink : lavalink.Client = self.client.lavalink
        except AttributeError:
            self.client.lavalink = self.lavalink = lavalink.Client(self.client.user.id)
            self.client.lavalink.add_node(
                    'localhost',
                    2333,
                    'youshallnotpass',
                    'us',
                    'default-node')

    async def disconnect(self, *, force: bool) -> None:
        await self.channel.guild.change_voice_state(channel=None)
        player = self.lavalink.player_manager.get(self.channel.guild.id)
        if player:
            player.channel_id = False
            await player.stop()
        self.cleanup()

class MusicQueue(menus.ListPageSource):
    def __init__(self, data: List[lavalink.AudioTrack] , ctx: commands.Context, player):
        self.ctx = ctx
        self.player = player
        super().__init__(data, per_page=10)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        embed = discord.Embed(title="Queue", 
                description="\n".join(
                    f'`{i+1}.` [{v.title}]({v.uri}) requested by **{self.ctx.guild.get_member(v.requester).name}**' for i, v in enumerate(entries, start=offset)
                    )
                )
        status = (f"\N{TWISTED RIGHTWARDS ARROWS} Shuffle: {'enabled' if self.player.shuffle else 'disabled'} | "
        f"\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS} Repeat: {'enabled' if self.player.repeat else 'disabled'} | "
        f"\N{SPEAKER} Volume : {self.player.volume}")
        embed.set_footer(text=status)
        return embed

def can_stop():
    def predicate(ctx):
        if not ctx.guild:
            raise commands.CheckFailure("Only usable within a server")
        if not ctx.guild.me.voice:
            return True
        my_voice = ctx.guild.me.voice.channel
        try:
            if checks.is_owner_or_moderator_check(ctx.message):
                return True
        except commands.CheckFailure:
            pass
        if ctx.guild.me.voice:
            if len(my_voice.members) == 2 and ctx.author in my_voice.members:
                return True
            if len(my_voice.members) == 1:
                return True
            raise commands.CheckFailure(
                    "Can only use this when nobody or "
                    "only one user in voice channel with me"
                    )
    return commands.check(predicate)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, 'lavalink'):
            self.bot.lavalink = lavalink.Client(self.bot.user.id)
            self.bot.lavalink.add_node(
                    'localhost',
                    2333,
                    'youshallnotpass',
                    'us',
                    'default-node')
            self.bot.lavalink.add_event_hook(self.track_hook)

        self.pages = {}
        self.skip_votes = {}

    def current_voice_channel(self, ctx):
        if ctx.guild and ctx.guild.me.voice:
            return ctx.guild.me.voice.channel
        return None

    def cog_unload(self):
        self.bot.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx):
        guild_check = ctx.guild is not None
        #  This is essentially the same as `@commands.guild_only()`
        #  except it saves us repeating ourselves (and also a few lines).

        if guild_check:
            # Ensure that the bot and command author
            # share a mutual voicechannel.
            await self.ensure_voice(ctx)

        return guild_check
    async def cog_after_invoke(self,ctx):
        for page in self.pages.get(ctx.message.guild.id, []):
            await page.show_page(page.current_page)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        deafen yourself when joining a voice channel
        """
        if member.id == member.guild.me.id and after.channel is None:
            await after.guild.voice_client.disconnect(force=True)
            await self.bot.change_presence(activity=None)
        if member.id != member.guild.me.id or not after.channel:
            return
        my_perms = after.channel.permissions_for(member)
        if not after.deaf and my_perms.deafen_members:
            await member.edit(deafen=True)

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            guild_id = int(event.player.guild_id)
            guild : discord.Guild = self.bot.get_guild(guild_id)
            await guild.voice_client.disconnect(force=True)
            # Disconnect from the channel -- there's nothing else to play.
        if isinstance(event, lavalink.events.TrackEndEvent):
            if self.skip_votes and guild_id in self.skip_votes.keys():
                self.skip_votes[guild_id].clear()
        if isinstance(event, lavalink.events.TrackStartEvent):
            await self.bot.change_presence(
                    activity=discord.Activity(type=discord.ActivityType.listening, name=event.player.current.title)
                    )
        if isinstance(event, lavalink.events.TrackExceptionEvent):
            channel = event.player.fetch('channel')
            await channel.send(f"Error while playing Track: "
                               f"**{event.track.title}**:"
                               f"\n`{event.exception}`")

    @commands.group(aliases=['p'],invoke_without_command=True)
    async def play(self, ctx, *, query: str):
        """ Searches and plays a song from a given query. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        query = query.strip('<>')

        if not url_rx.match(query):
            query = f'ytsearch:{query}'

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('Nothing found!')

        embed = discord.Embed(color=discord.Color.blurple())

        if results['loadType'] == 'PLAYLIST_LOADED':
            tracks = results['tracks']

            for track in tracks:
                player.add(requester=ctx.author.id, track=track)

            embed.title = 'Playlist Enqueued!'
            embed.description = (f'{results["playlistInfo"]["name"]}'
                                 f'- {len(tracks)} tracks')
        else:
            track = results['tracks'][0]
            embed.title = 'Track Enqueued'
            embed.description = (f'[{track["info"]["title"]}]'
                                 f'({track["info"]["uri"]})')
            player.add(requester=ctx.author.id, track=track)

        await ctx.send(embed=embed)

        if not player.is_playing:
            await player.play()

    @play.command("soundcloud", aliases=['sc'])
    async def sc_play(self, ctx, *, query: str):
        """
        search and play songs from soundcloud
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        query = query.strip('<>')

        if not url_rx.match(query):
            query = f'scsearch:{query}'

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('Nothing found!')

        embed = discord.Embed(color=discord.Color.blurple())

        if results['loadType'] == 'PLAYLIST_LOADED':
            tracks = results['tracks']

            for track in tracks:
                player.add(requester=ctx.author.id, track=track)

            embed.title = 'Playlist Enqueued!'
            embed.description = (f'{results["playlistInfo"]["name"]}'
                    f'- {len(tracks)} tracks')
        else:
            track = results['tracks'][0]
            embed.title = 'Track Enqueued'
            embed.description = (f'[{track["info"]["title"]}]'
                    f'({track["info"]["uri"]})')
            player.add(requester=ctx.author.id, track=track)

        await ctx.send(embed=embed)

        if not player.is_playing:
            await player.play()
    @commands.command()
    async def seek(self, ctx, *, seconds: int):
        """ Seeks to a given position in a track. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if ctx.author.id != player.current.requester:
            return await ctx.send("Only requester can seek.")

        track_time = player.position + (seconds * 1000)
        await player.seek(track_time)

        await ctx.send(
                f'Moved track to **{lavalink.utils.format_time(track_time)}**'
                )

    @commands.command(name="fskip", aliases=['forceskip'])
    @checks.is_owner_or_moderator()
    async def force_skip(self, ctx):
        """
        can only be invoked by moderators,
        immediately skips the current song
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Not playing.')
        await player.skip()
        if self.skip_votes:
            self.skip_votes[ctx.guild.id].clear()
        await ctx.send("⏭ | Skipped by moderator")

    @commands.command()
    async def skip(self, ctx):
        """
        if invoked by requester skips the current song
        otherwise starts a skip vote, use again to remove skip vote
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Not playing.')
        current_voice = self.current_voice_channel(ctx)

        if (ctx.author.id == player.current.requester
                or len(current_voice.members) <= 2):
            await player.skip()
            if ctx.guild.id in self.skip_votes.keys():
                self.skip_votes[ctx.guild.id].clear()
            await ctx.send('⏭ | Skipped by requester.')
        else:
            if ctx.guild.id not in self.skip_votes.keys():
                self.skip_votes[ctx.guild.id] = {ctx.author.id}
            else:
                if ctx.author.id in self.skip_votes.values():
                    self.skip_votes[ctx.guild.id].remove(ctx.author.id)
                else:
                    self.skip_votes[ctx.guild.id].add(ctx.author.id)

            skip_vote_number = len(self.skip_votes[ctx.guild.id])
            number_of_users_in_voice = len(current_voice.members)-1
            if skip_vote_number >= number_of_users_in_voice / 2:
                await player.skip()
                self.skip_votes[ctx.guild.id].clear()
                await ctx.send('⏭ | Skip vote passed.')
            else:
                votes_needed = \
                    math.ceil(number_of_users_in_voice/2) - skip_vote_number
                await ctx.send(f"current skip vote: "
                               f"{votes_needed}"
                               f"more vote(s) needed "
                               f"for skip")

    @commands.command(aliases=['np', 'n', 'playing'])
    async def now(self, ctx):
        """ Shows some stats about the currently playing song. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.current:
            return await ctx.send('Nothing playing.')

        position = lavalink.utils.format_time(player.position)
        requester = ctx.guild.get_member(player.current.requester)
        if player.current.stream:
            duration = '🔴 LIVE'
        else:
            duration = lavalink.utils.format_time(player.current.duration)
        song = (f'**[{player.current.title}]({player.current.uri})**\n'
                f'({position}/{duration}) '
                f'requested by '
                f'**{requester.display_name if requester else "?"}**')

        embed = discord.Embed(color=discord.Color.blurple(),
                              title='Now Playing', description=song)
        status = (f"\N{TWISTED RIGHTWARDS ARROWS} Shuffle: {'enabled' if player.shuffle else 'disabled'} | "
        f"\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS} Repeat: {'enabled' if player.repeat else 'disabled'} | "
        f"\N{SPEAKER} Volume : {player.volume}")

        embed.set_footer(text=status)
        await ctx.send(embed=embed)

    @commands.Cog.listener(name="on_reaction_clear")
    async def remove_page_on_menu_close(self, message, reactions):
        current_pages = self.pages.get(message.guild.id, None)
        if not current_pages:
            return
        found_page = next(filter(lambda p: p.message == message, current_pages), None)
        if found_page:
            self.pages[message.guild.id].remove(found_page)

    @commands.command(aliases=['q', 'playlist'])
    async def queue(self, ctx):
        """ Shows the player's queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.queue:
            return await ctx.send('Nothing queued.')


        pages= menus.MenuPages(source=MusicQueue(player.queue, ctx, player), clear_reactions_after=True)
        await pages.start(ctx)
        if ctx.guild.id in self.pages:
            self.pages[ctx.guild.id].append(pages)
        else:
            self.pages[ctx.guild.id] = [pages]
        

    @commands.command(aliases=['resume'])
    @checks.is_owner_or_moderator()
    async def pause(self, ctx):
        """ Pauses/Resumes the current track. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Not playing.')

        if player.paused:
            await player.set_pause(False)
            await ctx.send('⏯ | Resumed')
        else:
            await player.set_pause(True)
            await ctx.send('⏯ | Paused')

    @commands.command(aliases=['vol'])
    @checks.is_owner_or_moderator()
    async def volume(self, ctx, volume: int = None):
        """ Changes the player's volume (0-1000). """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not volume:
            return await ctx.send(f'🔈 | {player.volume}%')
        # Lavalink will automatically cap values between, or equal to 0-1000.
        await player.set_volume(volume)
        await ctx.send(f'🔈 | Set to {player.volume}%')

    @commands.command()
    async def shuffle(self, ctx):
        """ Shuffles the player's queue. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.is_playing:
            return await ctx.send('Nothing playing.')

        player.shuffle = not player.shuffle
        await ctx.send(f'🔀 | Shuffle '
                       f'{"enabled" if player.shuffle else "disabled"}')

    @commands.command(aliases=['loop'])
    async def repeat(self, ctx):
        """
        Repeats the current song until the command is invoked again
        or until a new song is queued.
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Nothing playing.')

        player.repeat = not player.repeat
        await ctx.send('🔁 | Repeat ' + ('enabled' if player.repeat else 'disabled'))

    @commands.command()
    async def remove(self, ctx, index: int):
        """ Removes an item from the player's queue with the given index. """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        can_remove = False
        try:
            can_remove = checks.is_owner_or_moderator_check(ctx.message)
        except commands.CheckFailure:
            pass
        if can_remove or ctx.author.id == player.queue[index-1].requester:
            if not player.queue:
                return await ctx.send('Nothing queued.')

            if index > len(player.queue) or index < 1:
                return await ctx.send(f'Index has to be **between** 1 and {len(player.queue)}')

            removed = player.queue.pop(index - 1)  # Account for 0-index.

            await ctx.send(f'Removed **{removed.title}** from the queue.')
        else:
            await ctx.send("Only requester and moderators can remove from the list")



    @commands.group(aliases=["search"], invoke_without_command=True)
    async def find(self, ctx, *, query):
        """ Lists the first 10 search results from a given query.
            also allows you to queue one of the results (use p and the index number)
            for example p 1 to play the first song in the results.
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        original_query = query
        if not query.startswith('ytsearch:') and not query.startswith('scsearch:'):
            query = 'ytsearch:' + query

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('Nothing found.')

        tracks = results['tracks'][:10]  # First 10 results

        o = (f"The first 10 results found via query `{original_query}`\n"
             f"use `queue` or `play` followed by the number of the result to queue that song\n")
        for index, track in enumerate(tracks, start=1):
            track_title = track['info']['title']
            track_uri = track['info']['uri']
            o += f'`{index}.` [{track_title}]({track_uri})\n'

        embed = discord.Embed(color=discord.Color.blurple(), description=o)
        await ctx.send(embed=embed)
        def queue_check(message):

            if not re.match(r"(q(uery)?|p(lay)?)", message.content):
                return False
            try:
                get_message_numbers = ''.join(c for c in message.content if c.isdigit())
                number = int(get_message_numbers)

            except ValueError:
                raise commands.CommandError("please choose a number between 1 and 10")
            return (number >= 1 or number <= 10) and message.channel == ctx.channel and message.author == ctx.author
        try:
            msg = await ctx.bot.wait_for("message", check=queue_check, timeout=10.0)
        except asyncio.TimeoutError:
            return
        get_message_numbers = ''.join(c for c in msg.content if c.isdigit())
        result_number = int(get_message_numbers)
        ctx.command = self.play
        await self.cog_before_invoke(ctx)
        await ctx.invoke(self.play, query=tracks[result_number-1]['info']['uri'])

    @find.group(name="scsearch",aliases=["sc", "soundcloud"], invoke_without_command=True)
    async def find_sc(self, ctx, *, query):
        """ Lists the first 10 soundcloud search results from a given query.
            also allows you to queue one of the results (use p and the index number)
            for example p 1 to play the first song in the results.
        """
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        original_query = query
        query = 'scsearch:' + query

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('Nothing found.')

        tracks = results['tracks'][:10]  # First 10 results

        o = (f"The first 10 results found via query `{original_query}`\n"
             f"use `queue` or `play` followed by the number of the result to queue that song\n")
        for index, track in enumerate(tracks, start=1):
            track_title = track['info']['title']
            track_uri = track['info']['uri']
            o += f'`{index}.` [{track_title}]({track_uri})\n'

        embed = discord.Embed(color=discord.Color.blurple(), description=o)
        await ctx.send(embed=embed)
        def queue_check(message):

            if not re.match(r"(q(uery)?|p(lay)?)", message.content):
                return False
            try:
                get_message_numbers = ''.join(c for c in message.content if c.isdigit())
                number = int(get_message_numbers)

            except ValueError:
                raise commands.CommandError("please choose a number between 1 and 10")
            return (number >= 1 or number <= 10) and message.channel == ctx.channel and message.author == ctx.author
        try:
            msg = await ctx.bot.wait_for("message", check=queue_check, timeout=10.0)
        except asyncio.TimeoutError:
            return
        get_message_numbers = ''.join(c for c in msg.content if c.isdigit())
        result_number = int(get_message_numbers)
        ctx.command = self.play
        await self.cog_before_invoke(ctx)
        await ctx.invoke(self.play, query=tracks[result_number-1]['info']['uri'])

    @commands.command(aliases=['dc','stop','leave','quit'])
    @can_stop()
    async def disconnect(self, ctx: commands.Context):
        """ Disconnects the player from the voice channel and clears its queue. """
        await ctx.voice_client.disconnect(force=True)
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send('Not connected.')

        player.queue.clear()
        await player.stop()
        await ctx.send('*⃣ | Disconnected.')

    async def ensure_voice(self, ctx):
        """ This check ensures that the bot and command author are in the same voicechannel. """
        should_connect = ctx.command.name in ('play', 'junbi_ok','soundcloud')  # Add commands that require joining voice to work.

        if should_connect and self.current_voice_channel(ctx) is None:
            if self.bot.lavalink.node_manager.available_nodes:
                voice_client = await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
                player : lavalink.DefaultPlayer = self.bot.lavalink.player_manager.create(ctx.guild.id)
                player.store("channel", ctx.channel)
            else:
                raise commands.CommandError("No audio player nodes available. Please wait a few minutes for a reconnect")
        elif self.current_voice_channel(ctx) is not None and not self.bot.lavalink.node_manager.available_nodes:
            await ctx.guild.voice_client.disconnect(force=True)
            raise commands.CommandError("No audio player nodes available. Please wait a few minutes for a reconnect")
        if ctx.command.name in ('find', 'scsearch', 'disconnect', 'now', 'queue'):
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CheckFailure('Join a voicechannel first.')

        permissions = ctx.author.voice.channel.permissions_for(ctx.me)

        if not permissions.connect or not permissions.speak:  # Check user limit too?
            raise commands.CheckFailure('I need the `CONNECT` and `SPEAK` permissions.')

    @commands.command(name="lc")
    @checks.is_owner()
    async def lavalink_reconnect(self, ctx):
        self.bot.lavalink.add_node(
                'localhost',
                2333,
                'youshallnotpass',
                'us',
                'default-node')



def setup(bot):
    bot.add_cog(Music(bot))

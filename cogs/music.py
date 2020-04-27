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
from .utils import checks
import asyncio

url_rx = re.compile('https?:\\/\\/(?:www\\.)?.+')  # noqa: W605


def can_stop():
    def predicate(ctx):
        if not ctx.guild:
            raise commands.CheckFailure("Only usable within a server")
        if not ctx.guild.me.voice:
            raise commands.CheckFailure("I am not in voice no need to stop")
        my_voice = ctx.guild.me.voice.channel
        if checks.is_owner_or_moderator_check(ctx.message):
            return True
        if ctx.guild.me.voice:
            if len(my_voice.members) == 2 and ctx.author in my_voice.members:
                return True
            if len(my_voice.members) == 1:
                return True
            raise commands.CheckFailure(
                    "Can only stop when nobody or"
                    "only one in voice channel with me"
                    )
    return commands.check(predicate)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # This ensures the client isn't overwritten during cog reloads.
        if not hasattr(bot, 'lavalink'):
            bot.lavalink = lavalink.Client(bot.user.id)
            # Host, Port, Password, Region, Name
            bot.lavalink.add_node(
                    '127.0.0.1',
                    2333,
                    'youshallnotpass',
                    'us',
                    'default-node')
            bot.add_listener(bot.lavalink.voice_update_handler,
                             'on_socket_response')

        bot.lavalink.add_event_hook(self.track_hook)
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

    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            guild_id = int(event.player.guild_id)
            await self.connect_to(guild_id, None)
            # Disconnect from the channel -- there's nothing else to play.
        if isinstance(event, lavalink.events.TrackEndEvent):
            if self.skip_votes and guild_id in self.skip_votes.keys():
                self.skip_votes[guild_id].clear()
            await self.bot.change_presence(activity=None)
        if isinstance(event, lavalink.events.TrackStartEvent):
            await self.bot.change_presence(
                    activity=discord.Game(name=event.player.current.title)
                    )
        if isinstance(event, lavalink.events.TrackExceptionEvent):
            channel = event.player.fetch('channel')
            await channel.send(f"Error while playing Track: **{event.track.title}**:\n"
                               f"`{event.exception}`")

    async def connect_to(self, guild_id: int, channel_id: str):
        """ Connects to the given voicechannel ID.
        A channel_id of `None` means disconnect. """
        ws = self.bot._connection._get_websocket(guild_id)
        await ws.voice_state(str(guild_id), channel_id)
        # The above looks dirty,
        # we could alternatively use `bot.shards[shard_id].ws` but that assumes
        # the bot instance is an AutoShardedBot.

    @commands.command()                                                                              
    async def junbi_ok(self, ctx):                                                                   
                                                                                                     
        player = self.bot.lavalink.players.get(ctx.guild.id)                                         
        results = await player.node.get_tracks("https://youtu.be/wWQPnhG0xHU")
        player.add(requester=ctx.author.id, track=results["tracks"][0])                    
        await ctx.send("junbi ok \N{OK Hand Sign}")                                                                
        if not player.is_playing:                                                                    
            await player.play()      

    @commands.command(aliases=['p'])
    async def play(self, ctx, *, query: str):
        """ Searches and plays a song from a given query. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

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

    @commands.command()
    async def seek(self, ctx, *, seconds: int):
        """ Seeks to a given position in a track. """
        player = self.bot.lavalink.players.get(ctx.guild.id)
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
        player = self.bot.lavalink.players.get(ctx.guild.id)

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
        player = self.bot.lavalink.players.get(ctx.guild.id)

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
                await ctx.send(f"current skip vote: "
                               f"{math.ceil(number_of_users_in_voice/2) - skip_vote_number}"
                               f"more vote(s) needed "
                               f"for skip")

    @commands.command()
    @can_stop()
    async def stop(self, ctx):
        """ Stops the player and clears its queue. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Not playing.')

        player.queue.clear()
        await player.stop()
        await ctx.send('⏹ | Stopped.')

    @commands.command(aliases=['np', 'n', 'playing'])
    async def now(self, ctx):
        """ Shows some stats about the currently playing song. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.current:
            return await ctx.send('Nothing playing.')

        position = lavalink.utils.format_time(player.position)
        requester = ctx.guild.get_member(player.current.requester)
        if player.current.stream:
            duration = '🔴 LIVE'
        else:
            duration = lavalink.utils.format_time(player.current.duration)
        song = f'**[{player.current.title}]({player.current.uri})**\n({position}/{duration}) ' \
               f'requested by **{requester.display_name if requester else "?"}**'

        embed = discord.Embed(color=discord.Color.blurple(),
                              title='Now Playing', description=song)
        await ctx.send(embed=embed)

    @commands.command(aliases=['q', 'playlist'])
    async def queue(self, ctx, page: int = 1):
        """ Shows the player's queue. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.queue:
            return await ctx.send('Nothing queued.')

        items_per_page = 10
        pages = math.ceil(len(player.queue) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue_list = ''
        for index, track in enumerate(player.queue[start:end], start=start):
            requester = ctx.guild.get_member(track.requester)
            queue_list += f'`{index + 1}.` [**{track.title}**]({track.uri}) requested by **{requester.display_name if requester else "?"}**\n'

        embed = discord.Embed(colour=discord.Color.blurple(),
                              description=f'**{len(player.queue)} tracks**\n\n{queue_list}')
        embed.set_footer(text=f'Viewing page {page}/{pages}')
        await ctx.send(embed=embed)

    @commands.command(aliases=['resume'])
    @checks.is_owner_or_moderator()
    async def pause(self, ctx):
        """ Pauses/Resumes the current track. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

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
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not volume:
            return await ctx.send(f'🔈 | {player.volume}%')

        await player.set_volume(volume)  # Lavalink will automatically cap values between, or equal to 0-1000.
        await ctx.send(f'🔈 | Set to {player.volume}%')

    @commands.command()
    @checks.is_owner_or_moderator()
    async def shuffle(self, ctx):
        """ Shuffles the player's queue. """
        player = self.bot.lavalink.players.get(ctx.guild.id)
        if not player.is_playing:
            return await ctx.send('Nothing playing.')

        player.shuffle = not player.shuffle
        await ctx.send('🔀 | Shuffle ' + ('enabled' if player.shuffle else 'disabled'))

    @commands.command(aliases=['loop'])
    async def repeat(self, ctx):
        """ Repeats the current song until the command is invoked again or until a new song is queued. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send('Nothing playing.')

        player.repeat = not player.repeat
        await ctx.send('🔁 | Repeat ' + ('enabled' if player.repeat else 'disabled'))

    @commands.command()
    async def remove(self, ctx, index: int):
        """ Removes an item from the player's queue with the given index. """
        player = self.bot.lavalink.players.get(ctx.guild.id)
        if checks.is_owner_or_moderator_check(ctx.message) or ctx.author.id == player.queue[index-1].requester:
            if not player.queue:
                return await ctx.send('Nothing queued.')

            if index > len(player.queue) or index < 1:
                return await ctx.send(f'Index has to be **between** 1 and {len(player.queue)}')

            removed = player.queue.pop(index - 1)  # Account for 0-index.

            await ctx.send(f'Removed **{removed.title}** from the queue.')
        else:
            await ctx.send("Only requester and moderators can remove from the list")



    @commands.command(aliases=["search"])
    async def find(self, ctx, *, query):
        """ Lists the first 10 search results from a given query. 
            also allows you to queue one of the results
        """
        player = self.bot.lavalink.players.get(ctx.guild.id)

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

    @commands.command(aliases=['dc'])
    @can_stop()
    async def disconnect(self, ctx):
        """ Disconnects the player from the voice channel and clears its queue. """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send('Not connected.')

        player.queue.clear()
        await player.stop()
        await self.connect_to(ctx.guild.id, None)
        await ctx.send('*⃣ | Disconnected.')

    async def ensure_voice(self, ctx):
        """ This check ensures that the bot and command author are in the same voicechannel. """
        player = self.bot.lavalink.players.create(ctx.guild.id, endpoint=str(ctx.guild.region))
        # Create returns a player if one exists, otherwise creates.

        should_connect = ctx.command.name in ('play', 'junbi_ok')  # Add commands that require joining voice to work.

        if ctx.command.name in ('find', 'disconnect', 'now'):
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandInvokeError('Join a voicechannel first.')

        permissions = ctx.author.voice.channel.permissions_for(ctx.me)

        if not permissions.connect or not permissions.speak:  # Check user limit too?
            raise commands.CommandInvokeError('I need the `CONNECT` and `SPEAK` permissions.')

        if not player.is_connected:
            if not should_connect:
                raise commands.CommandInvokeError('Not connected.')

            player.store('channel', ctx.channel)
            await self.connect_to(ctx.guild.id, str(ctx.author.voice.channel.id))
        elif player.is_connected and not self.current_voice_channel(ctx):
            self.bot.lavalink.players.remove(ctx.guild.id)
            player = self.bot.lavalink.players.create(ctx.guild.id)
            if not should_connect:
                raise commands.CommandInvokeError('Not connected.')

            player.store('channel', ctx.channel)
            await self.connect_to(ctx.guild.id, str(ctx.author.voice.channel.id))
        else:
            if int(player.channel_id) != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError('You need to be in my voicechannel.')


def setup(bot):
    bot.add_cog(Music(bot))

import asyncio
import discord
from discord.ext import commands
from .utils import checks
import time
import re

"""
Credits to https://github.com/Rapptz/ for the cog
"""
if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('/usr/local/lib/libopus.so')

class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = '**{0.title}** requested by **{1.display_name}**'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)

class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set() # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())
        self.song_queue = list()
        self.wait_timer = time.time()

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)


    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            await self.bot.change_presence(game=None)
            self.wait_timer = time.time()
            self.current = await self.songs.get()
            self.song_queue.pop(0)
            self.skip_votes.clear()
            await self.bot.send_message(self.current.channel, 'Now playing ' + str(self.current))
            await self.bot.change_presence(game=discord.Game(name=self.current.player.title))
            self.current.player.start()
            await self.play_next_song.wait()

class Music:
    """Voice related commands.

    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}
        self.timeout_timer_task = self.bot.loop.create_task(self.timeout_timer(300))

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass
        #self.check_running_task.cancel()

    async def leave_voice_channel(self, voice_channel, voice_id):
        voice_channel.audio_player.cancel()
        del self.voice_states[voice_id]
        voice_channel.song_queue.clear()
        await voice_channel.voice.disconnect()
        await self.bot.change_presence(game=None)

    async def timeout_timer(self, timeout):
        """
        disconnect after playing no music for a certain amount of time
        :param timeout: number of seconds the bot will wait until disconnecting
        :return: null
        """
        while self == self.bot.get_cog('Music'):
            voice_states_copy = self.voice_states.copy()
            for voice_id in voice_states_copy:
                voice_channel = self.voice_states.get(voice_id)
                if not voice_channel.is_playing() and time.time() - voice_channel.wait_timer > timeout:
                    try:
                        await self.leave_voice_channel(voice_channel, voice_id)
                    except:
                        pass
            await asyncio.sleep(5)

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel: discord.Channel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Already in a voice channel...')
        except discord.InvalidArgument:
            await self.bot.say('This is not a voice channel...')
        else:
            await self.bot.say('Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str):
        """Plays a song.

        If there is a song currently in the queue, then it is
        queued until the next song is done playing.

        This command automatically searches as well from YouTube.
        The list of supported sites can be found here:
        https://rg3.github.io/youtube-dl/supportedsites.html
        """
        state = self.get_voice_state(ctx.message.server)
        user_voice_channel = ctx.message.author.voice_channel
        if user_voice_channel is None:
            await self.bot.say('You are not in a voice channel.')
            return
        opts = {
            'default_search': 'auto',
            'quiet': True,
            'geo-bypass': True
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return

        try:
            beforeArgs = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 15"
            song = self.format_non_embed_link(song)
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next,before_options=beforeArgs)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            if player.is_live:
                await self.bot.say("livestream, skipped.")
                return
            entry = VoiceEntry(ctx.message, player)
            state.song_queue.append(entry)
            await self.bot.say('Enqueued ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Sets the volume of the currently playing song."""

        if value > 80:
            await self.bot.say("Earrape mode disabled, please don't make me shout >.<")
            return
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    @checks.is_owner_or_moderator()
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.

        This also clears the queue.
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            await self.leave_voice_channel(voice_channel=state, voice_id=server.id)
        except Exception as e:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.

        50% or more of total voice chat users skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Not playing any music right now...')
            return

        voter = ctx.message.author
        # subtract the bot from the user count
        user_count = len(state.voice.channel.voice_members) - 1
        if voter == state.current.requester:
            await self.bot.say('Requester requested skipping song...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            percentage = int((total_votes/user_count) * 100)
            if float(total_votes) >= user_count/2:
                await self.bot.say('Skip vote passed, skipping song...')
                state.song_queue.pop(0)
                state.skip()
            else:
                await self.bot.say("Voted to skip currently at[{}/{}]({}%)".format(total_votes,user_count,percentage))

        else:
            await self.bot.say('You have already voted to skip this song.')

    @commands.command(pass_context=True, no_pm=True)
    async def unskip(self, ctx):
        """
        withdraw skip vote
        """
        state = self.get_voice_state(ctx.message.server)
        voter = ctx.message.author
        # subtract the bot from the user count
        user_count = len(state.voice.channel.voice_members) - 1
        if voter.id not in state.skip_votes:
            await self.bot.say("You haven't voted skip ")
        else:
            state.skip_votes.discard(voter.id)
            total_votes = len(state.skip_votes)
            percentage = int((total_votes/user_count) * 100)
            await self.bot.say("Vote withdrawn currently at[{}/{}]({}%)".format(total_votes,user_count,(percentage)))

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.server)
        user_count = len(state.voice.channel.voice_members) - 1
        if state.current is None:
            await self.bot.say('Not playing anything.')
        else:
            skip_count = len(state.skip_votes)
            await self.bot.say('Now playing {} [skips: {}/{}]\n'.format(state.current, skip_count,user_count))
            if state.song_queue:
                message = '\nUpcoming songs:\n'
                for index, entry in enumerate(state.song_queue):
                    message += str(index+1) + '. {}\n'.format(entry)
                await self.bot.say(message)

    def format_non_embed_link(self, link: str):
        find_url_regex = re.search('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', link)
        if find_url_regex:
            if '<' in link[0] or '>' in link[len(link)-1]:
                return link[1:len(link)-1]
        return link


def setup(bot):
    bot.add_cog(Music(bot))


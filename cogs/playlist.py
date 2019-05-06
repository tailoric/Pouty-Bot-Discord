import asyncio
import discord
from discord.ext import commands
from .utils import checks
import time
import re
import youtube_dl as ytdl
import os

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
    def __init__(self, message, audio_source, info, filename):
        self.requester = message.author
        self.channel = message.channel
        self.audio_source = audio_source
        self.filename = filename
        self.info = info

    def __str__(self):
        fmt = '**{0.title}** requested by **{1.display_name}**'
        duration = self.info.get("duration", None)
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))

        return fmt.format(self.audio_source, self.requester)

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
        self.start_time = time

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
            # await self.bot.change_presence(game=None)
            self.wait_timer = time.time()
            self.current = await self.songs.get()
            self.song_queue.pop(0)
            self.skip_votes.clear()
            # await self.current.channel.send('Now playing ' + str(self.current))
            # await self.bot.change_presence(game=discord.Game(name=self.current.audio_source.title))
            self.voice.state.play(self.current.audio_source, after=self.toggle_next)
            self.start_time = time.time()
            await self.play_next_song.wait()

class Music(commands.Cog):
    """Voice related commands.

    Works in multiple servers at once.
    """
    def __init__(self, bot):
        self.bot = bot
        opts = {
            'default_search': 'auto',
            'quiet': True,
            'extractaudio': True,
            'format': 'bestaudio',
            'buffer-size': 16000,
            'progress_hooks' : [self.download_hook],
            'outtmpl': "data/ytdl/%(title)s.%(ext)s"
        }
        self.ytdownloader = ytdl.YoutubeDL(opts)
        self.voice_states = {}
        self.downloads = asyncio.Queue()
        self.finished_downloads = list()
        self.timeout_timer_task = self.bot.loop.create_task(self.timeout_timer(300))
        self.downloader = self.bot.loop.create_task(self.downloader_task())

    def download_hook(self, download):
        if download['status'] == 'finished':
            download['filename'] = download['filename'].replace('\\', '/')
            self.finished_downloads.append(download["filename"])

    async def downloader_task(self):
        while True:
            queried_song = await self.downloads.get()
            info = self.ytdownloader.extract_info(queried_song["item"])
            filename = self.finished_downloads.pop()
            entry = VoiceEntry(queried_song["ctx"].message, discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(source=filename)), info, filename)
            queried_song["state"].song_queue.append(entry)
            await queried_song["state"].songs.put(entry)

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.guild)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                self.timeout_timer_task.cancel()
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
                    except Exception as e:
                        print(e)
            await asyncio.sleep(5)

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel: discord.VoiceChannel):
        """Joins a voice channel."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await ctx.send('Already in a voice channel...')
        except discord.InvalidArgument:
            await ctx.send('This is not a voice channel...')
        else:
            await ctx.send('Ready to play audio in ' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Summons the bot to join your voice channel."""
        summoned_channel = ctx.message.author.voice.channel
        if summoned_channel is None:
            await ctx.send('You are not in a voice channel.')
            return False

        state = self.get_voice_state(ctx.message.guild)
        if state.voice is None:
            state.voice = await summoned_channel.connect()
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
        state = self.get_voice_state(ctx.message.guild)
        user_voice_channel = ctx.message.author.voice.channel
        if user_voice_channel is None:
            await ctx.send('You are not in a voice channel.')
            return
        if state.voice is None:
            success = await ctx.invoke(self.summon)
            if not success:
                return
        try:
            download_item = {
                "item": song,
                "ctx": ctx,
                "state": state
            }
            await self.downloads.put(download_item)
        except Exception as e:
            fmt = 'An error occurred while processing this request: ```py\n{}: {}\n```'
            await ctx.message.channel.send(fmt.format(type(e).__name__, e))

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Sets the volume of the currently playing song."""

        if value > 80:
            await ctx.send("Earrape mode disabled, please don't make me shout >.<")
            return
        state = self.get_voice_state(ctx.message.guild)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await ctx.send('Set the volume to {:.0%}'.format(player.volume))

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Stops playing audio and leaves the voice channel.

        This also clears the queue.
        """
        server = ctx.message.guild
        state = self.get_voice_state(server)

        if state.voice.is_playing():
            state.voice.channel.stop()

        try:
            await state.voice.disconnect()
        except Exception as e:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Vote to skip a song. The song requester can automatically skip.

        50% or more of total voice chat users skip votes are needed for the song to be skipped.
        """

        state = self.get_voice_state(ctx.message.guild)
        if not state.is_playing():
            await ctx.send('Not playing any music right now...')
            return

        voter = ctx.message.author
        # subtract the bot from the user count
        user_count = len(state.voice.channel.voice_members) - 1
        if voter == state.current.requester:
            await ctx.send('Requester requested skipping song...')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            percentage = int((total_votes/user_count) * 100)
            if float(total_votes) >= user_count/2:
                await ctx.send('Skip vote passed, skipping song...')
                state.skip()
            else:
                await ctx.send("Voted to skip currently at[{}/{}]({}%)".format(total_votes,user_count,percentage))

        else:
            await ctx.send('You have already voted to skip this song.')

    @commands.command(pass_context=True, no_pm=True)
    async def unskip(self, ctx):
        """
        withdraw skip vote
        """
        state = self.get_voice_state(ctx.message.guild)
        voter = ctx.message.author
        # subtract the bot from the user count
        user_count = len(state.voice.channel.voice_members) - 1
        if voter.id not in state.skip_votes:
            await ctx.send("You haven't voted skip ")
        else:
            state.skip_votes.discard(voter.id)
            total_votes = len(state.skip_votes)
            percentage = int((total_votes/user_count) * 100)
            await ctx.send("Vote withdrawn currently at[{}/{}]({}%)".format(total_votes,user_count,(percentage)))

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Shows info about the currently played song."""

        state = self.get_voice_state(ctx.message.guild)
        user_count = len(state.voice.channel.voice_members) - 1
        if state.current is None:
            await ctx.send('Not playing anything.')
        else:
            player = state.current.player
            find_url_regex = re.search('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', state.current.player.url)
            url = None
            if not find_url_regex:
                yt = ytdl.YoutubeDL({'quiet': True})
                info = yt.extract_info("ytsearch: "+ state.current.player.url, download=False)
                url = info['entries'][0]['webpage_url']
            else:
                url = state.current.player.url
            skip_count = len(state.skip_votes)
            fmt_playtime = self.get_playtime(player)
            await ctx.send('Now playing {} [skips: {}/{}]{}\n<{}>\n'.format(state.current, skip_count,user_count,fmt_playtime, url))
            if state.song_queue:
                message = '\nUpcoming songs:\n'
                for index, entry in enumerate(state.song_queue):
                    message += str(index+1) + '. {}\n'.format(entry)
                await ctx.send(message)

    def get_playtime(self, player):
        playtime = time.time() - player._start
        if player.duration:
            return '`[{0}/{1}]`'.format(
                time.strftime('%H:%M:%S', time.gmtime(playtime)),
                time.strftime('%H:%M:%S', time.gmtime(player.duration))
            )
        else:
            return '`[{0}]`'.format(time.strftime('%H:%M:%S', time.gmtime(playtime)))
    def format_non_embed_link(self, link: str):
        find_url_regex = re.search('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', link)
        if find_url_regex:
            if '<' in link[0] or '>' in link[len(link)-1]:
                return link[1:len(link)-1]
        return link


def setup(bot):
    bot.add_cog(Music(bot))


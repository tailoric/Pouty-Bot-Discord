from discord.ext import commands
from enum import Enum, auto
from .utils import checks
import random


class CardColor(Enum):
    heart = "\N{WHITE HEART SUIT}"
    spade = "\N{WHITE SPADE SUIT}"
    diamond = "\N{WHITE DIAMOND SUIT}"
    club = "\N{WHITE CLUB SUIT}"


class GameState(Enum):
    RUNNING = auto()
    DEALER_PHASE = auto()
    GAME_OVER = auto()


class Card():
    def __init__(self, value, color, face):
        self.value = value
        self.color = color
        self.face = face

    def __str__(self):
        return f"{self.face}{self.color}"


class BlackJackGame():

    def __init__(self, ctx, player, bet):
        self.player = player
        self.ctx = ctx
        self.state = GameState.RUNNING
        self.bet = bet
        self.deck = self.generate_deck()
        self.dealer_hand = [self.deck.pop(0), self.deck.pop(0)]
        self.player_hand = [self.deck.pop(0), self.deck.pop(0)]
        if self.player_value == 21:
            self.state = GameState.DEALER_PHASE

    def __eq__(self, other):
        return self.player == other.player

    def generate_deck(self):
        deck = []
        for color in list(CardColor):
            deck.append(Card(1, color.value, "A"))
            deck.append(Card(10, color.value, "J"))
            deck.append(Card(10, color.value, "Q"))
            deck.append(Card(10, color.value, "K"))
            for i in range(2, 11):
                deck.append(Card(i, color.value, str(i)))
        random.shuffle(deck)
        return deck

    @property
    def player_value(self):
        total = sum(c.value for c in self.player_hand)
        if any(c.face == "A" for c in self.player_hand) and total <= 11:
            total += 10
        return total

    @property
    def dealer_value(self):
        total = sum(c.value for c in self.dealer_hand)
        if any(c.face == "A" for c in self.dealer_hand) and total <= 11:
            total += 10
        return total

    
    def get_winner(self):

        if self.state in (GameState.DEALER_PHASE, GameState.RUNNING):
            return "running", False

        dealer_has_bj = len(self.dealer_hand) == 2 and self.dealer_value == 21
        player_has_bj = len(self.player_hand) == 2 and self.player_value == 21
        if self.player_value > 21:
            return "dealer", False
        elif self.dealer_value > 21 or self.player_value > self.dealer_value:
            return "player", player_has_bj
        elif self.player_value < self.dealer_value:
            return "dealer", False
        elif self.player_value == self.dealer_value:
            if player_has_bj and dealer_has_bj:
                return "tie", False
            if player_has_bj and not dealer_has_bj:
                return "player", True
            return "tie", False

    def player_draw(self):
        card = self.deck.pop(0)
        self.player_hand.append(card)
        if self.player_value == 21:
            self.state = GameState.DEALER_PHASE
            self.stand()
        elif self.player_value > 21:
            self.state = GameState.GAME_OVER
        return card

    def dealer_draw(self):
        card = self.deck.pop(0)
        self.dealer_hand.append(card)
        if self.dealer_value > 21:
            self.state = GameState.GAME_OVER
        return card
    
    def stand(self):
        if self.state == GameState.GAME_OVER:
            return
        while(self.dealer_value < 17):
            self.dealer_draw()
        self.state = GameState.GAME_OVER

    def __str__(self):
        dealer_hand = ""
        player_hand = (f"**{self.player.display_name}** hand:"
                       f" {', '.join([str(x) for x in self.player_hand])}"
                       f" total: {self.player_value}")
        if self.state == GameState.RUNNING:
            dealer_hand = (f"**dealer** hand: {self.dealer_hand[0]}, "
                           f"? total: {self.dealer_hand[0].value}\n")
        else:
            dealer_hand = (f"**dealer** hand:"
                           f" {', '.join([str(x) for x in self.dealer_hand])}"
                           f" total: {self.dealer_value}")
        return f"{dealer_hand}\n{player_hand}"

class BlackJack(commands.Cog):
    """
    gamble your life away in Blackjack
    """
    def __init__(self, bot):
        self.bot = bot
        self.payday = self.bot.get_cog("Payday")
        self.games = []

    def cog_unload(self):
        if not self.payday:
            return
        try:
            for game in self.games:
                self.bot.loop.create_task(self.payday.add_money(game.player.id, game.bet))
                self.games.remove(game)
                del game
        except Exception as e:
            import logging
            logger = logging.getLogger("PoutyBot")
            logger.error("Exception while giving back blackjack bets", exc_info=1)
            owner = self.bot.get_user(self.bot.owner_id)
            pending_payouts = "Some BlackJack payouts are still pending\n"
            for game in self.games:
                pending_payouts += f"{game.player.mention}: {game.bet:,}"
            self.bot.loop.create_task(owner.send(pending_payouts))

    async def cog_before_invoke(self, ctx):
        # try to ensure that payday is loaded everytime we invoke a command
        self.payday = self.bot.get_cog("Payday")

    @commands.group(name="blackjack",invoke_without_command=True, aliases=["bj"])
    @checks.channel_only("test", "bot-shenanigans", 336912585960194048)    
    @commands.guild_only()
    async def blackjack_group(self, ctx, bet:int):
        """
        very basic implementation of black jack:
        Every game/round starts with a full deck
        You can only hit (draw a new card) or stand (let dealer draw)
        If you win with a Blackjack you get 1.5 times of your bet as payout
        otherwise you get the bet as payout.
        """
        if self.payday:
            balance = await self.payday.fetch_money(ctx.author.id)
            if not balance:
                return await ctx.send("No bank account create one with `.payday`")
            if balance.get("money") < bet:
                return await ctx.send("You can't bet more than you own!")
        else:
            await ctx.send("Payday not loaded this game is just for fun")
        if bet < 1:
            return await ctx.send("You can't bet less than 1")
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if game:
            return await ctx.send("You already started a game either hit or stand")
        game = BlackJackGame(ctx, ctx.author, bet)
        if self.payday:
            await self.payday.subtract_money(ctx.author.id, bet)
        self.games.append(game)
        if game.state == GameState.DEALER_PHASE:
            game.stand()
            await self.payout(ctx, game)
            return
        return await ctx.send(game)

    async def payout(self, ctx, game):
        self.games.remove(game)
        balance = 0
        if not self.payday:
            balance = game.bet
        winner, is_blackjack = game.get_winner()
        if winner == "dealer":
            winner = "**Dealer** wins!"
            if self.payday:
                balance = (await self.payday.fetch_money(ctx.author.id)).get("money")
        elif winner == "player":
            winner = f"**{game.player.display_name}** wins!" 
            multiplicator = 1.5 if is_blackjack else 1
            if self.payday:
                balance = await self.payday.add_money(ctx.author.id, int(game.bet + game.bet * multiplicator))
        elif winner == "tie":
            winner = f"**Game is a tie!**"
            if self.payday:
                balance = await self.payday.add_money(ctx.author.id, game.bet)
        await ctx.send(f"{winner}\nnew balance: {balance:,}\n{game}")
        del game

    @blackjack_group.command(name="hit", aliases=["draw"])
    async def draw_card(self, ctx):
        """
        draw a new card if you go over 21 you lose!
        """
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if not game:
            return await ctx.send("No game running start one with `.bj`")
        game.player_draw()
        if game.state == GameState.DEALER_PHASE or game.state == GameState.GAME_OVER:
            game.stand()
            await self.payout(ctx, game)
            return
        return await ctx.send(game)

    @blackjack_group.command(name="surrender", aliases=["fold"])
    async def surrender(self, ctx):
        """
        If you don't like your initial hand you can discard the game and start new
        only works if you haven't hit yet
        """
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if not game:
            return await ctx.send("No game running start one with `.bj`")
        if len(game.player_hand) > 2:
            return await ctx.send("You already drew at least a card, you are now commited to this game")
        if self.payday:
            await self.payday.add_money(ctx.author.id, game.bet)
            await ctx.send("You gave up on this game and got your bet back, better luck next time.")
        else:
            await ctx.send("No money was bet but this game still gets stopped, better luck next time.")
        self.games.remove(game) 
        del game

    @blackjack_group.command(name="stand", aliases=["stop"])
    async def stand(self, ctx):
        """
        stop drawing cards and let the dealer draw, game is over after this
        """
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if not game:
            return await ctx.send("No game running start one with `.bj`")
        game.stand()
        await self.payout(ctx, game)

    @blackjack_group.command(name="status")
    async def status(self, ctx):
        """
        gives you the status of the currently running game
        """
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if not game:
            return await ctx.send("No game running start one with `.bj`")
        await ctx.send(str(game)+f"\nbet: {game.bet}")


def setup(bot):
    bot.add_cog(BlackJack(bot))

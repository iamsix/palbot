import discord
from discord.ext import commands

class TTTButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        # Using a zero-width space (\u200b) keeps the buttons reasonably sized when empty
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.board_index = y * 3 + x

    async def callback(self, interaction: discord.Interaction):
        # Pass the interaction and the specific button clicked back to the View
        await self.view.handle_move(interaction, self)

class TTTView(discord.ui.View):
    def __init__(self, p1: discord.Member):
        super().__init__(timeout=None)
        self.p1 = p1
        self.p2 = None
        self.p1_moves = [] # Tracks board indices for X
        self.p2_moves = [] # Tracks board indices for O
        
        # Build the 3x3 grid
        for y in range(3):
            for x in range(3):
                self.add_item(TTTButton(x, y))

    def check_win(self, symbol: str) -> bool:
        winning_lines = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8], # Horizontal
            [0, 3, 6], [1, 4, 7], [2, 5, 8], # Vertical
            [0, 4, 8], [2, 4, 6]             # Diagonal
        ]
        for line in winning_lines:
            if all(self.children[i].label == symbol for i in line):
                return True
        return False

    async def handle_move(self, interaction: discord.Interaction, button: TTTButton):
        # Determine whose turn it is based on the number of moves made
        is_p1_turn = len(self.p1_moves) == len(self.p2_moves)
        
        # ---------------- TURN VALIDATION ----------------
        if is_p1_turn:
            if interaction.user != self.p1:
                return await interaction.response.send_message("It is Player 1's turn!", ephemeral=True)
            
            symbol = 'X'
            style = discord.ButtonStyle.success # Green for X
            active_moves = self.p1_moves
            next_player_text = f"{self.p2.mention}'s turn (O)" if self.p2 else "Waiting for Player 2 to click..."
            
        else:
            # If Player 2 hasn't been assigned yet, the first person to click (who isn't P1) becomes P2.
            if self.p2 is None:
                if interaction.user == self.p1:
                    return await interaction.response.send_message("You can't play against yourself! Waiting for someone else to click.", ephemeral=True)
                self.p2 = interaction.user
            
            if interaction.user != self.p2:
                return await interaction.response.send_message(f"It is {self.p2.display_name}'s turn!", ephemeral=True)
            
            symbol = 'O'
            style = discord.ButtonStyle.danger # Red for O
            active_moves = self.p2_moves
            next_player_text = f"{self.p1.mention}'s turn (X)"

        # ---------------- APPLY MOVE ----------------
        button.label = symbol
        button.style = style
        button.disabled = True
        active_moves.append(button.board_index)

        # ---------------- THE CATCH (Infinite Logic) ----------------
        # If the player has made more than 3 moves, clear their oldest move
        if len(active_moves) > 3:
            oldest_index = active_moves.pop(0)
            oldest_button = self.children[oldest_index]
            
            # Reset the oldest button to empty
            oldest_button.label = '\u200b'
            oldest_button.style = discord.ButtonStyle.secondary
            oldest_button.disabled = False

        # ---------------- WIN CHECK ----------------
        if self.check_win(symbol):
            # Disable all buttons upon victory
            for child in self.children:
                child.disabled = True
            
            winner = self.p1 if symbol == 'X' else self.p2
            content = f"🏆 **{winner.mention} wins!**"
            await interaction.response.edit_message(content=content, view=self)
            self.stop()
            return

        # ---------------- CONTINUE GAME ----------------
        await interaction.response.edit_message(content=next_player_text, view=self)


class InfiniteTicTacToe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tictactoe", aliases=["ttt"])
    async def tictactoe(self, ctx):
        """Starts a game of Infinite Tic-Tac-Toe."""
        view = TTTView(ctx.author)
        content = f"**Infinite Tic-Tac-Toe!** Only your last 3 moves stay on the board.\n{ctx.author.mention} goes first (X). **Anyone else** can click next to become Player 2 (O)!"
        
        await ctx.send(content, view=view)

# Setup function to load the cog
async def setup(bot):
    await bot.add_cog(InfiniteTicTacToe(bot))
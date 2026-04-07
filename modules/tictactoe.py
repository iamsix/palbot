import discord
from discord.ext import commands

class TTTButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.board_index = y * 3 + x

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_move(interaction, self)

class TTTView(discord.ui.View):
    def __init__(self, p1: discord.Member):
        super().__init__(timeout=None)
        self.p1 = p1
        self.p2 = None
        self.p1_moves = [] 
        self.p2_moves = [] 
        
        # FIX: Added a dedicated turn tracker instead of relying on array lengths
        self.is_p1_turn = True 
        
        for y in range(3):
            for x in range(3):
                self.add_item(TTTButton(x, y))

    def check_win(self, symbol: str) -> bool:
        winning_lines = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]            
        ]
        for line in winning_lines:
            if all(self.children[i].label == symbol for i in line):
                return True
        return False

    async def handle_move(self, interaction: discord.Interaction, button: TTTButton):
        # ---------------- TURN VALIDATION ----------------
        if self.is_p1_turn:
            if interaction.user != self.p1:
                return await interaction.response.send_message("It is Player 1's turn!", ephemeral=True)
            
            symbol = 'X'
            style = discord.ButtonStyle.success 
            active_moves = self.p1_moves
            next_player_text = f"{self.p2.mention}'s turn (O)" if self.p2 else "Waiting for Player 2 to click..."
            
        else:
            if self.p2 is None:
                if interaction.user == self.p1:
                    return await interaction.response.send_message("You can't play against yourself! Waiting for someone else to click.", ephemeral=True)
                self.p2 = interaction.user
            
            if interaction.user != self.p2:
                return await interaction.response.send_message(f"It is {self.p2.display_name}'s turn!", ephemeral=True)
            
            symbol = 'O'
            style = discord.ButtonStyle.danger 
            active_moves = self.p2_moves
            next_player_text = f"{self.p1.mention}'s turn (X)"

        # ---------------- APPLY MOVE ----------------
        button.label = symbol
        button.style = style
        button.disabled = True
        active_moves.append(button.board_index)

        # ---------------- THE CATCH (Infinite Logic) ----------------
        if len(active_moves) > 3:
            oldest_index = active_moves.pop(0)
            oldest_button = self.children[oldest_index]
            
            oldest_button.label = '\u200b'
            oldest_button.style = discord.ButtonStyle.secondary
            oldest_button.disabled = False

        # ---------------- WIN CHECK ----------------
        if self.check_win(symbol):
            for child in self.children:
                child.disabled = True
            
            winner = self.p1 if symbol == 'X' else self.p2
            content = f"🏆 **{winner.mention} wins!**"
            await interaction.response.edit_message(content=content, view=self)
            self.stop()
            return

        # ---------------- CONTINUE GAME ----------------
        # FIX: Flip the turn state manually after a successful move
        self.is_p1_turn = not self.is_p1_turn
        
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

async def setup(bot):
    await bot.add_cog(InfiniteTicTacToe(bot))
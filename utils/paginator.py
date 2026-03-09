import discord

class Paginator(discord.ui.View):
    def __init__(self, ctx, data, callback):
        super().__init__(timeout=300.0) 
        self.ctx = ctx
        self.data = data
        self.callback = callback
        self.current_page = 0
        self.message = None

        self.update_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message("Only the command author can change pages.", ephemeral=True)
        return False
    
    def update_buttons(self):
        """Updates the label of the indicator button."""
        total_pages = len(self.data)
        self.page_indicator.label = f"{self.current_page + 1} / {total_pages}"
        if total_pages <= 1:
            self.clear_items()

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def get_page_content(self, page_number):
        self.current_page = page_number % len(self.data)
        content, embed = await self.callback(self.data, self.current_page)
        return content, embed

    # Left
    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        content, embed = await self.get_page_content(self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # Right
    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        content, embed = await self.get_page_content(self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(content=content, embed=embed, view=self)

    async def start(self):
        content, embed = await self.get_page_content(0)
        # Send the message, attach the view, and pass paginator=self for your MoreContext logic
        self.message = await self.ctx.send(content=content, embed=embed, view=self, paginator=self)
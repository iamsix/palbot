import asyncio


class Paginator:
    def __init__(self, ctx, data, callback):
        self.bot = ctx.bot
        self.ctx = ctx
        self.waiting = None
        self.channel = ctx.channel
        self.callback = callback
        self.message = ctx.message
        self.author = ctx.author
        self.data = data
        self.paginating = len(data) > 1
        self.current_page = 0
        self.interface = {
                '\N{BLACK LEFT-POINTING TRIANGLE}': self.previous_page,
                '\N{BLACK RIGHT-POINTING TRIANGLE}': self.next_page,
                }
        print(id(self))

    def __del__(self):
        self.paginating = False
        self.func = lambda:None
        self.waiting = lambda:None
        self.message = None

    async def next_page(self):
        await self.load_page(self.current_page + 1)

    async def previous_page(self):
        await self.load_page(self.current_page - 1)

    async def load_page(self, page_number, post=False):
        page_number = page_number % (len(self.data))
        self.current_page = page_number
        content, embed = await self.callback(self.data, page_number)
        if not post:
            await self.message.edit(content=content, embed=embed)
            return
        else:
            self.message = await self.ctx.send(content=content, embed=embed, paginator=self)
            if not self.paginating:
                return
            for emoji in self.interface.keys():
                await self.message.add_reaction(emoji)


    def react_check(self, reaction, user):
        if not self.message:
            self.func = lambda:None
            return False
        if user is None or user.id != self.author.id:
            return False
        if reaction.message.id != self.message.id:
            return False

        for emoji in self.interface.keys():
            if reaction.emoji == emoji:
                self.func = self.interface[emoji]
                return True
        return False


    async def paginate(self):
        self.bot.loop.create_task(self.load_page(0, True))
        while self.paginating:
            try:
                self.waiting = self.bot.wait_for('reaction',
                                                check=self.react_check, 
                                                timeout=300.0)
                reaction, user = await self.waiting
            except asyncio.TimeoutError:
                self.paginating = False
                try:
                    await self.message.clear_reactions()
                except:
                    print("failed to clear reactions")
                    pass
                finally:
                    break
            await self.func()


                

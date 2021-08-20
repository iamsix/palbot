import discord
from discord.ext import commands
import asyncio
import random
from statistics import mode, StatisticsError
import re


class Randomizers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def cactus(self, ctx):
        """bleeeh"""
        output = ""
        rand = random.randint(2, 10)
        for _ in range(0, rand):
            output += "ee" if random.randint(0, 5) == 0 else "e"
        await ctx.send(f"bl{output}h")

    @commands.command()
    async def brak(self, ctx):
        """mmm chicken"""
        rand = random.randint(2, 10)
        if ctx.author.display_name.lower().startswith('rc'):
            output = f"{ctx.author.mention} gets {rand}lbs of boiled beef"
        else:
            output = f"{ctx.author.mention} gets {rand} boiled chickens"
        await ctx.send(output)

    @commands.command()
    async def bbnet(self, ctx):
        """looololol"""
        if ctx.author.display_name.lower().startswith('rc'):
            output = "lol"
        else:
            output = ""
            rand = random.randint(2, 10)
            for _ in range(0, rand):
                output += "l"
                output += "oo" if random.randint(0, 5) == 0 else "o"
        await ctx.send(output)

    
    @commands.command(name="8=D")
    async def eightd(self, ctx):
        output = "8"
        rand = random.randint(2, 10)
        for _ in range(0, rand):
            output += "==" if random.randint(0, 5) == 0 else "="
        output += "D"
        await ctx.send(output)


    @commands.command()
    async def ziti(self, ctx):
        """skrrt"""
        output = ""
        rand = random.randint(2, 19)
        for _ in range(0, rand):
            output += "rr" if random.randint(0, 5) == 0 else "r"
        await ctx.send(f"sk{output}t")

    class Die:
        die_regex = re.compile(r'(\d+)?d(\d+)([\+\-]\d+)?')
        def __init__(self, die: str):
            result = self.die_regex.match(die)
            if not result:
                raise commands.BadArgument
            self.die = die
            self.count = int(result.group(1)) if result.group(1) else 1
            self.value = max(int(result.group(2)), 1) if result.group(2) else 6
            self.adjustment = int(result.group(3)) if result.group(3) else 0

        def __str__(self):
            return f"{self.count}d{self.value}"

        @classmethod
        async def convert(cls, ctx, die):
            return cls(die)

    @commands.command()
    async def roll(self, ctx, *, die: Die = Die("1d6")):
        """Roll a die such as 1d6"""
        results = []
        total = 0
        for _ in range(0,die.count):
            roll = random.randint(1,die.value)
            total += roll
            if die.value == 2:
                coins = {1: "heads", 2: "tails"}
                results.append(f"{coins[roll]} ({roll})")
            else:
                results.append(roll)
                
        
        out = f"Rolled {die}:: {', '.join(map(str, results))}"
        if die.count > 1:
            try:
                winner = f" - Most common roll: {mode(results)}"
            except StatisticsError:
                if die.value == 2:
                    winner = " - Tie"
                else:
                    winner = ""
            if die.value != 2:
                highest = f" - Highest roll: {max(results)}"
            else:
                highest = ""
            out += f" :: Total {total}{winner}{highest}"
        await ctx.send(out)

    @roll.error
    async def roll_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid input - input is format is `{ctx.prefix}roll 1d6` or `2d20`, `5d12`, etc")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(error)
            return
        else:
            raise(error)


    @commands.command(name='error')
    async def error_generator(self, ctx):
        """Error: Help Message Concatination Error"""
        firstword = random.choice(self.error_first)
        secondword = random.choice(self.error_second)
        thirdword = random.choice(self.error_third)
        fourthword = random.choice(self.error_fourth)
        if fourthword != "Flag":
            heading = f"{fourthword}: "
        else:
            heading = ""
        
        await ctx.send(f"{heading}{firstword} {secondword} {thirdword} {fourthword}")
        
    error_first = ["Temporary", "Intermittant", "Partial", "Redundant", "Total",
                    "Multiplexed", "Inherent", "Duplicated", "Dual-Homed", "Synchronous",
                    "Bidirectional", "Serial", "Asynchronous", "Multiple", "Replicated",
                    "Non-Replicated", "Unregistered", "Non-Specific", "Generic", "Migrated",
                    "Localised", "Resignalled", "Dereferenced", "Nullified", "Aborted",
                    "Serious", "Minor", "Major", "Extraneous", "Illegal", "Insufficient",
                    "Viral", "Unsupported", "Outmoded", "Legacy", "Permanent", "Invalid",
                    "Deprecated", "Virtual", "Unreportable", "Undetermined", "Undiagnosable",
                    "Unfiltered", "Static", "Dynamic", "Delayed", "Immediate", "Nonfatal",
                    "Fatal", "Non-Valid", "Unvalidated", "Non-Static", "Unreplicatable",
                    "Non-Serious"]

    error_second = ["Array", "Systems", "Hardware", "Software", "Firmware",
                    "Backplane", "Logic-Subsystem", "Integrity", "Subsystem", "Memory",
                    "Comms", "Integrity", "Checksum", "Protocol", "Parity", "Bus", "Timing",
                    "Synchronisation", "Topology", "Transmission", "Reception", "Stack",
                    "Framing", "Code", "Programming", "Peripheral", "Environmental",
                    "Loading", "Operation", "Parameter", "Syntax", "Initialisation",
                    "Execution", "Resource", "Encryption", "Decryption", "File",
                    "Precondition", "Authentication", "Paging", "Swapfile", "Service",
                    "Gateway", "Request", "Proxy", "Media", "Registry", "Configuration",
                    "Metadata", "Streaming", "Retrieval", "Installation", "Library", "Handler"]

    error_third = ["Interruption", "Destabilisation", "Destruction",
                    "Desynchronisation", "Failure", "Dereferencing", "Overflow", "Underflow",
                    "NMI", "Interrupt", "Corruption", "Anomoly", "Seizure", "Override",
                    "Reclock", "Rejection", "Invalidation", "Halt", "Exhaustion", "Infection",
                    "Incompatibility", "Timeout", "Expiry", "Unavailability", "Bug",
                    "Condition", "Crash", "Dump", "Crashdump", "Stackdump", "Problem",
                    "Lockout"]

    error_fourth = ["Error", "Problem", "Warning", "Signal", "Flag"]


    @commands.command(name='mba')
    async def mba_generator(self, ctx):
        """Actualize Visionary Phrases"""
        verb = random.choice(self.mba_verbs)
        adjective = random.choice(self.mba_adjectives)
        noun = random.choice(self.mba_nouns)
        await ctx.send(f"{verb} {adjective} {noun}")


    mba_verbs = ["gamify", "aggregate", "architect", "benchmark", "brand", "cultivate", "deliver", "deploy", "disintermediate", "drive",
    "e-enable", "embrace", "empower", "enable", "engage", "engineer", "enhance", "envisioneer", "evolve", "expedite",
    "exploit", "extend", "facilitate", "generate", "grow", "harness", "implement", "incentivize", "incubate",
    "innovate", "integrate", "iterate", "leverage", "matrix", "maximize", "mesh", "monetize", "morph", "optimize",
    "orchestrate", "productize", "recontextualize", "redefine", "reintermediate", "reinvent", "repurpose",
    "revolutionize", "scale", "seize", "strategize", "streamline", "syndicate", "synergize", "synthesize",
    "target", "transform", "transition", "unleash", "utilize", "visualize", "whiteboard"]

    mba_adjectives = ["24/365", "24/7", "B2B", "B2C", "back-end", "best-of-breed", "bleeding-edge", "bricks-and-clicks",
    "clicks-and-mortar", "collaborative", "compelling", "cross-platform", "cross-media", "customized", "cutting-edge",
    "distributed", "dot-com", "dynamic", "e-business", "efficient", "end-to-end", "enterprise", "extensible", "frictionless",
    "front-end", "global", "granular", "holistic", "impactful", "innovative", "integrated", "interactive", "intuitive", "killer",
    "leading-edge", "magnetic", "mission-critical", "next-generation", "one-to-one", "open-source", "out-of-the-box",
    "plug-and-play", "proactive", "real-time", "revolutionary", "rich", "robust", "scalable", "seamless", "sexy", "sticky",
    "strategic", "synergistic", "transparent", "turn-key", "ubiquitous", "user-centric", "value-added", "vertical", "viral",
    "virtual", "visionary", "web-enabled", "wireless", "world-class", "software-as-a-service"]

    mba_nouns = ["action-items", "applications", "architectures", "bandwidth", "channels", "communities", "content", "convergence",
    "deliverables", "e-business", "e-commerce", "e-markets", "e-services", "e-tailers", "experiences", "eyeballs",
    "functionalities", "infomediaries", "infrastructures", "initiatives", "interfaces", "markets", "methodologies",
    "metrics", "mindshare", "models", "networks", "niches", "paradigms", "partnerships", "platforms", "portals", "relationships",
    "ROI", "synergies", "web-readiness", "schemas", "solutions", "supply-chains", "systems", "technologies", "users", "vortals",
    "web services"]


    @commands.command(name="developers")
    async def development_generator(self, ctx):
        """Design dynamic development strategies"""
        verb = random.choice(self.dev_verbs)
        adjective = random.choice(self.dev_modifiers)
        noun = random.choice(self.dev_nouns)
        await ctx.send(f"{verb} {adjective} {noun}")

    dev_verbs = ["Design", "Maintain", "Test", "Produce", "Implement", "Research", "Conceptualize", "Analyze", "Initiate", "Abstract",
    "Program", "Develop", "Review", "Verify", "Replicate", "Evaluate", "Integrate", "Sprint", "Terminate", "Deploy", "Model"]
    dev_modifiers = ["Sequential", "Downwards", "Structural", "Modified", "Extreme", "Up Front", "Waterfall", "Agile", "Critical", "Flawed",
    "Top-Down", "Discrete", "Evolutionary", "Initial", "Scrum", "Horizontal", "Usability", "Throwaway", "Rapid", "Incremental", "Extreme", "Reduced", "Insufficient",
    "Dynamic", "Business", "Operating", "Rapid", "Object-Oriented", "Iterative", "Unified", "V-Model", "Linear", "Unit", "Spiral", "Daily", "Retrospective", "Epic", "Rockstar"]
    dev_nouns = ["Prototype", "Software", "Critical View", "Requirements Specification", "Models", "Architecture", "Meetings", "Products", "Objectives", "Logic",
    "Applications", "Environments", "Tasks", "Deployments", "Processes", "Abstractions", "Data Structures", "NoSQL", "Web 2.0", "XML", "XSL", "Memcache", "Cloud Comuting", "Clusters",
    "Version Control", "Code", "Feedback Loops", "Masters", "Stakeholders", "Managers", "Storytimes", "User Stories", "Programmers", 'Maintenence', 'Testing', 'Production',
    "Backlog Grooming"]
    
    @commands.command()
    async def wfl(self, ctx):
        """What's for lunch? You probably don't want it"""
        descr = random.choice(self.wfl_descriptives)
        
        dupemain = random.randint(0,2)
        if not dupemain:
            main = "{} and {}".format(random.choice(self.wfl_foods), random.choice(self.wfl_foods))
        else:
            main = random.choice(self.wfl_foods)
        
        sw = random.choice(self.wfl_withs)
        
        dupeseconds = random.randint(0,2)
        if not dupeseconds:
            second =  "{} and {}".format(random.choice(self.wfl_foods), random.choice(self.wfl_foods))
        else:
            second = random.choice(self.wfl_foods)
            
        serve = random.choice(self.wfl_servings)
        
        await ctx.send("{} {} {} {} {}".format(descr, main, sw, second, serve))

    wfl_descriptives = ["Stewed", "Broiled", "Sauteed", "Steamed", "Baked", "Toasted", "Grilled", "Peeled", 
    "Barbecued", "Flame-broiled", "Aged", "Fermented", "Spiced", "Spicy", "Hot", "Chilled", "Salted", "Stuffed", 
    "Sweet and Sour", "Creamy", "Dried", "Roasted", "Dry-roasted", "Pan-fried", "Deep-fried", "Savory", "Sweet", 
    "Yellowed", "Greenish", "Beige", "Orange", "Reddish", "Brown", "Colorful", "Delicious", "Sumptuous", "Decadent", 
    "Fragrant", "Tepid", "Steaming", "Sizzling", "Chipped"]
    
    wfl_foods = ["Yam", "Carrot", "Rhubarb", "Spinach", "Bell Pepper", "Mushroom", "Kale", "Chard", "Garlic", "Squash", 
    "Pumpkin", "Rice", "Oatmeal", "Walnut", "Peanut", "Almond", "Hazelnut", "Pine Nut", "Lemon", "Lime", "Grape", 
    "Tangerine", "Watermelon", "Tamarind", "Pineapple", "Apple", "Banana", "Grapefruit", "Tortilla", "Meat", "Chicken",
    "Pork", "Lamb", "Veal", "Sausage", "Frankfurter", "Hot Dog", "Polish Sausage", "Kielbasa", "Duck", "Mock-Duck", 
    "Tofu", "Head Cheese", "Liver", "Cod", "Ham", "Bacon", "Turkey", "Goat", "Pulled Pork", "Pastrami", "Roast Beef", 
    "Mystery Meat", "Lunch Meat", "Meat", "Salmon", "Trout", "Tuna", "Swordfish", "Sea Urchin", "Oyster", "Clam", 
    "Mussel", "Scallop", "Shellfish", "Abalone", "Seaweed", "Mustard", "Ketchup", "Cheese", "Cardamom", "Coriander", 
    "Turmeric", "Rutabaga", "Muskrat", "Beaver", "Bass", "Spam", "Cheese", "Cheddar", "Pulled Pork", "Cole Slaw",
    "Cilantro Avocado", "Plantain"]
    
    wfl_withs = ["with", "with", "with a side of", "tossed with", "topped with", "served with", "on a bed of"]

    wfl_servings = ["Slices", "Tea", "Chunks", "Sticks", "Powder", "Noodles", "Pie", "Puree", "Paste", "Oil", "Sauce", 
    "Stew", "Soup", "Stroganoff", "Tarts", "Balls", "Bread", "Flatbread", "Fritters", "Souffle", "Omelette", "Sushi",
    "Roll", "Burger", "Sandwich", "Pudding", "Shish-Kebab", "Pizza", "Pasta", "Pilaf", "Scramble", "Paste", "Pie",
    "Cookies", "Scones", "Cake", "Brownies", "Pastry", "Muffins", "Smoothie", "Milkshake", "Salad", "Chutney", "Jam", 
    "Fondue", "Jerky", "Juice", "Drippings", "Gravy", "Gravy", "Chips", "Cream"]



def setup(bot):
    bot.add_cog(Randomizers(bot))

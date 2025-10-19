import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

config_file = "ticket_config.json"  # defaultowo ticket_config w glownym folderze

def load_config():
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

config = load_config()

class SetupModal(discord.ui.Modal, title="Ticket System Setup"):
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        placeholder="Support Tickets",
        default="Support Tickets",
        max_length=256
    )
    
    embed_description = discord.ui.TextInput(
        label="Embed Description",
        placeholder="Click the button below to create a ticket",
        style=discord.TextStyle.paragraph,
        default="Click the button below to create a support ticket. Our staff will assist you shortly.",
        max_length=4000
    )
    
    embed_color = discord.ui.TextInput(
        label="Embed Color (Hex)",
        placeholder="0x5865F2",
        default="0x5865F2",
        max_length=10
    )
    
    button_label = discord.ui.TextInput(
        label="Button Label",
        placeholder="Create Ticket",
        default="Create Ticket",
        max_length=80
    )
    
    category_name = discord.ui.TextInput(
        label="Ticket Category Name",
        placeholder="Tickets",
        default="Tickets",
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        guild_id = str(interaction.guild_id)
        
        category = await interaction.guild.create_category(self.category_name.value)
        
        if guild_id not in config:
            config[guild_id] = {}
        
        config[guild_id]["embed_title"] = self.embed_title.value
        config[guild_id]["embed_description"] = self.embed_description.value
        config[guild_id]["embed_color"] = self.embed_color.value
        config[guild_id]["button_label"] = self.button_label.value
        config[guild_id]["category_id"] = category.id
        config[guild_id]["staff_roles"] = []
        
        save_config(config)
        
        view = RoleSelectView(guild_id, interaction.channel)
        await interaction.followup.send("Category created! Now select the staff roles that can manage tickets:", view=view, ephemeral=True)

class RoleSelectView(discord.ui.View):
    def __init__(self, guild_id, channel):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.channel = channel
    
    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select staff roles",
        min_values=1,
        max_values=10
    )
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [role.id for role in select.values]
        config[self.guild_id]["staff_roles"] = role_ids
        save_config(config)
        
        await interaction.response.send_message(f"Staff roles saved! Creating ticket panel...", ephemeral=True)
        
        try:
            color = int(config[self.guild_id]["embed_color"], 16)
        except:
            color = 0x5865F2
        
        embed = discord.Embed(
            title=config[self.guild_id]["embed_title"],
            description=config[self.guild_id]["embed_description"],
            color=color
        )
        embed.set_footer(text=f"{interaction.guild.name} Support System")
        
        view = TicketButton(self.guild_id)
        await self.channel.send(embed=embed, view=view)
        
        self.stop()

class TicketButton(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        
        button_label = config.get(guild_id, {}).get("button_label", "Create Ticket")
        self.children[0].label = button_label
    
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket_btn", emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        existing_ticket = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
        if existing_ticket:
            await interaction.response.send_message("You already have an open ticket!", ephemeral=True)
            return
        
        guild_config = config.get(str(guild.id), {})
        category_id = guild_config.get("category_id")
        staff_role_ids = guild_config.get("staff_roles", [])
        
        category = bot.get_channel(category_id)
        if not category:
            await interaction.response.send_message("Ticket system not configured properly.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for role_id in staff_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        ticket_channel = await category.create_text_channel(
            name=f"ticket-{user.name}",
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title=f"Ticket from {user.name}",
            description=f"{user.mention} has created a ticket. Staff will be with you shortly.",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        
        close_view = CloseTicketView()
        await ticket_channel.send(f"{user.mention}", embed=embed, view=close_view)
        
        await interaction.followup.send(f"Ticket created! {ticket_channel.mention}", ephemeral=True)

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_config = config.get(str(interaction.guild_id), {})
        staff_role_ids = guild_config.get("staff_roles", [])
        
        user_role_ids = [role.id for role in interaction.user.roles]
        is_staff = any(role_id in staff_role_ids for role_id in user_role_ids)
        
        if not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only staff can close tickets!", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing ticket in 5 seconds...")
        
        for i in range(5, 0, -1):
            await interaction.channel.send(f"Deleting in {i}...")
            await asyncio.sleep(1)
        
        await interaction.channel.delete()

@bot.event
async def on_ready():
    print(f'{bot.user} is online!')
    
    bot.add_view(TicketButton("persistent"))
    bot.add_view(CloseTicketView())
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="setup", description="Setup the ticket system")
@app_commands.default_permissions(administrator=True)
async def setup(interaction: discord.Interaction):
    modal = SetupModal()
    await interaction.response.send_modal(modal)

bot.run("tokenbota") #bot token
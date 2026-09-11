import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import random
import string
import uuid

# Load environment variables from .env file
load_dotenv()

# Law Enforcement Role IDs
LAW_ENFORCEMENT_ROLES = [1469606955843850270]

# Role allowed to run /start_session, /over, /set_peacetime, and /release
# (Administrators can also run all of these - see is_session_manager)
SESSION_MANAGER_ROLE_ID = 1469610749256011914

# Role (in addition to Law Enforcement) allowed to run /earlyaccess
EARLY_ACCESS_ROLE_ID = 1546055063359852596

# Role allowed to run /supervise_start and /supervise_end, in addition to
# Administrators - see is_supervise_manager
STAFF_TRAINER_ROLE_ID = 1546050155646816286

# Role (in addition to Staff Trainer and Administrators) allowed to reveal a
# supervised session's code via the button on its notification - see
# has_supervise_code_access
STAFF_IN_TRAINING_ROLE_ID = 1543163870049476659

# The 3 roles allowed to run /earlyaccess (Administrators can also run it -
# see has_earlyaccess_access)
EARLY_ACCESS_COMMAND_ROLES = LAW_ENFORCEMENT_ROLES + [EARLY_ACCESS_ROLE_ID]

# /infract role ladder for regular members - index 0 is given on their 1st
# infraction, index 1 on their 2nd, etc. Reaching a 5th infraction (i.e. past
# the end of this list) grants no role - it's the kick/ban threshold instead.
INFRACTION_ROLES = [
    1546082959986004079,  # Infraction 1
    1546083021504126998,  # Infraction 2
    1546083037438152845,  # Infraction 3
    1546083029812908122,  # Infraction 4
]

# /infract role ladder used instead of INFRACTION_ROLES when the person being
# infracted is Staff (Admin, Session Manager, or Law Enforcement).
STAFF_STRIKE_ROLES = [
    1546083207076642947,  # Staff Strike 1
    1546083365378064385,  # Staff Strike 2
    1546083345463513149,  # Staff Strike 3
    1546083357199441930,  # Staff Strike 4
]

# HR role - the only role (besides Administrators) allowed to run
# /loa_approve and /loa_reject
HR_ROLE_ID = 1546124112340983848

# Role (besides Administrators) allowed to run /say
SAY_ROLE_ID = 1510876852112195694

# Roles allowed to submit /loa_request (Administrators can also run it - see
# is_loa_eligible). This is the full list of Staff roles eligible for LOA.
LOA_ELIGIBLE_ROLES = [
    1510876852112195694,
    1523180647722516660,
    1510651270816338070,
    1510651809633665244,
    1546124112340983848,  # HR
    1523222450479960104,
    1543174482229989438,
    1529036514950905987,
    1529036512036130967,
    1529036517476007987,
    1523222456968413325,
    1529036625462693898,
    1529036625990914108,
    1543177268971438101,
    1543177270628454523,
    1543177260377440276,
    1543177271584497737,
    1543177283261431818,
    1523188202385571892,
    1543187103435718746,
    1543164964590592020,
    1543164756431478864,
    1543164851868799017,
    1546050155646816286,
    1543164642593996800,
    1543164323806060574,
    1543164217010556969,
    1543164132088352792,
    1543164492165288008,
    1543163870049476659,
    1469610749256011914,
    1469606955843850270,
    1510652955353944074,
    1510653170198511728,
    1523177785609425026,
    1510875615446827048,
    1510875561877049384,
    1510875492763566160,
    1510876143639597136,
    1510876727893819553,
    1546050107953250314,
]

# Replace with the ID of a role that has 'View Channels' explicitly denied in your server
BLACKLISTED_ROLE_ID = 1546154617451057243 

def is_staff_member(member: discord.Member) -> bool:
    """Whether the given member is Staff for /infract purposes: an
    Administrator, the Session Manager role, or a Law Enforcement role.
    Staff get the Staff Strike role ladder instead of the regular Infraction one."""
    if member.guild_permissions.administrator:
        return True
    role_ids = {role.id for role in member.roles}
    return (
        SESSION_MANAGER_ROLE_ID in role_ids
        or any(rid in role_ids for rid in LAW_ENFORCEMENT_ROLES)
    )

# Setup bot with intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Vehicle data storage file
VEHICLES_FILE = "vehicles.json"
# Citations data storage file
CITATIONS_FILE = "citations.json"
# Infractions data storage file
INFRACTIONS_FILE = "infractions.json"
# Active session storage file - tracks each posted session notification so its
# Peacetime status can be edited later, keyed by the notification message ID.
ACTIVE_SESSIONS_FILE = "active_sessions.json"
# Supervised (private) session storage file - kept separate from
# ACTIVE_SESSIONS_FILE so /supervise_start sessions never show up in the
# public /over, /set_peacetime, /release, or /force_end pickers.
SUPERVISE_SESSIONS_FILE = "supervise_sessions.json"
# LOA (Leave of Absence) request storage file, keyed by request ID
LOA_REQUESTS_FILE = "loa_requests.json"
# Blacklist storage file - tracks users who have been blacklisted and are pending ban
BLACKLIST_FILE = "blacklist.json"

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        with open(BLACKLIST_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_blacklist(data):
    with open(BLACKLIST_FILE, 'w') as f:
        json.dump(data, f, indent=2)

async def execute_delayed_ban(guild: discord.Guild, user_id: int, delay_seconds: int):
    """Wait for the delay, then ban the user if they are still on the blacklist."""
    await asyncio.sleep(delay_seconds)
    
    blacklist = load_blacklist()
    user_id_str = str(user_id)
    
    if user_id_str in blacklist:
        try:
            member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            await member.ban(reason="Failed to appeal/removed from blacklist in time.")
        except discord.NotFound:
            await guild.ban(discord.Object(id=user_id), reason="Failed to appeal/removed from blacklist in time.")
        except discord.Forbidden:
            print(f"Missing permissions to ban {user_id}")
            return
            
        blacklist.pop(user_id_str, None)
        save_blacklist(blacklist)

def load_vehicles():
    """Load vehicle data from JSON file"""
    if os.path.exists(VEHICLES_FILE):
        with open(VEHICLES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_vehicles(data):
    """Save vehicle data to JSON file"""
    with open(VEHICLES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_citations():
    """Load citation data from JSON file"""
    if os.path.exists(CITATIONS_FILE):
        with open(CITATIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_citations(data):
    """Save citation data to JSON file"""
    with open(CITATIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_infractions():
    """Load infraction data from JSON file"""
    if os.path.exists(INFRACTIONS_FILE):
        with open(INFRACTIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_infractions(data):
    """Save infraction data to JSON file"""
    with open(INFRACTIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_active_sessions():
    """Load active session data from JSON file, keyed by notification message ID"""
    if os.path.exists(ACTIVE_SESSIONS_FILE):
        with open(ACTIVE_SESSIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_active_sessions(data):
    """Save active session data to JSON file"""
    with open(ACTIVE_SESSIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_supervise_sessions():
    """Load supervised session data from JSON file"""
    if os.path.exists(SUPERVISE_SESSIONS_FILE):
        with open(SUPERVISE_SESSIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_supervise_sessions(data):
    """Save supervised session data to JSON file"""
    with open(SUPERVISE_SESSIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_loa_requests():
    """Load LOA request data from JSON file"""
    if os.path.exists(LOA_REQUESTS_FILE):
        with open(LOA_REQUESTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_loa_requests(data):
    """Save LOA request data to JSON file"""
    with open(LOA_REQUESTS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def generate_loa_id():
    """Generate a unique LOA request ID"""
    return uuid.uuid4().hex[:8]

def generate_citation_id():
    """Generate a unique citation ID (3 random characters)"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))

def generate_infraction_id():
    """Generate a unique infraction ID (3 random characters)"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))

def is_law_enforcement(interaction: discord.Interaction) -> bool:
    """Check if user has law enforcement role"""
    return any(role.id in LAW_ENFORCEMENT_ROLES for role in interaction.user.roles)

def is_session_manager(interaction: discord.Interaction) -> bool:
    """Check if user can manage sessions/Peacetime/release: the session manager
    role, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id == SESSION_MANAGER_ROLE_ID for role in interaction.user.roles)
    )

def require_session_manager():
    """App command check that gates a command to the session manager role (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return is_session_manager(interaction)
    return app_commands.check(predicate)

def has_earlyaccess_access(interaction: discord.Interaction) -> bool:
    """Check if user can run /earlyaccess: Law Enforcement, the Early Access
    role, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id in EARLY_ACCESS_COMMAND_ROLES for role in interaction.user.roles)
    )

def require_earlyaccess_access():
    """App command check that gates a command to the /earlyaccess roles (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return has_earlyaccess_access(interaction)
    return app_commands.check(predicate)


def is_supervise_manager(interaction: discord.Interaction) -> bool:
    """Check if user can run /supervise_start and /supervise_end: the Staff
    Trainer role, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id == STAFF_TRAINER_ROLE_ID for role in interaction.user.roles)
    )

def require_supervise_manager():
    """App command check that gates a command to Staff Trainer (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return is_supervise_manager(interaction)
    return app_commands.check(predicate)

def has_supervise_code_access(interaction: discord.Interaction) -> bool:
    """Check if user can reveal a supervised session's code: Staff Trainer,
    Staff In Training, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(
            role.id in (STAFF_TRAINER_ROLE_ID, STAFF_IN_TRAINING_ROLE_ID)
            for role in interaction.user.roles
        )
    )



def is_loa_eligible(interaction: discord.Interaction) -> bool:
    """Check if user can run /loa_request: any of the Staff roles in
    LOA_ELIGIBLE_ROLES, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id in LOA_ELIGIBLE_ROLES for role in interaction.user.roles)
    )

def require_loa_eligible():
    """App command check that gates a command to the LOA-eligible roles (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return is_loa_eligible(interaction)
    return app_commands.check(predicate)

def is_hr(interaction: discord.Interaction) -> bool:
    """Check if user can run /loa_approve and /loa_reject: the HR role, or
    any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id == HR_ROLE_ID for role in interaction.user.roles)
    )

def require_hr():
    """App command check that gates a command to HR (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return is_hr(interaction)
    return app_commands.check(predicate)

def can_use_say(interaction: discord.Interaction) -> bool:
    """Check if user can run /say: the Say role, or any Administrator"""
    return (
        interaction.user.guild_permissions.administrator
        or any(role.id == SAY_ROLE_ID for role in interaction.user.roles)
    )

def require_say_access():
    """App command check that gates a command to the /say role (or Admin)"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return can_use_say(interaction)
    return app_commands.check(predicate)


def validate_vehicle_data(year, brand, model, trim, color, plate, state, owner, all_vehicles=None):
    """Validate vehicle registration data"""
    errors = []
    
    # Validate year
    try:
        year_int = int(year)
        if year_int < 1900 or year_int > datetime.now().year + 1:
            errors.append("Vehicle year must be between 1900 and current year + 1")
    except ValueError:
        errors.append("Vehicle year must be a number")
    
    # Validate plate (max 7 characters)
    if len(plate) > 7:
        errors.append("License plate must be 7 characters or less")
    if not plate or len(plate.strip()) == 0:
        errors.append("License plate cannot be empty")
    
    # Validate other fields aren't empty
    if not brand or len(brand.strip()) == 0:
        errors.append("Vehicle brand cannot be empty")
    if not model or len(model.strip()) == 0:
        errors.append("Vehicle model cannot be empty")
    if not trim or len(trim.strip()) == 0:
        errors.append("Vehicle trim cannot be empty")
    if not color or len(color.strip()) == 0:
        errors.append("Vehicle color cannot be empty")
    if not state or len(state.strip()) == 0:
        errors.append("Vehicle state cannot be empty")
    if not owner or len(owner.strip()) == 0:
        errors.append("Vehicle owner cannot be empty")
    
    # Check for duplicate plate + state combination
    if all_vehicles:
        for user_id, user_data in all_vehicles.items():
            for vehicle in user_data["vehicles"]:
                if vehicle["plate"].upper() == plate.upper() and vehicle["state"].upper() == state.upper():
                    errors.append(f"❌ Plate '{plate}' in {state} is already registered! Each plate must be unique per state.")
                    break
    
    return errors

# Initialize the command group
blacklist_group = app_commands.Group(name="blacklist", description="Manage the server blacklist")
bot.tree.add_command(blacklist_group)

@blacklist_group.command(name="add", description="Add a user to the blacklist and schedule them for a ban in 1-3 hours")
@require_loa_eligible()
async def blacklist_add(interaction: discord.Interaction, target: discord.Member, reason: str):
    if interaction.user.id != interaction.guild.owner_id:
        if interaction.user.top_role.position <= target.top_role.position:
            await interaction.response.send_message("❌ You cannot blacklist a member equal to or higher than you!", ephemeral=True)
            return

    blacklist = load_blacklist()
    user_id_str = str(target.id)

    if user_id_str in blacklist:
        await interaction.response.send_message("❌ This user is already on the blacklist.", ephemeral=True)
        return

    await interaction.response.defer()

    saved_role_ids = [role.id for role in target.roles if role.id != interaction.guild.id]
    blacklisted_role = interaction.guild.get_role(BLACKLISTED_ROLE_ID)

    try:
        if blacklisted_role:
            await target.edit(roles=[blacklisted_role], reason=f"Blacklisted by {interaction.user.name}")
        else:
            await interaction.followup.send("⚠️ `BLACKLISTED_ROLE_ID` is invalid. Please configure it. (Ban timer still started).")
    except discord.Forbidden:
        await interaction.followup.send("❌ I lack the 'Manage Roles' permission to modify this user.")
        return

    delay_seconds = random.randint(3600, 10800)
    ban_timestamp = datetime.now().timestamp() + delay_seconds

    blacklist[user_id_str] = {
        "username": target.name,
        "blacklisted_by": interaction.user.name,
        "reason": reason,
        "ban_timestamp": ban_timestamp,
        "guild_id": interaction.guild.id,
        "saved_roles": saved_role_ids
    }
    save_blacklist(blacklist)

    asyncio.create_task(execute_delayed_ban(interaction.guild, target.id, delay_seconds))

    hours = round(delay_seconds / 3600, 1)
    embed = discord.Embed(
        title="⛔ User Blacklisted",
        description=f"{target.mention} has been added to the blacklist and locked out of channels.\nThey will be **permanently banned in {hours} hours** unless removed.",
        color=discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text=f"Blacklisted by {interaction.user.name}")

    await interaction.followup.send(embed=embed)


@blacklist_group.command(name="remove", description="Remove a user from the blacklist and restore their roles")
@require_loa_eligible()
async def blacklist_remove(interaction: discord.Interaction, target: discord.Member):
    blacklist = load_blacklist()
    user_id_str = str(target.id)

    if user_id_str not in blacklist:
        await interaction.response.send_message("❌ This user is not on the blacklist.", ephemeral=True)
        return

    await interaction.response.defer()

    data = blacklist.pop(user_id_str)
    save_blacklist(blacklist)

    roles_to_restore = []
    for role_id in data.get("saved_roles", []):
        role = interaction.guild.get_role(role_id)
        if role:
            roles_to_restore.append(role)

    try:
        await target.edit(roles=roles_to_restore, reason=f"Removed from blacklist by {interaction.user.name}")
        await interaction.followup.send(f"✅ {target.mention} was removed from the blacklist. Roles restored.")
    except discord.Forbidden:
        await interaction.followup.send(f"✅ {target.mention} was removed from the blacklist, but I lacked permission to restore their roles.")

@bot.event
async def on_ready():
    """Bot startup event"""
    # Load the blacklist and schedule any pending bans
    blacklist = load_blacklist()
    current_time = datetime.now().timestamp()
    
    for user_id_str, data in list(blacklist.items()):
        ban_time = data.get("ban_timestamp")
        guild_id = data.get("guild_id")
        
        if ban_time and guild_id:
            guild = bot.get_guild(guild_id)
            if guild:
                remaining = ban_time - current_time
                if remaining <= 0:
                    asyncio.create_task(execute_delayed_ban(guild, int(user_id_str), 0))
                else:
                    asyncio.create_task(execute_delayed_ban(guild, int(user_id_str), remaining))
    print(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="register_vehicle", description="Register a vehicle for roleplay")
async def register_vehicle(
    interaction: discord.Interaction,
    year: str,
    brand: str,
    model: str,
    trim: str,
    color: str,
    plate: str,
    state: str,
    owner: str
):
    """Register a new vehicle"""
    await interaction.response.defer()
    
    # Load existing vehicles first
    vehicles = load_vehicles()
    
    # Validate input (pass all vehicles for duplicate checking)
    errors = validate_vehicle_data(year, brand, model, trim, color, plate, state, owner, vehicles)
    if errors:
        error_msg = "\n".join(f"{error}" for error in errors)
        await interaction.followup.send(f"**Validation Errors:**\n{error_msg}")
        return
    user_id = str(interaction.user.id)
    
    # Initialize user's vehicle list if needed
    if user_id not in vehicles:
        vehicles[user_id] = {"username": interaction.user.name, "vehicles": []}
    
    # Create vehicle entry
    vehicle = {
        "year": year,
        "brand": brand,
        "model": model,
        "trim": trim,
        "color": color,
        "plate": plate,
        "state": state,
        "owner": owner,
        "registered_at": datetime.now().isoformat()
    }
    
    vehicles[user_id]["vehicles"].append(vehicle)
    save_vehicles(vehicles)
    
    # Create confirmation embed
    embed = discord.Embed(
        title="✅ Vehicle Registered Successfully",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Year", value=year, inline=True)
    embed.add_field(name="Brand", value=brand, inline=True)
    embed.add_field(name="Model", value=model, inline=True)
    embed.add_field(name="Trim", value=trim, inline=True)
    embed.add_field(name="Color", value=color, inline=True)
    embed.add_field(name="License Plate", value=plate, inline=True)
    embed.add_field(name="State", value=state, inline=True)
    embed.add_field(name="Owner", value=owner, inline=False)
    embed.set_footer(text=f"Registered by {interaction.user.name}")
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="my_vehicles", description="View all your registered vehicles")
async def my_vehicles(interaction: discord.Interaction):
    """View user's vehicles"""
    await interaction.response.defer()
    
    vehicles = load_vehicles()
    user_id = str(interaction.user.id)
    
    if user_id not in vehicles or not vehicles[user_id]["vehicles"]:
        await interaction.followup.send("❌ You haven't registered any vehicles yet!")
        return
    
    # Create embed with all vehicles
    embed = discord.Embed(
        title=f"🚗 Registered Vehicles - {interaction.user.name}",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    for idx, vehicle in enumerate(vehicles[user_id]["vehicles"], 1):
        vehicle_info = (
            f"**Year:** {vehicle['year']}\n"
            f"**Brand:** {vehicle['brand']}\n"
            f"**Model:** {vehicle['model']}\n"
            f"**Trim:** {vehicle['trim']}\n"
            f"**Color:** {vehicle['color']}\n"
            f"**Plate:** {vehicle['plate']} ({vehicle['state']})\n"
            f"**Owner:** {vehicle['owner']}"
        )
        embed.add_field(name=f"Vehicle #{idx}", value=vehicle_info, inline=False)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="remove_vehicle", description="Remove a registered vehicle")
async def remove_vehicle(interaction: discord.Interaction, vehicle_number: int):
    """Remove a vehicle by index"""
    await interaction.response.defer()
    
    vehicles = load_vehicles()
    user_id = str(interaction.user.id)
    
    if user_id not in vehicles or not vehicles[user_id]["vehicles"]:
        await interaction.followup.send("❌ You haven't registered any vehicles!")
        return
    
    if vehicle_number < 1 or vehicle_number > len(vehicles[user_id]["vehicles"]):
        await interaction.followup.send(f"❌ Invalid vehicle number! You have {len(vehicles[user_id]['vehicles'])} vehicles.")
        return
    
    removed_vehicle = vehicles[user_id]["vehicles"].pop(vehicle_number - 1)
    save_vehicles(vehicles)
    
    embed = discord.Embed(
        title="✅ Vehicle Removed",
        color=discord.Color.red(),
        description=f"Removed: {removed_vehicle['year']} {removed_vehicle['brand']} {removed_vehicle['model']} ({removed_vehicle['plate']})"
    )
    
    await interaction.followup.send(embed=embed)

SESSION_CHANNELS = {
    "1510658237807198250": "Session 1",
    "1523170349452099664": "Session 2"
}

# Channel(s) where /supervise_start posts its notification. These should be
# channels whose Discord permissions are already locked down to Staff Trainer
# + Staff In Training (+ Admins) - the bot's access checks control who can
# click "Reveal Code", but real privacy also depends on who can see the
# channel(s) at all.
SUPERVISE_SESSION_CHANNEL_IDS = [1527529181364097224]  # add more IDs to this list as needed

# Channel that a supervised session's code gets fully released to once the
# person who started it presses "Reveal Session Code" and fills in the
# AORP/FRP Speed Limit form. This is the same "Session 1" channel used by
# /start_session - the resulting notification looks like a normal session
# post, except the code is shown right away (no early access step).
SUPERVISED_RELEASE_CHANNEL_ID = 1510658237807198250


class SessionDetailsModal(discord.ui.Modal, title="Start Roleplay Session"):
    """Step 2 of /start_session: session details, shown after Peacetime + channel are picked."""

    session_code = discord.ui.TextInput(
        label="Session Code",
        placeholder="e.g. Downtown Chase",
        max_length=100,
        required=True
    )
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Optional details about the session",
        max_length=500,
        required=False
    )
    aorp = discord.ui.TextInput(
        label="Area Of Roleplay (AORP)",
        placeholder="e.g. Downtown District",
        max_length=100,
        required=True
    )
    frp_speed_limit = discord.ui.TextInput(
        label="FRP Speed Limit",
        placeholder="Numbers only, e.g. 80",
        max_length=10,
        required=True
    )

    def __init__(self, peacetime: str, channel_id: int):
        super().__init__()
        self.peacetime = peacetime
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        # Validate FRP Speed Limit is numeric-only
        speed_value = self.frp_speed_limit.value.strip()
        if not speed_value.isdigit():
            await interaction.response.send_message(
                f"❌ FRP Speed Limit must be numbers only. You entered: `{speed_value}`. "
                f"Please run `/start_session` again.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = bot.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(self.channel_id)
            except discord.NotFound:
                channel = None
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have access to the selected channel.",
                    ephemeral=True
                )
                return

        if channel is None:
            await interaction.followup.send(
                "❌ Couldn't find the selected session channel. Check the channel ID and that the bot can see it.",
                ephemeral=True
            )
            return

        peacetime_colors = {
            "On": discord.Color.green(),
            "Off": discord.Color.red(),
            "Strict": discord.Color.orange()
        }

        embed = discord.Embed(
            title="🎬 Roleplay Session Started!",
            color=peacetime_colors.get(self.peacetime, discord.Color.gold()),
            timestamp=datetime.now()
        )
        if self.description.value:
            embed.add_field(name="Description", value=self.description.value, inline=False)
        embed.add_field(name="Peacetime", value=self.peacetime, inline=True)
        embed.add_field(name="Area Of Roleplay (AORP)", value=self.aorp.value, inline=True)
        embed.add_field(name="FRP Speed Limit", value=f"{speed_value} mph", inline=True)
        embed.add_field(name="Session Code", value="🔒 Pending release", inline=False)
        embed.add_field(name="Started By", value=interaction.user.mention, inline=False)

        try:
            sent_message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to post in {channel.mention}.",
                ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Failed to post the session notification: {e}",
                ephemeral=True
            )
            return

        # Track this session so /set_peacetime, /over, and /release can find and
        # edit its notification message later - keyed by message ID so multiple
        # concurrent sessions (e.g. one in each session channel) don't conflict.
        sessions = load_active_sessions()
        sessions[str(sent_message.id)] = {
            "channel_id": channel.id,
            "session_code": self.session_code.value,
            "peacetime": self.peacetime,
            "aorp": self.aorp.value,
            "frp_speed_limit": speed_value,
            "started_by": interaction.user.name,
            "started_at": datetime.now().isoformat(),
            "code_released": False
        }
        save_active_sessions(sessions)

        await interaction.followup.send(
            f"✅ Session notification posted in {channel.mention}! The session code is hidden until "
            f"someone with access runs `/release`.",
            ephemeral=True
        )


class PeacetimeSelect(discord.ui.Select):
    """Peacetime picker, part of step 1 of /start_session."""

    def __init__(self):
        options = [
            discord.SelectOption(label="On", value="On", description="Peacetime active - no conflict RP actions"),
            discord.SelectOption(label="Off", value="Off", description="Peacetime disabled"),
            discord.SelectOption(label="Strict", value="Strict", description="Strict peacetime enforcement")
        ]
        super().__init__(
            placeholder="Select Peacetime setting...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.peacetime = self.values[0]
        for option in self.options:
            option.default = (option.value == self.values[0])
        await interaction.response.edit_message(view=self.view)


class SessionChannelSelect(discord.ui.Select):
    """Channel picker, part of step 1 of /start_session."""

    def __init__(self):
        options = [
            discord.SelectOption(label=name, value=channel_id)
            for channel_id, name in SESSION_CHANNELS.items()
        ]
        super().__init__(
            placeholder="Select channel to post in...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.channel_id = int(self.values[0])
        for option in self.options:
            option.default = (option.value == self.values[0])
        await interaction.response.edit_message(view=self.view)


class ContinueButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Continue", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        view: SessionSetupView = self.view
        if not view.peacetime or not view.channel_id:
            await interaction.response.send_message(
                "❌ Please select both a Peacetime setting and a channel before continuing.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(
            SessionDetailsModal(peacetime=view.peacetime, channel_id=view.channel_id)
        )


class SessionSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.peacetime = None
        self.channel_id = None
        self.add_item(PeacetimeSelect())
        self.add_item(SessionChannelSelect())
        self.add_item(ContinueButton())


@bot.tree.command(name="start_session", description="Start a roleplay session and post a notification")
@require_session_manager()
async def start_session(interaction: discord.Interaction):
    """Start a roleplay session - opens a form to configure session settings"""
    await interaction.response.send_message(
        "**Step 1/2:** Select the Peacetime setting and the channel to post in, then click Continue.",
        view=SessionSetupView(),
        ephemeral=True
    )


class PeacetimeUpdateSelect(discord.ui.Select):
    """Step 2 of /set_peacetime: choose the new Peacetime status for the picked session."""

    def __init__(self, message_id: str, session_data: dict):
        self.message_id = message_id
        self.session_data = session_data
        options = [
            discord.SelectOption(label="On", value="On", description="Peacetime active - no conflict RP actions"),
            discord.SelectOption(label="Off", value="Off", description="Peacetime disabled"),
            discord.SelectOption(label="Strict", value="Strict", description="Strict peacetime enforcement")
        ]
        super().__init__(
            placeholder="Select new Peacetime status...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Re-check the required role at the point of use, since a component
        # attached to a message could in theory be interacted with by anyone
        # who can see it, not just whoever ran the original command.
        if not is_session_manager(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to change the Peacetime status.",
                ephemeral=True
            )
            return

        new_status = self.values[0]
        sessions = load_active_sessions()
        session_data = sessions.get(self.message_id)
        if not session_data:
            await interaction.response.edit_message(
                content="❌ That session is no longer active.",
                view=None
            )
            return

        channel = bot.get_channel(session_data["channel_id"])
        if channel is None:
            try:
                channel = await bot.fetch_channel(session_data["channel_id"])
            except (discord.NotFound, discord.Forbidden):
                channel = None

        if channel is None:
            await interaction.response.edit_message(
                content="❌ Couldn't find the channel for that session anymore.",
                view=None
            )
            return

        try:
            message = await channel.fetch_message(int(self.message_id))
        except (discord.NotFound, discord.Forbidden):
            await interaction.response.edit_message(
                content="❌ The original session notification message no longer exists.",
                view=None
            )
            return

        status_colors = {
            "On": discord.Color.green(),
            "Off": discord.Color.red(),
            "Strict": discord.Color.orange()
        }

        # Edit the Peacetime field (and color) on the original notification
        # embed in place, so the posted message always reflects the live status.
        embed = message.embeds[0]
        for idx, field in enumerate(embed.fields):
            if field.name == "Peacetime":
                embed.set_field_at(idx, name="Peacetime", value=new_status, inline=field.inline)
                break
        embed.colour = status_colors.get(new_status, discord.Color.gold())

        await message.edit(embed=embed)

        session_data["peacetime"] = new_status
        session_data["peacetime_updated_by"] = interaction.user.name
        session_data["peacetime_updated_at"] = datetime.now().isoformat()
        sessions[self.message_id] = session_data
        save_active_sessions(sessions)

        await interaction.response.edit_message(
            content=(
                f"✅ Peacetime for session code **{session_data['session_code']}** updated to "
                f"**{new_status}** and the notification message has been updated."
            ),
            view=None
        )


class PeacetimeUpdateView(discord.ui.View):
    def __init__(self, message_id: str, session_data: dict):
        super().__init__(timeout=120)
        self.add_item(PeacetimeUpdateSelect(message_id=message_id, session_data=session_data))


def get_ongoing_sessions() -> dict:
    """Return active sessions that haven't been marked as ended yet"""
    sessions = load_active_sessions()
    return {mid: data for mid, data in sessions.items() if not data.get("ended")}


def get_releasable_sessions() -> dict:
    """Return ongoing sessions whose session code hasn't been released yet"""
    return {
        mid: data for mid, data in get_ongoing_sessions().items()
        if not data.get("code_released")
    }


class SessionPickerSelect(discord.ui.Select):
    """Step 1 of /set_peacetime: pick which active session's notification to update."""

    def __init__(self, sessions: dict):
        options = []
        for message_id, data in sessions.items():
            channel_name = SESSION_CHANNELS.get(str(data.get("channel_id")), str(data.get("channel_id")))
            options.append(discord.SelectOption(
                label=str(data.get("session_code", "Unknown"))[:100],
                description=f"{channel_name} - currently {data.get('peacetime', '?')}"[:100],
                value=message_id
            ))
        super().__init__(
            placeholder="Select which session to update...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        message_id = self.values[0]
        sessions = load_active_sessions()
        session_data = sessions.get(message_id)
        if not session_data or session_data.get("ended"):
            await interaction.response.edit_message(
                content="❌ That session is no longer active.",
                view=None
            )
            return

        await interaction.response.edit_message(
            content=(
                f"**Step 2/2:** Updating Peacetime for session code **{session_data['session_code']}** "
                f"(currently **{session_data['peacetime']}**). Select the new status:"
            ),
            view=PeacetimeUpdateView(message_id=message_id, session_data=session_data)
        )


class SessionPickerView(discord.ui.View):
    def __init__(self, sessions: dict):
        super().__init__(timeout=120)
        self.add_item(SessionPickerSelect(sessions))


@bot.tree.command(name="set_peacetime", description="Change the Peacetime status of an active session")
@require_session_manager()
async def set_peacetime(interaction: discord.Interaction):
    """Pick an active session, then change its Peacetime status - edits the posted notification message"""
    sessions = get_ongoing_sessions()

    if not sessions:
        await interaction.response.send_message(
            "❌ There are no active sessions to update. Start one with `/start_session` first.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "**Step 1/2:** Select which active session's Peacetime status you want to change:",
        view=SessionPickerView(sessions),
        ephemeral=True
    )


async def delete_session_message_after_delay(channel_id: int, message_id: str, delay_seconds: int = 300):
    """Wait, then delete the ended session's notification message and clean up its record"""
    await asyncio.sleep(delay_seconds)
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(int(message_id))
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
        print(f"Failed to delete session message {message_id}: {e}")
    finally:
        sessions = load_active_sessions()
        if sessions.pop(str(message_id), None) is not None:
            save_active_sessions(sessions)


async def purge_session_channel(channel, keep_message_id: int):
    """Delete every other message in the session channel, leaving only the
    'Session Ended' notification (which has its own delayed-deletion timer).
    Requires the bot to have Manage Messages in the channel."""
    try:
        await channel.purge(limit=None, check=lambda m: m.id != keep_message_id)
    except discord.Forbidden:
        print(f"Missing permission to purge messages in channel {channel.id} (need Manage Messages).")
    except discord.HTTPException as e:
        print(f"Failed to purge channel {channel.id}: {e}")


async def end_active_session(message_id: str, ended_by_name: str):
    """Core logic to mark one active session as ended: edits its notification
    embed in place, updates the stored record, and schedules the channel purge
    plus the notification's own delayed deletion. Shared by /over (one session
    at a time, via picker) and /force_end (all sessions, no picker).
    Returns (success: bool, description: str) - description is a short,
    human-readable line suitable for showing on its own or in a batch summary."""
    sessions = load_active_sessions()
    session_data = sessions.get(message_id)
    if not session_data or session_data.get("ended"):
        return False, "That session is no longer active."

    channel = bot.get_channel(session_data["channel_id"])
    if channel is None:
        try:
            channel = await bot.fetch_channel(session_data["channel_id"])
        except (discord.NotFound, discord.Forbidden):
            channel = None

    if channel is None:
        return False, f"Couldn't find the channel for session **{session_data.get('session_code', 'Unknown')}**."

    try:
        message = await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden):
        # Message is already gone - just clean up the stored record.
        sessions.pop(message_id, None)
        save_active_sessions(sessions)
        return False, f"The notification message for session **{session_data.get('session_code', 'Unknown')}** no longer exists."

    # Mark the notification as ended in place
    embed = message.embeds[0]
    embed.title = "🔴 Session Ended"
    embed.colour = discord.Color.dark_grey()

    status_set = False
    for idx, field in enumerate(embed.fields):
        if field.name == "Status":
            embed.set_field_at(idx, name="Status", value="Ended", inline=field.inline)
            status_set = True
            break
    if not status_set:
        embed.add_field(name="Status", value="Ended", inline=True)

    await message.edit(embed=embed)

    session_data["ended"] = True
    session_data["ended_by"] = ended_by_name
    session_data["ended_at"] = datetime.now().isoformat()
    sessions[message_id] = session_data
    save_active_sessions(sessions)

    # Schedule the channel purge (keeping only this notification) and the
    # notification's own delayed deletion, without blocking the caller
    asyncio.create_task(purge_session_channel(channel, keep_message_id=message.id))
    asyncio.create_task(delete_session_message_after_delay(channel.id, message_id))

    return True, f"Session code **{session_data['session_code']}** marked as ended in {channel.mention}."


class EndSessionSelect(discord.ui.Select):
    """Step 1 (and only step) of /over: pick which session to end."""

    def __init__(self, sessions: dict):
        options = []
        for message_id, data in sessions.items():
            channel_name = SESSION_CHANNELS.get(str(data.get("channel_id")), str(data.get("channel_id")))
            options.append(discord.SelectOption(
                label=str(data.get("session_code", "Unknown"))[:100],
                description=f"{channel_name} - Peacetime: {data.get('peacetime', '?')}"[:100],
                value=message_id
            ))
        super().__init__(
            placeholder="Select which session to end...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        # Re-check the required role at the point of use, same reasoning as
        # the other session-management components.
        if not is_session_manager(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to end a session.",
                ephemeral=True
            )
            return

        message_id = self.values[0]
        success, description = await end_active_session(message_id, ended_by_name=interaction.user.name)

        if not success:
            await interaction.response.edit_message(content=f"❌ {description}", view=None)
            return

        await interaction.response.edit_message(
            content=(
                f"✅ {description} The channel is being cleared, and the notification "
                f"message will be deleted automatically in 5 minutes."
            ),
            view=None
        )


class EndSessionView(discord.ui.View):
    def __init__(self, sessions: dict):
        super().__init__(timeout=120)
        self.add_item(EndSessionSelect(sessions))


@bot.tree.command(name="over", description="End an active roleplay session")
@require_session_manager()
async def over(interaction: discord.Interaction):
    """Pick an active session to end - marks its notification as ended, then deletes it after 5 minutes"""
    sessions = get_ongoing_sessions()

    if not sessions:
        await interaction.response.send_message(
            "❌ There are no active sessions to end.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select which session you'd like to end:",
        view=EndSessionView(sessions),
        ephemeral=True
    )


@bot.tree.command(name="force_end", description="Immediately end ALL active sessions, no confirmation (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def force_end(interaction: discord.Interaction):
    """End every active session at once - no picker, no confirmation step"""
    await interaction.response.defer(ephemeral=True)

    sessions = get_ongoing_sessions()
    if not sessions:
        await interaction.followup.send("❌ There are no active sessions to end.", ephemeral=True)
        return

    lines = []
    for message_id in list(sessions.keys()):
        success, description = await end_active_session(message_id, ended_by_name=interaction.user.name)
        lines.append(f"{'✅' if success else '❌'} {description}")

    summary = "\n".join(lines)
    await interaction.followup.send(
        f"🛑 Force-ended {len(sessions)} session(s):\n{summary}\n\n"
        f"Affected channels are being cleared, and each notification message "
        f"will be deleted automatically in 5 minutes.",
        ephemeral=True
    )


class RevealCodeButton(discord.ui.Button):
    """An ephemeral button, only visible to the invoker, that reveals the
    session code by editing the public notification message. Shared by
    /release and /earlyaccess, each supplying its own access_check so the
    button re-checks whichever permission its originating command requires."""

    def __init__(self, message_id: str, session_data: dict, access_check, unauthorized_message: str,
                 label: str = "🔓 Reveal Session Code",
                 load_sessions_fn=load_active_sessions, save_sessions_fn=save_active_sessions):
        super().__init__(label=label, style=discord.ButtonStyle.danger)
        self.message_id = message_id
        self.session_data = session_data
        self.access_check = access_check
        self.unauthorized_message = unauthorized_message
        # Defaults to the public active_sessions.json store; /supervise_start
        # passes load_supervise_sessions/save_supervise_sessions instead so
        # the same button works against its separate, private store.
        self.load_sessions_fn = load_sessions_fn
        self.save_sessions_fn = save_sessions_fn

    async def callback(self, interaction: discord.Interaction):
        # Re-check access at the point of use, same reasoning as the other
        # session-management components.
        if not self.access_check(interaction):
            await interaction.response.send_message(
                self.unauthorized_message,
                ephemeral=True
            )
            return

        sessions = self.load_sessions_fn()
        session_data = sessions.get(self.message_id)
        if not session_data or session_data.get("ended"):
            await interaction.response.edit_message(
                content="❌ That session is no longer active.",
                view=None
            )
            return

        if session_data.get("code_released"):
            await interaction.response.edit_message(
                content=f"The session code was already released: **{session_data['session_code']}**",
                view=None
            )
            return

        channel = bot.get_channel(session_data["channel_id"])
        if channel is None:
            try:
                channel = await bot.fetch_channel(session_data["channel_id"])
            except (discord.NotFound, discord.Forbidden):
                channel = None

        if channel is None:
            await interaction.response.edit_message(
                content="❌ Couldn't find the channel for that session anymore.",
                view=None
            )
            return

        try:
            message = await channel.fetch_message(int(self.message_id))
        except (discord.NotFound, discord.Forbidden):
            await interaction.response.edit_message(
                content="❌ The original session notification message no longer exists.",
                view=None
            )
            return

        # Reveal the session code on the public notification embed
        embed = message.embeds[0]
        for idx, field in enumerate(embed.fields):
            if field.name == "Session Code":
                embed.set_field_at(idx, name="Session Code", value=session_data["session_code"], inline=field.inline)
                break

        await message.edit(embed=embed)

        session_data["code_released"] = True
        session_data["code_released_by"] = interaction.user.name
        session_data["code_released_at"] = datetime.now().isoformat()
        sessions[self.message_id] = session_data
        self.save_sessions_fn(sessions)

        await interaction.response.edit_message(
            content=(
                f"✅ Session code revealed in {channel.mention}: **{session_data['session_code']}**"
            ),
            view=None
        )


class RevealCodeView(discord.ui.View):
    def __init__(self, message_id: str, session_data: dict, access_check, unauthorized_message: str,
                 label: str = "🔓 Reveal Session Code", timeout=120,
                 load_sessions_fn=load_active_sessions, save_sessions_fn=save_active_sessions):
        super().__init__(timeout=timeout)
        self.add_item(RevealCodeButton(
            message_id=message_id,
            session_data=session_data,
            access_check=access_check,
            unauthorized_message=unauthorized_message,
            label=label,
            load_sessions_fn=load_sessions_fn,
            save_sessions_fn=save_sessions_fn
        ))


class ReleaseSessionSelect(discord.ui.Select):
    """Step 1 of /release: pick which session to release the code for. Labels
    deliberately avoid the session code itself - it isn't shown until the
    reveal button on the next step is pressed."""

    def __init__(self, sessions: dict):
        options = []
        for message_id, data in sessions.items():
            channel_name = SESSION_CHANNELS.get(str(data.get("channel_id")), str(data.get("channel_id")))
            options.append(discord.SelectOption(
                label=f"{data.get('aorp', 'Unknown area')} ({channel_name})"[:100],
                description=f"Peacetime: {data.get('peacetime', '?')} - Started by {data.get('started_by', '?')}"[:100],
                value=message_id
            ))
        super().__init__(
            placeholder="Select which session to release the code for...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        message_id = self.values[0]
        sessions = load_active_sessions()
        session_data = sessions.get(message_id)
        if not session_data or session_data.get("ended") or session_data.get("code_released"):
            await interaction.response.edit_message(
                content="❌ That session is no longer available for release.",
                view=None
            )
            return

        await interaction.response.edit_message(
            content=(
                f"**Step 2/2:** Session in **{session_data.get('aorp', 'Unknown area')}** selected. "
                f"Press below to reveal its session code - only you can see this button."
            ),
            view=RevealCodeView(
                message_id=message_id,
                session_data=session_data,
                access_check=is_session_manager,
                unauthorized_message="❌ You don't have the required role to release session codes."
            )
        )


class ReleaseSessionView(discord.ui.View):
    def __init__(self, sessions: dict):
        super().__init__(timeout=120)
        self.add_item(ReleaseSessionSelect(sessions))


@bot.tree.command(name="release", description="Reveal a session's code on its notification (Session Manager / Admin only)")
@require_session_manager()
async def release(interaction: discord.Interaction):
    """Pick an active session, then reveal its session code on the public notification"""
    sessions = get_releasable_sessions()

    if not sessions:
        await interaction.response.send_message(
            "❌ There are no sessions with an unreleased code right now.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "**Step 1/2:** Select which session's code you want to release:",
        view=ReleaseSessionView(sessions),
        ephemeral=True
    )


class SuperviseDetailsModal(discord.ui.Modal, title="Start Supervised Session"):
    """Modal for /supervise_start - simpler than the public session flow since
    this is an internal staff-training session, not a roleplay one."""

    session_code = discord.ui.TextInput(
        label="Session Code",
        placeholder="e.g. TRAIN-042",
        max_length=100,
        required=True
    )
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Optional details about the supervised session",
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        session_id = str(uuid.uuid4())

        embed = discord.Embed(
            title="🔒 Supervised Session Started",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        if self.description.value:
            embed.add_field(name="Description", value=self.description.value, inline=False)
        embed.add_field(name="Session Code", value="🔒 Hidden - use the button below", inline=False)
        embed.add_field(name="Status", value="Active", inline=True)
        embed.add_field(name="Started By", value=interaction.user.mention, inline=False)

        posted_messages = []
        failures = []

        for channel_id in SUPERVISE_SESSION_CHANNEL_IDS:
            channel = bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden):
                    failures.append(f"`{channel_id}` (not found or no access)")
                    continue

            try:
                sent_message = await channel.send(embed=embed)
                # Attach the reveal button after sending, since its custom_id
                # embeds the message's own session_id/channel; timeout=None
                # keeps it clickable for the life of the session.
                await sent_message.edit(view=SuperviseRevealCodeView(session_id))
            except discord.Forbidden:
                failures.append(f"{channel.mention} (missing permission to post)")
                continue
            except discord.HTTPException as e:
                failures.append(f"{channel.mention} ({e})")
                continue

            posted_messages.append({"channel_id": channel.id, "message_id": sent_message.id})

        if not posted_messages:
            await interaction.followup.send(
                "❌ Couldn't post the supervised session notification to any configured channel:\n"
                + "\n".join(failures),
                ephemeral=True
            )
            return

        session_data = {
            "session_code": self.session_code.value,
            "description": self.description.value or None,
            "started_by": interaction.user.name,
            "started_by_id": str(interaction.user.id),
            "started_at": datetime.now().isoformat(),
            "ended": False,
            "released_to_session1": False,
            "messages": posted_messages
        }
        sessions = load_supervise_sessions()
        sessions[session_id] = session_data
        save_supervise_sessions(sessions)

        channel_mentions = ", ".join(f"<#{m['channel_id']}>" for m in posted_messages)
        confirmation = (
            f"✅ Supervised session notification posted in {channel_mentions}! The session code is "
            f"hidden until a Staff Trainer or Staff In Training member presses the reveal button - "
            f"it's shown to them only, and never written into the public embed."
        )
        if failures:
            confirmation += "\n\n⚠️ Failed to post to:\n" + "\n".join(failures)

        await interaction.followup.send(confirmation, ephemeral=True)


@bot.tree.command(name="supervise_start", description="Start a private supervised (staff training) session")
@require_supervise_manager()
async def supervise_start(interaction: discord.Interaction):
    """Start a supervised session - opens a short form, then posts a private notification"""
    await interaction.response.send_modal(SuperviseDetailsModal())


class SupervisedReleaseModal(discord.ui.Modal, title="Release Session Code"):
    """Shown only to the person who started a supervised session, the moment
    they press Reveal Session Code (and only if it hasn't been released yet).
    Collects the AORP and FRP Speed Limit so the code can be posted as a full
    session notification - code fully shown, no early access - in the
    Session 1 channel."""

    aorp = discord.ui.TextInput(
        label="Area Of Roleplay (AORP)",
        placeholder="e.g. Downtown District",
        max_length=100,
        required=True
    )
    frp_speed_limit = discord.ui.TextInput(
        label="FRP Speed Limit",
        placeholder="Numbers only, e.g. 80",
        max_length=10,
        required=True
    )

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id

    async def on_submit(self, interaction: discord.Interaction):
        # Validate FRP Speed Limit is numeric-only, same rule as /start_session
        speed_value = self.frp_speed_limit.value.strip()
        if not speed_value.isdigit():
            await interaction.response.send_message(
                f"❌ FRP Speed Limit must be numbers only. You entered: `{speed_value}`. "
                f"Press Reveal Session Code again to retry.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        sessions = load_supervise_sessions()
        session_data = sessions.get(self.session_id)
        if not session_data:
            await interaction.followup.send("❌ This session's data could no longer be found.", ephemeral=True)
            return

        if session_data.get("released_to_session1"):
            await interaction.followup.send(
                f"❌ This session's code was already released to <#{SUPERVISED_RELEASE_CHANNEL_ID}>.",
                ephemeral=True
            )
            return

        channel = bot.get_channel(SUPERVISED_RELEASE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(SUPERVISED_RELEASE_CHANNEL_ID)
            except discord.NotFound:
                channel = None
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have access to the Session 1 channel.",
                    ephemeral=True
                )
                return

        if channel is None:
            await interaction.followup.send(
                "❌ Couldn't find the Session 1 channel. Check the channel ID and that the bot can see it.",
                ephemeral=True
            )
            return

        starter_id = session_data.get("started_by_id")
        embed = discord.Embed(
            title="🎬 Roleplay Session Started!",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        if session_data.get("description"):
            embed.add_field(name="Description", value=session_data["description"], inline=False)
        embed.add_field(name="Area Of Roleplay (AORP)", value=self.aorp.value, inline=True)
        embed.add_field(name="FRP Speed Limit", value=f"{speed_value} mph", inline=True)
        embed.add_field(name="Session Code", value=f"🔓 {session_data['session_code']}", inline=False)
        embed.add_field(
            name="Started By",
            value=f"<@{starter_id}>" if starter_id else session_data.get("started_by", "Unknown"),
            inline=False
        )

        try:
            sent_message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to post in {channel.mention}.",
                ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Failed to post the notification: {e}", ephemeral=True)
            return

        session_data["released_to_session1"] = True
        session_data["released_by"] = interaction.user.name
        session_data["released_by_id"] = str(interaction.user.id)
        session_data["released_at"] = datetime.now().isoformat()
        session_data["release_channel_id"] = channel.id
        session_data["release_message_id"] = sent_message.id
        session_data["aorp"] = self.aorp.value
        session_data["frp_speed_limit"] = speed_value
        sessions[self.session_id] = session_data
        save_supervise_sessions(sessions)

        await interaction.followup.send(
            f"✅ Session code released and posted in {channel.mention}.",
            ephemeral=True
        )


class SuperviseRevealCodeButton(discord.ui.Button):
    """Reveal button for supervised sessions. Unlike RevealCodeButton (used by
    /release and /earlyaccess), this always replies ephemerally and never
    edits the public notification's embed - the code must never appear
    anywhere but in a reply only the clicker can see, or in the full
    Session 1 release the starter can trigger (see SupervisedReleaseModal)."""

    def __init__(self, session_id: str):
        super().__init__(
            label="🔓 Reveal Session Code",
            style=discord.ButtonStyle.danger,
            custom_id=f"supervise_reveal_{session_id}"
        )
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        if not has_supervise_code_access(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to reveal this session's code.",
                ephemeral=True
            )
            return

        sessions = load_supervise_sessions()
        session_data = sessions.get(self.session_id)
        if not session_data:
            await interaction.response.send_message(
                "❌ This session's data could no longer be found.",
                ephemeral=True
            )
            return

        is_starter = (
            session_data.get("started_by_id") is not None
            and str(interaction.user.id) == session_data.get("started_by_id")
        )

        # Only the person who started this session gets the option to release
        # it to Session 1 - and only while it hasn't already been released.
        # Everyone else (Staff Trainer, Staff In Training, other Admins) just
        # gets the code shown to them, with no release path.
        if is_starter and not session_data.get("released_to_session1"):
            await interaction.response.send_modal(SupervisedReleaseModal(self.session_id))
            return

        status_note = " (this session has ended)" if session_data.get("ended") else ""
        release_note = ""
        if session_data.get("released_to_session1"):
            release_note = f"\nℹ️ This code was already released to <#{SUPERVISED_RELEASE_CHANNEL_ID}>."
        await interaction.response.send_message(
            f"🔓 Session code: **{session_data['session_code']}**{status_note}{release_note}",
            ephemeral=True
        )

        # Log who revealed it (for records) without touching the public embed.
        revealed_by = session_data.setdefault("revealed_by", [])
        revealed_by.append({"user": interaction.user.name, "at": datetime.now().isoformat()})
        sessions[self.session_id] = session_data
        save_supervise_sessions(sessions)


class SuperviseRevealCodeView(discord.ui.View):
    def __init__(self, session_id: str):
        super().__init__(timeout=None)
        self.add_item(SuperviseRevealCodeButton(session_id))


def get_ongoing_supervise_sessions() -> dict:
    """Return supervised sessions that haven't been marked as ended yet"""
    sessions = load_supervise_sessions()
    return {sid: data for sid, data in sessions.items() if not data.get("ended")}


class EndSuperviseSessionSelect(discord.ui.Select):
    """Step 1 (and only step) of /supervise_end: pick which supervised session to end."""

    def __init__(self, sessions: dict):
        options = []
        for session_id, data in sessions.items():
            options.append(discord.SelectOption(
                label=str(data.get("session_code", "Unknown"))[:100],
                description=f"Started by {data.get('started_by', '?')}"[:100],
                value=session_id
            ))
        super().__init__(
            placeholder="Select which supervised session to end...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        # Re-check the required role at the point of use, same reasoning as
        # the other session-management components.
        if not is_supervise_manager(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to end a supervised session.",
                ephemeral=True
            )
            return

        session_id = self.values[0]
        sessions = load_supervise_sessions()
        session_data = sessions.get(session_id)
        if not session_data or session_data.get("ended"):
            await interaction.response.edit_message(content="❌ That session is no longer active.", view=None)
            return

        updated_channels = []
        problem_channels = []

        for msg_ref in session_data.get("messages", []):
            channel = bot.get_channel(msg_ref["channel_id"])
            if channel is None:
                try:
                    channel = await bot.fetch_channel(msg_ref["channel_id"])
                except (discord.NotFound, discord.Forbidden):
                    problem_channels.append(str(msg_ref["channel_id"]))
                    continue

            try:
                message = await channel.fetch_message(msg_ref["message_id"])
            except (discord.NotFound, discord.Forbidden):
                problem_channels.append(channel.mention)
                continue

            embed = message.embeds[0]
            embed.title = "🔴 Supervised Session Ended"
            embed.colour = discord.Color.dark_grey()

            status_set = False
            for idx, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(idx, name="Status", value="Ended", inline=field.inline)
                    status_set = True
                    break
            if not status_set:
                embed.add_field(name="Status", value="Ended", inline=True)

            # Drop the reveal button so the code can no longer be requested;
            # the notification itself is kept in place for records.
            await message.edit(embed=embed, view=None)
            updated_channels.append(channel.mention)

        session_data["ended"] = True
        session_data["ended_by"] = interaction.user.name
        session_data["ended_at"] = datetime.now().isoformat()
        sessions[session_id] = session_data
        save_supervise_sessions(sessions)

        result = f"✅ Supervised session code **{session_data['session_code']}** marked as ended"
        if updated_channels:
            result += f" in {', '.join(updated_channels)}"
        if problem_channels:
            result += f"\n⚠️ Couldn't update: {', '.join(problem_channels)}"

        await interaction.response.edit_message(content=result, view=None)


class EndSuperviseSessionView(discord.ui.View):
    def __init__(self, sessions: dict):
        super().__init__(timeout=120)
        self.add_item(EndSuperviseSessionSelect(sessions))


@bot.tree.command(name="supervise_end", description="End an active supervised (staff training) session")
@require_supervise_manager()
async def supervise_end(interaction: discord.Interaction):
    """Pick an active supervised session to end - marks its notification(s) as ended and keeps them for records"""
    sessions = get_ongoing_supervise_sessions()

    if not sessions:
        await interaction.response.send_message(
            "❌ There are no active supervised sessions to end.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select which supervised session you'd like to end:",
        view=EndSuperviseSessionView(sessions),
        ephemeral=True
    )


EARLYACCESS_GREETINGS = [
    "👋 Hey {mention}, thanks for checking in! Ready to jump in?",
    "🎉 Welcome, {mention}! Glad to see you here.",
    "👋 Hi {mention}! Hope you're having a good one.",
]


class EarlyAccessRevealSelect(discord.ui.Select):
    """Shown to /earlyaccess users only when more than one session is active,
    so they can pick which one's code to reveal."""

    def __init__(self, sessions: dict):
        options = []
        for message_id, data in sessions.items():
            channel_name = SESSION_CHANNELS.get(str(data.get("channel_id")), str(data.get("channel_id")))
            options.append(discord.SelectOption(
                label=f"{data.get('aorp', 'Unknown area')} ({channel_name})"[:100],
                description=f"Peacetime: {data.get('peacetime', '?')} - Started by {data.get('started_by', '?')}"[:100],
                value=message_id
            ))
        super().__init__(
            placeholder="Select which session to reveal the code for...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        message_id = self.values[0]
        sessions = load_active_sessions()
        session_data = sessions.get(message_id)
        if not session_data or session_data.get("ended") or session_data.get("code_released"):
            await interaction.response.edit_message(
                content="❌ That session is no longer available for release.",
                view=None
            )
            return

        await interaction.response.edit_message(
            content=(
                f"Session in **{session_data.get('aorp', 'Unknown area')}** selected. "
                f"Press below to reveal its code - only you can see this button."
            ),
            view=RevealCodeView(
                message_id=message_id,
                session_data=session_data,
                access_check=has_earlyaccess_access,
                unauthorized_message="❌ You don't have access to reveal session codes.",
                label="🔓 Reveal Code"
            )
        )


class EarlyAccessSelectView(discord.ui.View):
    def __init__(self, sessions: dict):
        super().__init__(timeout=120)
        self.add_item(EarlyAccessRevealSelect(sessions))


@bot.tree.command(name="earlyaccess", description="Get early access to reveal the current session's code")
@require_earlyaccess_access()
async def earlyaccess(interaction: discord.Interaction):
    """Friendly entry point for Law Enforcement / Early Access roles to reveal
    a session's code - auto-picks the session if only one is active, otherwise
    lets the user pick which one first."""
    sessions = get_releasable_sessions()
    greeting = random.choice(EARLYACCESS_GREETINGS).format(mention=interaction.user.mention)

    if not sessions:
        await interaction.response.send_message(
            f"{greeting}\n\n❌ There are no session codes available to reveal right now.",
            ephemeral=True
        )
        return

    if len(sessions) == 1:
        message_id, session_data = next(iter(sessions.items()))
        await interaction.response.send_message(
            f"{greeting}\n\nPress below to reveal the session code - only you can see this button.",
            view=RevealCodeView(
                message_id=message_id,
                session_data=session_data,
                access_check=has_earlyaccess_access,
                unauthorized_message="❌ You don't have access to reveal session codes.",
                label="🔓 Reveal Code"
            ),
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"{greeting}\n\nThere are multiple active sessions - select which one you'd like the code for:",
        view=EarlyAccessSelectView(sessions),
        ephemeral=True
    )


@bot.tree.command(name="all_vehicles", description="View all registered vehicles (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def all_vehicles(interaction: discord.Interaction):
    """View all vehicles registered (admin command)"""
    await interaction.response.defer()
    
    vehicles = load_vehicles()
    
    if not vehicles:
        await interaction.followup.send("❌ No vehicles registered yet!")
        return
    
    embed = discord.Embed(
        title="🚗 All Registered Vehicles",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    
    total_vehicles = 0
    for user_id, user_data in vehicles.items():
        vehicle_list = "\n".join(
            f"  • {v['year']} {v['brand']} {v['model']} ({v['plate']}) - Owner: {v['owner']}"
            for v in user_data["vehicles"]
        )
        embed.add_field(
            name=f"{user_data['username']} ({len(user_data['vehicles'])} vehicle(s))",
            value=vehicle_list or "No vehicles",
            inline=False
        )
        total_vehicles += len(user_data["vehicles"])
    
    embed.set_footer(text=f"Total vehicles: {total_vehicles}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="issue_citation", description="Issue a citation/ticket to a user (Law Enforcement only)")
async def issue_citation(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str,
    fine_amount: int
):
    """Issue a citation to a user"""
    await interaction.response.defer()
    
    # Check if user has law enforcement role
    if not is_law_enforcement(interaction):
        await interaction.followup.send("❌ You don't have permission to issue citations! Only Law Enforcement can issue citations.")
        return
    
    # Load citations
    citations = load_citations()
    
    # Generate citation ID
    citation_id = generate_citation_id()
    
    # Create citation entry
    citation = {
        "citation_id": citation_id,
        "issued_to": user.name,
        "issued_to_id": str(user.id),
        "issued_by": interaction.user.name,
        "issued_by_id": str(interaction.user.id),
        "reason": reason,
        "fine_amount": fine_amount,
        "issued_at": datetime.now().isoformat(),
        "paid": False
    }
    
    # Initialize user's citations if needed
    if str(user.id) not in citations:
        citations[str(user.id)] = []
    
    citations[str(user.id)].append(citation)
    save_citations(citations)
    
    # Create confirmation embed for officer
    embed = discord.Embed(
        title="✅ Citation Issued",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Citation ID", value=citation_id, inline=True)
    embed.add_field(name="Issued To", value=user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Fine Amount", value=f"${fine_amount}", inline=True)
    embed.add_field(name="Issued By", value=interaction.user.mention, inline=True)
    embed.set_footer(text=f"Officer: {interaction.user.name}")
    
    await interaction.followup.send(embed=embed)
    
    # Send DM to cited user
    try:
        user_embed = discord.Embed(
            title="🚨 You Have Been Cited",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        user_embed.add_field(name="Citation ID", value=citation_id, inline=False)
        user_embed.add_field(name="Reason", value=reason, inline=False)
        user_embed.add_field(name="Fine Amount", value=f"${fine_amount}", inline=True)
        user_embed.add_field(name="Issued By", value=interaction.user.name, inline=True)
        user_embed.add_field(name="Status", value="⚠️ Outstanding", inline=False)
        user_embed.set_footer(text="Use /my_citations to view your citations")
        
        await user.send(embed=user_embed)
    except discord.Forbidden:
        pass  # User has DMs disabled

@bot.tree.command(name="my_citations", description="View all citations issued to you")
async def my_citations(interaction: discord.Interaction):
    """View user's citations"""
    await interaction.response.defer()
    
    citations = load_citations()
    user_id = str(interaction.user.id)
    
    if user_id not in citations or not citations[user_id]:
        await interaction.followup.send("✅ You have no citations! Clean record.")
        return
    
    # Create embed with all citations
    embed = discord.Embed(
        title=f"📋 Your Citations - {interaction.user.name}",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    
    total_fine = 0
    outstanding_count = 0
    
    for idx, citation in enumerate(citations[user_id], 1):
        status = "✅ Paid" if citation.get("paid", False) else "⚠️ Outstanding"
        citation_info = (
            f"**Citation ID:** {citation['citation_id']}\n"
            f"**Reason:** {citation['reason']}\n"
            f"**Fine:** ${citation['fine_amount']}\n"
            f"**Issued By:** {citation['issued_by']}\n"
            f"**Date:** {citation['issued_at'][:10]}\n"
            f"**Status:** {status}"
        )
        embed.add_field(name=f"Citation #{idx}", value=citation_info, inline=False)
        total_fine += citation['fine_amount']
        if not citation.get("paid", False):
            outstanding_count += 1
    
    embed.add_field(name="Summary", value=f"**Total Fine:** ${total_fine}\n**Outstanding:** {outstanding_count}", inline=False)
    await interaction.followup.send(embed=embed)

class InfractionModal(discord.ui.Modal, title="Issue Infraction"):
    """Step 2 of /infract: reason + evidence, shown after the target user is
    picked as a command option."""

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this infraction being issued?",
        max_length=500,
        required=True
    )
    evidence = discord.ui.TextInput(
        label="Evidence",
        style=discord.TextStyle.paragraph,
        placeholder="Link(s) to clips/screenshots, or a description",
        max_length=500,
        required=False
    )

    def __init__(self, target: discord.Member):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        infractions = load_infractions()
        infraction_id = generate_infraction_id()
        user_id = str(self.target.id)

        # Staff (Admin/Session Manager/Law Enforcement) escalate on a separate
        # "Staff Strike" role ladder instead of the regular Infraction one.
        staff_track = is_staff_member(self.target)
        role_ladder = STAFF_STRIKE_ROLES if staff_track else INFRACTION_ROLES
        track_label = "Staff Strike" if staff_track else "Infraction"

        infraction = {
            "infraction_id": infraction_id,
            "issued_to": self.target.name,
            "issued_to_id": user_id,
            "issued_by": interaction.user.name,
            "issued_by_id": str(interaction.user.id),
            "reason": self.reason.value,
            "evidence": self.evidence.value or "None provided",
            "staff_track": staff_track,
            "issued_at": datetime.now().isoformat()
        }

        if user_id not in infractions:
            infractions[user_id] = []
        infractions[user_id].append(infraction)
        save_infractions(infractions)

        level = len(infractions[user_id])  # 1-indexed level reached with this infraction

        # Update the target's role to match their new level: drop any older
        # level role on this ladder, then add the one for the new level. Past
        # the top of the ladder (level 5+) there's no role - that's the
        # kick/ban threshold instead.
        role_note = None
        if level <= len(role_ladder):
            new_role_id = role_ladder[level - 1]
            try:
                guild = interaction.guild
                stale_roles = [
                    role for role in self.target.roles
                    if role.id in role_ladder and role.id != new_role_id
                ]
                if stale_roles:
                    await self.target.remove_roles(*stale_roles, reason=f"{track_label} level updated to {level}")

                new_role = guild.get_role(new_role_id)
                if new_role:
                    await self.target.add_roles(new_role, reason=f"{track_label} #{level} issued by {interaction.user.name}")
                else:
                    role_note = f"⚠️ Couldn't find the {track_label} {level} role in this server - check the role ID is correct."
            except discord.Forbidden:
                role_note = "⚠️ I don't have permission to manage that role - check my Manage Roles permission and role position."
            except discord.HTTPException as e:
                role_note = f"⚠️ Failed to update roles: {e}"
        else:
            role_note = (
                f"🚨 {self.target.mention} has reached **{track_label} level {level}** - the maximum on this ladder. "
                f"Please manually kick or ban them via Dyno (e.g. `!kick {self.target.mention}` or "
                f"`!ban {self.target.mention}`, depending on this server's Dyno prefix)."
            )

        # Confirmation embed for whoever issued it
        embed = discord.Embed(
            title=f"⚠️ {track_label} Issued",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Infraction ID", value=infraction_id, inline=True)
        embed.add_field(name="Issued To", value=self.target.mention, inline=True)
        embed.add_field(name=f"{track_label} Level", value=str(level), inline=True)
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        embed.add_field(name="Evidence", value=self.evidence.value or "None provided", inline=False)
        embed.add_field(name="Issued By", value=interaction.user.mention, inline=False)
        embed.set_footer(text=f"Admin: {interaction.user.name}")

        await interaction.followup.send(embed=embed)
        if role_note:
            await interaction.followup.send(role_note)

        # Send DM to the infracted user
        try:
            user_embed = discord.Embed(
                title=f"⚠️ You Have Received a {track_label}",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            user_embed.add_field(name="Infraction ID", value=infraction_id, inline=False)
            user_embed.add_field(name="Reason", value=self.reason.value, inline=False)
            if self.evidence.value:
                user_embed.add_field(name="Evidence", value=self.evidence.value, inline=False)
            user_embed.add_field(name=f"{track_label} Level", value=str(level), inline=True)
            user_embed.add_field(name="Issued By", value=interaction.user.name, inline=True)
            user_embed.set_footer(text="Use /my_infractions to view your infraction history")

            await self.target.send(embed=user_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled


@bot.tree.command(name="infract", description="Issue an infraction to a user (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def infract(interaction: discord.Interaction, user: discord.Member):
    """Open the infraction form (Reason + Evidence) for the given user"""
    await interaction.response.send_modal(InfractionModal(target=user))

@bot.tree.command(name="my_infractions", description="View all infractions issued to you")
async def my_infractions(interaction: discord.Interaction):
    """View user's infractions"""
    await interaction.response.defer()

    infractions = load_infractions()
    user_id = str(interaction.user.id)

    if user_id not in infractions or not infractions[user_id]:
        await interaction.followup.send("✅ You have no infractions! Clean record.")
        return

    embed = discord.Embed(
        title=f"⚠️ Your Infractions - {interaction.user.name}",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )

    for idx, infraction in enumerate(infractions[user_id], 1):
        infraction_info = (
            f"**Infraction ID:** {infraction['infraction_id']}\n"
            f"**Reason:** {infraction['reason']}\n"
            f"**Issued By:** {infraction['issued_by']}\n"
            f"**Date:** {infraction['issued_at'][:10]}"
        )
        embed.add_field(name=f"Infraction #{idx}", value=infraction_info, inline=False)

    embed.add_field(name="Summary", value=f"**Total Infractions:** {len(infractions[user_id])}", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="user_profile", description="View a user's profile including their citations and infractions")
async def user_profile(interaction: discord.Interaction, user: discord.Member):
    """View user profile with citations and infractions"""
    await interaction.response.defer()
    
    vehicles = load_vehicles()
    citations = load_citations()
    infractions = load_infractions()
    
    user_id = str(user.id)
    
    # Create profile embed
    embed = discord.Embed(
        title=f"👤 {user.name}'s Profile",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    
    # Add vehicle info
    if user_id in vehicles:
        vehicle_count = len(vehicles[user_id]["vehicles"])
        embed.add_field(name="🚗 Registered Vehicles", value=f"{vehicle_count} vehicle(s)", inline=False)
    else:
        embed.add_field(name="🚗 Registered Vehicles", value="No vehicles registered", inline=False)
    
    # Add citation info
    if user_id in citations and citations[user_id]:
        citation_count = len(citations[user_id])
        outstanding = sum(1 for c in citations[user_id] if not c.get("paid", False))
        total_fine = sum(c['fine_amount'] for c in citations[user_id])
        
        citation_info = (
            f"**Total Citations:** {citation_count}\n"
            f"**Outstanding:** {outstanding}\n"
            f"**Total Fine:** ${total_fine}"
        )
        embed.add_field(name="🚨 Citations", value=citation_info, inline=False)
    else:
        embed.add_field(name="🚨 Citations", value="No citations on record", inline=False)

    # Add infraction info, including which role/level they're currently on
    if user_id in infractions and infractions[user_id]:
        infraction_count = len(infractions[user_id])
        staff_track = is_staff_member(user)
        role_ladder = STAFF_STRIKE_ROLES if staff_track else INFRACTION_ROLES
        track_label = "Staff Strike" if staff_track else "Infraction"

        if infraction_count <= len(role_ladder):
            level_line = f"**Current Level:** {track_label} {infraction_count} (<@&{role_ladder[infraction_count - 1]}>)"
        else:
            level_line = f"**Current Level:** {track_label} {infraction_count} - 🚨 Kick/ban threshold reached"

        recent = infractions[user_id][-3:]
        recent_info = "\n".join(
            f"• `{i['infraction_id']}` {i['reason']} ({i['issued_at'][:10]})"
            for i in reversed(recent)
        )
        infraction_info = f"**Total {track_label}s:** {infraction_count}\n{level_line}\n{recent_info}"
        if infraction_count > len(recent):
            infraction_info += f"\n*...and {infraction_count - len(recent)} more*"
        embed.add_field(
            name="⚠️ Staff Strikes" if staff_track else "⚠️ Infractions",
            value=infraction_info,
            inline=False
        )
    else:
        embed.add_field(name="⚠️ Infractions", value="No infractions on record", inline=False)
    
    embed.set_footer(text=f"Requested by {interaction.user.name}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="mark_citation_paid", description="Mark a citation as paid (Law Enforcement only)")
async def mark_citation_paid(
    interaction: discord.Interaction,
    citation_id: str,
    user: discord.User
):
    """Mark a citation as paid"""
    await interaction.response.defer()
    
    # Check if user has law enforcement role
    if not is_law_enforcement(interaction):
        await interaction.followup.send("❌ You don't have permission to manage citations! Only Law Enforcement can do this.")
        return
    
    citations = load_citations()
    user_id = str(user.id)
    
    if user_id not in citations:
        await interaction.followup.send(f"❌ No citations found for {user.name}!")
        return
    
    # Find and mark citation as paid
    found = False
    for citation in citations[user_id]:
        if citation['citation_id'] == citation_id:
            citation['paid'] = True
            citation['paid_at'] = datetime.now().isoformat()
            citation['paid_by'] = interaction.user.name
            found = True
            break
    
    if not found:
        await interaction.followup.send(f"❌ Citation ID '{citation_id}' not found!")
        return
    
    save_citations(citations)
    
    # Create confirmation embed
    embed = discord.Embed(
        title="✅ Citation Marked as Paid",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    embed.add_field(name="Citation ID", value=citation_id, inline=True)
    embed.add_field(name="Citizen", value=user.mention, inline=True)
    embed.add_field(name="Marked By", value=interaction.user.mention, inline=False)
    
    await interaction.followup.send(embed=embed)

# ---------------------------------------------------------------------------
# Leave of Absence (LOA) system
# ---------------------------------------------------------------------------

# Expected format for the date/time fields on the /loa_request form
LOA_DATETIME_FORMAT = "%Y-%m-%d %H:%M"
LOA_DATETIME_EXAMPLE = "2025-06-15 18:00"

# Optional: channel ID to post a notification in whenever a new LOA request
# comes in, so HR knows to review it via /loa_approve or /loa_reject. Leave
# as None to skip posting (HR can still see pending requests via the
# /loa_approve and /loa_reject dropdowns at any time).
LOA_NOTIFICATION_CHANNEL_ID = None


def parse_loa_datetime(value: str) -> datetime:
    """Parse a LOA form date/time field. Raises ValueError (with a
    user-friendly message) if the value doesn't match LOA_DATETIME_FORMAT."""
    try:
        return datetime.strptime(value.strip(), LOA_DATETIME_FORMAT)
    except ValueError:
        raise ValueError(
            f"Couldn't understand `{value}`. Please use the format "
            f"`YYYY-MM-DD HH:MM` (24-hour time), e.g. `{LOA_DATETIME_EXAMPLE}`."
        )


def get_pending_loa_requests() -> dict:
    """Return only the LOA requests still awaiting a decision."""
    requests = load_loa_requests()
    return {
        request_id: data
        for request_id, data in requests.items()
        if data.get("status") == "pending"
    }


class LOARequestModal(discord.ui.Modal, title="Request Leave of Absence"):
    """Form shown by /loa_request: start/end date+time and a reason."""

    start_datetime = discord.ui.TextInput(
        label="Start Date & Time (YYYY-MM-DD HH:MM)",
        placeholder=LOA_DATETIME_EXAMPLE,
        max_length=20,
        required=True
    )
    end_datetime = discord.ui.TextInput(
        label="End Date & Time (YYYY-MM-DD HH:MM)",
        placeholder=LOA_DATETIME_EXAMPLE,
        max_length=20,
        required=True
    )
    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why are you requesting this LOA?",
        max_length=500,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Validate both date/times before saving anything
        try:
            start_dt = parse_loa_datetime(self.start_datetime.value)
        except ValueError as e:
            await interaction.response.send_message(f"❌ Start date/time: {e}", ephemeral=True)
            return

        try:
            end_dt = parse_loa_datetime(self.end_datetime.value)
        except ValueError as e:
            await interaction.response.send_message(f"❌ End date/time: {e}", ephemeral=True)
            return

        if end_dt <= start_dt:
            await interaction.response.send_message(
                "❌ The end date/time must be after the start date/time. Please run `/loa_request` again.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        requests = load_loa_requests()
        request_id = generate_loa_id()
        while request_id in requests:  # guard against the unlikely collision
            request_id = generate_loa_id()

        requests[request_id] = {
            "request_id": request_id,
            "user_id": str(interaction.user.id),
            "username": interaction.user.name,
            "start": self.start_datetime.value.strip(),
            "end": self.end_datetime.value.strip(),
            "reason": self.reason.value,
            "status": "pending",
            "requested_at": datetime.now().isoformat(),
            "decided_by": None,
            "decided_at": None,
        }
        save_loa_requests(requests)

        embed = discord.Embed(
            title="📝 LOA Request Submitted",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Request ID", value=request_id, inline=True)
        embed.add_field(name="Status", value="⏳ Pending", inline=True)
        embed.add_field(name="Start", value=self.start_datetime.value.strip(), inline=True)
        embed.add_field(name="End", value=self.end_datetime.value.strip(), inline=True)
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        embed.set_footer(text="An HR team member will review this request")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Optional public/HR-facing notification
        if LOA_NOTIFICATION_CHANNEL_ID:
            channel = bot.get_channel(LOA_NOTIFICATION_CHANNEL_ID)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(LOA_NOTIFICATION_CHANNEL_ID)
                except (discord.NotFound, discord.Forbidden):
                    channel = None
            if channel is not None:
                notify_embed = discord.Embed(
                    title="📥 New LOA Request",
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                notify_embed.add_field(name="Requested By", value=interaction.user.mention, inline=True)
                notify_embed.add_field(name="Request ID", value=request_id, inline=True)
                notify_embed.add_field(name="Start", value=self.start_datetime.value.strip(), inline=True)
                notify_embed.add_field(name="End", value=self.end_datetime.value.strip(), inline=True)
                notify_embed.add_field(name="Reason", value=self.reason.value, inline=False)
                notify_embed.set_footer(text="Use /loa_approve or /loa_reject to review")
                try:
                    await channel.send(embed=notify_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass


@bot.tree.command(name="loa_request", description="Request a Leave of Absence (Staff only)")
@require_loa_eligible()
async def loa_request(interaction: discord.Interaction):
    """Open the LOA request form"""
    await interaction.response.send_modal(LOARequestModal())


async def resolve_loa_request(request_id: str, approve: bool, decided_by: discord.Member):
    """Core logic shared by /loa_approve and /loa_reject: marks the request
    with a decision, saves it, and DMs the requester. Returns
    (success: bool, description: str, requester_id: str | None)."""
    requests = load_loa_requests()
    data = requests.get(request_id)
    if not data or data.get("status") != "pending":
        return False, "That LOA request is no longer pending.", None

    data["status"] = "approved" if approve else "rejected"
    data["decided_by"] = decided_by.name
    data["decided_by_id"] = str(decided_by.id)
    data["decided_at"] = datetime.now().isoformat()
    requests[request_id] = data
    save_loa_requests(requests)

    description = (
        f"LOA request from **{data['username']}** ({data['start']} → {data['end']}) "
        f"was {'approved' if approve else 'rejected'}."
    )

    # DM the requester
    requester = bot.get_user(int(data["user_id"]))
    if requester is None:
        try:
            requester = await bot.fetch_user(int(data["user_id"]))
        except discord.NotFound:
            requester = None

    if requester is not None:
        try:
            user_embed = discord.Embed(
                title=f"{'✅' if approve else '❌'} Your LOA Request Was {'Approved' if approve else 'Rejected'}",
                color=discord.Color.green() if approve else discord.Color.red(),
                timestamp=datetime.now()
            )
            user_embed.add_field(name="Request ID", value=request_id, inline=True)
            user_embed.add_field(name="Start", value=data["start"], inline=True)
            user_embed.add_field(name="End", value=data["end"], inline=True)
            user_embed.add_field(name="Reason", value=data["reason"], inline=False)
            user_embed.add_field(name="Decided By", value=decided_by.name, inline=False)
            await requester.send(embed=user_embed)
        except discord.Forbidden:
            pass  # User has DMs disabled

    return True, description, data["user_id"]


class LOAApproveSelect(discord.ui.Select):
    """Step 1 (and only step) of /loa_approve: pick which pending request to approve."""

    def __init__(self, requests: dict):
        options = []
        for request_id, data in requests.items():
            options.append(discord.SelectOption(
                label=f"{data.get('username', 'Unknown')} - {data.get('start', '?')}"[:100],
                description=f"Until {data.get('end', '?')} - {data.get('reason', '')}"[:100],
                value=request_id
            ))
        super().__init__(
            placeholder="Select which LOA request to approve...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_hr(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to approve LOA requests.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        success, description, _ = await resolve_loa_request(self.values[0], approve=True, decided_by=interaction.user)

        if not success:
            await interaction.edit_original_response(content=f"❌ {description}", view=None)
            return

        await interaction.edit_original_response(content=f"✅ {description}", view=None)


class LOAApproveView(discord.ui.View):
    def __init__(self, requests: dict):
        super().__init__(timeout=120)
        self.add_item(LOAApproveSelect(requests))


class LOARejectSelect(discord.ui.Select):
    """Step 1 (and only step) of /loa_reject: pick which pending request to reject."""

    def __init__(self, requests: dict):
        options = []
        for request_id, data in requests.items():
            options.append(discord.SelectOption(
                label=f"{data.get('username', 'Unknown')} - {data.get('start', '?')}"[:100],
                description=f"Until {data.get('end', '?')} - {data.get('reason', '')}"[:100],
                value=request_id
            ))
        super().__init__(
            placeholder="Select which LOA request to reject...",
            min_values=1,
            max_values=1,
            options=options[:25]  # Discord allows at most 25 options per select
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_hr(interaction):
            await interaction.response.send_message(
                "❌ You don't have the required role to reject LOA requests.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        success, description, _ = await resolve_loa_request(self.values[0], approve=False, decided_by=interaction.user)

        if not success:
            await interaction.edit_original_response(content=f"❌ {description}", view=None)
            return

        await interaction.edit_original_response(content=f"✅ {description}", view=None)


class LOARejectView(discord.ui.View):
    def __init__(self, requests: dict):
        super().__init__(timeout=120)
        self.add_item(LOARejectSelect(requests))


@bot.tree.command(name="loa_approve", description="Approve a pending LOA request (HR only)")
@require_hr()
async def loa_approve(interaction: discord.Interaction):
    """Pick a pending LOA request to approve"""
    pending = get_pending_loa_requests()

    if not pending:
        await interaction.response.send_message(
            "❌ There are no pending LOA requests to approve.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select which LOA request you'd like to approve:",
        view=LOAApproveView(pending),
        ephemeral=True
    )


@bot.tree.command(name="loa_reject", description="Reject a pending LOA request (HR only)")
@require_hr()
async def loa_reject(interaction: discord.Interaction):
    """Pick a pending LOA request to reject"""
    pending = get_pending_loa_requests()

    if not pending:
        await interaction.response.send_message(
            "❌ There are no pending LOA requests to reject.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Select which LOA request you'd like to reject:",
        view=LOARejectView(pending),
        ephemeral=True
    )


@bot.tree.command(name="say", description="Send a message as the bot (restricted role only)")
@require_say_access()
@app_commands.describe(
    message="The message to send",
    channel="Channel to send it in (defaults to the current channel)"
)
async def say(
    interaction: discord.Interaction,
    message: str,
    channel: discord.TextChannel = None
):
    """Send a message to a channel as the bot itself"""
    target_channel = channel or interaction.channel

    try:
        await target_channel.send(message)
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ I don't have permission to send messages in {target_channel.mention}.",
            ephemeral=True
        )
        return
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"❌ Failed to send message: {e}",
            ephemeral=True
        )
        return

    confirmation = f"✅ Message sent in {target_channel.mention}."
    await interaction.response.send_message(confirmation, ephemeral=True)

@bot.tree.command(name="version", description="Check the current software version of the bot")
async def version(interaction: discord.Interaction):
    """Display the bot's software version, codename, and developer"""
    embed = discord.Embed(
        title="Software Version",
        description="**Software:** Lily\n**Version:** 0.1\n**Codename:** Lily\n**Developer:** <@904243741106245704>",
        color=discord.Color.blurple(),
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"Requested by {interaction.user.name}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="terminate", description="Terminate a staff member and remove their staff roles")
@require_loa_eligible()
@app_commands.describe(
    target="The staff member to terminate",
    reason="The reason for termination"
)
async def terminate(
    interaction: discord.Interaction, 
    target: discord.Member, 
    reason: str
):
    """Terminate a staff member by stripping their roles (requires higher role hierarchy)"""
    await interaction.response.defer()

    # Bypass hierarchy check if the invoker is the server owner
    if interaction.user.id != interaction.guild.owner_id:
        # Check if the invoker has a strictly higher top role than the target
        if interaction.user.top_role.position <= target.top_role.position:
            await interaction.followup.send("❌ You cannot terminate a staff member who has a role equal to or higher than yours!")
            return
    
    # Identify which staff roles the target currently has based on the LOA list
    roles_to_remove = [
        role for role in target.roles 
        if role.id in LOA_ELIGIBLE_ROLES
    ]

    if not roles_to_remove:
        await interaction.followup.send(f"❌ {target.mention} does not have any recognizable staff roles to remove.")
        return

    # Attempt to remove the roles
    try:
        await target.remove_roles(*roles_to_remove, reason=f"Terminated by {interaction.user.name} - Reason: {reason}")
    except discord.Forbidden:
        await interaction.followup.send("❌ I do not have permission to remove roles from this user. Ensure my bot role is higher than theirs in the server settings.")
        return
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Failed to update roles: {e}")
        return

    # Notify the terminated user via DM
    try:
        dm_embed = discord.Embed(
            title="🚨 Notice of Termination",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        dm_embed.add_field(name="Reason", value=reason, inline=False)
        dm_embed.add_field(name="Terminated By", value=interaction.user.name, inline=False)
        dm_embed.set_footer(text="Your staff roles have been removed.")
        await target.send(embed=dm_embed)
    except discord.Forbidden:
        pass # The user has DMs disabled

    # Post confirmation in the channel
    confirm_embed = discord.Embed(
        title="✅ Staff Member Terminated",
        description=f"Successfully terminated {target.mention}.",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    confirm_embed.add_field(name="Reason", value=reason, inline=False)
    confirm_embed.add_field(name="Roles Removed", value=str(len(roles_to_remove)), inline=True)
    confirm_embed.set_footer(text=f"Terminated by {interaction.user.name}")

    await interaction.followup.send(embed=confirm_embed)

@bot.event
async def on_command_error(ctx, error):
    """Error handling for prefix commands"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command!")
    else:
        print(f"Error: {error}")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Error handling for slash commands"""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command! (Administrator required)",
            ephemeral=True
        )
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "❌ You don't have the required role to use this command.",
            ephemeral=True
        )
    else:
        print(f"App command error: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("❌ An unexpected error occurred.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        except discord.HTTPException:
            pass



# Run the bot
def main():
    """Main entry point"""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set!")
        return
    
    bot.run(token)

if __name__ == "__main__":
    main()

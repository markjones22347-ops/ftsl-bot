"""
FTSL Verification + Pullback Bot
A complete, production-ready Discord bot for user verification and emergency pullback system.

Features:
- Secure verification system with DM and button fallback
- Account age and join time security checks
- Attempt limiting with cooldown
- Flagged user blocking
- Anti-raid mode
- Emergency pullback system
- Local JSON storage
- Fully automatic file creation
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Discord IDs
VERIFIED_ROLE_ID = 1500218041449844977
UNVERIFIED_ROLE_ID = 1500224847219920987
ADMIN_ROLE_ID = 1500217835950047323
VERIFICATION_CHANNEL_ID = 1500220647295553536
BACKUP_INVITE = "https://discord.gg/sHeHF8VyYC"

# Security settings
MIN_ACCOUNT_AGE_DAYS = 7
MIN_JOIN_DELAY_SECONDS = 10
MAX_VERIFICATION_ATTEMPTS = 3
ATTEMPT_COOLDOWN_SECONDS = 30

# File paths
VERIFIED_USERS_FILE = "verified_users.json"
FLAGGED_USERS_FILE = "flagged.json"
RAID_MODE_FILE = "raid_mode.txt"

# Uptime Robot support
UPTIME_PORT = int(os.getenv('PORT', 10000))

# ==============================================================================
# STORAGE MANAGEMENT
# ==============================================================================

# ==============================================================================
# UPTIME ROBOT HTTP SERVER
# ==============================================================================

class UptimeHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for Uptime Robot pings."""
    
    def do_GET(self):
        """Handle GET requests for uptime monitoring."""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'OK')

    def do_HEAD(self):
        """Handle HEAD requests for uptime monitoring."""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-Length', '2')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

def start_uptime_server():
    """Start the HTTP server for uptime monitoring in a background thread."""
    try:
        server = HTTPServer(('0.0.0.0', UPTIME_PORT), UptimeHandler)
        print(f"Uptime server started on port {UPTIME_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"Error starting uptime server: {e}")

# ==============================================================================
# STORAGE MANAGEMENT
# ==============================================================================

class StorageManager:
    """Handles all local JSON file operations with auto-creation."""
    
    def __init__(self):
        self.verified_users: Set[str] = set()
        self.flagged_users: Set[str] = set()
        self.raid_mode: bool = False
        self._load_all_files()
    
    def _load_all_files(self):
        """Load all storage files, creating them if they don't exist."""
        self._load_verified_users()
        self._load_flagged_users()
        self._load_raid_mode()
    
    def _load_verified_users(self):
        """Load verified users from JSON file."""
        try:
            if os.path.exists(VERIFIED_USERS_FILE):
                with open(VERIFIED_USERS_FILE, 'r') as f:
                    data = json.load(f)
                    self.verified_users = set(data.get('verified', []))
            else:
                self._create_verified_users_file()
        except Exception as e:
            print(f"Error loading verified users: {e}")
            self.verified_users = set()
            self._create_verified_users_file()
    
    def _create_verified_users_file(self):
        """Create the verified users JSON file with default structure."""
        try:
            with open(VERIFIED_USERS_FILE, 'w') as f:
                json.dump({'verified': []}, f, indent=2)
        except Exception as e:
            print(f"Error creating verified users file: {e}")
    
    def _load_flagged_users(self):
        """Load flagged users from JSON file."""
        try:
            if os.path.exists(FLAGGED_USERS_FILE):
                with open(FLAGGED_USERS_FILE, 'r') as f:
                    data = json.load(f)
                    self.flagged_users = set(data.get('flagged', []))
            else:
                self.flagged_users = set()
        except Exception as e:
            print(f"Error loading flagged users: {e}")
            self.flagged_users = set()
    
    def _load_raid_mode(self):
        """Load raid mode status from file."""
        try:
            self.raid_mode = os.path.exists(RAID_MODE_FILE)
        except Exception as e:
            print(f"Error loading raid mode: {e}")
            self.raid_mode = False
    
    def save_verified_users(self):
        """Save verified users to JSON file."""
        try:
            with open(VERIFIED_USERS_FILE, 'w') as f:
                json.dump({'verified': list(self.verified_users)}, f, indent=2)
        except Exception as e:
            print(f"Error saving verified users: {e}")
    
    def add_verified_user(self, user_id: str):
        """Add a user to the verified list."""
        self.verified_users.add(user_id)
        self.save_verified_users()
    
    def remove_verified_user(self, user_id: str):
        """Remove a user from the verified list."""
        self.verified_users.discard(user_id)
        self.save_verified_users()
    
    def is_verified(self, user_id: str) -> bool:
        """Check if a user is verified."""
        return str(user_id) in self.verified_users
    
    def is_flagged(self, user_id: str) -> bool:
        """Check if a user is flagged."""
        return str(user_id) in self.flagged_users
    
    def get_verified_count(self) -> int:
        """Get the count of verified users."""
        return len(self.verified_users)
    
    def get_flagged_count(self) -> int:
        """Get the count of flagged users."""
        return len(self.flagged_users)

# ==============================================================================
# VERIFICATION SYSTEM
# ==============================================================================

class VerificationSystem:
    """Handles all verification logic and security checks."""
    
    def __init__(self, storage: StorageManager, bot: commands.Bot):
        self.storage = storage
        self.bot = bot
        self.pending_verifications: Dict[str, Dict] = {}
        self.verification_attempts: Dict[str, Dict] = {}
    
    def generate_math_question(self) -> tuple[str, str]:
        """Generate a simple math captcha question and its answer."""
        # Pick a random operation
        ops = ['+', '-', 'x']
        op = random.choice(ops)
        
        if op == '+':
            a = random.randint(1, 20)
            b = random.randint(1, 20)
            question = f"What is {a} + {b}?"
            answer = str(a + b)
        elif op == '-':
            a = random.randint(5, 20)
            b = random.randint(1, a)
            question = f"What is {a} - {b}?"
            answer = str(a - b)
        else:  # multiplication
            a = random.randint(2, 10)
            b = random.randint(2, 10)
            question = f"What is {a} x {b}?"
            answer = str(a * b)
        
        return question, answer
    
    def check_account_age(self, member: discord.Member) -> tuple[bool, str]:
        """Check if the user's account is old enough."""
        account_age = datetime.now() - member.created_at
        if account_age.days < MIN_ACCOUNT_AGE_DAYS:
            return False, f"Your account is too new. You must wait {MIN_ACCOUNT_AGE_DAYS - account_age.days} more days."
        return True, ""
    
    def check_join_delay(self, member: discord.Member) -> tuple[bool, str]:
        """Check if the user has been in the server long enough."""
        join_age = datetime.now() - member.joined_at
        if join_age.total_seconds() < MIN_JOIN_DELAY_SECONDS:
            remaining = MIN_JOIN_DELAY_SECONDS - int(join_age.total_seconds())
            return False, f"Please wait {remaining} more seconds before verifying."
        return True, ""
    
    def check_attempt_limits(self, user_id: str) -> tuple[bool, str]:
        """Check if the user has exceeded attempt limits."""
        user_id_str = str(user_id)
        
        if user_id_str not in self.verification_attempts:
            self.verification_attempts[user_id_str] = {
                'attempts': 0,
                'last_attempt': None,
                'cooldown_until': None
            }
        
        attempts_data = self.verification_attempts[user_id_str]
        
        # Check cooldown
        if attempts_data['cooldown_until']:
            if datetime.now() < attempts_data['cooldown_until']:
                remaining = int((attempts_data['cooldown_until'] - datetime.now()).total_seconds())
                return False, f"You must wait {remaining} more seconds before trying again."
        
        # Check attempt count
        if attempts_data['attempts'] >= MAX_VERIFICATION_ATTEMPTS:
            return False, f"You have exceeded the maximum number of verification attempts ({MAX_VERIFICATION_ATTEMPTS})."
        
        return True, ""
    
    def record_attempt(self, user_id: str, success: bool = False):
        """Record a verification attempt."""
        user_id_str = str(user_id)
        
        if user_id_str not in self.verification_attempts:
            self.verification_attempts[user_id_str] = {
                'attempts': 0,
                'last_attempt': None,
                'cooldown_until': None
            }
        
        attempts_data = self.verification_attempts[user_id_str]
        attempts_data['attempts'] += 1
        attempts_data['last_attempt'] = datetime.now().isoformat()
        
        if not success:
            # Set cooldown on failed attempt
            attempts_data['cooldown_until'] = datetime.now() + timedelta(seconds=ATTEMPT_COOLDOWN_SECONDS)
    
    def reset_attempts(self, user_id: str):
        """Reset verification attempts for a user."""
        user_id_str = str(user_id)
        if user_id_str in self.verification_attempts:
            del self.verification_attempts[user_id_str]
    
    def get_user_attempts(self, user_id: str) -> Dict:
        """Get attempt information for a user."""
        user_id_str = str(user_id)
        return self.verification_attempts.get(user_id_str, {
            'attempts': 0,
            'last_attempt': None,
            'cooldown_until': None
        })
    
    async def start_verification(self, member: discord.Member) -> tuple[bool, str]:
        """Run security checks before allowing verification."""
        user_id_str = str(member.id)
        
        # Check raid mode
        if self.storage.raid_mode:
            try:
                await member.send(f"The server is currently under protection. Please join the backup server: {BACKUP_INVITE}")
            except:
                pass
            return False, "The server is currently under protection mode."
        
        # Check if already verified
        if self.storage.is_verified(user_id_str):
            return False, "You are already verified."
        
        # Check if flagged
        if self.storage.is_flagged(user_id_str):
            return False, "You are flagged from verification."
        
        # Check account age
        age_ok, age_msg = self.check_account_age(member)
        if not age_ok:
            return False, age_msg
        
        # Check join delay
        join_ok, join_msg = self.check_join_delay(member)
        if not join_ok:
            return False, join_msg
        
        # Check attempt limits
        attempt_ok, attempt_msg = self.check_attempt_limits(user_id_str)
        if not attempt_ok:
            return False, attempt_msg
        
        return True, ""
    
    async def verify_answer(self, member: discord.Member, answer: str) -> tuple[bool, str]:
        """Verify a user's captcha answer."""
        user_id_str = str(member.id)
        
        # Check if pending verification exists
        if user_id_str not in self.pending_verifications:
            self.record_attempt(user_id_str, success=False)
            return False, "No pending verification found. Please click the button again."
        
        pending = self.pending_verifications[user_id_str]
        
        # Check expiration (10 minutes)
        created_at = datetime.fromisoformat(pending['created_at'])
        if datetime.now() - created_at > timedelta(minutes=10):
            del self.pending_verifications[user_id_str]
            self.record_attempt(user_id_str, success=False)
            return False, "Verification expired. Please click the button again."
        
        # Check answer
        if pending['answer'] != answer.strip():
            self.record_attempt(user_id_str, success=False)
            attempts_data = self.get_user_attempts(user_id_str)
            remaining = MAX_VERIFICATION_ATTEMPTS - attempts_data['attempts']
            
            if remaining <= 0:
                # Kick user for exceeding attempts
                try:
                    await member.kick(reason="Exceeded verification attempts")
                except:
                    pass
                return False, "You have exceeded the maximum number of attempts and have been kicked."
            
            return False, f"Wrong answer. You have {remaining} attempt(s) remaining."
        
        # Verification successful
        del self.pending_verifications[user_id_str]
        self.record_attempt(user_id_str, success=True)
        
        # Add to verified users
        self.storage.add_verified_user(user_id_str)
        
        return True, "Verification successful!"
    
    async def complete_verification(self, member: discord.Member, guild: discord.Guild) -> bool:
        """Complete the verification process by assigning roles."""
        try:
            # Get roles
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
            
            if not verified_role:
                print(f"Error: Verified role not found (ID: {VERIFIED_ROLE_ID})")
                return False
            
            # Remove Unverified role
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role)
            
            # Add Verified role
            if verified_role not in member.roles:
                await member.add_roles(verified_role)
            
            # Send backup invite
            try:
                await member.send(f"**Verification Complete!**\n\nWelcome to the server! Here is our backup server invite in case of emergencies: {BACKUP_INVITE}")
            except:
                pass
            
            return True
        except Exception as e:
            print(f"Error completing verification: {e}")
            return False
    
    def _get_unverified_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Get the Unverified role by ID."""
        return guild.get_role(UNVERIFIED_ROLE_ID)
    
    async def setup_channel_permissions(self, guild: discord.Guild):
        """Setup channel permissions for the verification system."""
        try:
            unverified_role = self._get_unverified_role(guild)
            verification_channel = guild.get_channel(VERIFICATION_CHANNEL_ID)
            verified_role = guild.get_role(VERIFIED_ROLE_ID)
            
            if not unverified_role or not verification_channel:
                print("Error: Missing required role or channel")
                return
            
            # Set up verification channel permissions
            # Unverified role can only see verification channel
            for channel in guild.channels:
                try:
                    if channel.id == VERIFICATION_CHANNEL_ID:
                        # Verification channel: Unverified can view and send
                        await channel.set_permissions(unverified_role, view_channel=True, send_messages=True, read_message_history=True)
                    else:
                        # Other channels: Unverified cannot view
                        await channel.set_permissions(unverified_role, view_channel=False)
                except Exception as e:
                    print(f"Error setting permissions for channel {channel.name}: {e}")
            
            print("Channel permissions configured successfully")
        except Exception as e:
            print(f"Error setting up channel permissions: {e}")

# ==============================================================================
# UI COMPONENTS
# ==============================================================================

class VerificationModal(Modal, title='Verification'):
    """Modal for answering the captcha question."""
    
    answer = TextInput(label='Your Answer', placeholder='Enter the answer', max_length=10)
    
    def __init__(self, verification_system: VerificationSystem, member: discord.Member, question: str):
        super().__init__()
        self.verification_system = verification_system
        self.member = member
        self.question = question
        # Update the title to show the question
        self.title = f'Verify: {question}'
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        answer = self.answer.value.strip()
        
        success, message = await self.verification_system.verify_answer(self.member, answer)
        
        if success:
            # Complete verification
            guild = interaction.guild
            if await self.verification_system.complete_verification(self.member, guild):
                await interaction.response.send_message("✅ Verification successful! You now have access to the server.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Error completing verification. Please contact staff.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)

class VerificationButtonView(View):
    """View with verification button."""
    
    def __init__(self, verification_system: VerificationSystem):
        super().__init__(timeout=None)
        self.verification_system = verification_system
    
    @discord.ui.button(label='Start Verification', style=discord.ButtonStyle.green, custom_id='verify_button')
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        """Handle verification button click."""
        member = interaction.user
        
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        
        # Run security checks
        can_verify, check_msg = await self.verification_system.start_verification(member)
        if not can_verify:
            await interaction.response.send_message(f"❌ {check_msg}", ephemeral=True)
            return
        
        # Generate a math question
        question, answer = self.verification_system.generate_math_question()
        user_id_str = str(member.id)
        self.verification_system.pending_verifications[user_id_str] = {
            'answer': answer,
            'created_at': datetime.now().isoformat()
        }
        
        # Show modal with the question
        modal = VerificationModal(self.verification_system, member, question)
        await interaction.response.send_modal(modal)

# ==============================================================================
# PULLBACK SYSTEM
# ==============================================================================

class PullbackSystem:
    """Handles emergency pullback functionality."""
    
    def __init__(self, storage: StorageManager, bot: commands.Bot):
        self.storage = storage
        self.bot = bot
    
    async def send_pullback_message(self, user_id: str):
        """Send pullback message to a single user."""
        try:
            user = await self.bot.fetch_user(int(user_id))
            await user.send(
                f"⚠️ **EMERGENCY PULLBACK**\n\n"
                f"The main server is currently unavailable or under attack. "
                f"Please join the backup server immediately: {BACKUP_INVITE}"
            )
            return True
        except Exception as e:
            print(f"Error sending pullback to user {user_id}: {e}")
            return False
    
    async def send_pullback_to_all(self):
        """Send pullback message to all verified users."""
        success_count = 0
        fail_count = 0
        
        for user_id in self.storage.verified_users:
            if await self.send_pullback_message(user_id):
                success_count += 1
            else:
                fail_count += 1
        
        return success_count, fail_count
    
    async def check_bot_removed(self, guild_id: int) -> bool:
        """Check if bot was removed from the main server."""
        try:
            guild = self.bot.get_guild(guild_id)
            return guild is None
        except:
            return True

# ==============================================================================
# MAIN BOT CLASS
# ==============================================================================

class FTSLBot(commands.Bot):
    """Main bot class combining all systems."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.storage = StorageManager()
        self.verification_system = None
        self.pullback_system = None
        self.main_guild_id = None
    
    async def setup_hook(self):
        """Set up the bot when ready."""
        # Initialize systems
        self.verification_system = VerificationSystem(self.storage, self)
        self.pullback_system = PullbackSystem(self.storage, self)
        
        # Sync commands
        await self.tree.sync()
        print("Slash commands synced")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        print(f"Bot logged in as {self.user.name} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} guild(s)")
        
        # Log startup information
        print(f"\n=== STARTUP LOG ===")
        print(f"Verified users: {self.storage.get_verified_count()}")
        print(f"Flagged users: {self.storage.get_flagged_count()}")
        print(f"Raid mode: {'ENABLED' if self.storage.raid_mode else 'DISABLED'}")
        print(f"===================\n")
        
        # Check if bot was removed from main server
        if self.main_guild_id:
            if await self.pullback_system.check_bot_removed(self.main_guild_id):
                print("Bot was removed from main server. Sending pullback messages...")
                success, fail = await self.pullback_system.send_pullback_to_all()
                print(f"Pullback sent: {success} successful, {fail} failed")
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild."""
        print(f"Joined guild: {guild.name} (ID: {guild.id})")
        
        # Set main guild if not set
        if not self.main_guild_id:
            self.main_guild_id = guild.id
        
        # Setup channel permissions
        await self.verification_system.setup_channel_permissions(guild)
    
    async def on_member_join(self, member: discord.Member):
        """Called when a member joins the guild."""
        print(f"Member joined: {member.name} (ID: {member.id})")
        
        # Set main guild if not set
        if not self.main_guild_id:
            self.main_guild_id = member.guild.id
        
        # Check raid mode
        if self.storage.raid_mode:
            try:
                await member.send(f"The server is currently under protection. Please join the backup server: {BACKUP_INVITE}")
            except:
                pass
            return
        
        # Note: Unverified role is auto-assigned by Discord, no need to add it here
        
        # Send welcome message pointing to verification channel
        verification_channel = member.guild.get_channel(VERIFICATION_CHANNEL_ID)
        if verification_channel:
            try:
                await verification_channel.send(
                    f"Welcome {member.mention}! Please click the **Start Verification** button below to verify."
                )
            except Exception as e:
                print(f"Error sending welcome message: {e}")
    
    async def on_message(self, message: discord.Message):
        """Called when a message is sent."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Process commands
        await self.process_commands(message)

# ==============================================================================
# SLASH COMMANDS
# ==============================================================================

def setup_commands(bot: FTSLBot):
    """Set up all slash commands."""
    
    @bot.tree.command(name="verify", description="Verification management commands")
    @app_commands.describe(action="The action to perform", user="The target user")
    @app_commands.choices(action=[
        app_commands.Choice(name="reset", value="reset"),
        app_commands.Choice(name="status", value="status")
    ])
    async def verify_command(interaction: discord.Interaction, action: str, user: discord.Member = None):
        """Handle verification commands."""
        if not user:
            user = interaction.user
        
        if action == "reset":
            # Check if user has admin role
            admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
            if not admin_role or admin_role not in interaction.user.roles:
                await interaction.response.send_message("❌ You need the Admin role to use this command.", ephemeral=True)
                return
            
            user_id_str = str(user.id)
            bot.storage.remove_verified_user(user_id_str)
            bot.verification_system.reset_attempts(user_id_str)
            
            await interaction.response.send_message(f"✅ Verification state reset for {user.mention}.", ephemeral=True)
        
        elif action == "status":
            user_id_str = str(user.id)
            is_verified = bot.storage.is_verified(user_id_str)
            is_flagged = bot.storage.is_flagged(user_id_str)
            attempts = bot.verification_system.get_user_attempts(user_id_str)
            
            account_age = datetime.now() - user.created_at
            join_age = datetime.now() - user.joined_at if user.joined_at else None
            
            embed = discord.Embed(title=f"Verification Status: {user.name}", color=discord.Color.blue())
            embed.add_field(name="Verified", value="✅ Yes" if is_verified else "❌ No", inline=True)
            embed.add_field(name="Flagged", value="⚠️ Yes" if is_flagged else "✅ No", inline=True)
            embed.add_field(name="Account Age", value=f"{account_age.days} days", inline=True)
            if join_age:
                embed.add_field(name="Join Age", value=f"{join_age.days} days", inline=True)
            embed.add_field(name="Attempts Used", value=str(attempts['attempts']), inline=True)
            embed.add_field(name="Max Attempts", value=str(MAX_VERIFICATION_ATTEMPTS), inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="pullback", description="Send emergency pullback message to all verified users")
    async def pullback_command(interaction: discord.Interaction):
        """Handle pullback command."""
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if not admin_role or admin_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You need the Admin role to use this command.", ephemeral=True)
            return
        
        await interaction.response.send_message("⚠️ Sending pullback messages to all verified users...", ephemeral=True)
        
        success, fail = await bot.pullback_system.send_pullback_to_all()
        
        followup = f"✅ Pullback complete!\n\nSuccessful: {success}\nFailed: {fail}"
        await interaction.followup.send(followup, ephemeral=True)
    
    @bot.tree.command(name="forceverify", description="Force verify a user (admin only)")
    @app_commands.describe(user="The user to force verify")
    async def forceverify_command(interaction: discord.Interaction, user: discord.Member):
        """Handle force verify command."""
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if not admin_role or admin_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You need the Admin role to use this command.", ephemeral=True)
            return
        
        user_id_str = str(user.id)
        
        # Check if already verified
        if bot.storage.is_verified(user_id_str):
            await interaction.response.send_message(f"❌ {user.mention} is already verified.", ephemeral=True)
            return
        
        # Add to verified users
        bot.storage.add_verified_user(user_id_str)
        
        # Complete verification
        if await bot.verification_system.complete_verification(user, interaction.guild):
            await interaction.response.send_message(f"✅ Force verified {user.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error force verifying {user.mention}.", ephemeral=True)
    
    @bot.tree.command(name="setup", description="Setup verification system (admin only)")
    async def setup_command(interaction: discord.Interaction):
        """Handle setup command."""
        admin_role = interaction.guild.get_role(ADMIN_ROLE_ID)
        if not admin_role or admin_role not in interaction.user.roles:
            await interaction.response.send_message("❌ You need the Admin role to use this command.", ephemeral=True)
            return
        
        await interaction.response.send_message("⚙️ Setting up verification system...", ephemeral=True)
        
        # Setup channel permissions
        await bot.verification_system.setup_channel_permissions(interaction.guild)
        
        # Send verification button message
        verification_channel = interaction.guild.get_channel(VERIFICATION_CHANNEL_ID)
        if verification_channel:
            view = VerificationButtonView(bot.verification_system)
            await verification_channel.send("Click the button below to start verification:", view=view)
        
        await interaction.followup.send("✅ Verification system setup complete!", ephemeral=True)

# ==============================================================================
# BOT ENTRY POINT
# ==============================================================================

def main():
    """Main entry point for the bot."""
    # Get bot token from environment variable
    token = os.getenv('DISCORD_TOKEN')
    
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set!")
        print("Please set your bot token as an environment variable.")
        return
    
    # Start uptime server in background thread
    uptime_thread = threading.Thread(target=start_uptime_server, daemon=True)
    uptime_thread.start()
    
    # Create and run bot
    bot = FTSLBot()
    setup_commands(bot)
    
    try:
        bot.run(token)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == "__main__":
    main()

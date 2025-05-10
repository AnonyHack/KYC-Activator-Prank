import os
import logging
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import (
    Update, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaDocument,
    Poll
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from telegram.error import BadRequest
from aiohttp import web
from typing import Union, List, Optional

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('kyc_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration from environment variables
CONFIG = {
    'token': os.getenv('TELEGRAM_BOT_TOKEN'),
    'admin_ids': [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id],
}

# Force Join Configuration
CHANNEL_USERNAMES = os.getenv("CHANNEL_USERNAMES", "@megahubbots,@Freenethubz,@Freenethubchannel").split(",")
CHANNEL_LINKS = os.getenv("CHANNEL_LINKS", "https://t.me/megahubbots,https://t.me/Freenethubz,https://t.me/Freenethubchannel").split(",")

# MongoDB connection
client = MongoClient(os.getenv('MONGODB_URI'))
db = client[os.getenv('DATABASE_NAME', '')]

# Collections
users_collection = db['users']
leaderboard_collection = db['leaderboard']
admins_collection = db['admins']

# Initialize database with admin user if empty
if admins_collection.count_documents({}) == 0 and os.getenv('ADMIN_IDS'):
    for admin_id in CONFIG['admin_ids']:
        admins_collection.update_one(
            {'user_id': admin_id},
            {'$set': {'user_id': admin_id}},
            upsert=True
        )

# Webhook configuration
PORT = int(os.getenv('PORT', 10000))
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '') + WEBHOOK_PATH

# Welcome message
WELCOME_MESSAGE = """
🌟 *Welcome to the KYC UDP Activator Bot!* 🌟

🎭 This is a fun prank tool that "activates" KYC on your phone number. 

✨ *Quick Commands:*
/activatekyc - Start the KYC activation
/howtouse - Detailed instructions
/leaderboard - Top activations
/contactus - Contact support

⚠️ *Note:* This is just for fun! No real KYC is performed.
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# Enhanced animations
PROGRESS_FRAMES = [
    "🟩⬜⬜⬜⬜ [13%] Scanning device...",
    "🟩🟩⬜⬜⬜ [27%] Checking network...",
    "🟩🟩🟩⬜⬜ [41%] Verifying identity...",
    "🟩🟩🟩🟩⬜ [63%] Connecting to server...",
    "🟩🟩🟩🟩🟩 [100%] Activation complete!",
]

SIGNAL_FRAMES = [
    "📡 [▫▫▫▫▫] Searching for signal...",
    "📡 [■▫▫▫▫] Connecting to tower...",
    "📡 [■■▫▫▫] Establishing link...",
    "📡 [■■■▫▫] Authenticating...",
    "📡 [■■■■▫] Finalizing...",
    "📡 [■■■■■] ✅ Signal locked!",
]

# Enhanced KYC activation responses
KYC_RESPONSES = [
    "✨ *KYC Activated Successfully!* ✨\n\n📱 Phone: {phone}\n🔒 Status: VIP Verified\n🎉 Enjoy unlimited access!",
    "🚀 *KYC Upgrade Complete!*\n\n📱 Phone: {phone}\n💎 Tier: Diamond Level\n🔥 Premium features unlocked!",
    "✅ *Verification Successful!*\n\n📱 Phone: {phone}\n🛡️ Protection: Enabled\n🌐 Full access granted!",
    "💳 *KYC Activated!*\n\n📱 Phone: {phone}\n⭐ Status: Trusted User\n🔓 Restrictions removed!",
]

# Database Management Functions
def add_user(user):
    """Add user to database if not exists"""
    users_collection.update_one(
        {'user_id': user.id},
        {'$set': {
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'join_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }},
        upsert=True
    )

def is_admin(user_id):
    """Check if user is admin"""
    return admins_collection.count_documents({'user_id': user_id}) > 0 or user_id in CONFIG['admin_ids']

def add_kyc_activation(user_id, username, phone_number):
    """Add KYC activation to leaderboard"""
    leaderboard_collection.update_one(
        {'user_id': user_id},
        {'$set': {
            'username': username,
            'phone_number': phone_number,
            'activation_date': datetime.now()
        }},
        upsert=True
    )

def get_leaderboard():
    """Get top 10 activations from leaderboard"""
    return list(leaderboard_collection.find().sort('activation_date', -1).limit(10))

def get_user_count():
    """Get total number of users"""
    return users_collection.count_documents({})

def get_all_users():
    """Get all user IDs for broadcasting"""
    return [user['user_id'] for user in users_collection.find({}, {'user_id': 1})]

async def is_member_of_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is a member of all required channels."""
    for channel in CHANNEL_USERNAMES:
        try:
            chat_member = await context.bot.get_chat_member(channel, user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False
        except BadRequest:
            return False
    return True

async def send_force_join_message(update: Update):
    """Send force join message with buttons for all channels."""
    buttons = [[InlineKeyboardButton(f"Join {CHANNEL_USERNAMES[i]}", url=CHANNEL_LINKS[i])] 
               for i in range(len(CHANNEL_USERNAMES))]
    buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="verify_join")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "🔒 *Access Restricted* 🔒\n\n"
        "To use this bot, you must join our official channels:\n\n"
        "👉 Tap each button below to join\n"
        "👉 Then click 'I've Joined' to verify"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle join verification callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if await is_member_of_channels(user_id, context):
        await query.answer("✅ Verification successful! You can now use the bot.")
        await query.message.edit_text(
            "✅ *Verification Complete!*\n\n"
            "You've successfully joined all required channels.\n"
            "Use /start to begin!",
            parse_mode="Markdown"
        )
    else:
        await query.answer("❌ You haven't joined all channels yet!", show_alert=True)

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user = update.effective_user
    add_user(user)
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    keyboard = [
        [InlineKeyboardButton("✨ Activate KYC", callback_data="activate_kyc")],
        [InlineKeyboardButton("📊 Leaderboard", callback_data="show_leaderboard"),
         InlineKeyboardButton("ℹ️ How To Use", callback_data="how_to_use")]
    ]
    
    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def activate_kyc(update: Union[Update, CallbackQueryHandler], context: ContextTypes.DEFAULT_TYPE):
    """Handle KYC activation."""
    user = update.effective_user
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    await context.bot.send_message(
        chat_id=user.id,
        text="📱 *KYC Activation Started*\n\n"
             "Please send your phone number with country code:\n"
             "Example: `+256751722034`\n\n"
             "🔒 We don't store or use your real number",
        parse_mode="Markdown"
    )
    context.user_data["awaiting_phone_number"] = True

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's phone number input."""
    if context.user_data.get("awaiting_phone_number"):
        phone_number = update.message.text
        user = update.effective_user
        
        context.user_data["awaiting_phone_number"] = False
        add_kyc_activation(user.id, user.username, phone_number)

        # Enhanced activation animation
        progress_msg = await update.message.reply_text("🔄 *Starting KYC Activation...*", parse_mode="Markdown")
        
        for frame in PROGRESS_FRAMES:
            await asyncio.sleep(0.7)
            try:
                await progress_msg.edit_text(frame)
            except Exception as e:
                logger.error(f"Error updating progress: {e}")

        for frame in SIGNAL_FRAMES:
            await asyncio.sleep(0.7)
            try:
                await progress_msg.edit_text(frame)
            except Exception as e:
                logger.error(f"Error updating signal: {e}")

        # Send final response
        response = random.choice(KYC_RESPONSES).format(phone=phone_number)
        await progress_msg.edit_text(response, parse_mode="Markdown")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced leaderboard command."""
    leaderboard_data = get_leaderboard()
    
    if not leaderboard_data:
        await update.message.reply_text("🏆 *Leaderboard is empty!*\nBe the first with /activatekyc", parse_mode="Markdown")
        return

    leaderboard_text = "🏆 *KYC Activation Leaderboard* 🏆\n\n"
    leaderboard_text += "Rank | User       | Phone\n"
    leaderboard_text += "-----|------------|-------\n"
    
    for idx, entry in enumerate(leaderboard_data[:10], 1):
        username = entry.get('username', 'Anonymous').replace('|', '\\|')[:10]
        phone = entry.get('phone_number', 'N/A')[:6] + '***'
        leaderboard_text += f"{idx:<4} | {username:<10} | {phone}\n"
    
    leaderboard_text += f"\nTotal Activations: {len(leaderboard_data)}"

    await update.message.reply_text(leaderboard_text, parse_mode="MarkdownV2")

async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced reset leaderboard command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*\nAdmin privileges required.", parse_mode="Markdown")
        return

    leaderboard_collection.delete_many({})
    await update.message.reply_text(
        "♻️ *Leaderboard Reset*\n\n"
        "All activation records have been cleared.\n"
        "New activations will start fresh!",
        parse_mode="Markdown"
    )

async def how_to_use(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced how-to-use command."""
    instructions = """
📘 *KYC Activator Bot Guide* 📘
━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ *Getting Started*
- Use /start to begin
- Join required channels if prompted

2️⃣ *Activation Process*
- Use /activatekyc
- Enter your phone number
- Watch the magic happen!

3️⃣ *Features*
- Fun KYC activation simulation
- Leaderboard tracking
- Regular updates

4️⃣ *Important Notes*
- This is just for entertainment
- No real KYC is performed
- No personal data is stored

🎉 Enjoy the experience!
━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(instructions, parse_mode="Markdown")

async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced contact us command."""
    keyboard = [
        [InlineKeyboardButton("📩 Message Admin", url="https://t.me/Silando")],
        [InlineKeyboardButton("📢 Announcements", url="https://t.me/megahubbots")],
        [InlineKeyboardButton("💬 Support Channel", url="https://t.me/Freenethubz")]
    ]
    
    contact_text = """
📞 *Contact Information* 📞

🔹 *Email:* freenethubbusiness@gmail.com
🔹 *Business Hours:* 9AM - 5PM (EAT)

📌 *For:*
- Business inquiries
- Bug reports
- Feature requests

🚫 *Please don't spam!*
━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(
        contact_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced stats command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*", parse_mode="Markdown")
        return

    user_count = get_user_count()
    activated_count = leaderboard_collection.count_documents({})
    
    stats_text = """
📈 *Bot Statistics Dashboard* 📈
━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 *Users:*
├─ Total: {}
└─ Active Today: {}

✅ *Activations:*
├─ Total: {}
└─ Last 24h: {}

⚙️ *System:*
├─ Uptime: 99.9%
└─ Status: Operational
━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".format(
        user_count,
        users_collection.count_documents({"join_date": {"$gte": datetime.now().strftime('%Y-%m-%d')}}),
        activated_count,
        leaderboard_collection.count_documents({"activation_date": {"$gte": datetime.now().replace(hour=0, minute=0, second=0)}})
    )

    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast command to send a message to all users."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied*", parse_mode="Markdown")
        return

    if "broadcasting" not in context.user_data:
        context.user_data["broadcasting"] = True
        await update.message.reply_text(
            "📢 *Broadcast Mode Enabled*\n\n"
            "Please send the message you want to broadcast to all users.",
            parse_mode="Markdown"
        )
        return

    # Broadcast the user's message
    user_ids = get_all_users()
    success = 0
    failures = 0

    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=update.message.text,
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.warning(f"Failed to send to {user_id}: {e}")
            failures += 1

    await update.message.reply_text(
        f"📊 *Broadcast Results*\n\n"
        f"✅ Success: {success}\n"
        f"❌ Failures: {failures}\n"
        f"📩 Total Sent: {success + failures}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

    # Reset broadcasting state
    context.user_data["broadcasting"] = False

# Message handler for broadcasting
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the message to be broadcasted."""
    if context.user_data.get("broadcasting"):
        await broadcast_message(update, context)

# Main application setup
def main():
    """Run the bot."""
    application = Application.builder().token(CONFIG['token']).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("activatekyc", activate_kyc))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("howtouse", how_to_use))
    application.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))
    application.add_handler(CommandHandler("contactus", contact_us))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(CallbackQueryHandler(activate_kyc, pattern="^activate_kyc$"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message))  # Handle broadcast messages
    
    # Start the bot
    if os.getenv('RENDER'):
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=WEBHOOK_URL
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()

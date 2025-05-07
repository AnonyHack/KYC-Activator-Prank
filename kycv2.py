import os
import logging
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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
👋 Welcome to the *KYC UDP Activator Bot*! 🤖

This bot is a fun prank tool that "activates" KYC on your phone number. 😜

🔹 To get started, use the /activatekyc command.
🔹 For help, use the /howtouse command.
🔹 Check the leaderboard with /leaderboard.

*Note*: This is just for fun! 😄
"""

# Progress bar animation
PROGRESS_FRAMES = [
    "[■□□□□□□□□□□□□□] 13%",
    "[■■□□□□□□□□□□□□] 27%",
    "[■■■□□□□□□□□□□□] 34%",
    "[■■■■□□□□□□□□□□] 41%",
    "[■■■■■□□□□□□□□□] 49%",
    "[■■■■■■□□□□□□□□] 56%",
    "[■■■■■■■□□□□□□□] 63%",
    "[■■■■■■■■□□□□□□] 71%",
    "[■■■■■■■■■□□□□□] 78%",
    "[■■■■■■■■■■□□□□] 85%",
    "[■■■■■■■■■■■□□□] 91%",
    "[■■■■■■■■■■■■□□] 96%",
    "[■■■■■■■■■■■■■■] 100%",
]

# Signal verification animation
SIGNAL_FRAMES = [
    "📡 [▫▫▫▫▫] Connecting...",
    "📡 [■▫▫▫▫] Connecting...",
    "📡 [■■▫▫▫] Connecting...",
    "📡 [■■■▫▫] Connecting...",
    "📡 [■■■■▫] Almost Done...",
    "📡 [■■■■■] ✅ Verified!",
]

# Random KYC activation responses
KYC_RESPONSES = [
    "✅ KYC Activated Successfully! 🎉",
    "🚀 Your KYC has been upgraded to VIP status! 🔥",
    "💳 KYC Verified! Enjoy Free Unlimited Internet! 🌐",
    "✅ KYC Activation Completed. You're now verified!",
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
            'activation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "🚨 You must join all required channels to use this bot.\n\n"
        "After joining, type /start again.",
        reply_markup=reply_markup
    )

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user = update.effective_user
    add_user(user)
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

async def activate_kyc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /activatekyc command."""
    user = update.effective_user
    
    if not await is_member_of_channels(user.id, context):
        await send_force_join_message(update)
        return

    await update.message.reply_text("📱 Please send your phone number with the country code (e.g., +256751722034):")
    context.user_data["awaiting_phone_number"] = True

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's phone number input."""
    if context.user_data.get("awaiting_phone_number"):
        phone_number = update.message.text
        user = update.effective_user
        
        # Reset the state immediately
        context.user_data["awaiting_phone_number"] = False
        
        # Save to leaderboard
        add_kyc_activation(user.id, user.username, phone_number)

        # Simulate activation process
        progress_msg = await update.message.reply_text("🔄 Activating KYC...")
        for frame in PROGRESS_FRAMES:
            await asyncio.sleep(0.5)
            try:
                await progress_msg.edit_text(frame)
            except Exception as e:
                logger.error(f"Error updating progress message: {str(e)}")

        # Send final verification message
        await progress_msg.edit_text(
            f"{random.choice(KYC_RESPONSES)}\n\n📱 *Phone Number*: {phone_number}", 
            parse_mode="Markdown"
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /leaderboard command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    leaderboard_data = get_leaderboard()
    leaderboard_text = "🏆 *Leaderboard* 🏆\n\n"
    
    for entry in leaderboard_data:
        leaderboard_text += f"👤 {entry.get('username', 'N/A')} - 📱 {entry.get('phone_number', 'N/A')}\n"

    if not leaderboard_text.strip():
        leaderboard_text = "No activations yet. Be the first! 🥇"

    await update.message.reply_text(leaderboard_text, parse_mode="Markdown")

async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /resetleaderboard command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    leaderboard_collection.delete_many({})
    await update.message.reply_text("🔄 Leaderboard has been reset!")

async def how_to_use(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /howtouse command."""
    instructions = """
    📝 *How to Use the KYC UDP Activator Bot* 📝

    1️⃣ Start by clicking /start to begin.
    2️⃣ Ensure you're a member of the required channels.
    3️⃣ Use /activatekyc to start the activation process.
    4️⃣ Follow the instructions and provide your phone number.
    5️⃣ Enjoy the fun KYC activation response! 🎉
    """
    await update.message.reply_text(instructions, parse_mode="Markdown")

async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /contactus command."""
    contact_text = (
        "📞 ★彡( 𝕮𝖔𝖓𝖙𝖆𝖈𝖙 𝖀𝖘 )彡★ 📞\n\n"
        "📧 Eᴍᴀɪʟ: `freenethubbusiness@gmail.com`\n\n"
        "Fᴏʀ Aɴʏ Iꜱꜱᴜᴇꜱ, Bᴜꜱɪɴᴇꜱꜱ Dᴇᴀʟꜱ Oʀ IɴQᴜɪʀɪᴇꜱ, Pʟᴇᴀꜱᴇ Rᴇᴀᴄʜ Oᴜᴛ Tᴏ Uꜱ \n\n"
        "❗ *ONLY FOR BUSINESS AND HELP, DON'T SPAM!*"
    )
    
    keyboard = [[InlineKeyboardButton("📩 Mᴇꜱꜱᴀɢᴇ Aᴅᴍɪɴ", url="https://t.me/Silando")]]
    
    await update.message.reply_text(
        contact_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /stats command."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    user_count = get_user_count()
    activated_count = leaderboard_collection.count_documents({})
    text = f"📊 *Bᴏᴛ Sᴛᴀᴛɪꜱᴛɪᴄꜱ*\n\n"
    text += f"👥 Tᴏᴛᴀʟ Uꜱᴇʀꜱ: {user_count}\n"
    text += f"✅ Tᴏᴛᴀʟ Aᴄᴛɪᴠᴀᴛɪᴏɴꜱ: {activated_count}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to all users."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    broadcast_text = update.message.text.replace("/broadcast", "").strip()
    if not broadcast_text:
        await update.message.reply_text(
            "⚠️ Please provide a message to broadcast. Example:\n`/broadcast Hello users!`", 
            parse_mode="Markdown"
        )
        return

    user_ids = get_all_users()
    success = 0
    failures = 0

    await update.message.reply_text(f"📢 Starting broadcast to {len(user_ids)} users...")

    for user_id in user_ids:
        try:
            await context.bot.send_message(
                user_id,
                f"📢 *Announcement from admin*:\n\n{broadcast_text}",
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {str(e)}")
            failures += 1

    await update.message.reply_text(f"📢 Broadcast completed!\n✅ Success: {success}\n❌ Failures: {failures}")

# Health check endpoint
async def health_check(request):
    """Health check endpoint to verify the service is running."""
    return web.Response(text="OK")

def main():
    """Run the bot."""
    application = Application.builder().token(CONFIG['token']).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("activatekyc", activate_kyc))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("howtouse", how_to_use))
    application.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))
    application.add_handler(CommandHandler("contactus", contact_us))  # Updated contactus command
    application.add_handler(CommandHandler("stats", stats))  # Updated stats command
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    
    # Message handler for phone number
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))
    
    # Start the bot with webhook if running on Render
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

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

# Load environment variables
load_dotenv()

# Enable logging for debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(",") if admin_id]

# Force Join Configuration
CHANNEL_USERNAMES = os.getenv("CHANNEL_USERNAMES", "@megahubbots", "@Freenethubz", "@Freenethubchannel").split(",")
CHANNEL_LINKS = os.getenv("CHANNEL_LINKS", "https://t.me/megahubbots", "https://t.me/Freenethubz", "https://t.me/Freenethubchannel").split(",")

# MongoDB connection
client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("DATABASE_NAME", "")]

# Collections
users_collection = db["users"]
leaderboard_collection = db["leaderboard"]

# Webhook configuration
PORT = int(os.getenv("PORT", 10000))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "") + WEBHOOK_PATH

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
    "✅ KYC Activation Completed. You’re now verified!",
]

# Function to check if user is subscribed to all required channels
async def is_member_of_channels(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is a member of all required channels."""
    for channel in CHANNEL_USERNAMES:
        try:
            chat_member = await context.bot.get_chat_member(channel, user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                return False  # User is not subscribed
        except BadRequest:
            return False  # Bot is not an admin or the channel does not exist
    return True  # User is subscribed to all channels

# Function to send force join message with buttons
async def send_force_join_message(update: Update):
    """Send force join message with buttons for all channels."""
    buttons = [[InlineKeyboardButton(f"Join {CHANNEL_USERNAMES[i]}", url=CHANNEL_LINKS[i])] for i in range(len(CHANNEL_USERNAMES))]
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "🚨 You must join all required channels to use this bot.\n\n"
        "After joining, type /start again.",
        reply_markup=reply_markup
    )

# Function to check if a user is an admin
def is_admin(user_id: int) -> bool:
    """Check if the user is an admin."""
    return user_id in ADMIN_IDS

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user_id = update.message.from_user.id
    user = update.message.from_user

    # Check if user is subscribed to all channels
    if not await is_member_of_channels(user_id, context):
        await send_force_join_message(update)
        return

    # Add user to the database
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "join_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }},
        upsert=True,
    )

    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")

# Command: /activatekyc
async def activate_kyc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /activatekyc command."""
    user_id = update.message.from_user.id

    # Check if user is subscribed to all channels
    if not await is_member_of_channels(user_id, context):
        await send_force_join_message(update)
        return

    # Request phone number
    await update.message.reply_text("📱 Please send your phone number with the country code (e.g., +256751722034):")
    context.user_data["awaiting_phone_number"] = True

# Handle phone number input
async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user's phone number input."""
    if context.user_data.get("awaiting_phone_number"):
        phone_number = update.message.text
        user = update.message.from_user

        # Save user data to the leaderboard
        leaderboard_collection.update_one(
            {"user_id": user.id},
            {"$set": {
                "username": user.username,
                "phone_number": phone_number,
                "activation_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }},
            upsert=True,
        )

        # Reset the state immediately to avoid repeating the message
        context.user_data["awaiting_phone_number"] = False

        # Simulate activation process
        progress_msg = await update.message.reply_text("🔄 Activating KYC...")
        for frame in PROGRESS_FRAMES:
            await asyncio.sleep(0.5)
            await progress_msg.edit_text(frame)

        # Send final verification message
        await progress_msg.edit_text(f"{random.choice(KYC_RESPONSES)}\n\n📱 *Phone Number*: {phone_number}", parse_mode="Markdown")

# Command: /leaderboard
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /leaderboard command."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    leaderboard = leaderboard_collection.find().sort("activation_date", -1).limit(10)
    leaderboard_text = "🏆 *Leaderboard* 🏆\n\n"
    for entry in leaderboard:
        leaderboard_text += f"👤 {entry['username']} - 📱 {entry['phone_number']}\n"

    if not leaderboard_text.strip():
        leaderboard_text = "No activations yet. Be the first! 🥇"

    await update.message.reply_text(leaderboard_text, parse_mode="Markdown")

# Command: /resetleaderboard (Admin only)
async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /resetleaderboard command."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Reset leaderboard data
    leaderboard_collection.delete_many({})
    await update.message.reply_text("🔄 Leaderboard has been reset!")

# Add all handlers to the application
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("activatekyc", activate_kyc))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))

    # Message Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))

    # Start the bot with webhook if running on Render
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL,
    )

if __name__ == "__main__":
    main()
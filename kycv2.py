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
    RequestHandler,  # Import RequestHandler for webhook handling
)
from telegram.error import BadRequest
from aiohttp import web  # Add this import for the health check endpoint

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
CHANNEL_USERNAMES = os.getenv("CHANNEL_USERNAMES", "@megahubbots,@Freenethubz,@Freenethubchannel").split(",")
CHANNEL_LINKS = os.getenv("CHANNEL_LINKS", "https://t.me/megahubbots,https://t.me/Freenethubz,https://t.me/Freenethubchannel").split(",")

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

# Command: /howtouse
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

# Command: /contactus
async def contact_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /contactus command."""
    contact_info = """
    📞 *Contact Us*

    For inquiries or support, please reach out to:
    - Email: Freenethubbusiness@gmail.com
    - Telegram: @Silando
    """
    await update.message.reply_text(contact_info, parse_mode="Markdown")

# Command: /stats (Admin only)
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /stats command."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    user_count = users_collection.count_documents({})
    await update.message.reply_text(f"📊 Total unique users: {user_count}")

# Command: /banuser (Admin only)
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /banuser command."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please specify the user ID to ban.")
        return

    user_id_to_ban = int(context.args[0])
    try:
        users_collection.delete_one({"user_id": user_id_to_ban})
        await update.message.reply_text(f"✅ User {user_id_to_ban} has been banned.")
    except Exception as e:
        logger.error(f"Error banning user: {str(e)}")
        await update.message.reply_text("⚠️ Unable to ban the user. Please check the user ID.")

# Command: /unbanuser (Admin only)
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /unbanuser command."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Please specify the user ID to unban.")
        return

    user_id_to_unban = int(context.args[0])
    try:
        users_collection.update_one(
            {"user_id": user_id_to_unban},
            {"$set": {"banned": False}},
            upsert=True
        )
        await update.message.reply_text(f"✅ User {user_id_to_unban} has been unbanned.")
    except Exception as e:
        logger.error(f"Error unbanning user: {str(e)}")
        await update.message.reply_text("⚠️ Unable to unban the user. Please check the user ID.")

# Command: /broadcast (Admin only)
async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast a message to all users (admin only)."""
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("⚠️ You are not authorized to use this command.")
        return

    # Get the broadcast message
    broadcast_text = update.message.text.replace("/broadcast", "").strip()
    if not broadcast_text:
        await update.message.reply_text("⚠️ Please provide a message to broadcast. Example:\n`/broadcast Hello users!`", parse_mode="Markdown")
        return

    # Get all user IDs from the database
    user_ids = [user["user_id"] for user in users_collection.find({}, {"user_id": 1})]
    success = 0
    failures = 0

    await update.message.reply_text(f"📢 Starting broadcast to {len(user_ids)} users...")

    # Send the broadcast message to all users
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_text)
            success += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user_id}: {str(e)}")
            failures += 1

    # Send a summary of the broadcast
    await update.message.reply_text(f"📢 Broadcast completed!\n✅ Success: {success}\n❌ Failures: {failures}")

# Health check endpoint
async def health_check(request):
    """Health check endpoint to verify the service is running."""
    return web.Response(text="OK")

# Add handlers to the application
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("activatekyc", activate_kyc))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("howtouse", how_to_use))
    application.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))
    application.add_handler(CommandHandler("banuser", ban_user))
    application.add_handler(CommandHandler("unbanuser", unban_user))
    application.add_handler(CommandHandler("contactus", contact_us))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast_message))

    # Message Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number))

    # Webhook and health check
    app = web.Application()
    app.router.add_get("/health", health_check)  # Add health check route
    app.router.add_post(WEBHOOK_PATH, application.create_webhook_handler())  # Use create_webhook_handler()

    # Start the web server
    web.run_app(app, port=PORT)

if __name__ == "__main__":
    main()

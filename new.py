import os
import random
import time
from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from threading import Timer

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["anonymous_chat_bot"]
waiting_users_collection = db["waiting_users"]
active_chats_collection = db["active_chats"]
reports_collection = db["reports"]

# Generate random nickname
def generate_random_name():
    return f"Stranger{random.randint(1000, 9999)}"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Anonymous Chat Bot!\n"
        "Use /next to find a partner.\n"
        "Use /stop to end the chat.\n"
        "Use /report to report issues.\n"
        "Use /help for full instructions."
    )

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 Commands:\n"
        "/start - Start the bot\n"
        "/next - Find a new partner\n"
        "/stop - Stop chatting\n"
        "/report <reason> - Report bad behavior\n"
        "/help - Show this help message"
    )

# /next command
async def next_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id

    if active_chats_collection.find_one({"user_id": user_id}):
        await update.message.reply_text("❌ You are already chatting! Use /stop first.")
        return

    waiting_user = waiting_users_collection.find_one()

    if waiting_user:
        partner_id = waiting_user['user_id']
        random_name = generate_random_name()

        # Connect users
        active_chats_collection.insert_many([
            {"user_id": user_id, "partner_id": partner_id, "nickname": random_name, "start_time": time.time()},
            {"user_id": partner_id, "partner_id": user_id, "nickname": random_name, "start_time": time.time()}
        ])

        waiting_users_collection.delete_one({"user_id": partner_id})

        await context.bot.send_message(chat_id=user_id, text=f"✅ Connected! You are now chatting with {random_name}.")
        await context.bot.send_message(chat_id=partner_id, text=f"✅ Connected! You are now chatting with {random_name}.")

    else:
        waiting_users_collection.insert_one({"user_id": user_id})
        await update.message.reply_text("⏳ Waiting for a partner...")

# /stop command
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    active_chat = active_chats_collection.find_one({"user_id": user_id})

    if active_chat:
        partner_id = active_chat['partner_id']

        await context.bot.send_message(chat_id=partner_id, text="⚠️ Your partner has left the chat.")
        active_chats_collection.delete_many({"user_id": {"$in": [user_id, partner_id]}})
        await update.message.reply_text("✅ You left the chat.")
    else:
        waiting_users_collection.delete_one({"user_id": user_id})
        await update.message.reply_text("❌ You are not chatting with anyone.")

# /report command
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text

    report_message = text.split("/report", 1)[1].strip() if len(text.split("/report", 1)) > 1 else "No reason given."

    reports_collection.insert_one({
        "user_id": user_id,
        "report": report_message,
        "timestamp": time.time()
    })

    await update.message.reply_text("✅ Report received. Thank you for helping us keep the community safe!")

# Message relay between users
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text

    active_chat = active_chats_collection.find_one({"user_id": user_id})

    if active_chat:
        partner_id = active_chat['partner_id']

        # Typing simulation
        await context.bot.send_chat_action(chat_id=partner_id, action="typing")

        # Forward message
        await context.bot.send_message(chat_id=partner_id, text=text)
    else:
        await update.message.reply_text("❗ You are not chatting with anyone. Use /next.")

# Unknown commands
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Unknown command.")

# Main bot function
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("next", next_partner))
    app.add_handler(CommandHandler("stop", stop_chat))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), relay_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()

if __name__ == "__main__":
    main()
    
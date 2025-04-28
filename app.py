import os
import random
import time
import asyncio
from dotenv import load_dotenv
from pymongo import MongoClient
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["anonymous_chat_bot"]
waiting_users_collection = db["waiting_users"]
active_chats_collection = db["active_chats"]
reports_collection = db["reports"]

# Generate random nickname
def generate_random_name():
    return f"Stranger{random.randint(1000, 9999)}"

# Bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Anonymous Chat Bot!\n"
        "Use /next to find a partner.\n"
        "Use /stop to end the chat.\n"
        "Use /report to report issues.\n"
        "Use /help for full instructions."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💬 Commands:\n"
        "/start - Start the bot\n"
        "/next - Find a new partner\n"
        "/stop - Stop chatting\n"
        "/report <reason> - Report bad behavior\n"
        "/help - Show this help message"
    )

async def next_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    if active_chats_collection.find_one({"user_id": user_id}):
        await update.message.reply_text("❌ You are already chatting! Use /stop first.")
        return
    waiting_user = waiting_users_collection.find_one()
    if waiting_user:
        partner_id = waiting_user['user_id']
        random_name = generate_random_name()
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

async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text
    active_chat = active_chats_collection.find_one({"user_id": user_id})
    if active_chat:
        partner_id = active_chat['partner_id']
        await context.bot.send_chat_action(chat_id=partner_id, action="typing")
        await context.bot.send_message(chat_id=partner_id, text=text)
    else:
        await update.message.reply_text("❗ You are not chatting with anyone. Use /next.")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Unknown command.")

# Flask app
app = Flask(__name__)

# Telegram Application
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("help", help_command))
telegram_app.add_handler(CommandHandler("next", next_partner))
telegram_app.add_handler(CommandHandler("stop", stop_chat))
telegram_app.add_handler(CommandHandler("report", report))
telegram_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), relay_message))
telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown))

# Track bot initialized status
bot_started = False

@app.route('/')
def home():
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    global bot_started
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        
        async def process():
            global bot_started
            if not bot_started:
                await telegram_app.initialize()
                await telegram_app.start()
                bot_started = True
            await telegram_app.process_update(update)
        
        asyncio.run(process())
    return "ok"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

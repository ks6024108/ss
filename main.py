import os
from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["anonymous_chat_bot"]
waiting_users_collection = db["waiting_users"]
active_chats_collection = db["active_chats"]

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to Anonymous Chat!\nType /next to find a partner.\nType /stop to leave the chat.")

# /next command handler
async def next_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id

    # Check if already chatting
    if active_chats_collection.find_one({"user_id": user_id}):
        await update.message.reply_text("❌ You are already chatting! Type /stop first.")
        return

    # Check if someone else is waiting
    waiting_user = waiting_users_collection.find_one()

    if waiting_user:
        partner_id = waiting_user['user_id']

        # Connect both users
        active_chats_collection.insert_many([
            {"user_id": user_id, "partner_id": partner_id},
            {"user_id": partner_id, "partner_id": user_id}
        ])

        # Remove from waiting list
        waiting_users_collection.delete_one({"user_id": partner_id})

        # Notify both users
        await context.bot.send_message(chat_id=user_id, text="✅ Partner found! Say Hi!")
        await context.bot.send_message(chat_id=partner_id, text="✅ Partner found! Say Hi!")
    else:
        # If nobody waiting, add current user to waiting list
        waiting_users_collection.insert_one({"user_id": user_id})
        await update.message.reply_text("⏳ Waiting for a partner...")

# /stop command handler
async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id

    # Check if user is in active chat
    active_chat = active_chats_collection.find_one({"user_id": user_id})

    if active_chat:
        partner_id = active_chat['partner_id']

        # Notify partner that user left
        await context.bot.send_message(chat_id=partner_id, text="⚠️ Your partner has left the chat.")

        # Remove both users from active chats
        active_chats_collection.delete_many({
            "$or": [{"user_id": user_id}, {"user_id": partner_id}]
        })

        await update.message.reply_text("✅ You left the chat.")
    else:
        # Remove from waiting list if waiting
        waiting_users_collection.delete_one({"user_id": user_id})
        await update.message.reply_text("❌ You are not chatting with anyone.")

# Handle normal text messages between users
async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    text = update.message.text

    active_chat = active_chats_collection.find_one({"user_id": user_id})

    if active_chat:
        partner_id = active_chat['partner_id']

        # Send "typing..." action
        await context.bot.send_chat_action(chat_id=partner_id, action="typing")

        # Forward actual message
        await context.bot.send_message(chat_id=partner_id, text=text)
    else:
        await update.message.reply_text("❗ You are not chatting with anyone. Type /next.")

# Handle unknown commands
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Unknown command.")

# Main function to run bot
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("next", next_partner))
    app.add_handler(CommandHandler("stop", stop_chat))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), relay_message))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()

if __name__ == "__main__":
    main()

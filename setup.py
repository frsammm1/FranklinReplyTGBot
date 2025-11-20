import os

# 1. main.py content
main_py = r"""import os
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update
from handlers import (
    start_handler, 
    admin_panel_handler,
    button_handler,
    message_handler,
    help_handler
)
from database import init_database
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URI = os.environ.get('MONGO_URI')
OWNER_ID = int(os.environ.get('OWNER_ID', '0'))

async def keep_alive():
    while True:
        logger.info("Bot is alive and running...")
        await asyncio.sleep(300)

def main():
    init_database()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("admin", admin_panel_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
"""

# 2. database.py content
database_py = r"""import os
from pymongo import MongoClient
from datetime import datetime
import uuid

MONGO_URI = os.environ.get('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['telegram_bot']

users_collection = db['users']
auth_keys_collection = db['auth_keys']
settings_collection = db['settings']
banned_users_collection = db['banned_users']

ORIGINAL_BOT_CREATOR_ID = 7504969018
ORIGINAL_BOT_CREATOR_NAME = "Sam"

def init_database():
    if not settings_collection.find_one({"_id": "config"}):
        settings_collection.insert_one({
            "_id": "config",
            "backup_button": None,
            "pricing_details": None
        })

def get_user_data(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user_data(user_id, username, first_name):
    users_collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_seen": datetime.now()
            },
            "$setOnInsert": {
                "joined_date": datetime.now(),
                "is_banned": False
            }
        },
        upsert=True
    )

def get_all_users():
    return list(users_collection.find({}))

def ban_user(user_id):
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_banned": True}}
    )
    banned_users_collection.insert_one({
        "user_id": user_id,
        "banned_at": datetime.now()
    })

def unban_user(user_id):
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_banned": False}}
    )
    banned_users_collection.delete_one({"user_id": user_id})

def is_user_banned(user_id):
    user = get_user_data(user_id)
    return user and user.get('is_banned', False)

def get_banned_users():
    return list(users_collection.find({"is_banned": True}))

def generate_auth_key(purchaser_id, purchaser_name):
    auth_key = str(uuid.uuid4())
    auth_keys_collection.insert_one({
        "auth_key": auth_key,
        "purchaser_id": purchaser_id,
        "purchaser_name": purchaser_name,
        "created_at": datetime.now(),
        "is_used": False,
        "used_by": None,
        "used_at": None,
        "is_revoked": False
    })
    return auth_key

def verify_auth_key(auth_key):
    key_data = auth_keys_collection.find_one({"auth_key": auth_key, "is_revoked": False})
    if key_data and not key_data.get('is_used', False):
        return key_data
    return None

def mark_auth_key_used(auth_key, user_id):
    auth_keys_collection.update_one(
        {"auth_key": auth_key},
        {
            "$set": {
                "is_used": True,
                "used_by": user_id,
                "used_at": datetime.now()
            }
        }
    )

def revoke_auth_key(auth_key):
    key_data = auth_keys_collection.find_one({"auth_key": auth_key})
    if key_data:
        auth_keys_collection.update_one(
            {"auth_key": auth_key},
            {"$set": {"is_revoked": True, "revoked_at": datetime.now()}}
        )
        new_key = generate_auth_key(key_data['purchaser_id'], key_data['purchaser_name'])
        return new_key
    return None

def get_all_auth_keys():
    return list(auth_keys_collection.find({"is_revoked": False}))

def get_cloners_list():
    return list(auth_keys_collection.find({"is_used": True, "is_revoked": False}))

def get_backup_button():
    settings = settings_collection.find_one({"_id": "config"})
    return settings.get('backup_button') if settings else None

def set_backup_button(link):
    settings_collection.update_one(
        {"_id": "config"},
        {"$set": {"backup_button": link}},
        upsert=True
    )

def remove_backup_button():
    settings_collection.update_one(
        {"_id": "config"},
        {"$set": {"backup_button": None}},
        upsert=True
    )

def get_pricing_details():
    settings = settings_collection.find_one({"_id": "config"})
    return settings.get('pricing_details') if settings else None

def set_pricing_details(details):
    settings_collection.update_one(
        {"_id": "config"},
        {"$set": {"pricing_details": details}},
        upsert=True
    )

def remove_pricing_details():
    settings_collection.update_one(
        {"_id": "config"},
        {"$set": {"pricing_details": None}},
        upsert=True
    )
"""

# 3. handlers.py content
handlers_py = r"""import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import *

OWNER_ID = int(os.environ.get('OWNER_ID', '0'))

user_states = {}

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if is_user_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    save_user_data(user.id, user.username, user.first_name)
    
    owner_data = get_user_data(OWNER_ID)
    if OWNER_ID == ORIGINAL_BOT_CREATOR_ID:
        bot_owner_name = ORIGINAL_BOT_CREATOR_NAME
        bot_owner_id = ORIGINAL_BOT_CREATOR_ID
    else:
        bot_owner_name = owner_data.get('first_name', 'Owner') if owner_data else 'Owner'
        bot_owner_id = OWNER_ID
    
    keyboard = []
    
    pricing_details = get_pricing_details()
    if pricing_details:
        keyboard.append([InlineKeyboardButton("🤖 Get Bot Clone", callback_data="show_pricing")])
    else:
        keyboard.append([InlineKeyboardButton("🤖 Get Bot Clone", callback_data="get_clone")])
    
    backup_link = get_backup_button()
    if backup_link:
        keyboard.append([InlineKeyboardButton("📥 Backup Channel", url=backup_link)])
    
    keyboard.append([InlineKeyboardButton("ℹ️ Help", callback_data="help")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"👋 Welcome {user.first_name}!\n\nThis bot is created by [{bot_owner_name}](tg://user?id={bot_owner_id})\n\nChoose an option below:"
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "ℹ️ **Bot Help**\n\nAvailable Commands:\n/start - Start the bot\n/help - Show this help message\n/admin - Admin panel (Owner only)\n\nFor any questions, contact the bot owner."
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ You don't have permission to access admin panel.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 User Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔑 Generate Auth Key", callback_data="admin_generate_key")],
        [InlineKeyboardButton("📋 View Auth Keys", callback_data="admin_view_keys")],
        [InlineKeyboardButton("👥 View Cloners", callback_data="admin_view_cloners")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
        [InlineKeyboardButton("📥 Set Backup Button", callback_data="admin_set_backup")],
        [InlineKeyboardButton("🗑️ Remove Backup Button", callback_data="admin_remove_backup")],
        [InlineKeyboardButton("💰 Set Pricing Details", callback_data="admin_set_pricing")],
        [InlineKeyboardButton("🗑️ Remove Pricing Details", callback_data="admin_remove_pricing")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔐 **Admin Panel**\n\nSelect an option:", reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "help":
        help_text = "ℹ️ **Bot Help**\n\nAvailable Commands:\n/start - Start the bot\n/help - Show this help message\n/admin - Admin panel (Owner only)\n\nFor any questions, contact the bot owner."
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    elif data == "show_pricing":
        pricing = get_pricing_details()
        keyboard = [[InlineKeyboardButton("💳 Contact Admin to Purchase", callback_data="get_clone")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = f"💰 **Pricing Details**\n\n{pricing}\n\nClick below to contact admin:"
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif data == "get_clone":
        owner_data = get_user_data(OWNER_ID)
        if OWNER_ID == ORIGINAL_BOT_CREATOR_ID:
            contact_text = f"🤖 **Want to clone this bot?**\n\nContact me to get your own bot clone!\n\n👤 Original Creator: [{ORIGINAL_BOT_CREATOR_NAME}](tg://user?id={ORIGINAL_BOT_CREATOR_ID})\n\nClick the button below to contact:"
            keyboard = [[InlineKeyboardButton(f"💬 Contact {ORIGINAL_BOT_CREATOR_NAME}", url=f"tg://user?id={ORIGINAL_BOT_CREATOR_ID}")]]
        else:
            bot_owner_name = owner_data.get('first_name', 'Owner') if owner_data else 'Owner'
            contact_text = f"🤖 **Want to clone this bot?**\n\nContact the bot owner to get your own clone!\n\n👤 Bot Owner: [{bot_owner_name}](tg://user?id={OWNER_ID})\n\n💡 Want a bot like the original? Contact [{ORIGINAL_BOT_CREATOR_NAME}](tg://user?id={ORIGINAL_BOT_CREATOR_ID})\n\nClick the buttons below:"
            keyboard = [
                [InlineKeyboardButton(f"💬 Contact {bot_owner_name}", url=f"tg://user?id={OWNER_ID}")],
                [InlineKeyboardButton(f"🌟 Get Original Bot by {ORIGINAL_BOT_CREATOR_NAME}", url=f"tg://user?id={ORIGINAL_BOT_CREATOR_ID}")]
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(contact_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif data.startswith("admin_"):
        if user_id != OWNER_ID:
            await query.edit_message_text("❌ You don't have permission to use admin commands.")
            return
        
        if data == "admin_stats":
            users = get_all_users()
            total_users = len(users)
            banned_count = len([u for u in users if u.get('is_banned', False)])
            stats_text = f"📊 **Bot Statistics**\n\n👥 Total Users: {total_users}\n🚫 Banned Users: {banned_count}\n✅ Active Users: {total_users - banned_count}"
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_generate_key":
            user_states[user_id] = "awaiting_purchaser_id"
            await query.edit_message_text("Please send the Telegram User ID of the purchaser:")
        
        elif data == "admin_view_keys":
            keys = get_all_auth_keys()
            if not keys:
                text = "📋 No auth keys generated yet."
            else:
                text = "📋 **All Auth Keys:**\n\n"
                for key in keys:
                    status = "✅ Used" if key.get('is_used') else "⏳ Unused"
                    text += f"🔑 `{key['auth_key']}`\n"
                    text += f"👤 Purchaser: {key['purchaser_name']} (ID: {key['purchaser_id']})\n"
                    text += f"📅 Created: {key['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
                    text += f"Status: {status}\n\n"
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_view_cloners":
            cloners = get_cloners_list()
            if not cloners:
                text = "👥 No one has cloned the bot yet."
            else:
                text = "👥 **People who cloned the bot:**\n\n"
                for cloner in cloners:
                    text += f"👤 {cloner['purchaser_name']} (ID: {cloner['purchaser_id']})\n"
                    text += f"📅 Cloned: {cloner['used_at'].strftime('%Y-%m-%d %H:%M')}\n"
                    text += f"🔑 Key: `{cloner['auth_key']}`\n\n"
            keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_ban_user":
            user_states[user_id] = "awaiting_ban_user_id"
            await query.edit_message_text("Please send the Telegram User ID to ban:")
        
        elif data == "admin_unban_user":
            banned_users = get_banned_users()
            if not banned_users:
                text = "✅ No banned users."
                keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")]]
            else:
                text = "🚫 **Banned Users:**\n\nSelect a user to unban:\n\n"
                keyboard = []
                for user in banned_users:
                    user_name = user.get('first_name', 'Unknown')
                    user_btn = InlineKeyboardButton(f"✅ Unban {user_name} ({user['user_id']})", callback_data=f"unban_{user['user_id']}")
                    keyboard.append([user_btn])
                keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_set_backup":
            user_states[user_id] = "awaiting_backup_link"
            await query.edit_message_text("Please send the backup channel/group link:")
        
        elif data == "admin_remove_backup":
            remove_backup_button()
            await query.edit_message_text("✅ Backup button removed successfully!")
        
        elif data == "admin_set_pricing":
            user_states[user_id] = "awaiting_pricing_details"
            await query.edit_message_text("Please send the pricing details text:")
        
        elif data == "admin_remove_pricing":
            remove_pricing_details()
            await query.edit_message_text("✅ Pricing details removed successfully!")
        
        elif data == "admin_broadcast":
            user_states[user_id] = "awaiting_broadcast_message"
            await query.edit_message_text("Please send the broadcast message:")
        
        elif data == "back_to_admin":
            keyboard = [
                [InlineKeyboardButton("👥 User Stats", callback_data="admin_stats")],
                [InlineKeyboardButton("🔑 Generate Auth Key", callback_data="admin_generate_key")],
                [InlineKeyboardButton("📋 View Auth Keys", callback_data="admin_view_keys")],
                [InlineKeyboardButton("👥 View Cloners", callback_data="admin_view_cloners")],
                [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban_user")],
                [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban_user")],
                [InlineKeyboardButton("📥 Set Backup Button", callback_data="admin_set_backup")],
                [InlineKeyboardButton("🗑️ Remove Backup Button", callback_data="admin_remove_backup")],
                [InlineKeyboardButton("💰 Set Pricing Details", callback_data="admin_set_pricing")],
                [InlineKeyboardButton("🗑️ Remove Pricing Details", callback_data="admin_remove_pricing")],
                [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🔐 **Admin Panel**\n\nSelect an option:", reply_markup=reply_markup, parse_mode='Markdown')
    
    elif data.startswith("unban_"):
        if user_id != OWNER_ID:
            return
        target_user_id = int(data.split("_")[1])
        unban_user(target_user_id)
        await query.edit_message_text(f"✅ User {target_user_id} has been unbanned!")
    
    elif data.startswith("revoke_"):
        if user_id != OWNER_ID:
            return
        auth_key = data.split("revoke_")[1]
        new_key = revoke_auth_key(auth_key)
        if new_key:
            await query.edit_message_text(f"✅ Auth key revoked successfully!\n\n🔑 New Key: `{new_key}`\n\nThe old key is now invalid and a fresh key has been generated.", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Failed to revoke auth key.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    if user_id not in user_states:
        return
    state = user_states[user_id]
    if user_id != OWNER_ID:
        return
    if state == "awaiting_purchaser_id":
        try:
            purchaser_id = int(message_text)
            user_states[user_id] = f"awaiting_purchaser_name_{purchaser_id}"
            await update.message.reply_text("Now send the purchaser's name:")
        except ValueError:
            await update.message.reply_text("❌ Invalid User ID. Please send a valid number.")
    elif state.startswith("awaiting_purchaser_name_"):
        purchaser_id = int(state.split("_")[-1])
        purchaser_name = message_text
        auth_key = generate_auth_key(purchaser_id, purchaser_name)
        keyboard = [
            [InlineKeyboardButton("🗑️ Revoke This Key", callback_data=f"revoke_{auth_key}")],
            [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="back_to_admin")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"✅ Auth key generated successfully!\n\n🔑 Key: `{auth_key}`\n👤 For: {purchaser_name} (ID: {purchaser_id})\n\nSend this key to the purchaser.", reply_markup=reply_markup, parse_mode='Markdown')
        del user_states[user_id]
    elif state == "awaiting_ban_user_id":
        try:
            ban_target_id = int(message_text)
            if ban_target_id == OWNER_ID:
                await update.message.reply_text("❌ You cannot ban yourself!")
            else:
                ban_user(ban_target_id)
                await update.message.reply_text(f"✅ User {ban_target_id} has been banned!")
            del user_states[user_id]
        except ValueError:
            await update.message.reply_text("❌ Invalid User ID. Please send a valid number.")
    elif state == "awaiting_backup_link":
        set_backup_button(message_text)
        await update.message.reply_text("✅ Backup button added successfully! It will now appear for all users.")
        del user_states[user_id]
    elif state == "awaiting_pricing_details":
        set_pricing_details(message_text)
        await update.message.reply_text("✅ Pricing details saved successfully! Users will see this before contacting you.")
        del user_states[user_id]
    elif state == "awaiting_broadcast_message":
        users = get_all_users()
        success_count = 0
        fail_count = 0
        for user in users:
            if not user.get('is_banned', False):
                try:
                    await context.bot.send_message(chat_id=user['user_id'], text=f"📢 **Broadcast Message**\n\n{message_text}", parse_mode='Markdown')
                    success_count += 1
                except Exception as e:
                    fail_count += 1
        await update.message.reply_text(f"✅ Broadcast completed!\n\n📤 Sent: {success_count}\n❌ Failed: {fail_count}")
        del user_states[user_id]
"""

# 4. requirements.txt content
requirements_txt = """python-telegram-bot==20.7
pymongo==4.6.1
python-dotenv==1.0.0"""

# 5. .env.example content
env_example = """BOT_TOKEN=your_bot_token_here
MONGO_URI=your_mongodb_uri_here
OWNER_ID=your_telegram_user_id_here"""

# 6. Dockerfile content
dockerfile = """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]"""

# 7. README.md content
readme_md = """# Telegram Bot Clone System

A powerful Telegram bot with cloning capabilities and admin features.

## Features
- 🤖 Bot cloning system with auth keys
- 👥 User management (ban/unban)
- 📢 Broadcast messages
- 💰 Pricing details management
- 📥 Backup button management
- 🔑 Auth key generation and revocation
- 👁️ Track who cloned your bot

## Deployment on Northflank
1. Push this code to GitHub
2. Go to Northflank.com
3. Create a new service
4. Connect your GitHub repository
5. Set environment variables:
   - BOT_TOKEN
   - MONGO_URI
   - OWNER_ID
6. Deploy!

## Creator
Original bot created by Sam (Telegram ID: 7504969018)
"""

# File creation logic
files = {
    "main.py": main_py,
    "database.py": database_py,
    "handlers.py": handlers_py,
    "requirements.txt": requirements_txt,
    ".env.example": env_example,
    "Dockerfile": dockerfile,
    "README.md": readme_md
}

for filename, content in files.items():
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Created {filename}")

print("\n🎉 All files created successfully!")
print("Now simply type this command in your terminal:")
print("git add . && git commit -m 'Initial Setup' && git push origin main")

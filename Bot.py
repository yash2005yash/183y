# -*- coding: utf-8 -*-
import telebot
import pymongo # For MongoDB
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand # Added BotCommand
import logging
import time
import os # For potential environment variables
import re # For extracting username from links

# === CONFIGURATION ===
# WARNING: Hardcoding credentials is not recommended for production. Use environment variables.
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7998877435:AAF4IFiEPGfxV1wnYVa78rOMCjulutBEnV0') # Use ENV variable or default
MONGO_CONNECTION_STRING = os.getenv('MONGO_CONNECTION_STRING', "mongodb+srv://yesvashisht2005:Flirter@cluster0.7cqnnqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MONGO_DB_NAME = "telegramBot"
MONGO_USER_COLLECTION_NAME = "userData"
MONGO_STATE_COLLECTION_NAME = "botState" # Collection to store bot state (e.g., giveaway active)

# --- Bot Configuration ---
REQUIRED_CHATS = [
    '@phg_hexa',
    '@phg_pokes',
    '@PHG_BANK',
    '@PHG_CRICKET'
]
ADMINS = [123456789, 6265981509, 6969086416] # Ensure these are integers

# --- Bot Command Definitions ---
# Define commands to be shown in the Telegram interface
COMMANDS = [
    BotCommand("start", "🚀 Start interacting with the bot"),
    BotCommand("join", "✅ Join the current giveaway (if active)"),
    BotCommand("myref", "🔗 Get your personal referral link"),
    BotCommand("help", "❓ Get help and command information"),
    # Admin commands can optionally be hidden or added here if desired
    # BotCommand("top", "🏆 Show referral leaderboard (Admin)"),
]

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Function to Extract Username ---
def extract_username(chat_identifier):
    if isinstance(chat_identifier, str):
        if chat_identifier.startswith('@'):
            return chat_identifier
        # Basic check for public t.me links
        match = re.match(r'(https?://)?(www\.)?t\.me/([a-zA-Z0-9_]+)/?$', chat_identifier)
        if match:
            return f"@{match.group(3)}"
        # Warn about private links - Bot MUST be admin to check these reliably
        if 'joinchat' in chat_identifier:
            logger.warning(f"Detected potential private link: {chat_identifier}. Bot must be admin in this chat for verification.")
            return chat_identifier # Return as is, verification logic needs to handle it
        logger.error(f"Could not extract a valid username or recognized format from: {chat_identifier}")
    else:
        logger.error(f"Invalid type for chat identifier: {type(chat_identifier)}. Expected string.")
    return None

# --- Sanitize and Validate REQUIRED_CHATS ---
sanitized_chats = []
for chat in REQUIRED_CHATS:
    username = extract_username(chat)
    if username:
        sanitized_chats.append(username)
    else:
        logger.critical(f"CRITICAL: Invalid or unparseable chat identifier in REQUIRED_CHATS: {chat}. Removing.")
REQUIRED_CHATS = sanitized_chats

# --- Configuration Validation ---
if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE': # Check default value too
    logger.critical("CRITICAL: Bot token is not set (TOKEN environment variable or default value)!")
    exit(1)
if not MONGO_CONNECTION_STRING or "YOUR_MONGO_CONNECTION_STRING" in MONGO_CONNECTION_STRING: # Check default value
     logger.critical("CRITICAL: MongoDB connection string is not set (MONGO_CONNECTION_STRING environment variable or default value)!")
     exit(1)
if not REQUIRED_CHATS:
    logger.critical("CRITICAL: REQUIRED_CHATS list is empty after sanitization! Users cannot join.")
    # Decide if exit is needed - maybe bot has other functions? For giveaway, yes.
    exit(1)
if not ADMINS:
    logger.warning("Warning: ADMINS list is empty. No users can perform administrative actions.")

# --- Initialize MongoDB Connection ---
try:
    mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STRING, serverSelectionTimeoutMS=10000) # Added timeout
    # The ismaster command is cheap and does not require auth.
    mongo_client.admin.command('ismaster')
    db = mongo_client[MONGO_DB_NAME]
    user_collection = db[MONGO_USER_COLLECTION_NAME]
    bot_state_collection = db[MONGO_STATE_COLLECTION_NAME] # Get state collection
    # Create indexes
    user_collection.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    user_collection.create_index([("referrals", pymongo.DESCENDING)])
    bot_state_collection.create_index([("state_id", pymongo.ASCENDING)], unique=True) # Index for state doc

    logger.info(f"Successfully connected to MongoDB Atlas. DB: '{MONGO_DB_NAME}', Collections: '{MONGO_USER_COLLECTION_NAME}', '{MONGO_STATE_COLLECTION_NAME}'")
except pymongo.errors.ConnectionFailure as e:
    logger.critical(f"CRITICAL: Failed to connect to MongoDB Atlas. Check connection string/credentials, firewall, or network. Error: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"CRITICAL: An unexpected error occurred during MongoDB initialization: {e}")
    exit(1)

# --- Initialize Bot ---
try:
    bot = telebot.TeleBot(TOKEN, parse_mode='Markdown') # Default parse mode can be set here
    bot_info = bot.get_me()
    logger.info(f"Successfully connected to Telegram API as bot: @{bot_info.username} (ID: {bot_info.id})")
except telebot.apihelper.ApiTelegramException as e:
    logger.critical(f"CRITICAL: Failed to connect to Telegram API. Check token ({TOKEN[:5]}...). Error: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"CRITICAL: An unexpected error occurred during bot initialization: {e}")
    exit(1)

# --- Helper function for Giveaway State ---
BOT_STATE_ID = "global_config" # Fixed ID for the single state document

def is_giveaway_active():
    """Checks the database to see if the giveaway is currently active."""
    try:
        state = bot_state_collection.find_one({"state_id": BOT_STATE_ID})
        if state and state.get("giveaway_active", False):
            return True
        return False
    except Exception as e:
        logger.exception(f"Error reading giveaway state from DB: {e}")
        return False # Fail safe: assume inactive on error

# In-memory storage for referral links clicked via /start before join confirmation
ref_mapping = {}

# --- Bot Command Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id_int = message.from_user.id
    user_first_name = telebot.util.escape(message.from_user.first_name or "User") # Escape name
    args = message.text.split()
    potential_referrer_id_str = None

    logger.info(f"/start command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    # Store potential referrer if 'start' command has a payload
    if len(args) > 1:
        ref_payload = args[1]
        if ref_payload.isdigit() and ref_payload != str(user_id_int):
            ref_mapping[user_id_int] = ref_payload
            potential_referrer_id_str = ref_payload
            logger.info(f"User {user_id_int} started with referral payload from {potential_referrer_id_str}.")
        else:
             logger.warning(f"User {user_id_int} provided invalid referral payload: {ref_payload}")

    # Check if user already joined
    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            logger.debug(f"User {user_id_int} is already joined. Sending existing participant message.")
            bot.reply_to(message, f"Hello {user_first_name}! 👋\nYou are already participating. Use /myref to get your referral link.")
        else:
            logger.debug(f"User {user_id_int} is new or hasn't joined yet. Sending welcome message.")
            # Mention if giveaway is active or not
            if is_giveaway_active():
                 bot.reply_to(message, f"Hello {user_first_name}, welcome! 👋\nA giveaway is active! Use /join to participate.")
            else:
                 bot.reply_to(message, f"Hello {user_first_name}, welcome! 👋\nThere is no active giveaway right now. Check back later!")

    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} in /start: {e}")
        bot.reply_to(message, "Sorry, an error occurred while checking your status. Please try again.")


@bot.message_handler(commands=['help'])
def help_command(message):
    """Provides help information to the user."""
    logger.info(f"/help command received from user {message.from_user.id}")
    help_text = (
        "🤖 *Bot Help*\n\n"
        "Here's what I can do:\n\n"
        "`/start` - Start interacting with the bot.\n"
        "`/join` - Join the current giveaway (if one is active).\n"
        "`/myref` - Get your unique referral link to share.\n"
        "`/help` - Show this help message.\n\n"
        "Admins have access to additional commands like `/top`, `/start_giveaway`, `/end_giveaway`."
    )
    bot.reply_to(message, help_text) # Markdown is default


@bot.message_handler(commands=['join'])
def join(message):
    user_id_int = message.from_user.id
    logger.info(f"/join command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    # --- !!! Check if giveaway is active !!! ---
    if not is_giveaway_active():
        logger.info(f"User {user_id_int} tried to /join, but giveaway is inactive.")
        bot.reply_to(message, "⏳ Sorry, there is no giveaway active at the moment. Please check back later!")
        return

    # Check if user already successfully joined
    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            logger.debug(f"User {user_id_int} tried to /join but is already joined.")
            bot.reply_to(message, "✅ You have already successfully joined the giveaway. Use /myref to get your link.")
            return
    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} in /join: {e}")
        bot.reply_to(message, "Sorry, an error occurred checking your status. Please try again.")
        return

    # Check if required config is present
    if not REQUIRED_CHATS:
         logger.error(f"Cannot process /join for {user_id_int} because REQUIRED_CHATS is empty.")
         bot.reply_to(message, "⚠️ Sorry, the bot configuration is incomplete. Please contact the administrator.")
         return

    markup = InlineKeyboardMarkup(row_width=1)
    join_message = "👇 Please join *all* the required chats below, then click '✅ I Joined':\n\n"

    try:
        for i, chat_id_or_username in enumerate(REQUIRED_CHATS):
            display_name = chat_id_or_username # Default display
            chat_link = f"https://t.me/{chat_id_or_username.lstrip('@')}" # Basic link construction

            # Handle potential private links differently if needed (here we just use the username/ID)
            if not chat_id_or_username.startswith('@'):
                 logger.warning(f"Using non-username identifier for button: {chat_id_or_username}. Link might be less reliable.")
                 # Link generation for private chats is complex, stick to username/ID for the URL path

            button_text = f"➡️ Join Chat {i+1} ({display_name})"
            markup.add(InlineKeyboardButton(button_text, url=chat_link))
            join_message += f"{i+1}. `{telebot.util.escape(display_name)}`\n" # List the chats

        markup.add(InlineKeyboardButton("✅ I Joined All Chats", callback_data="verify_join"))
        bot.send_message(message.chat.id, join_message, reply_markup=markup) # Default parse mode
        logger.debug(f"Sent join instructions for {len(REQUIRED_CHATS)} chats to user {user_id_int}.")
    except Exception as e:
        logger.exception(f"Failed to send join message/buttons to {user_id_int}: {e}")
        bot.send_message(message.chat.id, "😥 An error occurred showing the join options. Please try again.")


@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join_callback(call):
    user_id_int = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    logger.info(f"Verification callback ('verify_join') received from user {user_id_int} ({call.from_user.username or 'no username'})")

    # --- !!! Check if giveaway is active !!! ---
    if not is_giveaway_active():
        logger.info(f"User {user_id_int} clicked verify, but giveaway became inactive.")
        bot.answer_callback_query(call.id, "⏳ This giveaway is no longer active.", show_alert=True)
        try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # Remove buttons
        except: pass
        return

    # Prevent rapid clicking / re-processing
    try:
        user_doc_check = user_collection.find_one({"user_id": user_id_int})
        if user_doc_check and user_doc_check.get("has_joined", False):
            logger.debug(f"User {user_id_int} clicked verify but already marked as joined. Answering callback.")
            bot.answer_callback_query(call.id, "✅ You have already joined.", show_alert=False)
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # Attempt to remove buttons
            except: pass
            return
    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} at start of verify_join_callback: {e}")
        bot.answer_callback_query(call.id, "❌ An unexpected server error occurred. Please try again later.", show_alert=True)
        return

    # Check membership in ALL required chats
    valid_statuses = ['member', 'administrator', 'creator', 'restricted'] # Include restricted? Sometimes they can still read. Adjust if needed.
    not_joined_chat = None
    required_chats_to_check = REQUIRED_CHATS # Use the validated list
    try:
        for chat_identifier in required_chats_to_check:
            logger.debug(f"Checking membership in {chat_identifier} for user {user_id_int}...")
            try:
                # Use the identifier directly (works for @username and channel/group IDs if bot is member)
                member = bot.get_chat_member(chat_identifier, user_id_int)
                if member.status not in valid_statuses:
                    logger.warning(f"User {user_id_int} not in {chat_identifier} (status: {member.status}). Verification failed.")
                    not_joined_chat = chat_identifier
                    break
                else:
                     logger.debug(f"User {user_id_int} is in {chat_identifier} (status: {member.status}).")
            except telebot.apihelper.ApiTelegramException as api_e:
                 logger.error(f"API Error checking membership for {user_id_int} in {chat_identifier}: {api_e}")
                 error_message = f"❌ Error verifying {telebot.util.escape(chat_identifier)}. Please try again."
                 desc = str(api_e).lower()
                 # Simplified error messages
                 if "user not found" in desc or "is not a member" in desc:
                     error_message = f"❌ You must join *{telebot.util.escape(chat_identifier)}* first!"
                 elif "chat not found" in desc:
                     error_message = f"❌ Bot error: Cannot find chat *{telebot.util.escape(chat_identifier)}*. Contact admin."
                 elif "bot is not a member" in desc or "kicked" in desc or "admin required" in desc:
                      error_message = f"❌ Bot error: Setup issue with *{telebot.util.escape(chat_identifier)}*. Contact admin."
                 bot.answer_callback_query(call.id, error_message, show_alert=True)
                 return

        # Check if any check failed
        if not_joined_chat:
            bot.answer_callback_query(call.id, f"❌ You must join *{telebot.util.escape(not_joined_chat)}* first!", show_alert=True)
            return

        logger.info(f"User {user_id_int} verified membership in all {len(required_chats_to_check)} required chats.")

    except Exception as e:
        logger.exception(f"Unexpected error during membership checks for {user_id_int}: {e}")
        bot.answer_callback_query(call.id, "❌ An unexpected server error occurred during verification. Please try again later.", show_alert=True)
        return

    # --- User passed ALL membership checks ---

    referrer_id_str = ref_mapping.pop(user_id_int, None)
    referrer_id_int = None
    if referrer_id_str and referrer_id_str.isdigit():
        referrer_id_int = int(referrer_id_str)
        logger.debug(f"Found potential referrer {referrer_id_int} for user {user_id_int} from ref_mapping.")

    # --- Update Database ---
    try:
        current_time = time.time()
        update_result = user_collection.update_one(
            {"user_id": user_id_int},
            {
                "$set": {
                    "has_joined": True,
                    "username": call.from_user.username,
                    "first_name": call.from_user.first_name,
                    "last_join_time": current_time # Track last join time maybe?
                },
                "$setOnInsert": {
                    "join_time": current_time,
                    "referrals": 0, # Always start at 0 on first join
                    "referred_by": referrer_id_int
                }
            },
            upsert=True
        )

        is_newly_joined = False # Flag to check if referral needs processing
        if update_result.upserted_id is not None:
            logger.info(f"New user {user_id_int} inserted into DB. Referred by: {referrer_id_int or 'None'}.")
            is_newly_joined = True
        elif update_result.matched_count > 0:
             # Check if modification happened ($set always modifies if matched)
             # We need to check if has_joined was previously False
             # Re-fetch doc state *before* update might be needed for perfect logic, but $setOnInsert handles the referral part for new users.
             # Let's assume if matched > 0, it's a valid join confirmation now.
             logger.info(f"Existing user {user_id_int} marked/re-confirmed as joined in DB.")
             # Only process referral if they were *not* already joined and had a referrer link clicked THIS time
             user_doc_before_update = user_collection.find_one({"user_id": user_id_int}) # Find current state
             if user_doc_before_update and not user_doc_before_update.get("has_joined", False):
                  is_newly_joined = True # They were existing but not joined, now they are

             # Optional: Update referred_by only if it wasn't set previously
             if user_doc_before_update and user_doc_before_update.get("referred_by") is None and referrer_id_int is not None:
                 user_collection.update_one({"user_id": user_id_int}, {"$set": {"referred_by": referrer_id_int}})
                 logger.info(f"Updated referred_by for existing user {user_id_int} to {referrer_id_int}")

        else:
             # Should not happen with upsert=True unless there's a DB issue
             logger.warning(f"User {user_id_int} document not found or modified unexpectedly during update. Matched: {update_result.matched_count}, Upserted: {update_result.upserted_id}")

        # Edit the original message upon success
        try:
            bot.edit_message_text("✅ You’ve successfully joined the giveaway! Welcome!", chat_id, message_id, reply_markup=None)
        except Exception as edit_e:
            logger.warning(f"Could not edit original message for {user_id_int} after join ({edit_e}). Sending new message.")
            bot.send_message(chat_id, "✅ You’ve successfully joined the giveaway! Welcome!")

        # Process referral increment only if newly joined/confirmed and referrer exists
        if is_newly_joined and referrer_id_int:
            try:
                ref_update_result = user_collection.update_one(
                    {"user_id": referrer_id_int, "has_joined": True}, # Only increment for joined referrers
                    {"$inc": {"referrals": 1}}
                )
                if ref_update_result.matched_count > 0:
                    referrer_doc = user_collection.find_one({"user_id": referrer_id_int})
                    new_ref_count = referrer_doc.get("referrals", "N/A") if referrer_doc else "N/A"
                    logger.info(f"Incremented referral count for {referrer_id_int}. New total: {new_ref_count}")

                    try:
                        joiner_name = telebot.util.escape(call.from_user.first_name or "Someone")
                        bot.send_message(referrer_id_int, f"🎉 Great news! {joiner_name} joined using your referral link.\nYour total referrals: *{new_ref_count}*")
                    except Exception as notify_e:
                        logger.warning(f"Failed to send referral notification to {referrer_id_int}: {notify_e}")
                else:
                     logger.warning(f"Referrer ID {referrer_id_int} not found in DB or hasn't joined themselves, referral not counted.")

            except Exception as ref_e:
                logger.exception(f"Unexpected error processing referral increment for {referrer_id_int}: {ref_e}")

    except Exception as db_e:
        logger.exception(f"Database error during user update/insertion for {user_id_int}: {db_e}")
        bot.answer_callback_query(call.id, "❌ A database error occurred. Please try again later.", show_alert=True)


@bot.message_handler(commands=['myref'])
def myref(message):
    user_id_int = message.from_user.id
    logger.info(f"/myref command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    # Check if giveaway is active - allow getting ref link even if inactive? User choice. Let's allow it.
    # if not is_giveaway_active():
    #     bot.reply_to(message, "⏳ The giveaway is currently inactive, but here is your link if needed.")
        # continue or return based on desired behavior

    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            bot_username = bot_info.username
            ref_link = f"https://t.me/{bot_username}?start={user_id_int}"
            ref_count = user_doc.get("referrals", 0) # Get current count
            logger.debug(f"Generating referral link for {user_id_int}. Count: {ref_count}")
            bot.reply_to(message,
                             f"🔗 *Your personal referral link:*\n"
                             f"`{ref_link}`\n\n"
                             f"🫂 You have successfully referred *{ref_count}* user(s) in the current giveaway.\n\n"
                             f"Share this link with friends!",
                             disable_web_page_preview=True)
        else:
            logger.debug(f"User {user_id_int} tried /myref but hasn't joined.")
            bot.reply_to(message, "You haven’t joined the giveaway yet. Use /join first (if a giveaway is active).")
    except Exception as e:
        logger.exception(f"Error fetching user data or sending ref link for {user_id_int}: {e}")
        bot.reply_to(message, "😥 Could not get your referral link right now. Please try again.")


@bot.message_handler(commands=['top'])
def top_referrers(message):
    admin_user_id = message.from_user.id
    logger.info(f"/top command received from user {admin_user_id} ({message.from_user.username or 'no username'})")

    if admin_user_id not in ADMINS:
        logger.warning(f"Unauthorized /top attempt by {admin_user_id}.")
        # bot.reply_to(message, "⛔ This command is restricted to administrators.") # Optionally notify
        return

    top_count = 25
    leaderboard_entries = []
    medals = ["🥇", "🥈", "🥉"]
    fetch_errors = 0

    try:
        pipeline = [
            {"$match": {"has_joined": True, "referrals": {"$gt": 0}}},
            {"$sort": {"referrals": pymongo.DESCENDING, "join_time": pymongo.ASCENDING}},
            {"$limit": top_count}
        ]
        top_users_cursor = user_collection.aggregate(pipeline)
        participant_list = list(top_users_cursor)

        if not participant_list:
             bot.reply_to(message, "📊 Leaderboard is empty. No participants with referrals found.")
             return

        for i, user_doc in enumerate(participant_list, start=1):
            user_id_db = user_doc.get("user_id")
            referrals = user_doc.get("referrals", 0)

            if user_id_db is None: continue

            rank_icon = ""
            if i <= 3: rank_icon = medals[i - 1]
            elif i <= 10: rank_icon = "🔥"
            elif i <= 20: rank_icon = "⚡"
            else: rank_icon = "✅"

            user_display = f"User ID: {user_id_db}" # Default
            stored_first_name = user_doc.get("first_name")
            stored_username = user_doc.get("username")

            if stored_first_name: user_display = stored_first_name
            elif stored_username: user_display = f"@{stored_username}"
            # Removed the fallback get_chat for performance on leaderboards unless essential

            user_display_md = telebot.util.escape(user_display)
            leaderboard_entries.append(f"{i}. {rank_icon} {user_display_md} — *{referrals}* referrals")

        if not leaderboard_entries:
            bot.reply_to(message, "📊 No users with referrals found to display.")
            return

        total_participants = user_collection.count_documents({"has_joined": True})
        leaderboard_text = f"🏆 *Top {min(top_count, len(leaderboard_entries))} Referral Leaders*\n"
        leaderboard_text += f"_Total Participants: {total_participants}_\n\n"
        leaderboard_text += "\n".join(leaderboard_entries)

        bot.reply_to(message, leaderboard_text)
        logger.info(f"Sent leaderboard to admin {admin_user_id}.")

    except Exception as e:
        logger.exception(f"Error generating leaderboard: {e}")
        bot.reply_to(message, "Error generating the leaderboard.")


# --- Admin Commands ---

@bot.message_handler(commands=['start_giveaway'])
def start_giveaway(message):
    if message.from_user.id not in ADMINS: return
    admin_user_id = message.from_user.id
    logger.info(f"Admin {admin_user_id} triggered /start_giveaway")
    try:
        # Set giveaway state to active in DB
        bot_state_collection.update_one(
            {"state_id": BOT_STATE_ID},
            {"$set": {"giveaway_active": True}},
            upsert=True
        )
        # Optional: Reset referrals here IF you want every new giveaway to start fresh
        # reset_referrals() # Call helper if you create one
        # logger.info("Referral counts reset for new giveaway.")

        bot.reply_to(message, "✅ Giveaway state set to *ACTIVE*. Users can now use /join.")
        logger.info("Giveaway state set to ACTIVE in DB.")
    except Exception as e:
        logger.exception(f"Failed to start giveaway in DB: {e}")
        bot.reply_to(message, "❌ Failed to update giveaway state in the database.")


@bot.message_handler(commands=['end_giveaway'])
def end_giveaway(message):
    if message.from_user.id not in ADMINS: return
    admin_user_id = message.from_user.id
    logger.info(f"Admin {admin_user_id} triggered /end_giveaway")

    try:
        # 1. Determine the winner *before* resetting counts
        winner_pipeline = [
            {"$match": {"has_joined": True}},
            {"$sort": {"referrals": pymongo.DESCENDING, "join_time": pymongo.ASCENDING}},
            {"$limit": 1}
        ]
        winner_list = list(user_collection.aggregate(winner_pipeline))
        winner_announcement = "🏁 Giveaway ended. No participants found to determine a winner." # Default

        if winner_list:
            winner_doc = winner_list[0]
            winner_id = winner_doc.get("user_id")
            winner_referrals = winner_doc.get("referrals", 0)
            logger.info(f"Determined winner: {winner_id} with {winner_referrals} referrals.")

            winner_display = f"User ID {winner_id}"
            # Get display name (use stored first, then username, fallback to ID)
            if winner_doc.get("first_name"): winner_display = winner_doc.get("first_name")
            elif winner_doc.get("username"): winner_display = f"@{winner_doc.get('username')}"

            winner_display_md = telebot.util.escape(winner_display)
            winner_announcement = (f"🏁 *The giveaway has officially ended!*\n\n"
                                   f"🏆 Congratulations to the winner: *{winner_display_md}*!\n"
                                   f"They won with *{winner_referrals}* referrals!\n\n"
                                   f"Thank you all for participating!")
            logger.info(f"Winner announcement prepared for {winner_display_md}.")
        else:
            logger.info("Could not determine a winner (no participants found).")

        # 2. Set giveaway state to inactive
        bot_state_collection.update_one(
            {"state_id": BOT_STATE_ID},
            {"$set": {"giveaway_active": False}},
            upsert=True # Ensure state doc exists
        )
        logger.info("Giveaway state set to INACTIVE in DB.")

        # 3. Reset ALL user referral counts
        reset_result = user_collection.update_many(
            {}, # Empty filter matches all documents
            {"$set": {"referrals": 0}}
        )
        logger.info(f"Reset referral counts for {reset_result.modified_count} users.")

        # 4. Announce winner and completion
        bot.reply_to(message, f"{winner_announcement}\n\nGiveaway is now *INACTIVE*. Referral counts have been reset.")


    except Exception as e:
        logger.exception(f"Error during /end_giveaway process: {e}")
        bot.reply_to(message, "❌ An error occurred while ending the giveaway.")


@bot.message_handler(commands=['ping'])
def ping(message):
    logger.debug(f"Received /ping from {message.from_user.id}")
    start_time = time.time()
    try:
        # Check DB connection as part of ping
        db.command('ping')
        db_ok = True
    except Exception as e:
        logger.error(f"DB ping failed: {e}")
        db_ok = False

    try:
        reply_msg = bot.reply_to(message, "Checking...")
        end_time = time.time()
        latency = round((end_time - start_time) * 1000)
        status_text = f"Pong! ({latency}ms)\nDatabase: {'Connected ✅' if db_ok else 'Error ❌'}"
        bot.edit_message_text(status_text, chat_id=reply_msg.chat.id, message_id=reply_msg.message_id)
    except Exception as e:
         logger.error(f"Error processing ping response: {e}")


# --- Function to Set Bot Commands ---
def set_bot_commands():
    try:
        logger.info(f"Setting bot commands: {[c.command for c in COMMANDS]}")
        bot.set_my_commands(COMMANDS)
        logger.info("Successfully set bot commands in Telegram interface.")
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")


# --- Start the Bot ---
if __name__ == '__main__':
    logger.info("Bot starting...")
    logger.info(f"Required chats for join verification: {REQUIRED_CHATS}")
    logger.info(f"Admin User IDs: {ADMINS}")

    # Set the commands in Telegram UI
    set_bot_commands()

    try:
        # Increased timeout values for potentially slow networks or long polling
        bot.infinity_polling(timeout=30, long_polling_timeout=30, logger_level=logging.INFO)
    except KeyboardInterrupt:
        logger.info("Bot stopping due to KeyboardInterrupt (Ctrl+C)...")
    except Exception as e:
        logger.exception("CRITICAL: An unexpected error occurred during bot polling: %s", e)
    finally:
        logger.info("Closing MongoDB connection.")
        if mongo_client:
            mongo_client.close()
        logger.info("Bot polling stopped.")

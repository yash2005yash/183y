# -*- coding: utf-8 -*-
import telebot
import pymongo # For MongoDB
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import time
import os # For potential environment variables

# === CONFIGURATION ===
TOKEN = '7725594696:AAGo1lPrbtChtQkdBVT_JyzLg9fiAG3tgyI' # Replace with your actual Bot Token

# --- MongoDB Configuration ---
# WARNING: Hardcoding credentials is not recommended for production. Use environment variables.
MONGO_CONNECTION_STRING = "mongodb+srv://yesvashisht2005:Flirter@cluster0.7cqnnqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_DB_NAME = "telegramBot" # Choose a database name
MONGO_COLLECTION_NAME = "userData" # Choose a collection name

# --- Bot Configuration ---
CHANNEL_USERNAME = '@phg_hexa'  # Replace with your Channel username (e.g., @mychannel)
GROUP_USERNAME = '@phg_pokes'    # Replace with your Group username (e.g., @mygroup)
ADMINS = [123456789, 6265981509] # Replace/Add your Telegram user ID(s) as integers

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Get logger for this script

# --- Configuration Validation ---
if TOKEN == 'YOUR_BOT_TOKEN_HERE' or not TOKEN:
    logger.critical("CRITICAL: Bot token is not set!")
    exit(1)
if not MONGO_CONNECTION_STRING or "YOUR_MONGO_CONNECTION_STRING" in MONGO_CONNECTION_STRING:
     logger.critical("CRITICAL: MongoDB connection string is not set!")
     exit(1)
# Add other config warnings as before...

# --- Initialize MongoDB Connection ---
try:
    mongo_client = pymongo.MongoClient(MONGO_CONNECTION_STRING)
    # The ismaster command is cheap and does not require auth.
    mongo_client.admin.command('ismaster')
    db = mongo_client[MONGO_DB_NAME]
    user_collection = db[MONGO_COLLECTION_NAME]
    # Create index on user_id for faster lookups if it doesn't exist
    user_collection.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    logger.info(f"Successfully connected to MongoDB Atlas. Database: '{MONGO_DB_NAME}', Collection: '{MONGO_COLLECTION_NAME}'")
except pymongo.errors.ConnectionFailure as e:
    logger.critical(f"CRITICAL: Failed to connect to MongoDB Atlas. Check connection string, firewall rules, or network. Error: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"CRITICAL: An unexpected error occurred during MongoDB initialization: {e}")
    exit(1)


# --- Initialize Bot ---
try:
    bot = telebot.TeleBot(TOKEN)
    bot_info = bot.get_me()
    logger.info(f"Successfully connected to Telegram API as bot: @{bot_info.username} (ID: {bot_info.id})")
except telebot.apihelper.ApiTelegramException as e:
    logger.critical(f"CRITICAL: Failed to connect to Telegram API. Check token. Error: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"CRITICAL: An unexpected error occurred during bot initialization: {e}")
    exit(1)


# In-memory storage for referral links clicked via /start before join confirmation
ref_mapping = {}

# --- Bot Command Handlers ---

@bot.message_handler(commands=['start'])
def start(message):
    user_id_int = message.from_user.id # Use integer ID
    user_first_name = message.from_user.first_name or "User"
    args = message.text.split()
    potential_referrer_id_str = None

    logger.info(f"/start command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    # Store potential referrer if 'start' command has a payload
    if len(args) > 1:
        ref_payload = args[1]
        if ref_payload.isdigit() and ref_payload != str(user_id_int):
            ref_mapping[user_id_int] = ref_payload # Store as string temporarily
            potential_referrer_id_str = ref_payload
            logger.info(f"User {user_id_int} started with referral payload from {potential_referrer_id_str}.")
        else:
             logger.warning(f"User {user_id_int} provided invalid referral payload: {ref_payload}")

    # Check if user already joined (fetch from DB)
    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            logger.debug(f"User {user_id_int} is already joined. Sending existing participant message.")
            bot.send_message(message.chat.id, f"Hello {user_first_name}! 👋\nYou are already participating. Use /myref to get your referral link.")
        else:
            logger.debug(f"User {user_id_int} is new or hasn't joined yet. Sending welcome message.")
            bot.send_message(message.chat.id, f"Hello {user_first_name}, welcome to the bot! 👋\nUse /join to participate.")
    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} in /start: {e}")
        bot.send_message(message.chat.id, "Sorry, an error occurred. Please try again.")


@bot.message_handler(commands=['join'])
def join(message):
    user_id_int = message.from_user.id
    logger.info(f"/join command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    # Check if user already successfully joined
    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            logger.debug(f"User {user_id_int} tried to /join but is already joined.")
            bot.send_message(message.chat.id, "You have already joined the giveaway. Use /myref.")
            return
    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} in /join: {e}")
        bot.send_message(message.chat.id, "Sorry, an error occurred. Please try again.")
        return

    # Check if required config is present
    if not CHANNEL_USERNAME or not GROUP_USERNAME:
         logger.error(f"Cannot process /join for {user_id_int} because Channel/Group username is not configured.")
         bot.send_message(message.chat.id, "⚠️ Sorry, the bot is not fully configured. Please contact the administrator.")
         return

    markup = InlineKeyboardMarkup(row_width=1)
    try:
        channel_link = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        group_link = f"https://t.me/{GROUP_USERNAME.lstrip('@')}"
        markup.add(InlineKeyboardButton("➡️ Join Channel", url=channel_link))
        markup.add(InlineKeyboardButton("➡️ Join Group", url=group_link))
        markup.add(InlineKeyboardButton("✅ I Joined", callback_data="verify_join"))
        bot.send_message(message.chat.id, "👇 Please join our channel and group below, then click 'I Joined':", reply_markup=markup)
        logger.debug(f"Sent join instructions and buttons to user {user_id_int}.")
    except Exception as e:
        logger.exception(f"Failed to send join message/buttons to {user_id_int}: {e}")
        bot.send_message(message.chat.id, "😥 An error occurred showing the join options. Please try again.")


@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join_callback(call):
    user_id_int = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    logger.info(f"Verification callback ('verify_join') received from user {user_id_int} ({call.from_user.username or 'no username'})")

    # Prevent rapid clicking / re-processing if already joined
    try:
        user_doc_check = user_collection.find_one({"user_id": user_id_int})
        if user_doc_check and user_doc_check.get("has_joined", False):
            logger.debug(f"User {user_id_int} clicked verify but already marked as joined. Answering callback.")
            bot.answer_callback_query(call.id, "You have already joined.", show_alert=False)
            try: bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None) # Attempt to remove buttons
            except: pass # Ignore errors removing buttons
            return
    except Exception as e:
        logger.exception(f"Error checking user status for {user_id_int} at start of verify_join_callback: {e}")
        bot.answer_callback_query(call.id, "❌ An unexpected server error occurred. Please try again later.", show_alert=True)
        return

    # Check membership (same logic as before)
    try:
        logger.debug(f"Checking channel ({CHANNEL_USERNAME}) membership for user {user_id_int}...")
        chan_member = bot.get_chat_member(CHANNEL_USERNAME, user_id_int)
        valid_statuses = ['member', 'administrator', 'creator']
        if chan_member.status not in valid_statuses:
            logger.warning(f"User {user_id_int} not in channel {CHANNEL_USERNAME} (status: {chan_member.status}). Verification failed.")
            bot.answer_callback_query(call.id, f"❌ You must join the Channel ({CHANNEL_USERNAME}) first!", show_alert=True)
            return

        logger.debug(f"Checking group ({GROUP_USERNAME}) membership for user {user_id_int}...")
        grp_member = bot.get_chat_member(GROUP_USERNAME, user_id_int)
        if grp_member.status not in valid_statuses:
            logger.warning(f"User {user_id_int} not in group {GROUP_USERNAME} (status: {grp_member.status}). Verification failed.")
            bot.answer_callback_query(call.id, f"❌ You must join the Group ({GROUP_USERNAME}) first!", show_alert=True)
            return

        logger.info(f"User {user_id_int} verified membership in both channel and group.")

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"API Error checking membership for {user_id_int}: {e}")
        error_message = "❌ An error occurred during verification. Please try again."
        # Add specific checks as before (CHAT_ADMIN_REQUIRED, etc.)
        desc = str(e).lower()
        if "user not found" in desc: error_message = "❌ Could not verify membership. Ensure you've joined both."
        elif "chat not found" in desc: error_message = f"❌ Bot error: Cannot find channel/group. Contact admin."
        elif "bot is not a member" in desc or "bot was kicked" in desc or "chat_admin_required" in desc:
             error_message = "❌ Bot error: Bot needs admin rights in channel/group. Contact admin."
        bot.answer_callback_query(call.id, error_message, show_alert=True)
        return
    except Exception as e:
        logger.exception(f"Unexpected error checking membership for {user_id_int}: {e}")
        bot.answer_callback_query(call.id, "❌ An unexpected server error occurred. Please try again later.", show_alert=True)
        return

    # --- User passed membership checks ---

    # Retrieve potential referrer ID from temporary map and remove it
    referrer_id_str = ref_mapping.pop(user_id_int, None)
    referrer_id_int = None
    if referrer_id_str and referrer_id_str.isdigit():
        referrer_id_int = int(referrer_id_str)
        logger.debug(f"Found potential referrer {referrer_id_int} for user {user_id_int} from ref_mapping.")

    # --- Update Database ---
    try:
        current_time = time.time()
        # Use update_one with upsert=True to handle both new and existing users cleanly
        update_result = user_collection.update_one(
            {"user_id": user_id_int},
            {
                "$set": {
                    "has_joined": True,
                    "username": call.from_user.username, # Store username for convenience
                    "first_name": call.from_user.first_name # Store first name
                },
                "$setOnInsert": { # Fields set only when inserting a new document (upsert)
                    "join_time": current_time,
                    "referrals": 0,
                    "referred_by": referrer_id_int # Store int or None
                }
            },
            upsert=True # Create the document if it doesn't exist
        )

        if update_result.upserted_id is not None:
            logger.info(f"New user {user_id_int} inserted into DB. Referred by: {referrer_id_int or 'None'}.")
            is_newly_joined = True
        elif update_result.modified_count > 0:
            logger.info(f"Existing user {user_id_int} marked as joined in DB.")
            # Check if we need to set referrer for existing user who hadn't confirmed join
            # This logic is simplified by $setOnInsert, but can be added if needed:
            # user_doc_after_update = user_collection.find_one({"user_id": user_id_int})
            # if user_doc_after_update and user_doc_after_update.get("referred_by") is None and referrer_id_int is not None:
            #    user_collection.update_one({"user_id": user_id_int}, {"$set": {"referred_by": referrer_id_int}})
            #    logger.info(f"Set referred_by for existing user {user_id_int} to {referrer_id_int}")
            is_newly_joined = True # Treat as newly joined for referral notification
        else:
             logger.warning(f"User {user_id_int} document found but not modified (already joined?). UpsertedId: {update_result.upserted_id}, Matched: {update_result.matched_count}")
             is_newly_joined = False # Don't process referral again

        # Edit the original message upon success
        try:
            bot.edit_message_text("✅ You’ve successfully joined the giveaway! Welcome!", chat_id, message_id, reply_markup=None)
        except Exception as edit_e:
            logger.warning(f"Could not edit original message for {user_id_int} after join ({edit_e}). Sending new message.")
            bot.send_message(chat_id, "✅ You’ve successfully joined the giveaway! Welcome!")

        # Process referral increment and notification only if newly joined/confirmed and referrer exists
        if is_newly_joined and referrer_id_int:
            try:
                ref_update_result = user_collection.update_one(
                    {"user_id": referrer_id_int},
                    {"$inc": {"referrals": 1}}
                )
                if ref_update_result.matched_count > 0:
                    # Fetch the updated count to notify the referrer accurately
                    referrer_doc = user_collection.find_one({"user_id": referrer_id_int})
                    new_ref_count = referrer_doc.get("referrals", "N/A") if referrer_doc else "N/A"
                    logger.info(f"Incremented referral count for {referrer_id_int}. New total: {new_ref_count}")

                    # Notify referrer
                    try:
                        joiner_name = call.from_user.first_name or "Someone"
                        bot.send_message(referrer_id_int, f"🎉 Great news! {joiner_name} joined using your referral link.\nYour total referrals: *{new_ref_count}*", parse_mode="Markdown")
                    except Exception as notify_e:
                        logger.warning(f"Failed to send referral notification to {referrer_id_int}: {notify_e}")
                else:
                     logger.warning(f"Referrer ID {referrer_id_int} not found in DB to increment count.")

            except Exception as ref_e:
                logger.exception(f"Unexpected error processing referral increment for {referrer_id_int}: {ref_e}")

    except Exception as db_e:
        logger.exception(f"Database error during user update/insertion for {user_id_int}: {db_e}")
        bot.answer_callback_query(call.id, "❌ A database error occurred. Please try again later.", show_alert=True)


@bot.message_handler(commands=['myref'])
def myref(message):
    user_id_int = message.from_user.id
    logger.info(f"/myref command received from user {user_id_int} ({message.from_user.username or 'no username'})")

    try:
        user_doc = user_collection.find_one({"user_id": user_id_int})
        if user_doc and user_doc.get("has_joined", False):
            bot_username = bot_info.username
            ref_link = f"https://t.me/{bot_username}?start={user_id_int}"
            ref_count = user_doc.get("referrals", 0)
            logger.debug(f"Generating referral link for {user_id_int}. Count: {ref_count}")
            bot.send_message(message.chat.id,
                             f"🔗 *Your personal referral link:*\n"
                             f"`{ref_link}`\n\n"
                             f"🫂 You have successfully referred *{ref_count}* user(s).\n\n"
                             f"Share this link with friends!",
                             parse_mode="Markdown", disable_web_page_preview=True)
        else:
            logger.debug(f"User {user_id_int} tried /myref but hasn't joined.")
            bot.send_message(message.chat.id, "You haven’t joined the giveaway yet. Use /join first.")
    except Exception as e:
        logger.exception(f"Error fetching user data or sending ref link for {user_id_int}: {e}")
        bot.send_message(message.chat.id, "😥 Could not get your referral link right now. Please try again.")


# Renamed from /prog to /top
@bot.message_handler(commands=['top'])
def top_referrers(message):
    admin_user_id = message.from_user.id
    logger.info(f"/top command received from user {admin_user_id} ({message.from_user.username or 'no username'})")

    # Admin check
    if admin_user_id not in ADMINS:
        logger.warning(f"Unauthorized /top attempt by {admin_user_id}.")
        bot.reply_to(message, "⛔ This command is restricted to administrators.")
        return

    top_count = 25
    leaderboard_entries = []
    medals = ["🥇", "🥈", "🥉"]
    fetch_errors = 0

    try:
        # Fetch top participants from MongoDB, sorted by referrals descending
        pipeline = [
            {"$match": {"has_joined": True, "referrals": {"$gt": 0}}}, # Only users who joined and have > 0 refs
            {"$sort": {"referrals": pymongo.DESCENDING, "join_time": pymongo.ASCENDING}}, # Sort by refs desc, join time asc
            {"$limit": top_count}
        ]
        top_users_cursor = user_collection.aggregate(pipeline)
        # Alternative simpler find:
        # top_users_cursor = user_collection.find(
        #     {"has_joined": True}
        # ).sort("referrals", pymongo.DESCENDING).limit(top_count)

        logger.debug(f"Generating leaderboard. Fetching top {top_count} users from DB.")

        participant_list = list(top_users_cursor) # Execute query

        if not participant_list:
             bot.send_message(message.chat.id, "📊 Leaderboard is empty. No participants with referrals found.")
             return

        for i, user_doc in enumerate(participant_list, start=1):
            user_id_db = user_doc.get("user_id")
            referrals = user_doc.get("referrals", 0)

            if user_id_db is None:
                logger.warning("Found document in leaderboard query without user_id, skipping.")
                continue

            rank_icon = ""
            if i <= 3: rank_icon = medals[i - 1]
            elif i <= 10: rank_icon = "🔥"
            elif i <= 20: rank_icon = "⚡"
            else: rank_icon = "✅"

            # Display Name Logic (Prioritize stored name, fallback to get_chat)
            user_display = f"User ID: {user_id_db}" # Default
            stored_first_name = user_doc.get("first_name")
            stored_username = user_doc.get("username")

            if stored_first_name:
                user_display = stored_first_name
            elif stored_username:
                user_display = f"@{stored_username}"
            else: # Fallback: try fetching fresh info if not stored
                try:
                    user_info = bot.get_chat(user_id_db) # Use int ID
                    display_name = user_info.first_name
                    if user_info.last_name: display_name += f" {user_info.last_name}"
                    if display_name: user_display = display_name.strip()
                    elif user_info.username: user_display = f"@{user_info.username}"
                except Exception as e:
                    logger.warning(f"Could not fetch user info for {user_id_db} for leaderboard: {e}")
                    fetch_errors += 1

            user_display_md = telebot.util.escape(user_display)
            leaderboard_entries.append(f"{i}. {rank_icon} {user_display_md} — *{referrals}* referrals")

        if not leaderboard_entries:
            bot.send_message(message.chat.id, "📊 No users with referrals found to display.")
            return

        # Get total participant count separately (more efficient than counting full sorted list)
        total_participants = user_collection.count_documents({"has_joined": True})

        leaderboard_text = f"🏆 *Top {min(top_count, len(leaderboard_entries))} Referral Leaders*\n"
        leaderboard_text += f"_Total Participants: {total_participants}_\n\n"
        leaderboard_text += "\n".join(leaderboard_entries)
        if fetch_errors > 0:
            leaderboard_text += f"\n\n_(Note: Could not fetch fresh info for {fetch_errors} user(s))_"

        bot.send_message(message.chat.id, leaderboard_text, parse_mode="Markdown")
        logger.info(f"Sent leaderboard to admin {admin_user_id}.")

    except Exception as e:
        logger.exception(f"Error generating leaderboard: {e}")
        bot.send_message(message.chat.id, "Error generating the leaderboard.")


# --- Admin Commands --- (Keep names or change as desired)

@bot.message_handler(commands=['start_giveaway'])
def start_giveaway(message):
    if message.from_user.id not in ADMINS: return
    logger.info(f"Admin {message.from_user.id} triggered /start_giveaway")
    bot.reply_to(message, "🎉 Giveaway officially marked as started!")


@bot.message_handler(commands=['end_giveaway'])
def end_giveaway(message):
    if message.from_user.id not in ADMINS: return
    admin_user_id = message.from_user.id
    logger.info(f"Admin {admin_user_id} triggered /end_giveaway")

    try:
        # Find winner (top referrer) directly from DB
        winner_pipeline = [
            {"$match": {"has_joined": True}},
            {"$sort": {"referrals": pymongo.DESCENDING, "join_time": pymongo.ASCENDING}},
            {"$limit": 1}
        ]
        winner_list = list(user_collection.aggregate(winner_pipeline))

        if winner_list:
            winner_doc = winner_list[0]
            winner_id = winner_doc.get("user_id")
            winner_referrals = winner_doc.get("referrals", 0)
            logger.info(f"Determined winner: {winner_id} with {winner_referrals} referrals.")

            winner_display = f"User ID {winner_id}"
            stored_first_name = winner_doc.get("first_name")
            stored_username = winner_doc.get("username")
            if stored_first_name: winner_display = stored_first_name
            elif stored_username: winner_display = f"@{stored_username}"
            # Add fallback get_chat if needed

            winner_display_md = telebot.util.escape(winner_display)
            announcement = (f"🏁 *The giveaway has officially ended!*\n\n"
                            f"🏆 Congratulations to the winner: *{winner_display_md}*!\n"
                            f"They won with *{winner_referrals}* referrals!\n\n"
                            f"Thank you all for participating!")
            bot.reply_to(message, announcement, parse_mode="Markdown")
            logger.info(f"Announced winner ({winner_display_md}) to admin {admin_user_id}.")
        else:
            logger.info("Could not determine a winner (no participants found).")
            bot.reply_to(message, "🏁 Giveaway ended. No participants found to determine a winner.")

    except Exception as e:
        logger.exception(f"Error determining giveaway winner: {e}")
        bot.reply_to(message, "Error determining the winner.")


@bot.message_handler(commands=['ping'])
def ping(message):
    """ Basic health check command """
    logger.debug(f"Received /ping from {message.from_user.id}")
    start_time = time.time()
    try:
        reply_msg = bot.reply_to(message, "Pong!")
        end_time = time.time()
        latency = round((end_time - start_time) * 1000) # Latency in ms
        bot.edit_message_text(f"Pong! ({latency}ms)", chat_id=reply_msg.chat.id, message_id=reply_msg.message_id)
    except Exception as e:
         logger.error(f"Error processing ping: {e}")


# --- Start the Bot ---
if __name__ == '__main__':
    logger.info("Bot starting...")
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except KeyboardInterrupt:
        logger.info("Bot stopping due to KeyboardInterrupt (Ctrl+C)...")
    except Exception as e:
        logger.exception("CRITICAL: An unexpected error occurred during bot polling: %s", e)
    finally:
        logger.info("Closing MongoDB connection.")
        mongo_client.close() # Close the connection when bot stops
        logger.info("Bot polling stopped.")

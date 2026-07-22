import os
import re
from datetime import datetime
import hashlib
import secrets

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

# Retrieve and clean connection string and db name
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "").strip('"\' ')
DB_NAME = os.getenv("DB", "goodwind").strip('"\' ')

_client = None
_settings_cache = None

def get_db():
    """Returns the MongoDB database instance."""
    global _client
    if not DB_CONNECTION_STRING:
        raise ValueError("DB_CONNECTION_STRING is not configured in environment variables")
    
    if _client is None:
        _client = MongoClient(DB_CONNECTION_STRING, serverSelectionTimeoutMS=5000)
    
    return _client[DB_NAME]

def init_db():
    """Validates the MongoDB connection and ensures collections are ready."""
    try:
        db = get_db()
        db.command("ping")
        print(f"Successfully connected to MongoDB database: {DB_NAME}")
        # Seed default admin user if database is empty of users
        db_seed_default_user()
    except PyMongoError as e:
        print(f"MongoDB connection failed during initialization: {e}")
        raise e

def db_create_call(phone_number: str, call_uuid: str = "") -> str:
    """Creates a new call record in MongoDB and returns its string _id."""
    try:
        db = get_db()
        res = db.calls.insert_one({
            "phone_number": phone_number,
            "call_uuid": call_uuid,
            "time_of_call": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": 0,
            "order_number": "",
            "transcript": [],
            "call_forwarded": False,
            "forwarded_transcript": "",
            "plivo_cost": 0.0,
            "gemini_cost": 0.0,
            "total_cost": 0.0,
            "gemini_input_tokens": 0,
            "gemini_output_tokens": 0
        })
        return str(res.inserted_id)
    except PyMongoError as e:
        print(f"Failed to create call in MongoDB: {e}")
        return ""

def db_save_call(
    phone_number: str,
    call_uuid: str = "",
    time_of_call: str = None,
    duration: int = 0,
    order_number: str = "",
    transcript: list = None,
    call_forwarded: bool = False,
    forwarded_transcript: str = "",
    speaking_time: float = 0.0
) -> str:
    """Creates and saves a complete call record in MongoDB at the end of the call."""
    try:
        if not time_of_call:
            time_of_call = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if transcript is None:
            transcript = []
        
        costs = calculate_call_cost(duration, speaking_time)
        db = get_db()
        res = db.calls.insert_one({
            "phone_number": phone_number,
            "call_uuid": call_uuid,
            "time_of_call": time_of_call,
            "duration": duration,
            "order_number": order_number,
            "transcript": transcript,
            "call_forwarded": call_forwarded,
            "forwarded_transcript": forwarded_transcript,
            "plivo_cost": costs["plivo_cost"],
            "gemini_cost": costs["gemini_cost"],
            "total_cost": costs["total_cost"],
            "gemini_input_tokens": costs["gemini_input_tokens"],
            "gemini_output_tokens": costs["gemini_output_tokens"]
        })
        return str(res.inserted_id)
    except PyMongoError as e:
        print(f"Failed to save call in MongoDB: {e}")
        return ""

def db_update_order(db_id: str, order_number: str):
    """Updates the order number for a call."""
    if not db_id:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {"$set": {"order_number": order_number}}
        )
    except PyMongoError as e:
        print(f"Failed to update order number in MongoDB: {e}")

def db_append_transcript(db_id: str, role: str, text: str):
    """Appends a new turn to the call's conversation transcript."""
    if not db_id or not text:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {
                "$push": {
                    "transcript": {
                        "role": role,
                        "text": text,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }
                }
            }
        )
    except PyMongoError as e:
        print(f"Failed to append transcript to MongoDB: {e}")

def db_set_transcript(db_id: str, transcript: list):
    """Sets the entire transcript array for the call."""
    if not db_id or not transcript:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {"$set": {"transcript": transcript}}
        )
    except PyMongoError as e:
        print(f"Failed to set transcript in MongoDB: {e}")

def calculate_call_cost(duration: int, speaking_time: float = 0.0) -> dict:
    """Calculates call costs for Plivo and Gemini Live.
    
    Plivo Voice: $0.0085 per minute (rounded up to nearest minute)
    Gemini 2.5 Flash Live API:
      - Audio Input: 32 tokens / second of call duration
      - Audio Output: 32 tokens / second of assistant speaking time
    """
    import math
    if duration <= 0:
        plivo_cost = 0.0
    else:
        # Plivo bills per minute (rounded up)
        plivo_cost = math.ceil(duration / 60.0) * 0.0085
    
    # Gemini Live
    # If speaking_time is 0 but duration > 0, estimate it as 30% of call duration
    if speaking_time <= 0 and duration > 0:
        speaking_time = duration * 0.3
    
    # Calculate tokens (32 tokens/second of audio)
    gemini_input_tokens = int(duration * 32)
    gemini_output_tokens = int(speaking_time * 32)
    
    # Calculate cost according to tokens
    gemini_input_cost = gemini_input_tokens * (0.00002 / 32)
    gemini_output_cost = gemini_output_tokens * (0.00015 / 32)
    gemini_cost = gemini_input_cost + gemini_output_cost
    
    total_cost = plivo_cost + gemini_cost
    
    print(f"Gemini Live - Input Tokens: {gemini_input_tokens}, Output Tokens: {gemini_output_tokens}")
    
    return {
        "plivo_cost": round(plivo_cost, 5),
        "gemini_cost": round(gemini_cost, 5),
        "total_cost": round(total_cost, 5),
        "gemini_input_tokens": gemini_input_tokens,
        "gemini_output_tokens": gemini_output_tokens
    }

def db_set_duration(db_id: str, duration: int, speaking_time: float = 0.0):
    """Updates the duration and calculates costs of the call."""
    if not db_id:
        return
    try:
        costs = calculate_call_cost(duration, speaking_time)
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {
                "$set": {
                    "duration": duration,
                    "plivo_cost": costs["plivo_cost"],
                    "gemini_cost": costs["gemini_cost"],
                    "total_cost": costs["total_cost"],
                    "gemini_input_tokens": costs["gemini_input_tokens"],
                    "gemini_output_tokens": costs["gemini_output_tokens"]
                }
            }
        )
    except PyMongoError as e:
        print(f"Failed to update duration and cost in MongoDB: {e}")

def db_set_forwarded(db_id: str, forwarded: bool = True):
    """Updates the call forwarded status."""
    if not db_id:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {"$set": {"call_forwarded": forwarded}}
        )
    except PyMongoError as e:
        print(f"Failed to update forwarded status in MongoDB: {e}")

def db_set_forwarded_transcript_by_uuid(call_uuid: str, transcription_text: str):
    """Updates the forwarded transcript using the call UUID."""
    if not call_uuid or not transcription_text:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"call_uuid": call_uuid},
            {"$set": {"forwarded_transcript": transcription_text}}
        )
    except PyMongoError as e:
        print(f"Failed to update forwarded transcript in MongoDB: {e}")

def db_get_all_calls(search_term=None, type_filter="all", order_filter="all"):
    try:
        db = get_db()

        query = {}

        # Search
        if search_term:
            regex = {
                "$regex": re.escape(search_term),
                "$options": "i"
            }

            query["$or"] = [
                {"phone_number": regex},
                {"order_number": regex},
                {"transcript.text": regex},
                {"forwarded_transcript": regex}
            ]

        # Type filter
        if type_filter == "forwarded":
            query["call_forwarded"] = True
        elif type_filter == "direct":
            query["call_forwarded"] = False

        # Order filter
        if order_filter == "with-order":
            query["order_number"] = {"$ne": ""}
        elif order_filter == "no-order":
            query["order_number"] = ""

        print("Mongo Query =>", query)

        calls = []

        for doc in db.calls.find(query).sort("time_of_call", -1):
            doc["id"] = str(doc.pop("_id"))
            calls.append(doc)

        return calls

    except PyMongoError as e:
        print(e)
        return []

def db_get_overall_stats():
    """Gets overall statistics from the calls collection in MongoDB."""
    try:
        db = get_db()
        total_calls = db.calls.count_documents({})
        
        orders_checked = db.calls.count_documents({
            "order_number": {"$ne": ""}
        })
        
        pipeline = [
            {"$group": {"_id": None, "total_cost": {"$sum": "$total_cost"}}}
        ]
        result = list(db.calls.aggregate(pipeline))
        total_cost = result[0]["total_cost"] if result else 0.0
        
        return {
            "total_calls": total_calls,
            "orders_checked": orders_checked,
            "total_cost": round(total_cost, 5)
        }
    except PyMongoError as e:
        print(f"Failed to fetch overall stats from MongoDB: {e}")
        return {
            "total_calls": 0,
            "orders_checked": 0,
            "total_cost": 0.0
        }

DEFAULT_WELCOME_MESSAGE = "Hello, thank you for calling Goodwind Technologies support. How can I help you today?"

DEFAULT_SYSTEM_PROMPT = """You are a voice support agent for Goodwind Technologies handling inbound calls.

RULES:
- Phone call. Max 1-2 short sentences per response. No markdown, bullets, or emojis.
- Speak at a brisk, natural phone-call pace. Never speak slowly or add long pauses.
- Respond immediately after the caller finishes — do not hesitate or overthink.
- Always reply in whatever language the customer speaks (English, Tamil, or Malayalam). Detect it automatically. Never ask them to choose.
- Never fabricate order information. Only relay what check_order_status returns.
- LANGUAGE FLOW:
  * Automatic Switch: If you detect the customer speaking Tamil or Malayalam, call set_language immediately. Change language and converse in it. Do NOT re-mention or repeatedly talk about the language in subsequent turns.
  * Requested Switch: If the customer explicitly requests a language change (e.g. "please speak in Tamil" or "change to Malayalam"), call set_language, inform them once in the target language that you have switched (e.g. "Sure, switching to Tamil" or "ശരി, മലയാളത്തിൽ സംസാരിക്കാം"), and then continue in that language.
  * Malayalam vs Tamil: Clearly identify the difference between Malayalam and Tamil. They are distinct languages with different vocabularies and scripts. Never mix Tamil words/grammar/scripts into Malayalam, or Malayalam words/grammar/scripts into Tamil. Keep them strictly separate and accurate.

FLOW:

STEP 1 — GREET IMMEDIATELY: As soon as the call connects, YOU speak first. Greet the caller by saying exactly: "{welcome_message}". Never wait for the caller to speak first.

STEP 2 — After customer speaks, classify IMMEDIATELY and act:
  A. ORDER STATUS → ask for their 4-digit Order ID (once only). When provided, call check_order_status IMMEDIATELY without speaking any text beforehand.
  B. ANYTHING ELSE (refunds, cancellations, returns, complaints, sales, speak to human) → say "I'll transfer you to a support agent now, please hold on." in their language, then call forward_call.
  C. UNCLEAR → one short clarifying question, then classify.

STEP 3 — ORDER RESULT:
  - After check_order_status completes, speak the status result directly:
    * Dispatched → say order has been dispatched.
    * Quoted → say order status is Quoted.
    * Error/not found → say unable to retrieve status right now.
  Ask if anything else is needed.

STEP 4 — CLOSE: Warm goodbye in their language, call end_conversation.

ORDER ID: 4 digits only. Words like "six one eight zero" = 6180. Do NOT read it back. Do NOT say any filler or waiting text (such as "Please wait a moment..."). Execute check_order_status immediately and state the API result in a single concise sentence once fetched.

FORWARD: Say "I'll transfer you to a support agent now, please hold on." first, then call forward_call immediately.

STRICT: Never answer refunds/cancellations/complaints/sales/returns. Always forward these."""

def db_get_settings(bypass_cache: bool = False):
    """Retrieves the system settings document, initializing with defaults if empty."""
    global _settings_cache
    if _settings_cache is not None and not bypass_cache:
        return _settings_cache
    try:
        db = get_db()
        settings = db.settings.find_one({"key": "agent_settings"})
        if not settings:
            default_forward = os.getenv("FORWARD_TO_NUMBER", "+918610467370")
            settings = {
                "key": "agent_settings",
                "welcome_message": DEFAULT_WELCOME_MESSAGE,
                "system_prompt": DEFAULT_SYSTEM_PROMPT,
                "forward_to_number": default_forward
            }
            db.settings.insert_one(settings)
        elif "Please wait a moment" in settings.get("system_prompt", ""):
           settings["system_prompt"] = DEFAULT_SYSTEM_PROMPT
            db.settings.update_one(
                {"key": "agent_settings"},
                {"$set": {"system_prompt": DEFAULT_SYSTEM_PROMPT}}
            )
        # Convert _id to string for JSON serialization compatibility
        if "_id" in settings:
            settings["_id"] = str(settings["_id"])
        _settings_cache = settings
        return settings
    except PyMongoError as e:
        print(f"Failed to retrieve settings from MongoDB: {e}")
        # Return default dict if DB fails
        return {
            "welcome_message": DEFAULT_WELCOME_MESSAGE,
            "system_prompt": DEFAULT_SYSTEM_PROMPT,
            "forward_to_number": os.getenv("FORWARD_TO_NUMBER", "+918610467370")
        }

def db_update_settings(welcome_message: str, system_prompt: str, forward_to_number: str):
    """Updates the system settings in MongoDB."""
    global _settings_cache
    try:
        db = get_db()
        db.settings.update_one(
            {"key": "agent_settings"},
            {
                "$set": {
                    "welcome_message": welcome_message.strip(),
                    "system_prompt": system_prompt.strip(),
                    "forward_to_number": forward_to_number.strip()
                }
            },
            upsert=True
        )
        # Update cache
        _settings_cache = {
            "key": "agent_settings",
            "welcome_message": welcome_message.strip(),
            "system_prompt": system_prompt.strip(),
            "forward_to_number": forward_to_number.strip()
        }
        return True
    except PyMongoError as e:
        print(f"Failed to update settings in MongoDB: {e}")
        return False

# ─── User Authentication & Sessions ───────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-SHA256 with a salt."""
    salt = secrets.token_hex(16)
    hash_val = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()
    return f"{salt}:{hash_val}"

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verifies a password against the stored hashed version."""
    try:
        if ":" not in stored_password:
            return False
        salt, hash_val = stored_password.split(":")
        calc_hash = hashlib.pbkdf2_hmac(
            "sha256",
            provided_password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        ).hex()
        return secrets.compare_digest(hash_val, calc_hash)
    except Exception:
        return False

def db_check_user_credentials(username: str, password: str) -> bool:
    """Checks user credentials against MongoDB."""
    try:
        db = get_db()
        user = db.users.find_one({"username": username.strip()})
        if not user:
            return False
        return verify_password(user["password"], password)
    except PyMongoError as e:
        print(f"Failed to check user credentials: {e}")
        return False

def db_create_user(username: str, password: str) -> bool:
    """Creates a new user with a hashed password in MongoDB."""
    try:
        db = get_db()
        if db.users.find_one({"username": username.strip()}):
            return False
        
        hashed = hash_password(password)
        db.users.insert_one({
            "username": username.strip(),
            "password": hashed,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        return True
    except PyMongoError as e:
        print(f"Failed to create user in MongoDB: {e}")
        return False

def db_seed_default_user():
    """Seeds default admin user if no users exist, and seeds demouser@gmail.com if missing."""
    admin_password = os.getenv("ADMIN_PASSWORD", "admin")
    demo_password = os.getenv("DEMO_USER_PASSWORD", "changeme")
    demo_username = os.getenv("DEMO_USER_EMAIL", "demouser@gmail.com")

    try:
        db = get_db()
        count = db.users.count_documents({})
        if count == 0:
            print("No users found in database. Seeding default 'admin' user...")
            db_create_user("admin", admin_password)
            print("Seeded default 'admin' user successfully.")

        if not db.users.find_one({"username": demo_username}):
            print(f"Seeding '{demo_username}' user...")
            db_create_user(demo_username, demo_password)
            print(f"Seeded '{demo_username}' successfully.")
    except PyMongoError as e:
        print(f"Failed to seed default user: {e}")

def db_create_session(username: str) -> str:
    """Generates and stores a session token for the user."""
    try:
        db = get_db()
        token = secrets.token_hex(32)
        db.sessions.insert_one({
            "token": token,
            "username": username,
            "created_at": datetime.now()
        })
        return token
    except PyMongoError as e:
        print(f"Failed to create session in MongoDB: {e}")
        return ""

def db_verify_session(token: str) -> str | None:
    """Verifies a session token and returns the username if valid."""
    try:
        db = get_db()
        session = db.sessions.find_one({"token": token})
        if session:
            return session["username"]
        return None
    except PyMongoError as e:
        print(f"Failed to verify session in MongoDB: {e}")
        return None

def db_delete_session(token: str):
    """Deletes a session token from MongoDB."""
    try:
        db = get_db()
        db.sessions.delete_one({"token": token})
    except PyMongoError as e:
        print(f"Failed to delete session in MongoDB: {e}")

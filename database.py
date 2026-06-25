import os
from datetime import datetime

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

# Retrieve and clean connection string and db name
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING", "").strip('"\' ')
DB_NAME = os.getenv("DB", "goodwind").strip('"\' ')

_client = None

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
            "forwarded_transcript": ""
        })
        return str(res.inserted_id)
    except PyMongoError as e:
        print(f"Failed to create call in MongoDB: {e}")
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

def db_set_duration(db_id: str, duration: int):
    """Updates the duration of the call in seconds."""
    if not db_id:
        return
    try:
        db = get_db()
        db.calls.update_one(
            {"_id": ObjectId(db_id)},
            {"$set": {"duration": duration}}
        )
    except PyMongoError as e:
        print(f"Failed to update duration in MongoDB: {e}")

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

def db_get_all_calls():
    """Retrieves all call logs, ordered by time of call descending, mapping _id to id."""
    try:
        db = get_db()
        calls = []
        for doc in db.calls.find().sort("time_of_call", -1):
            doc["id"] = str(doc.pop("_id"))
            calls.append(doc)
        return calls
    except PyMongoError as e:
        print(f"Failed to retrieve calls from MongoDB: {e}")
        return []

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
  A. ORDER STATUS → ask for their 4-digit Order ID (once only), call check_order_status, relay result.
  B. ANYTHING ELSE (refunds, cancellations, returns, complaints, sales, speak to human) → say "I'll transfer you to a support agent now, please hold on." in their language, then call forward_call.
  C. UNCLEAR → one short clarifying question, then classify.

STEP 3 — ORDER RESULT:
  - Dispatched → say order is dispatched.
  - Quoted → say status is Quoted.
  - Error/not found → say unable to retrieve right now.
  Ask if anything else needed.

STEP 4 — CLOSE: Warm goodbye in their language, call end_conversation.

ORDER ID: 4 digits only. Words like "six one eight zero" = 6180. Do NOT read it back. Call check_order_status immediately.

FORWARD: Say "I'll transfer you to a support agent now, please hold on." first, then call forward_call immediately.

STRICT: Never answer refunds/cancellations/complaints/sales/returns. Always forward these."""

def db_get_settings():
    """Retrieves the system settings document, initializing with defaults if empty."""
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
        # Convert _id to string for JSON serialization compatibility
        if "_id" in settings:
            settings["_id"] = str(settings["_id"])
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
        return True
    except PyMongoError as e:
        print(f"Failed to update settings in MongoDB: {e}")
        return False

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

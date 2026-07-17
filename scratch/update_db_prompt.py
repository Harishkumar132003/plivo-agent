import sys
import os

# Add parent directory to path so we can import from database.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, DEFAULT_SYSTEM_PROMPT

def update_db_prompt():
    try:
        db = get_db()
        db.settings.update_one(
            {"key": "agent_settings"},
            {"$set": {"system_prompt": DEFAULT_SYSTEM_PROMPT}}
        )
        print("Successfully updated the system prompt in the database.")
    except Exception as e:
        print(f"Error updating database: {e}")

if __name__ == "__main__":
    update_db_prompt()

import requests
import os
from dotenv import load_dotenv

load_dotenv()

emoex_email = os.environ["EMOEX_EMAIL"]
emoex_password = os.environ["EMOEX_PASSWORD"]
product_id = os.environ["EMOEX_PRODUCT_ID"]
firebase_api_key = os.environ["FIREBASE_API_KEY"]
force_refresh = os.environ.get("FORCE_REFRESH", "true").lower() == "true"

# Sign in to Firebase to get an ID token
firebase_auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
auth_payload = {
    "email": emoex_email,
    "password": emoex_password,
    "returnSecureToken": True,
    "threadId": None,
}
auth_response = requests.post(firebase_auth_url, json=auth_payload)
auth_response.raise_for_status()
auth_data = auth_response.json()
id_token = auth_data["idToken"]

# Use the ID token to request the room token
room_token_url = "https://api.emoexai.com/realtime/roomToken"
headers = {"Authorization": f"Bearer {id_token}"}
room_payload = {"productId": product_id, "forceRefresh": force_refresh}
room_response = requests.post(room_token_url, headers=headers, data=room_payload)
room_response.raise_for_status()
room_data = room_response.json()
print(room_data)

# Extract USER_TOKEN and ROOM_NAME from response
user_token = room_data.get("data").get("userToken") 
room_name = room_data.get("data").get("roomName") 

# Token expiry information
import datetime
import base64
import json

# 1) From Firebase response (expiresIn is seconds as string)
expires_in = int(auth_data.get("expiresIn", "3600"))
expiry_dt = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in)
print("Firebase idToken expires in (seconds):", expires_in)
print("Approx expiry (UTC):", expiry_dt.isoformat() + "Z")

# 2) Decode JWT exp claim without verification (UTC timestamp)
def jwt_expiry(ts_jwt: str):
    try:
        payload_b64 = ts_jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        exp = payload.get("exp")
        return datetime.datetime.utcfromtimestamp(exp) if exp else None
    except Exception:
        return None

jwt_exp = jwt_expiry(id_token)
print("JWT exp claim (UTC):", jwt_exp)

# Update .env.livekit file
def update_env_file(filepath, updates):
    """
    Update or create a .env file with new values while preserving existing variables.
    
    Args:
        filepath: Path to the .env file
        updates: Dictionary of key-value pairs to update
    """
    existing_vars = {}
    
    # Read existing variables if file exists
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key.strip()] = value.strip()
                    
    # Adding last updated timestamp
    last_updated = datetime.datetime.utcnow().isoformat() + "Z"
    updates["LAST_UPDATED"] = f'"{last_updated}"'

    # Updating existing variables with new values
    existing_vars.update(updates)
    
    # Writing back to file
    with open(filepath, 'w') as f:
        for key, value in existing_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"Updated {filepath}")

# Constants and dynamic values to write
env_updates = {
    "LIVEKIT_URL": '"wss://emoex-hbcswei7.livekit.cloud"',
    # "wsUrl": "'wss://emoex-hbcswei7.livekit.cloud'",
    "room_token_url": "https://api.emoexai.com/realtime/roomToken",
    "USER_TOKEN": f'"{user_token}"' if user_token else '""',
    "ROOM_NAME": f'"{room_name}"' if room_name else '""'
}

update_env_file(".env.livekit", env_updates)

def extract_thread_from_token(token):
    """Extract thread_id from JWT token."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        
        # Print full payload for debugging
        print("\n=== Full JWT Payload ===")
        print(json.dumps(payload, indent=2))
        print("=" * 50)
        
        # Search for thread_id in various nested locations
        thread_id = None
        
        # Check direct field
        if 'thread_id' in payload:
            thread_id = payload['thread_id']
        
        # Check in roomConfig
        elif 'roomConfig' in payload:
            room_config = payload['roomConfig']
            if isinstance(room_config, str):
                # It might be JSON string, try parsing
                try:
                    room_config = json.loads(room_config)
                except:
                    pass
            if isinstance(room_config, dict) and 'thread_id' in room_config:
                thread_id = room_config['thread_id']
        
        # Search recursively in the entire payload
        if not thread_id:
            import re
            payload_str = json.dumps(payload)
            # Look for thread_ followed by alphanumeric characters
            thread_matches = re.findall(r'thread_[a-zA-Z0-9_-]+', payload_str)
            if thread_matches:
                # Get unique thread IDs
                unique_threads = list(set(thread_matches))
                thread_id = unique_threads[0] if len(unique_threads) == 1 else unique_threads
        
        return thread_id, payload.get('sub', 'unknown'), payload
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None, None, None

thread_id, user_sub, payload = extract_thread_from_token(user_token) if user_token else (None, None, None)


print(f"\nRoom Name: {room_name}")
print(f"User Sub: {user_sub}")

if thread_id:
    print(f"🔑 Thread ID: {thread_id}")
else:
    print("⚠️  Thread ID not found")
print(f"User Token: {user_token[:50]}..." if user_token and len(user_token) > 50 else f"User Token: {user_token}")


# print(f"Room Name: {room_name}")
# print(f"User Token: {user_token[:50]}..." if user_token and len(user_token) > 50 else f"User Token: {user_token}")
import requests
from agent.config import (
    FRAPPE_BASE_URL,
    FRAPPE_API_KEY,
    FRAPPE_API_SECRET,
    MACHINE_ID
)

HEADERS = {
    "Authorization": f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}",
    "Content-Type": "application/json"
}

def get_pending_commands():
    url = f"{FRAPPE_BASE_URL}/api/method/kneader3009.kneader3009.api.get_pending_commands"
    response = requests.get(url, headers=HEADERS, params={"machine_id": MACHINE_ID})
    response.raise_for_status()
    return response.json().get("message", [])

def update_command_status(command_id, status, message=None):
    url = f"{FRAPPE_BASE_URL}/api/method/kneader3009.kneader3009.api.update_command_status"
    payload = {
        "command_id": command_id,
        "status": status,
        "message": message
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

def update_machine_status(status_json):
    url = f"{FRAPPE_BASE_URL}/api/method/kneader3009.kneader3009.api.update_machine_status"
    payload = {
        "machine_id": MACHINE_ID,
        "status_json": status_json
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    return response.json()

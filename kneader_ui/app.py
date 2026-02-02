from datetime import datetime
import time
import uuid
from datetime import datetime
import time
import uuid

import json
import threading
import socket
import time
from datetime import datetime
import string
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import configparser
import re
import requests
import traceback

from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import paho.mqtt.client as mqtt

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(
    app,
    supports_credentials=True,
    origins=["http://localhost:8000", "https://shera-undefensible-pseudoindependently.ngrok-free.dev",
             "http://127.0.0.1:8000", "https://sppmaster.frappe.cloud", "http://localhost:8081",
             "http://mysite.local:8000","http://localhost:8080","chrome-extension://*"
             ]

)

ALLOWED_ORIGINS = [
    "https://sppmaster.frappe.cloud",
    "https://shera-undefensible-pseudoindependently.ngrok-free.dev",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8080",
    "http://sppmaster.local:8000",
]


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"

        response.headers.setdefault(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization"
        )
        response.headers.setdefault(
            "Access-Control-Allow-Methods",
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
    return response


# JWT CONFIG
app.config["JWT_SECRET_KEY"] = "super-secret-factory-key"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
jwt = JWTManager(app)
BROKER_HOST = "localhost"
BROKER_PORT = 1883

ERP_BASE_URL = "http://sppmaster.local:8000"
# ERPNext API Integration
ERP_API_KEY = "57f6f2eeee6cb49"
ERP_API_SECRET = "c681509ef0534d3"

ERP_HEADERS = {
    "Authorization": f"token {ERP_API_KEY}:{ERP_API_SECRET}"
}

HMI_HOST = "localhost"
HMI_PORT = 6000
LOG_DIR = "../logs"
log_file = os.path.join(LOG_DIR, "ui_controller.log")

os.makedirs(LOG_DIR, exist_ok=True)

# Global flags for status + batch lookup
BATCH_LOOKUP_IN_PROGRESS = False
LAST_STATUS_CACHE = None
LAST_STATUS_TS = 0.0


class ControllerMQTTClient:
    def __init__(self):
        self.client = mqtt.Client()
        self.client.on_message = self.on_message
        self.client.connect(BROKER_HOST, BROKER_PORT, 60)
        self.client.subscribe("kneader/responses/#")
        self.client.loop_start()
        self.response = None

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            print(f"MQTT Response → {msg.topic}: {payload}")
            self.response = payload
        except json.JSONDecodeError:
            print(f"MQTT Decode Error: invalid JSON from topic {msg.topic}")
            self.response = {"error": "Invalid JSON payload"}
        except Exception as e:
            print(f"MQTT on_message() exception: {e}")
            self.response = {"error": str(e)}

    def send_command(self, command, timeout=10):
        """Publish command and wait for controller's MQTT response"""
        req_id = command.get("request_id", "-")
        start = time.time()

        self.response = None
        self._log(f"[{req_id}] MQTT → sending command '{command.get('command')}' payload={command}")

        self.client.publish(f"kneader/commands/{command['command']}", json.dumps(command))

        for _ in range(int(timeout * 10)):  # poll every 0.1s
            if self.response:
                elapsed = time.time() - start
                self._log(
                    f"[{req_id}] MQTT ← got response for '{command.get('command')}' in {elapsed:.3f}s: {self.response}")
                return self.response
            time.sleep(0.1)

        elapsed = time.time() - start
        self._log(f"[{req_id}] MQTT TIMEOUT after {elapsed:.3f}s waiting for '{command.get('command')}'")
        return {"error": "Timeout waiting for controller response"}

    def _log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_file, "a", encoding='utf-8') as f:
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            print(f"Failed to write to log file: {e}")
        print(message)


controller = ControllerMQTTClient()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
config_path = os.path.join(parent_dir, './kneader/config.ini')

config = configparser.ConfigParser()
config.read(config_path)
compound_workorders_file = config["files"]["compound_workorder_file"]
master_workorders_file = config["files"]["master_workorder_file"]


def erp_call_method(method, params=None):
    """Call a Frappe/ERPNext whitelisted method.---bridge from flask to erpnext"""
    params = params or {}
    url = f"{ERP_BASE_URL}/api/method/{method}"
    log_app(f"Calling ERP method: {url} params={params}")
    resp = requests.post(url, headers=ERP_HEADERS, json=params, timeout=30)
    log_app(f"ERP response raw: {resp.status_code} {resp.text}")

    resp.raise_for_status()
    data = resp.json()
    # ERPNext wraps return value in "message"
    return data.get("message", data)


def log_app(msg, req_id=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if req_id:
        print(f"{ts} [FLASK] [{req_id}] {msg}", flush=True)
    else:
        print(f"{ts} [FLASK] {msg}", flush=True)


def load_workorders(batch_type="compound"):
    file_path = compound_workorders_file if batch_type == "compound" else master_workorders_file
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _ensure_steps_field(status: dict) -> dict:
    """
    Make sure status has a 'steps' array that Vue template (status.steps)
    can loop over. If 'steps' already exists from controller, keep it.
    Else, build it from prescan_status.status_by_stage.
    """
    # If controller already gave steps, keep them
    if status.get("steps"):
        return status

    prescan = status.get("prescan_status") or {}
    stages = prescan.get("status_by_stage") or {}

    steps = []

    for stage_no_str, stage in sorted(stages.items(), key=lambda kv: int(kv[0])):
        items = stage.get("items") or []
        mix_time = stage.get("mix_time")

        steps.append({
            "step_id": int(stage_no_str),
            "mix_time_sec": mix_time,
            "mix_time": mix_time,
            "items": items,  # each item has item_id, prescan_status, status,
        })

    status["steps"] = steps
    return status


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username") or data.get("usr")
    password = data.get("password") or data.get("pwd")

    try:
        erp_resp = requests.post(
            f"{ERP_BASE_URL}/api/method/login",
            data={"usr": username, "pwd": password},
            timeout=10
        )

        if erp_resp.status_code != 200 or "Invalid Login" in erp_resp.text:
            return jsonify({"msg": "Invalid ERPNext credentials"}), 401

        # Get user roles
        user_resp = requests.get(
            f"{ERP_BASE_URL}/api/resource/User/{username}",
            headers={
                "Authorization": f"token {ERP_API_KEY}:{ERP_API_SECRET}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        user_data = user_resp.json().get("data", {})
        roles = [r.get("role") for r in user_data.get("roles", [])]

        # Restrict login based on allowed roles
        allowed_roles = {"System Manager", "Batch Operator", "Mill Operator"}
        if not any(role in allowed_roles for role in roles):
            return jsonify({
                "msg": "Access denied. Only System Manager, Batch Operator, or Mill Operator can log in."
            }), 403

        # Create token
        identity = username  # main identity must be string
        additional_claims = {"roles": roles}
        token = create_access_token(identity=identity, additional_claims=additional_claims)

        # Return only the token
        return jsonify({"token": token}), 200

    except Exception as e:
        return jsonify({"msg": f"ERPNext login failed: {str(e)}"}), 500


@app.route('/')
def serve_ui():
    return send_from_directory('static', 'index.html')


@app.route('/api/cancel', methods=['POST'])
@jwt_required()
def cancel_process():
    try:
        response = controller.send_command({"command": "cancel"})
        if response and not response.get("error"):
            return jsonify({
                "status": "success",
                "message": "Prescan cancelled, system reset to IDLE",
                "data": response
            })
        else:
            error_msg = response.get("error", "Cancel failed") if response else "No response from controller"
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/load_workorder', methods=['POST'])
@jwt_required()
def load_workorder():
    print("🔥 ENTERED /api/load_workorder")

    data = request.get_json()
    batch_no = data.get("batch_no")

    if not batch_no:
        return jsonify({"status": "fail", "message": "batch_no required"}), 400

    try:
        raw = erp_call_method(
            "kneader3009.kneader_api.create_kneader_session",
            {"batch_no": batch_no}
        )

        session_resp = raw.get("message", raw)

        return jsonify({
            "status": "success",
            "session_id": session_resp["session_id"],
            "final_item": session_resp["final_item"],
            "sequence_steps": session_resp["sequence_steps"],
            "prescan_status": "PRESCAN"
        })

    except Exception as e:
        print("❌ LOAD_WORKORDER ERROR:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500




def erp_get(doctype, params=None, use_method=False, token=None):
    import json
    import requests

    params = params or {}

    encoded_params = {}
    for k, v in params.items():
        if isinstance(v, (dict, list)):
            encoded_params[k] = json.dumps(v)
        else:
            encoded_params[k] = v

    headers = {
        "Authorization": f"token {ERP_API_KEY}:{ERP_API_SECRET}",
        "Content-Type": "application/json"
    }

    # =Select correct ERPNext endpoint =
    if use_method:
        url = f"{ERP_BASE_URL}/api/method/frappe.client.get_list"
        encoded_params["doctype"] = doctype
    else:
        url = f"{ERP_BASE_URL}/api/resource/{doctype}"

    print("\n================ ERPNext API CALL ================")
    print(f"URL: {url}")
    print(f"Params: {encoded_params}")
    print(f"Headers: {headers}")
    t0 = time.time()
    resp = requests.get(url, headers=headers, params=encoded_params)
    dt = time.time() - t0
    log_app(f"ERP GET {url} took {dt:.3f}s")

    print(f"ERPNext → Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"ERPNext API error ({resp.status_code}): {resp.text}")
        return {}

    print("ERPNext API call successful!")
    return resp.json()


def erp_post(endpoint, data):
    """POST request to ERPNext"""
    url = f"{ERP_BASE_URL}/api/resource/{endpoint}"
    resp = requests.post(url, headers=ERP_HEADERS, json=data)
    return resp.json()


def erp_put(endpoint, data):
    """PUT request to ERPNext"""
    url = f"{ERP_BASE_URL}/api/resource/{endpoint}"
    resp = requests.put(url, headers=ERP_HEADERS, json=data)
    return resp.json()


def _extract_list(resp):
    """Extract list from ERPNext responses (data/message)."""
    return resp.get("data") or resp.get("message") or []


def _extract_doc(resp):
    """Extract a single full document from ERPNext response."""
    if isinstance(resp.get("data"), dict):
        return resp["data"]
    if isinstance(resp.get("data"), list) and resp["data"]:
        return resp["data"][0]
    if isinstance(resp.get("message"), dict):
        return resp["message"]
    if isinstance(resp.get("message"), list) and resp["message"]:
        return resp["message"][0]
    return {}


def _extract_item(row):
    """Find correct item field (item_code1 / item_code / item)."""
    for key in ("item_code", "item_code1", "final_item", "item"):
        if row.get(key):
            return str(row[key]).strip()
    for k, v in row.items():
        if "item" in k.lower() and v:
            return str(v).strip()
    return None


def get_final_production_item(token=None, manual_batch=None):
    func_start = time.time()
    try:
        if manual_batch:
            batch_no = manual_batch.strip()
            log_app(f"gFPI: manual batch_no={batch_no}")

            start_date, end_date = parse_batch_date(batch_no)
            log_app(f"Filtering Stock Entry between {start_date} and {end_date}")

            batch_entries = erp_get("Stock Entry", {
                "filters": [
                    ["Stock Entry Detail", "batch_no", "=", batch_no],
                    ["posting_date", "between", [str(start_date), str(end_date)]]
                ],
                "fields": [
                    "posting_date",
                    "item_name",
                    "items.batch_no",
                    "items.item_code",
                    "items.mix_barcode"
                ],
                "limit_page_length": 5
            }, use_method=True)

        else:
            log_app("gFPI: auto-fetch latest Batch entry...")
            t0 = time.time()

            batch_entries = erp_get("Stock Entry", {
                "filters": [["Stock Entry Detail", "item_group", "=", "Batch"]],
                "fields": ["posting_date", "item_name", "items.batch_no", "items.item_code"],
                "limit_page_length": 1,
                "order_by": "posting_date desc"
            }, use_method=True, token=token)

            log_app(f"gFPI: first Stock Entry erp_get took {time.time() - t0:.3f}s")

        data = batch_entries.get("data") or batch_entries.get("message")
        if not data:
            log_app("No Stock Entry found")
            return None

        first_entry = data[0]

        # Extract batch number
        batch_no = None
        if "batch_no" in first_entry and first_entry.get("batch_no"):
            batch_no = first_entry.get("batch_no")
        elif "items" in first_entry and isinstance(first_entry["items"], list):
            if first_entry["items"] and "batch_no" in first_entry["items"][0]:
                batch_no = first_entry["items"][0].get("batch_no")

        if not batch_no:
            log_app("batch_no not found in Stock Entry")
            log_app(f"Entry data: {first_entry}")
            return None

        log_app(f"Step 1 → Batch No: {batch_no}")

        # SAFE Item Code extraction (NO SECOND ERP CALL)
        item_code_full = None

        if "item_code" in first_entry and first_entry.get("item_code"):
            item_code_full = first_entry.get("item_code")
        elif "items" in first_entry and isinstance(first_entry["items"], list):
            if first_entry["items"] and "item_code" in first_entry["items"][0]:
                item_code_full = first_entry["items"][0].get("item_code")

        if not item_code_full:
            log_app("item_code not found in first Stock Entry result")
            log_app(f"Entry data: {first_entry}")
            return None

        log_app(f"Item Code extracted without 2nd ERP call: {item_code_full}")

        # Extract prefix for BOM
        prefix_match = re.search(r"B[_-]?\d+", item_code_full)
        item_code_prefix = prefix_match.group(0) if prefix_match else item_code_full.split()[0]
        log_app(f"🔹 Extracted Prefix for BOM: {item_code_prefix}")

        #  STEP 3 → Find BOM
        t2 = time.time()
        boms = erp_get("BOM", {
            "filters": [
                ["BOM Item", "item_code", "=", item_code_prefix],
                ["is_default", "=", 1],
                ["is_active", "=", 1]
            ],
            "fields": ["item"],
            "limit_page_length": 1
        }, token=token)

        log_app(f"gFPI: BOM erp_get took {time.time() - t2:.3f}s")

        bom_data = boms.get("data") or boms.get("message")

        if not bom_data:
            log_app("No BOM found by item — retrying via child table...")

            boms = erp_get("BOM", {
                "filters": [
                    ["BOM Item", "item_code", "=", item_code_prefix],
                    ["BOM", "is_default", "=", 1]
                ],
                "fields": ["name", "item"],
                "limit_page_length": 1
            }, use_method=True, token=token)

            bom_data = boms.get("data") or boms.get("message")

        if not bom_data:
            log_app(f"No BOM found for item={item_code_prefix}")
            return None

        final_item = bom_data[0]["item"]

        log_app(f"get_final_production_item() TOTAL {time.time() - func_start:.3f}s (final_item={final_item})")

        return {
            "batch_no": batch_no,
            "item_code_full": item_code_full,
            "item_code_prefix": item_code_prefix,
            "final_item": final_item
        }

    except Exception as e:
        log_app(f"Error in get_final_production_item: {e}")
        return None


# helper function to parse the batch number

def parse_batch_date(batch_no):
    year = int("20" + batch_no[:2])  # 25 -> 2025
    month_letter = batch_no[2].upper()
    day = int(batch_no[3:5])

    month = string.ascii_uppercase.index(month_letter) + 1

    current_date = datetime(year, month, day)

    # First day of current month
    first_day_current = current_date.replace(day=1)

    # First day of previous month
    prev_month_last_day = first_day_current - timedelta(days=1)
    first_day_prev = prev_month_last_day.replace(day=1)

    return first_day_prev.date(), current_date.date()


def find_mixing_sequence_for_final_item_app(final_item=None, batch_no=None, token=None):
    """
    Find the Mixing Sequence that produces `final_item` and return clean sequence_steps.
    Optimized: we ask ERPNext directly for the matching Mixing Sequence instead of
    fetching up to 1000 and looping in Python.
    """

    # 1 — If final_item not provided, fetch it from batch
    if not final_item:
        mix = get_final_production_item(token=token, manual_batch=batch_no)
        if not mix or "final_item" not in mix:
            return {"error": "Could not determine final item from batch"}
        final_item = mix["final_item"]

    final_item = str(final_item).strip()
    final_item_norm = final_item.lower()

    log_app(f"find_mixing_sequence: searching Mixing Sequence for final_item={final_item}")

    # 2 — Ask ERPNext for Mixing Sequence where child table "Mixing Sequence Mapping"
    #     has final_item = our final_item
    resp = erp_get(
        "Mixing Sequence",
        {
            "filters": [
                ["Mixing Sequence Mapping", "final_item", "=", final_item]
            ],
            "fields": ["name"],
            "limit_page_length": 1
        },
        use_method=True,
        token=token
    )

    seqs = _extract_list(resp) or []
    if not seqs:
        log_app(f"find_mixing_sequence: no Mixing Sequence found directly for {final_item}")
        return {"error": f"No Mixing sequence produces '{final_item}'"}

    seq_name = seqs[0].get("name")
    if not seq_name:
        return {"error": f"No valid Mixing Sequence name found for '{final_item}'"}

    log_app(f"find_mixing_sequence: using Mixing Sequence '{seq_name}' for final_item={final_item}")

    # 3 — Fetch complete Mixing Sequence document once
    doc_resp = erp_get(f"Mixing Sequence/{seq_name}", token=token)
    doc = _extract_doc(doc_resp) or {}

    produces = doc.get("produces_items") or []

    # 4 — Extra safety check that this sequence really produces our item
    found_match = False
    for row in produces:
        rdict = row if isinstance(row, dict) else dict(row)
        produced = _extract_item(rdict or {})
        produced_norm = str(produced).strip().lower() if produced else None
        if produced == final_item or produced_norm == final_item_norm:
            found_match = True
            break

    if not found_match:
        return {"error": f"No Mixing sequence produces '{final_item}' (after detail check)"}

    # -------- BUILD CLEAN sequence_steps --------
    mixing_items = doc.get("mixing_items", []) or []
    mixing_times = doc.get("mixing_time", []) or []

    # Group items by sequence: A → items[], B → items[]
    items_by_seq = {}
    for r in mixing_items:
        seq = str(r.get("sequence", "")).strip()
        itm = r.get("item_code")
        if seq:
            items_by_seq.setdefault(seq, []).append(itm)

    # Group mixing-time by sequence
    time_by_seq = {}
    for t in mixing_times:
        seq = str(t.get("sequence", "")).strip()
        mt = t.get("mixing_time")
        if seq:
            time_by_seq[seq] = mt

    # Preserve sequence order (using idx from mixing_time table)
    ordered_seq_rows = sorted(mixing_times, key=lambda x: x.get("idx", 0))
    ordered_sequences = [r.get("sequence") for r in ordered_seq_rows]

    # Build final array
    sequence_steps = []
    for seq in ordered_sequences:
        sequence_steps.append({
            "sequence": seq,
            "items": items_by_seq.get(seq, []),
            "mixing_time": time_by_seq.get(seq)
        })

    # Final return
    return {
        "final_item": final_item,
        "sequence_steps": sequence_steps
    }


@app.route("/api/debug/final_item", methods=["GET"])
@jwt_required()
def debug_final_item():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        return jsonify({
            "status": "fail",
            "message": "Invalid authorization header"
        }), 401

    batch_no = request.args.get("batch_no", None)
    if batch_no:
        print(f"Manual batch number received: {batch_no}")
    else:
        print("No manual batch number provided — using automatic mode")

    result = get_final_production_item(token=token, manual_batch=batch_no)

    if result:
        return jsonify({
            "status": "success",
            "message": "Final production item successfully fetched.",
            "data": result
        }), 200
    else:
        return jsonify({
            "status": "fail",
            "message": "Could not fetch final production item. Check ERPNext data or filters."
        }), 200


@app.route('/api/debug/token', methods=['GET'])
@jwt_required()
def debug_token():
    current_user = get_jwt_identity()
    return jsonify({
        "status": "success",
        "message": "Token is valid",
        "current_user": current_user
    })

@app.route("/api/create_session", methods=["POST"])
@jwt_required()
def create_session():
    try:
        data = request.get_json()
        batch_no = data.get("batch_no")

        if not batch_no:
            return jsonify({"status": "fail", "message": "batch_no required"}), 400

        # Call ERP (Frappe) to create session
        resp = erp_call_method(
            "kneader3009.kneader_api.create_kneader_session",
            {"batch_no": batch_no}
        )

        return jsonify({
            "status": "success",
            "session_id": resp.get("session_id")
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/prescan', methods=['POST'])
@jwt_required()
def prescan_item():
    try:
        data = request.get_json()
        print("📦 PRESCAN REQUEST:", data)
        barcode = data.get("barcode")
        session_id = data.get("session_id")
        print("🆔 SESSION:", session_id)
        print("📦 BARCODE:", barcode)
        if not barcode or not session_id:
            return jsonify({"status": "fail", "message": "Missing barcode or session_id"}), 400

        payload = {
            "session_id": session_id,
            "spp_batch_number": barcode
        }

        print("➡️ SENDING TO FRAPPE:")
        print("METHOD: kneader3009.kneader_api.prescan_item")
        print("PAYLOAD:", payload)

        resp = erp_call_method(
            "kneader3009.kneader_api.prescan_item",
            payload
        )

        print("⬅️ FRAPPE RESPONSE:", resp)
        return jsonify(resp)



    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/prescan_state', methods=['GET'])
@jwt_required()
def get_prescan_state():
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify({"status": "fail", "message": "session_id required"}), 400

        resp = erp_call_method(
            "kneader3009.kneader_api.get_kneader_prescan_state",
            {"session_id": session_id}
        )

        return jsonify(resp)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/confirm_prescan', methods=['POST'])
@jwt_required()
def confirm_prescan():
    try:
        response = controller.send_command({"command": "confirm_start"})
        if response and not response.get("error"):
            return jsonify(response)
        else:
            return jsonify({"status": "fail", "message": response.get("error",
                                                                      "Failed to confirm prescan") if response else "Failed to confirm prescan"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/scan', methods=['POST'])
@jwt_required()
def scan_item():
    try:
        data = request.json
        barcode = data.get('barcode')

        if not barcode:
            return jsonify({
                "status": "fail",
                "message": "No barcode provided"
            }),400

        # Always ask controller what state we are in
        status = controller.send_command({"command": "get_status"})
        state = status.get("process_state", "IDLE")

        # 🚨 Prescan must be EXPLICIT
        #if state == "PRESCANNING":
            #return jsonify({
                #"status": "fail",
                #"message": "Prescan is active. Use /api/prescan for prescanning."
            #})

        # ✅ Actual scan (OFFLINE)
        if state in ("WAITING_FOR_ITEMS", "MIXING"):
            return jsonify(
                controller.send_command({
                    "command": "scan_item",
                    "data": {"barcode": barcode}
                })
            )

        return jsonify({
            "status": "fail",
            "message": f"Scan not allowed in state: {state}"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/status', methods=['GET'])
@jwt_required()
def get_status():
    global LAST_STATUS_CACHE, LAST_STATUS_TS, BATCH_LOOKUP_IN_PROGRESS
    try:
        now = time.time()

        # 1) If a heavy batch lookup is running, just return last known status
        if BATCH_LOOKUP_IN_PROGRESS and LAST_STATUS_CACHE is not None:
            status = {**LAST_STATUS_CACHE, "_note": "cached_status_while_batch_loading"}
            status = _ensure_steps_field(status)
            return jsonify(status)

        # 2) Throttle calls: if UI calls faster than 2/sec, reuse cached result
        if LAST_STATUS_CACHE is not None and (now - LAST_STATUS_TS) < 0.5:
            status = _ensure_steps_field(dict(LAST_STATUS_CACHE))
            return jsonify(status)

        response = controller.send_command({"command": "get_status"})

        if response and not response.get("error"):
            LAST_STATUS_CACHE = response
            LAST_STATUS_TS = now
            status = _ensure_steps_field(dict(response))
            return jsonify(status)
        else:
            msg = response.get("error", "Controller not responding") if response else "Controller not responding"
            return jsonify({
                "process_state": "IDLE",
                "error_message": msg
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/abort', methods=['POST'])
@jwt_required()
def abort_process():
    try:
        response = controller.send_command({"command": "abort"})
        if response and not response.get("error"):
            return jsonify({"status": "success", "message": "Process aborted"})
        else:
            return jsonify({"status": "fail", "message": response.get("error", "Failed to abort")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/resume', methods=['POST'])
@jwt_required()
def resume_process():
    try:
        response = controller.send_command({"command": "resume"})
        if response and not response.get("error"):
            return jsonify({"status": "success", "message": "Process resumed"})
        else:
            return jsonify({"status": "fail", "message": response.get("error", "Failed to resume")})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/complete_abort', methods=['POST'])
@jwt_required()
def complete_abort():
    try:
        print("Received complete_abort request from frontend")
        response = controller.send_command({"command": "complete_abort"})
        print(f"Controller response: {response}")

        if response and not response.get("error"):
            return jsonify({
                "status": "success",
                "message": "Process completely aborted",
                "data": response
            })
        else:
            error_msg = response.get("error",
                                     "Failed to completely abort") if response else "No response from controller"
            print(f"Complete abort error: {error_msg}")
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        print(f"Complete abort exception: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/save_workorder', methods=['POST'])
@jwt_required()
def save_workorder():
    try:
        response = controller.send_command({"command": "save_workorder"})
        if response and not response.get("error"):
            return jsonify({
                "status": "success",
                "message": response.get("message", "Workorder saved successfully"),
                "data": response
            })
        else:
            error_msg = response.get("error", "Failed to save workorder") if response else "No response from controller"
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/confirm_completion', methods=['POST'])
@jwt_required()
def confirm_completion():
    try:
        response = controller.send_command({"command": "confirm_completion"})

        # Auto-update ERPNext work order
        if response and "workorder_id" in response:
            workorder_id = response["workorder_id"]
            erp_put(f"Work Order/{workorder_id}", {"status": "Completed"})

        return jsonify({
            "status": "success",
            "message": "Controller reset after completion and ERPNext updated",
            "data": response
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route('/api/reset', methods=['POST'])
@jwt_required()
def reset_process():
    try:
        controller.connected = False
        response = controller.send_command({"command": "reset"})
        if response and response.get("process_state") == "IDLE":
            return jsonify({"status": "success", "message": "Controller reset", "data": response})
        else:
            return jsonify({"status": "fail", "message": "Reset failed", "data": response})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/erp/workorders', methods=['GET'])
@jwt_required()
def erp_get_workorders():
    """Fetch Work Orders from ERPNext"""
    try:
        params = {
            "filters": [["status", "=", "Not Started"]],
            "fields": ["name", "production_item", "qty", "bom_no", "batch_size"]
        }
        data = erp_get("Work Order", params)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/erp/bom/<bom_name>', methods=['GET'])
@jwt_required()
def erp_get_bom(bom_name):
    """Fetch a specific BOM"""
    try:
        data = erp_get(f"BOM/{bom_name}")
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/erp/update_workorder', methods=['POST'])
@jwt_required()
def erp_update_workorder():
    """Update work order status"""
    try:
        data = request.json
        work_order = data.get("work_order")
        payload = {
            "status": data.get("status", "Completed"),
            "actual_qty": data.get("actual_qty", 0)
        }
        resp = erp_put(f"Work Order/{work_order}", payload)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/erp/create_batch', methods=['POST'])
@jwt_required()
def erp_create_batch():
    """Create a batch record in ERPNext"""
    try:
        data = request.json
        payload = {
            "batch_id": data.get("batch_id"),
            "item": data.get("item"),
            "manufacturing_date": data.get("manufacturing_date")
        }
        resp = erp_post("Batch", payload)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/find_mixing_sequence", methods=["GET", "POST"])
def api_find_mixing_sequence():
    log_app("=== /api/find_mixing_sequence START ===")
    req_start = time.time()

    try:
        # 1) Read input from frontend
        data = request.get_json(silent=True) or {}
        batch_no = request.args.get("batch_no") or data.get("batch_no")
        final_item = request.args.get("final_item") or data.get("final_item")

        if not batch_no and not final_item:
            return jsonify({"success": False, "error": "Provide 'batch_no' or 'final_item'"}), 400

        # 2) Call ERPNext single whitelisted method
        erp_out = erp_call_method(
            "kneader3009.kneader_api.get_mixing_sequence",
            {
                "batch_no": batch_no,
                "final_item": final_item,
            }
        )
        log_app(f"ERP OUT RAW: {erp_out}")

        # Frappe returns {"message": {...}}, unwrap it
        if isinstance(erp_out, dict) and "message" in erp_out:
            erp_data = erp_out["message"]
        else:
            erp_data = erp_out


        controller_workorder = {
            "batch_no": batch_no,
            "final_item": erp_data.get("final_item"),
            "sequence_steps": erp_data.get("sequence_steps", []),
        }

        # 4) Send workorder to controller
        ctrl_start = time.time()
        controller_response = controller.send_command({
            "command": "load_workorder",
            "data": controller_workorder,
        })
        log_app(f"Controller load_workorder took {time.time() - ctrl_start:.3f}s")

        # 5) Attach controller response & return to frontend
        erp_data["controller_response"] = controller_response

        log_app(f"=== /api/find_mixing_sequence DONE in {time.time() - req_start:.3f}s ===")
        return jsonify(erp_out), 200

    except Exception as e:
        log_app(f"/api/find_mixing_sequence exception: {e}")
        return jsonify({
            "success": False,
            "error": "Server error while finding mixing sequence",
            "detail": str(e),
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')


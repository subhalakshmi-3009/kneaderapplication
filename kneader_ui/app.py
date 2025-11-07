import json
import threading
import socket
import time
from datetime import datetime
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
    origins=["http://localhost:8000", "http://127.0.0.1:8000"]
)

# === JWT CONFIG ===
app.config["JWT_SECRET_KEY"] = "super-secret-factory-key"
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
jwt = JWTManager(app)
BROKER_HOST = "localhost"
BROKER_PORT = 1883

ERP_BASE_URL = "https://sppmaster.frappe.cloud"
# === ERPNext API Integration ===
ERP_API_KEY = "0ebe5e4fe8d8bc7"
ERP_API_SECRET = "79ec941325e2223"

ERP_HEADERS = {
    "Authorization": f"token {ERP_API_KEY}:{ERP_API_SECRET}"
}



HMI_HOST = "localhost"
HMI_PORT = 6000
LOG_DIR = "../logs"
log_file = os.path.join(LOG_DIR, "ui_controller.log")

os.makedirs(LOG_DIR, exist_ok=True)

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
        self.response = None
        self.client.publish("kneader/commands", json.dumps(command))
        for _ in range(int(timeout * 10)):
            if self.response:
                return self.response
            time.sleep(0.1)
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
master_workorders_file   = config["files"]["master_workorder_file"]


def load_workorders(batch_type="compound"):
    file_path = compound_workorders_file if batch_type == "compound" else master_workorders_file
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
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

        # Create token (identity must be a string)
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
def load_workorder_from_erp():
    data = request.get_json()
    workorder_name = data.get("workorder_name")
    batchType = data.get("type", "compound")

    try:

        batchType = request.args.get("type", "compound")


        workorder_data = erp_get(f"Work Order/{workorder_name}")
        workorder = workorder_data.get("data", {})
        if not workorder:
            return jsonify({"status": "fail", "message": "Work Order not found in ERPNext"}), 404

        batch_number = workorder.get("batch_no") or workorder_name
        bom_no = workorder.get("bom_no")


        bom_data = erp_get(f"BOM/{bom_no}")
        bom = bom_data.get("data", {})
        bom_items = bom.get("items", [])

        if not bom_items:
            return jsonify({"status": "fail", "message": "No BOM items found for this Work Order"}), 404

        # 🔹 Step 3.5 — Get Final Production Item from Mix Barcode Flow
        mix_info = get_final_production_item()

        # Build Kneader-compatible workorder JSON
        kneader_workorder = {
            "batch_number": batch_number,
            "workorder": {
                "workorder_id": workorder_name,
                "name": workorder.get("production_item") or workorder_name,
                "steps": [],
                # Add mix/barcode/final item info to workorder metadata
                "mix_barcode": mix_info.get("mix_barcode") if mix_info else None,
                "mix_item_code": mix_info.get("item_code") if mix_info else None,
                "bom_name": mix_info.get("bom_name") if mix_info else bom_no,
                "final_item": mix_info.get("final_item") if mix_info else workorder.get("production_item")
            }
        }

        # Split BOM items into mixing steps
        step_size = 3
        for i in range(0, len(bom_items), step_size):
            group = bom_items[i:i + step_size]
            step = {
                "step_id": (i // step_size) + 1,
                "mix_time_sec": 25,
                "items": []
            }
            for itm in group:
                step["items"].append({
                    "item_id": itm.get("item_code"),
                    "name": itm.get("item_name"),
                    "required_weight": itm.get("qty") or 0
                })
            kneader_workorder["workorder"]["steps"].append(step)

        # Send to controller
        controller_response = controller.send_command({
            "command": "load_workorder",
            "data": kneader_workorder["workorder"]
        })

        # Handle controller response
        if controller_response and not controller_response.get("error"):
            return jsonify({
                "status": "success",
                "message": f"{batchType.capitalize()} Work Order {workorder_name} loaded successfully",
                "workorder": kneader_workorder["workorder"]
            }), 200
        else:
            error_msg = controller_response.get("error", "Failed to load workorder into controller") \
                if controller_response else "Controller not responding"
            return jsonify({"status": "fail", "message": error_msg}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


import json
import requests

ERP_BASE_URL = "https://sppmaster.frappe.cloud"
ERP_HEADERS = {
    "Authorization": "token 0ebe5e4fe8d8bc7:79ec941325e2223",
    "Content-Type": "application/json"
}


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

    # === Select correct ERPNext endpoint ===
    if use_method:
        url = f"{ERP_BASE_URL}/api/method/frappe.client.get_list"
        encoded_params["doctype"] = doctype
    else:
        url = f"{ERP_BASE_URL}/api/resource/{doctype}"

    print("\n================ ERPNext API CALL ================")
    print(f"URL: {url}")
    print(f"Params: {encoded_params}")
    print(f"Headers: {headers}")

    resp = requests.get(url, headers=headers, params=encoded_params)

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


def get_final_production_item(token=None,manual_batch=None):
    try:
        if manual_batch:
            print(f"Using manually provided batch number: {manual_batch}")
            batch_no = manual_batch.strip()
        else:
            print("Auto-fetching latest Batch entry...")
        # Step 1 → Find Stock Entry where item_group = 'Batch'
        batch_entries = erp_get("Stock Entry", {
            "filters": [["Stock Entry Detail", "item_group", "=", "Batch"]],
            "fields": ["posting_date","item_name","items.batch_no"],
            "limit_page_length": 1,
            "order_by": "posting_date desc"
        },use_method=True, token=token)
        data = batch_entries.get("data") or batch_entries.get("message")
        if not data:
            print("No Stock Entry found with item_group='Batch'")
            return None

        batch_no = data[0].get("batch_no")
        if not batch_no:
            print("Stock Entry found but no batch_no field value")
            return None

        print(f"Step 1 → Batch No (Mix Barcode): {batch_no}")

        # Step 2 → Find Stock Entry where mix_barcode = batch_no
        mix_entries = erp_get("Stock Entry", {
            "filters": [["Stock Entry Detail", "mix_barcode", "=", batch_no]],
            "fields": ["item_name", "items.item_code"],
            "limit_page_length": 1
        }, token=token)  # Pass the token here

        mix_data = mix_entries.get("data") or mix_entries.get("message")
        if not mix_data:
            print(f"No Stock Entry found with mix_barcode={batch_no}")
            return None

        item_code_full = mix_data[0].get("item_code")
        if not item_code_full:
            print("Mix entry found but no item_code")
            return None

        print(f"Step 2 → Item Code (Full): {item_code_full}")

        prefix_match = re.search(r"B[_-]?\d+", item_code_full)
        item_code_prefix = prefix_match.group(0) if prefix_match else item_code_full.split()[0]

        print(f"🔹 Extracted Prefix for BOM: {item_code_prefix}")

        # Step 3 → Find BOM
        boms = erp_get("BOM", {
            "filters": [
                ["BOM Item","item_code", "=", item_code_prefix],
                ["is_default", "=", 1],
                ["is_active", "=", 1]
            ],
            "fields": ["item"],
            "limit_page_length": 1
        }, token=token)  # Pass the token here

        bom_data = boms.get("data") or boms.get("message")

        # Step 4 → If not found, try searching via BOM Item (child table)
        if not bom_data:
            print("No BOM found by item — retrying via child table...")
            boms = erp_get("BOM", {
                "filters": [
                    ["BOM Item", "item_code", "=", item_code_prefix],
                    ["BOM", "is_default", "=", 1]
                ],
                "fields": ["name", "item"],
                "limit_page_length": 1
            }, use_method=True, token=token)  # Pass the token here

            bom_data = boms.get("data") or boms.get("message")

        if not bom_data:
            print(f"No BOM found for item={item_code_prefix}")
            return None

        #bom_name = bom_data[0]["name"]
        final_item = bom_data[0]["item"]

        #print(f"Step 3 → Final Item: {final_item}, BOM: {bom_name}")

        return {
            "batch_no": batch_no,
            "item_code_full": item_code_full,
            "item_code_prefix": item_code_prefix,
            #"bom_name": bom_name,
            "final_item": final_item
        }

    except Exception as e:
        print(f"Error in get_final_production_item: {e}")
        return None



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


@app.route('/api/prescan', methods=['POST'])
@jwt_required()
def prescan_item():
    try:
        data = request.json
        barcode = data.get('barcode')
        if not barcode:
            return jsonify({"status": "fail", "message": "No barcode provided"})
        response = controller.send_command({"command": "prescan_item", "data": {"barcode": barcode}})


        if response:
            return jsonify(response)
        else:
            return jsonify({"status": "error", "message": "No response from controller"})
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
            return jsonify({"status": "fail", "message": response.get("error", "Failed to confirm prescan") if response else "Failed to confirm prescan"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/scan', methods=['POST'])
@jwt_required()
def scan_item():
    try:
        data = request.json
        barcode = data.get('barcode')
        if not barcode:
            return jsonify({"status": "fail", "message": "No barcode provided"})

        # Get current status
        status_response = controller.send_command({"command": "get_status"})
        current_state = status_response.get("process_state", "IDLE") if status_response else "IDLE"

        if current_state == "PRESCANNING":
            return prescan_item()
        elif current_state in ("WAITING_FOR_ITEMS", "MIXING"):
            scan_response = controller.send_command({"command": "scan_item", "data": {"barcode": barcode}})
            return jsonify(scan_response)
        else:
            return jsonify({
                "status": "fail",
                "message": f"Cannot scan in current state: {current_state}. Please wait for the current operation to complete."
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/status', methods=['GET'])
@jwt_required()
def get_status():
    try:
        response = controller.send_command({"command": "get_status"})
        if response and not response.get("error"):
            return jsonify(response)
        else:
            return jsonify({"process_state": "IDLE", "error_message": response.get("error", "Controller not responding") if response else "Controller not responding"})
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





if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
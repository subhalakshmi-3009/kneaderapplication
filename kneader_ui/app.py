import json
import threading
import socket
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import configparser
import requests
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)


app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
# === JWT CONFIG ===
app.config["JWT_SECRET_KEY"] = "super-secret-factory-key"  # 🔒 Change for production
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # Token never expires
jwt = JWTManager(app)
ERP_BASE_URL = "https://sppmaster.frappe.cloud"


HMI_HOST = "localhost"
HMI_PORT = 6000
LOG_DIR = "../logs"
log_file = os.path.join(LOG_DIR, "ui_controller.log")

os.makedirs(LOG_DIR, exist_ok=True)

class ControllerClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
        self._log("Controller client initialized")

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(3)
            self.socket.connect((HMI_HOST, HMI_PORT))
            self.connected = True
            self._log("Successfully connected to controller")
            return True
        except Exception as e:
            self._log(f"Connection failed: {str(e)}")
            self.connected = False
            return False

    def send_command(self, command, timeout=10):  # increased timeout
        if not self.connected:
            if not self.connect():
                return {"error": "Cannot connect to controller"}
        try:
            if command.get("command") == "scan_item":
                command["_via_hmi"] = True  # marker so controller knows to route it

            message = json.dumps(command) + "\n"
            with self.lock:
                try:
                    self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                except (socket.error, OSError):
                    self._log("Socket disconnected, reconnecting...")
                    self.connected = False
                    if not self.connect():
                        return {"error": "Cannot connect to controller"}

                self.socket.sendall(message.encode('utf-8'))
                self._log(f"Sent command: {message.strip()}")

                response_data = b""
                start_time = time.time()
                self.socket.settimeout(timeout)

                try:
                    while time.time() - start_time < timeout:
                        data = self.socket.recv(1024)
                        if not data:
                            break
                        response_data += data
                        try:
                            response_str = response_data.decode('utf-8').strip()
                            if response_str:
                                json.loads(response_str)
                                break
                        except json.JSONDecodeError:
                            continue
                except socket.timeout:
                    pass

                if response_data:
                    response_str = response_data.decode('utf-8').strip()
                    self._log(f"Received response: {response_str}")
                    try:
                        return json.loads(response_str)
                    except json.JSONDecodeError:
                        return {"raw_response": response_str}
                else:
                    self._log("No response from controller")
                    return {"error": "No response from controller"}

        except Exception as e:
            self._log(f"Send command error: {str(e)}")
            self.connected = False
            return {"error": str(e)}

    def _log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_file, "a", encoding='utf-8') as f:
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            print(f"Failed to write to log file: {e}")
        print(message)



controller = ControllerClient()

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
    username = data.get("username")
    password = data.get("password")

    try:
        # Authenticate with ERPNext
        erp_resp = requests.post(
            f"{ERP_BASE_URL}/api/method/login",
            data={"usr": username, "pwd": password},
            timeout=10
        )

        print("ERPNext response:", erp_resp.status_code, erp_resp.text)

        # ERPNext returns HTTP 200 even for invalid login, so check content
        if "Invalid Login" in erp_resp.text or "error" in erp_resp.text.lower():
            return jsonify({"msg": "Invalid ERPNext credentials"}), 401

        # Success → create our own token
        token = create_access_token(identity=username)
        return jsonify({"token": token}), 200

    except Exception as e:
        print("Login error:", e)
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
    try:
        data = request.json
        batchNumber = data.get('batchNumber')
        batchType   = data.get('batchType', 'compound')  # default to compound

        # Decide which file to load
        if batchType == 'master':
            workorder_file = r"C:/Users/rkann/config_files/workordersmb.json"
        else:
            workorder_file = r"C:/Users/rkann/config_files/workorders.json"

        # Load from correct file
        with open(workorder_file, 'r') as f:
            workorders = json.load(f)

        # Search batch
        selected_workorder = None
        for wo in workorders:
            if wo.get("batch_number") == batchNumber:
                selected_workorder = wo["workorder"]
                break

        if not selected_workorder:
            return jsonify({"status": "fail", "message": "Workorder not found"})

        # Send to controller
        response = controller.send_command({
            "command": "load_workorder",
            "data": selected_workorder
        })
        if response and not response.get("error"):
            return jsonify({
                "status": "success",
                "message": f"{batchType.capitalize()} Workorder loaded for pre-scanning",
                "workorder": selected_workorder
            })
        else:
            error_msg = response.get("error", "Failed to load workorder") if response else "Failed to load workorder"
            return jsonify({"status": "fail", "message": error_msg})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/prescan', methods=['POST'])
@jwt_required()
def prescan_item():
    try:
        data = request.json
        barcode = data.get('barcode')
        if not barcode:
            return jsonify({"status": "fail", "message": "No barcode provided"})
        response = controller.send_command({"command": "prescan_item", "data": {"barcode": barcode}})

        # Always return the response from controller to let frontend handle different statuses
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
        return jsonify({"status": "success", "message": "Controller reset after completion", "data": response})
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




if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
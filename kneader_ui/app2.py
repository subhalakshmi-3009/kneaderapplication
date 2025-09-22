import json
import threading
import socket
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.serving import WSGIRequestHandler
import os
import configparser


app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Configuration - FIXED PATHS
HMI_HOST = "localhost"
HMI_PORT = 6000
LOG_DIR = "../logs"
log_file = os.path.join(LOG_DIR, "ui_controller.log")  # Fixed path

# Create logs directory if it doesn't exist
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

    def send_command(self, command, timeout=3):
        """Send command to controller and return response"""
        if not self.connected:
            if not self.connect():
                return {"error": "Cannot connect to controller"}

        try:
            message = json.dumps(command) + "\n"

            with self.lock:
                # Test connection properly
                try:
                    self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                except (socket.error, OSError):
                    self._log("Socket disconnected, reconnecting...")
                    self.connected = False
                    if not self.connect():
                        return {"error": "Cannot connect to controller"}

                self.socket.sendall(message.encode('utf-8'))
                self._log(f"Sent command: {message.strip()}")

                # Improved response handling
                response_data = b""
                start_time = time.time()
                self.socket.settimeout(timeout)

                try:
                    while time.time() - start_time < timeout:
                        data = self.socket.recv(1024)
                        if not data:
                            break
                        response_data += data
                        # Check for complete JSON
                        try:
                            response_str = response_data.decode('utf-8').strip()
                            if response_str:
                                json.loads(response_str)  # Test if valid JSON
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
        print(message)  # Always print to console

    def _handle_gateway_event(self, event):
        """Handle events from gateway if needed"""
        print(f"Gateway event: {event}")
        # Implement your event handling logic here


# Initialize controller client
controller = ControllerClient()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
print(f"Config current_dir {parent_dir}")
#config_path = os.path.join(parent_dir, 'C:\\Users\\rkann\\PycharmProjects\\kneaderrestructured\\kneader\\config.ini')
config_path = os.path.join(parent_dir, '.\\kneader\\config.ini')

config = configparser.ConfigParser()
config.read(config_path)
workorders_file = config["files"]["workorder_config_file"]


def load_workorders():
    try:
        print(f"DEBUG: Loading workorders from {workorders_file}")
        with open(workorders_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"DEBUG: Workorders file not found: {workorders_file}")
        return None
            


@app.route('/')
def serve_ui():
    return send_from_directory('static', 'index.html')


@app.route('/api/batches/:batch_number', methods=['GET'])
def get_batches():
    try:
        workorders = load_workorders()
        batches = [{"batchNumber": wo["batch_number"], "name": wo["workorder"]["name"]} for wo in workorders]
        return jsonify(batches)
    except Exception as e:
        print(f"DEBUG: Exception in get_batches: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/load_workorder', methods=['POST'])
def load_workorder():
    try:
        data = request.json
        batchNumber = data.get('batchNumber')
        
        workorders = load_workorders()
        selected_workorder = None
        
        for wo in workorders:
            if wo.get("batch_number") == batchNumber:
                selected_workorder = wo["workorder"]
                break
        
        if not selected_workorder:
            return jsonify({"status": "fail", "message": "Workorder not found"})
        
        # Send command to controller to load the workorder for pre-scanning
        response = controller.send_command({
            "command": "load_workorder",
            "data": selected_workorder
        })
        
        if response and not response.get("error"):
            return jsonify({
                "status": "success", 
                "message": "Workorder loaded for pre-scanning",
                "workorder": selected_workorder
            })
        else:
            error_msg = response.get("error", "Failed to load workorder") if response else "Failed to load workorder"
            return jsonify({"status": "fail", "message": error_msg})
            
    except Exception as e:
        print(f"DEBUG: Exception in load_workorder: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/prescan', methods=['POST'])
def prescan_item():
    try:
        data = request.json
        barcode = data.get('barcode')
        if not barcode:
            return jsonify({"status": "fail", "message": "No barcode provided"})

        # Send prescan command to controller
        response = controller.send_command({"command": "prescan_item",
            "data": {"barcode": barcode}})
        
        if response and not response.get("error"):
            return jsonify(response)
        else:
            error_msg = response.get("error", "Failed to confirm pre-scanning") if response else "Failed to confirm pre-scanning"
            return jsonify({"status": "fail", "message": error_msg})
            
    except Exception as e:
        print(f"DEBUG: Exception in confirm_prescan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/confirm_prescan', methods=['POST'])
def confirm_prescan():
    try:
        response = controller.send_command({"command": "confirm_start"})
        
        if response and response.get("status") == "success":  # Changed from checking for "error"
            return jsonify({"status": "success", "message": "Pre-scanning confirmed"})
        else:
            error_msg = response.get("message", "Failed to confirm pre-scanning") if response else "Failed to confirm pre-scanning"
            return jsonify({"status": "fail", "message": error_msg})
            
    except Exception as e:
        print(f"DEBUG: Exception in confirm_prescan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        response = controller.send_command({"command": "get_status"})
        print(f"DEBUG: Raw controller response: {response}")

        # If controller not responding, try to reconnect
        if response and response.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False  # Force reconnection
            response = controller.send_command({"command": "get_status"})
            print(f"DEBUG: Status after reconnection attempt: {response}")

        if response and not response.get("error"):
            return jsonify(response)
        else:
            error_msg = response.get("error", "Controller not responding") if response else "Controller not responding"
            print(f"DEBUG: Controller error: {error_msg}")

            return jsonify({
                "process_state": "IDLE",
                "lid_open": True,
                "motor_running": False,
                "current_step_index": -1,
                "current_item_index": -1,
                "mixing_time_remaining": 0,
                "error_message": error_msg,
                "workorder_id": None
            })
    except Exception as e:
        print(f"DEBUG: Exception in get_status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scan', methods=['POST'])
def scan_item():
    try:
        data = request.json
        barcode = data.get('barcode')

        if not barcode:
            return jsonify({"status": "fail", "message": "No barcode provided"})

        # Get current status
        status_response = controller.send_command({"command": "get_status"})
        print(f"DEBUG: Current status before scan: {status_response}")

        # If controller not responding, try to reconnect
        if status_response and status_response.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False  # Force reconnection
            status_response = controller.send_command({"command": "get_status"})
            print(f"DEBUG: Status after reconnection attempt: {status_response}")

        if status_response and isinstance(status_response, dict) and not status_response.get("error"):
            current_state = status_response.get("process_state", "IDLE")
        else:
            current_state = "IDLE"
        #if current_state == "PRESCANNING" or current_state == "PRESCAN_COMPLETE":
        #    return prescan_item()
        
       # workorders = load_workorders()
        if current_state == "PRESCANNING" or current_state == "PRESCAN_COMPLETE":
                scan_response = controller.send_command({
                    "command": "scan_item",
                    "data": {"barcode": barcode}
                })
                
                if scan_response and not scan_response.get("error"):
                    return jsonify(scan_response)
                else:
                    error_msg = scan_response.get("error", "Scan failed") if scan_response else "Scan failed"
                    return jsonify({"status": "fail", "message": error_msg})
        else:
            current_state = "IDLE"

        workorders = load_workorders()

        if current_state == "WAITING_FOR_ITEMS":
            # Find matching workorder
            matching_workorder = None
            for workorder in workorders:
                if workorder.get("steps") and workorder["steps"][0].get("items"):
                    for item in workorder["steps"][0]["items"]:
                        if item.get("item_id") == barcode:
                            matching_workorder = workorder
                            break
                    if matching_workorder:
                        break

            if matching_workorder:
                # Start workorder
                print(f"DEBUG: Starting workorder: {matching_workorder['workorder_id']}")
                start_response = controller.send_command({
                    "command": "load_and_start_workorder",
                    "data": matching_workorder,
                    "barcode":barcode
                })
                print(f"DEBUG: Start workorder response: {start_response}")

                if start_response and not start_response.get("error"):
                    return jsonify({
                        "status": "success",
                        "message": f"Workorder {matching_workorder['workorder_id']} started"
                    })
                else:
                    error_msg = start_response.get("error",
                                                   "Failed to start workorder") if start_response else "Failed to start workorder"
                    return jsonify({"status": "fail", "message": error_msg})

        # If not starting a new workorder, scan the item
        print(f"DEBUG: Scanning item: {barcode}")
        scan_response = controller.send_command({
            "command": "scan_item",
            "data": {"barcode": barcode}
        })
        print(f"DEBUG: Scan response: {scan_response}")

        if scan_response and not scan_response.get("error"):
            return jsonify(scan_response)
        else:
            error_msg = scan_response.get("error", "Scan failed") if scan_response else "Scan failed"
            return jsonify({"status": "fail", "message": error_msg})

    except Exception as e:
        print(f"DEBUG: Exception in scan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/check_transitions', methods=['GET'])
def check_state_transitions():
    """Check and trigger state transitions in the controller"""
    try:
        # Get current status
        status = controller.send_command({"command": "get_status"})

        print(f"DEBUG: Current status from controller: {status}")

        # If controller not responding, try to reconnect
        if status and status.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False  # Force reconnection
            status = controller.send_command({"command": "get_status"})
            print(f"DEBUG: Status after reconnection attempt: {status}")

        if status and not status.get("error"):
            process_state = status.get("process_state")
            print(f"DEBUG: Process state: {process_state}")

            # If waiting for lid close, send close command
            if process_state == "WAITING_FOR_LID_CLOSE":
                print("DEBUG: Sending lid close command")
                close_response = controller.send_command({
                    "command": "write",
                    "tag_name": "wr_lid_status_kn1",
                    "value": 1  # Close lid
                })
                print(f"DEBUG: Lid close response: {close_response}")

                if close_response and not close_response.get("error"):
                    return jsonify({"status": "success", "message": "Lid close command sent"})
                else:
                    error_msg = close_response.get("error",
                                                   "Failed to send lid close command") if close_response else "Failed to send lid close command"
                    return jsonify({"status": "error", "message": error_msg})

            # If waiting for motor start, send start command
            elif process_state == "WAITING_FOR_MOTOR_START":
                print("DEBUG: Sending motor start command")
                motor_response = controller.send_command({
                    "command": "write",
                    "tag_name": "wr_motor_control_kn1",
                    "value": 1  # Start motor
                })
                print(f"DEBUG: Motor start response: {motor_response}")

                if motor_response and not motor_response.get("error"):
                    return jsonify({"status": "success", "message": "Motor start command sent"})
                else:
                    error_msg = motor_response.get("error",
                                                   "Failed to send motor start command") if motor_response else "Failed to send motor start command"
                    return jsonify({"status": "error", "message": error_msg})

            return jsonify({"status": "no_action", "message": "No transition needed"})

        return jsonify({"status": "error", "message": "Cannot get status from controller"})

    except Exception as e:
        print(f"DEBUG: Exception in check_transitions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/control/abort', methods=['POST'])
def abort_process():
    try:
        response = controller.send_command({"command": "abort"})
        print(f"DEBUG: Abort response: {response}")

        # If controller not responding, try to reconnect
        if response and response.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False  # Force reconnection
            response = controller.send_command({"command": "abort"})
            print(f"DEBUG: Abort response after reconnection: {response}")

        if response and not response.get("error"):
            return jsonify(response)
        else:
            error_msg = response.get("error", "Failed to abort process") if response else "Failed to abort process"
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        print(f"DEBUG: Exception in abort: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
def resume_process():
    try:
        response = controller.send_command({"command": "resume"})
        print(f"DEBUG: Resume response: {response}")
        
        if response and response.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False
            response = controller.send_command({"command": "resume"})
            print(f"DEBUG: Resume response after reconnection: {response}")
        
        if response and not response.get("error"):
            return jsonify(response)
        else:
            error_msg = response.get("error", "Failed to resume process") if response else "Failed to resume process"
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        print(f"DEBUG: Exception in resume: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/reset', methods=['POST'])
def reset_controller():
    try:
        response = controller.send_command({"command": "reset_controller"})
        print(f"DEBUG: Reset response: {response}")

        # If controller not responding, try to reconnect
        if response and response.get("error") == "No response from controller":
            print("DEBUG: Controller not responding, attempting to reconnect...")
            controller.connected = False  # Force reconnection
            response = controller.send_command({"command": "reset_controller"})
            print(f"DEBUG: Reset response after reconnection: {response}")

        if response and not response.get("error"):
            return jsonify(response)
        else:
            error_msg = response.get("error",
                                     "Failed to reset controller") if response else "Failed to reset controller"
            return jsonify({"status": "fail", "message": error_msg})
    except Exception as e:
        print(f"DEBUG: Exception in reset: {e}")
        return jsonify({"error": str(e)}), 500




@app.route('/api/workorders', methods=['GET'])
def get_workorders():
    try:
        workorders = load_workorders()
        return jsonify(workorders)
    except Exception as e:
        print(f"DEBUG: Exception in get_workorders: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # Test connection
    test_response = controller.send_command({"command": "get_status"})
    print(f"DEBUG: Health check response: {test_response}")

    # If controller not responding, try to reconnect
    if test_response and test_response.get("error") == "No response from controller":
        print("DEBUG: Controller not responding, attempting to reconnect...")
        controller.connected = False  # Force reconnection
        test_response = controller.send_command({"command": "get_status"})
        print(f"DEBUG: Health check after reconnection: {test_response}")

    controller_ok = test_response is not None and not test_response.get("error")

    return jsonify({
        "flask_status": "running",
        "controller_connected": controller.connected,
        "controller_responded": controller_ok,
        "controller_response": test_response if controller_ok else {"error": "Controller not responding"}
    })


if __name__ == '__main__':
   

    print(f"Starting Flask server, connecting to controller at {HMI_HOST}:{HMI_PORT}")
    app.run(debug=True, port=5000, host='0.0.0.0')
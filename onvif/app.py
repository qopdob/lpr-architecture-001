import os
from typing import Dict
from uuid import UUID

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

from gate.camera import CameraRelay

load_dotenv()

app = Flask(__name__)
CORS(app)

BASE_URL = 'http://acs:8000/api'
gates: Dict[UUID, CameraRelay] = {}

def fetch_data(endpoint: str) -> dict:
    response = requests.get(f"{BASE_URL}/{endpoint}")
    response.raise_for_status()
    return response.json()

def initialize_gates():
    global gates
    gates_data = fetch_data("gates/")
    gates = {
        UUID(gate['gate_id']): CameraRelay(
            uuid=UUID(gate['gate_id']),
            ip=gate['ip'],
            port=gate['port'],
            user=gate['username'],
            password=gate['password'],
        ) for gate in gates_data
    }

@app.before_first_request
def before_first_request():
    initialize_gates()

@app.route('/activate/<uuid:gate_id>', methods=['POST'])
def activate_gate(gate_id):
    if gate_id not in gates:
        return jsonify({"error": "Gate not found"}), 404
    
    success = gates[gate_id].activate()
    if success:
        return jsonify({"message": "Gate activated successfully"}), 200
    else:
        return jsonify({"error": "Failed to activate gate"}), 500

@app.route('/refresh-gates', methods=['POST'])
def refresh_gates():
    try:
        initialize_gates()
        return jsonify({"message": "Gates refreshed successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to refresh gates: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='8080', debug=True)

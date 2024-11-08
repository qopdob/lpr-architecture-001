import requests
from flask import Flask, request
from flask_cors import CORS
from werkzeug.serving import run_simple
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from typing import Dict
from uuid import UUID

app = Flask(__name__)
CORS(app)

ACS_BASE_URL = 'http://acs:8000/api'
GATE_BASE_URL = 'http://onvif:8080/'

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables to store configuration
gates_data = None
stream_to_gate = None
streams_data = None
camera_ip_to_data = None


def fetch_data(endpoint: str) -> dict:
    response = requests.get(f"{ACS_BASE_URL}/{endpoint}")
    response.raise_for_status()
    return response.json()


def setup_configuration():
    global gates_data, stream_to_gate, streams_data, camera_ip_to_data

    gates_data = fetch_data("gates/")

    stream_to_gate_data = fetch_data("stream-to-gate-mapping/")
    logging.info(f'stream_to_gate mapping: {stream_to_gate_data}')
    stream_to_gate = {
        UUID(item['camera_id']): UUID(item['gate_id']) for item in stream_to_gate_data if item
    }

    streams_data = fetch_data("streams/")
    logging.info(f'streams_data: {streams_data}')

    # Create a dict with camera IP as key and camera data as value
    camera_ip_to_data = {
        camera['stream_ip']: camera for camera in streams_data if 'stream_ip' in camera
    }
    logging.info(f'camera_ip_to_data: {camera_ip_to_data}')

def parse_xml_content(xml_content):
    root = ET.fromstring(xml_content)
    event_data = {}
    for child in root:
        key = child.tag.split('}')[-1]  # Remove namespace
        event_data[key] = child.text
    return event_data


def check_recent_access(camera_id: UUID) -> bool:
    response = requests.get(f"{ACS_BASE_URL}/recent-access-check/?camera_id={camera_id}&duration=3")
    response.raise_for_status()
    data = response.json()
    return data.get('recent_access', False)


def activate_gate(gate_id: UUID):
    response = requests.post(f"{GATE_BASE_URL}/activate/{gate_id}")
    response.raise_for_status()
    return response.json()


@app.before_first_request
def before_first_request():
    setup_configuration()


@app.route('/event', methods=['GET', 'POST'])
def alarm():
    if request.method == 'GET':
        return "Hikvision Alarm Server is running", 200

    if request.method == 'POST':
        try:
            if 'AlarmIn.xml' in request.files:
                xml_file = request.files['AlarmIn.xml']
                xml_content = xml_file.read().decode('utf-8')
            else:
                xml_content = request.get_data(as_text=True)

            xml_content = xml_content.split('--boundary--')[0].strip()
            event_data = parse_xml_content(xml_content)

            # Check if it's an active IO alarm
            if event_data.get('eventType') != 'IO' or event_data.get('eventState') != 'active':
                logger.info(f"Ignoring non-active or non-IO alarm from {event_data.get('ipAddress')}")
                return "Alarm ignored", 200

            logger.info(f"Processing active IO alarm from {event_data.get('ipAddress')}")

            # Process the alarm
            camera_ip = event_data.get('ipAddress')
            if camera_ip in camera_ip_to_data:
                camera_data = camera_ip_to_data[camera_ip]
                camera_id = UUID(camera_data['camera_id'])

                if check_recent_access(camera_id):
                    gate_id = stream_to_gate.get(camera_id)
                    if gate_id:
                        activation_result = activate_gate(gate_id)
                        logger.info(f"Gate {gate_id} activated for camera {camera_id}")
                    else:
                        logger.warning(f"No gate found for camera {camera_id}")
                else:
                    logger.info(f"No recent access for camera {camera_id}, gate not activated")
            else:
                logger.warning(
                    f"No camera data found for IP {camera_ip}. Available IPs: {list(camera_ip_to_data.keys())}")

            return "Alarm processed", 200
        except Exception as e:
            logger.error(f"Error processing alarm: {str(e)}")
            return f"Error processing alarm: {str(e)}", 500


if __name__ == '__main__':
    logger.info("Starting Hikvision Alarm Server...")
    logger.info("Listening on all interfaces, port 5000")
    run_simple('0.0.0.0', 5000, app, use_reloader=True, use_debugger=True)

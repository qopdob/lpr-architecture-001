import base64
import logging
import requests
import pytz
import cv2
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4
from typing import Dict, Deque
from data.config import config
from io import BytesIO
from PIL import Image
from predictors.detector import Detector
from stream.streams import Stream
from predictors.base import QueuedPredictor

from config_setup import setup_configuration


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_BASE_URL = config['acs']['base_url']

class LPRSystem:
    def __init__(self):
        self.streams_last_relay_lock = Lock()
        self.streams_last_event: Dict[UUID, Dict] = {}
        # self.gates: Dict[UUID, CameraRelay] = {}
        self.stream_to_gate: Dict[UUID, UUID] = {}
        self.streams: Dict[UUID, Stream] = {}
        self.detectors: Dict[UUID, Detector] = {}
        self.plate_infer_queue: QueuedPredictor = None
        self.char_infer_queue: QueuedPredictor = None
        self.plate_balancing_queue: Deque[UUID] = deque(maxlen=100)
        self.char_balancing_queue: Deque[UUID] = deque(maxlen=100)

    def setup(self):
        # Fetch configuration from Django microservice
        # self.gates, self.stream_to_gate, self.streams, self.detectors = setup_configuration(self.on_event)
        self.stream_to_gate, self.streams, self.detectors = setup_configuration(self.on_event)

        # Initialize streams_last_event
        self.streams_last_event = {
            stream_id: {
                'recognition': '',
                'datetime': datetime.utcnow(),
            } for stream_id, stream in self.streams.items()
        }

        # Setup inference queues
        self.plate_infer_queue = QueuedPredictor(callback=self.on_plates_detection, **config['models']['plate'])
        self.char_infer_queue = QueuedPredictor(callback=self.on_chars_detection, **config['models']['char'])

    def on_event(self, event_data: dict):
        _stream_uuid = event_data['stream_uuid']
        last_recognition = self.streams_last_event[_stream_uuid]
        is_different = event_data['recognition'] != last_recognition['recognition']
        time_delta = event_data['datetime'] - last_recognition['datetime']

        if is_different or time_delta.seconds > config['event']['duplicate_delay']:
            with self.streams_last_relay_lock:
                self.streams_last_event[_stream_uuid].update({
                    'recognition': event_data['recognition'],
                    'datetime': event_data['datetime'],
                })
            is_new_event = True
        else:
            is_new_event = False

        utc_datetime = pytz.utc.localize(event_data['datetime'])
        moscow_timezone = pytz.timezone('Europe/Moscow')
        moscow_datetime = utc_datetime.astimezone(moscow_timezone)

        if is_new_event:
            frame = event_data['frame']
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            buffered = BytesIO()
            image.save(buffered, format="JPEG", quality=50)
            img_str = base64.b64encode(buffered.getvalue()).decode()
            image_data = f"data:image/jpeg;base64,{img_str}"
        else:
            image_data = None

        lpr_event_data = {
            'camera_id': str(_stream_uuid),
            'license_plate': event_data['recognition'].upper(),
            'timestamp': moscow_datetime.isoformat(),
            'is_new_event': is_new_event,
        }

        if image_data is not None:
            lpr_event_data['image'] = image_data

        try:
            response = requests.post(f'{API_BASE_URL}/lpr-event/', json=lpr_event_data)
            response.raise_for_status()
            # result = response.json()

            # logging.info(f'LPR event sent: {lpr_event_data["license_plate"]}')
            # logging.info(f'Server response: {result}')
            #
            # if result.get('access_granted'):
            #     gate_uuid = self.stream_to_gate.get(_stream_uuid)
            #     if gate_uuid:
            #         self.gates[gate_uuid].activate()
            #         logging.info(f'Gate# {gate_uuid} - access granted, gate activated.')
            #     else:
            #         logging.warning(f'No gate associated with stream {_stream_uuid}')
            # else:
            #     reason = result.get('reason_for_refuse', 'Unknown reason')
            #     logging.info(f'Access denied for license plate: {event_data["recognition"]}. Reason: {reason}')
            #
            # # Log additional information from the response
            # logging.info(f'Event details: Camera: {result.get("camera_name")}, '
            #              f'License Plate: {result.get("license_plate")}, '
            #              f'Timestamp: {result.get("timestamp")}')

        except requests.RequestException as e:
            logging.error(f'Failed to send LPR event to server: {e}')

    def on_plates_detection(self, result):
        _stream_uuid = result['userdata']['stream_uuid']
        _frame_uuid = result['userdata']['frame_uuid']

        with self.detectors[_stream_uuid].lock:
            self.detectors[_stream_uuid].on_plates_detection(result, _frame_uuid)

    def on_chars_detection(self, result):
        _stream_uuid = result['userdata']['stream_uuid']
        _frame_uuid = result['userdata']['frame_uuid']

        with self.detectors[_stream_uuid].lock:
            self.detectors[_stream_uuid].on_chars_detection(result, _frame_uuid)

    def run(self):
        while True:
            self.process_char_queue()
            self.process_plate_queue()

    def process_char_queue(self):
        while self.char_balancing_queue and self.char_infer_queue.is_ready:
            stream_uuid = self.char_balancing_queue.popleft()
            detector = self.detectors[stream_uuid]
            with detector.lock:
                frame_uuid = detector.frames_awaiting_recognition.popleft()
                if frame_uuid not in detector.frames:
                    continue
                cropped = detector.frames[frame_uuid].cropped
            data = {
                'stream_uuid': stream_uuid,
                'frame_uuid': frame_uuid,
            }
            self.char_infer_queue.add_frame(cropped, userdata=data)

        if not self.char_balancing_queue:
            for stream_uuid, detector in self.detectors.items():
                with detector.lock:
                    if detector.frames_awaiting_recognition:
                        self.char_balancing_queue.append(stream_uuid)

    def process_plate_queue(self):
        while self.plate_balancing_queue and self.plate_infer_queue.is_ready:
            stream_uuid = self.plate_balancing_queue.popleft()
            stream = self.streams[stream_uuid]
            with stream.frame_lock:
                frame = stream.pop_frame()
            if frame is not None:
                frame_uuid = uuid4()
                data = {
                    'stream_uuid': stream_uuid,
                    'frame_uuid': frame_uuid,
                }
                detector = self.detectors[stream_uuid]
                with detector.lock:
                    detector.on_plates_detection_requested(frame_uuid, frame.copy())
                self.plate_infer_queue.add_frame(frame, userdata=data)

        if not self.plate_balancing_queue:
            for stream_uuid, detector in self.detectors.items():
                with detector.lock:
                    if detector.is_high_priority:
                        self.plate_balancing_queue.append(stream_uuid)


if __name__ == '__main__':
    lpr_system = LPRSystem()
    lpr_system.setup()
    lpr_system.run()


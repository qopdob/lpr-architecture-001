import requests
import logging
from uuid import UUID
from typing import Dict, Callable

from gate.camera import CameraRelay
from stream.streams import Stream
from predictors.detector import Detector
from data.config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = config['acs']['base_url']

def fetch_data(endpoint: str) -> dict:
    response = requests.get(f"{BASE_URL}/{endpoint}")
    response.raise_for_status()
    return response.json()

def setup_configuration(on_event: Callable):
    # gates_data = fetch_data("gates/")
    # gates: Dict[UUID, CameraRelay] = {
    #     UUID(gate['gate_id']): CameraRelay(
    #         uuid=gate['gate_id'],
    #         ip=gate['ip'],
    #         port=gate['port'],
    #         user=gate['username'],
    #         password=gate['password'],
    #     ) for gate in gates_data
    # }

    stream_to_gate_data = fetch_data("stream-to-gate-mapping/")
    logging.info(f'stream_to_gate mapping: {stream_to_gate_data}')
    stream_to_gate: Dict[UUID, UUID] = {
        UUID(item['camera_id']): UUID(item['gate_id']) for item in stream_to_gate_data if item
    }

    streams_data = fetch_data("streams/")
    streams: Dict[UUID, Stream] = {
        UUID(stream['camera_id']): Stream(
            uuid=stream['camera_id'],
            ip=stream['stream_ip'],
            port=stream['stream_port'],
            link=stream['stream_path'],
            user=stream['username'],
            password=stream['password'],
        ) for stream in streams_data
    }

    detectors: Dict[UUID, Detector] = {
        UUID(stream['camera_id']): Detector(UUID(stream['camera_id']), on_event)
        for stream in streams_data
    }

    # return gates, stream_to_gate, streams, detectors
    return stream_to_gate, streams, detectors


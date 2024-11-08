from datetime import datetime
import logging
import time
from typing import Optional
from uuid import UUID
from collections import deque, Counter
from threading import Lock

import numpy as np

from data.config import config
from predictors.processor import PlatePredictions, PlatePrediction, CharDetections
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class Frame:
    def __init__(self, uuid: UUID, original_image: np.array, timestamp: float):
        self.uuid: UUID = uuid
        self.original_image = original_image
        self.timestamp = timestamp
        self._plate_detections: Optional[PlatePredictions] = None
        self.plate_detection: Optional[PlatePrediction] = None  # most conf only
        self.recognition: Optional[CharDetections] = None

        self.is_not_empty = False  # detection with 0 boxes received
        self.is_dropped = False  # for future implementation of postprocess filtering

    @property
    def cropped(self):
        return self.plate_detection.cropped

    def on_plates_detection(self, result) -> None:
        if len(result['det']) == 0:
            return
        
        _plate_detections = PlatePredictions(result, self.original_image)
        _plate_detection = _plate_detections.plates[0]
        
        # TODO: CUSTOM FILTER HARDCODE SUKAAA UBRAT!
        # if (_plate_detection.box[2] + _plate_detection.box[0]) / 2 < self.original_image.shape[1] * 0.25:
        #     logging.info(f'Dropped frame with box={_plate_detection.box}')
        #     return
            
        # logging.info(f'Frame with box[3]={_plate_detection.box}')
        
        self._plate_detections = _plate_detections
        self.plate_detection = _plate_detection
        
        self.is_not_empty = True

    def on_chars_detection(self, result) -> None:
        if len(result['det']) != 0:
            self.recognition = CharDetections(result, self.cropped)


class Detector:
    STARVING_DELAY = config['detector']['starving_delay']
    OUTDATED_DELAY = config['detector']['outdated_delay']
    CONF_THRESHOLD = config['detector']['conf_threshold']
    COUNT_THRESHOLD = config['detector']['count_threshold']
    JUMP_THRESHOLD = config['detector']['jump_threshold']

    def __init__(self, uuid, event_callback):
        self.uuid: UUID = uuid
        self._last_detection_timestamp = time.time()
        self._last_detection_pos = 0, 0
        self.frames: dict[UUID, Frame] = {}
        self.frames_timeline: deque[UUID] = deque(maxlen=20)
        self.frames_awaiting_recognition: deque[UUID] = deque(maxlen=20)

        self.lock = Lock()
        self.event_callback = event_callback

        self._is_occupied = False

    @property
    def is_starving(self) -> bool:
        return time.time() - self._last_detection_timestamp > self.STARVING_DELAY

    @property
    def is_occupied(self) -> bool:
        return self._is_occupied

    @property
    def is_high_priority(self) -> bool:
        return self._is_occupied or self.is_starving

    def _drop_outdated(self) -> None:
        garbage = set(self.frames.keys()) - set(self.frames_timeline)
        for frame_uuid in garbage:
            del self.frames[frame_uuid]

    def on_plates_detection_requested(self, uuid: UUID, original_image: np.array):
        self.frames_timeline.append(uuid)
        self.frames[uuid] = Frame(uuid, original_image, time.time())
        self._drop_outdated()

    def on_plates_detection(self, result: dict, uuid: UUID):
        if uuid not in self.frames:
            logging.info(f'Frame was cleaned (old or recognized event), detection ignored.'
                            f'id# {uuid}')
            return
        frame = self.frames[uuid]
        frame.on_plates_detection(result)

        postprocess_filtered = False  # for future implementation as needed

        is_occupied = True
        
        
        
        if not frame.is_not_empty:
            is_occupied = False
        elif postprocess_filtered:
            frame.is_dropped = True
        else:
            pos = frame.plate_detection.box[:2]
            l_pos = self._last_detection_pos
            relative_movement = ((pos[0]-l_pos[0])**2+(pos[1]-l_pos[1])**2)**0.5 / sum(frame.original_image.shape[:2])
            if relative_movement > self.JUMP_THRESHOLD:
                self.frames_timeline.clear()
                logging.warning(f'New recognition is far away (by h) from the previous,'
                             f' cleaning timeline.')
            self.frames_awaiting_recognition.append(uuid)
            self._last_detection_timestamp = frame.timestamp
            self._last_detection_pos = pos

        self._is_occupied = is_occupied

    def consider_event(self) -> None:
        analyzer = Counter()
        counter = Counter()
        for frame_uuid in self.frames_timeline:
            frame = self.frames[frame_uuid]
            if frame.recognition is not None and frame.recognition.string is not None:
                chars_confs = frame.recognition.confs
                conf = frame.plate_detection.conf * sum(chars_confs) / len(chars_confs)
                analyzer[frame.recognition.string] += conf
                counter[frame.recognition.string] += 1
        if not analyzer or not counter:
            return
        best, conf = analyzer.most_common(1)[0]
        relative_conf = conf / analyzer.total() * 100
        if relative_conf > self.CONF_THRESHOLD and counter[best] >= self.COUNT_THRESHOLD:
            event_data = {
                'stream_uuid': self.uuid,
                'recognition': best,
                'datetime': datetime.utcnow(),
                'frame': self.frames[self.frames_timeline[-1]].original_image,
            }
            self.event_callback(event_data)

    def on_chars_detection(self, result: dict, uuid: UUID):
        if uuid not in self.frames:
            logging.info(f'Frame was cleaned (old or recognized event), detection ignored.'
                         f'id# {uuid}')
            return
        self.frames[uuid].on_chars_detection(result)
        self.consider_event()



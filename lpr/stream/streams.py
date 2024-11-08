import logging
import time
from threading import Thread, Lock
from typing import Optional
from uuid import UUID

import cv2
import numpy as np


class Stream:
    RECONNECTION_DELAY = 5

    def __init__(
            self,
            uuid: UUID,
            url: str = None,
            ip: str = None,
            port: str = None,
            link: str = None,
            user: str = None,
            password: str = None
    ):
        if url is not None:
            self._url = url
        elif ip is not None and port is not None:
            self._id = uuid
            self._stream = None
            auth = f'{user}:{password}@' if user or password else ''
            self._url = f'rtsp://{auth}{ip}:{port}/{link.lstrip("/") or ""}'

            self._stop_flag = False
            self._dropped = False
            self._thread = None
            self._frame = None
            self.frame_lock = Lock()

            self._open(initial=True)
        else:
            raise ValueError("Either 'url' or 'ip', 'port', 'link' must be provided.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _update(self, reconnection_delay: Optional[int] = None) -> None:
        if reconnection_delay is not None:
            logging.warning(f'Reconnecting in {reconnection_delay} second(s).')
            time.sleep(reconnection_delay)

        try:
            self._stream = cv2.VideoCapture(self._url)
            logging.info(f'Stream connected.')
            while self.is_open:
                ret, frame = self._stream.read()
                if not ret:
                    break

                with self.frame_lock:
                    self._frame = frame

        except Exception as e:
            logging.warning(f"Error reading the stream: {e}")
        finally:
            logging.warning(f'Stream disconnected.')
            if self._stream:
                self._stream.release()
            self._dropped = True

    @property
    def is_open(self) -> bool:
        return not self._stop_flag and (self._stream is not None) and self._stream.isOpened()

    @property
    def url(self) -> str:
        return self._url

    def pop_frame(self) -> Optional[np.ndarray]:
        if self._dropped and not self._stop_flag:
            self._open()
            return None

        frame = self._frame
        self._frame = None

        logging.debug(f'Frame requested by receiver.')
        return frame

    def _open(self, initial: bool = False) -> None:
        self._dropped = False
        if self._thread is not None:
            self._thread.join()
        thread = Thread(
            target=self._update,
            kwargs={'reconnection_delay': None if initial else self.RECONNECTION_DELAY}
        )
        thread.daemon = True
        thread.start()
        self._thread = thread

    def close(self) -> None:
        self._stop_flag = True

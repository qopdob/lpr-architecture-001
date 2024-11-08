import eventlet
eventlet.monkey_patch()

from threading import Thread, Event
import time

import requests
from flask import Flask, Response, stream_with_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit

import xml.etree.ElementTree as ET
from datetime import datetime
import logging

import base64

app = Flask(__name__)
cors = CORS(app)
app.config['SECRET_KEY'] = 'secret!'
async_mode = 'eventlet'

socket = SocketIO(app, async_mode=async_mode, cors_allowed_origins='*', logger=True, engineio_logger=True)
streams = dict()


class Stream:
    def __init__(self, url):
        self.url = url
        self.chunk = bytes()
        self.listeners = dict()
        self.active = False
        self.last_update = time.time()

    def read(self):
        while True:
            try:
                with requests.get(self.url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    self.active = True
                    for chunk in r.iter_content(chunk_size=1024 * 40):
                        self.chunk = chunk
                        self.last_update = time.time()
                        for listener in self.listeners.values():
                            listener.set()
            except requests.exceptions.RequestException as e:
                print(f"Error reading stream {self.url}: {str(e)}")
                self.active = False
            time.sleep(5)  # Wait before attempting to reconnect


class Listener:
    def __init__(self, stream):
        self.stream = stream
        self.event = Event()
        self.id = id(self)
        stream.listeners[self.id] = self.event

    def __del__(self):
        self.stream.listeners.pop(self.id, None)

    def gen(self):
        while True:
            if self.event.wait(timeout=1):
                self.event.clear()
                yield(self.stream.chunk)
            else:
                if not self.stream.active or time.time() - self.stream.last_update > 10:
                    yield (b'--frame\r\n'
                           b'Content-Type: text/plain\r\n\r\n'
                           b'No data available from stream\r\n')


def remove_not_active_streams():
    not_active = []
    for stream_id, (stream, thread) in streams.items():
        if not thread or not stream.active:
            not_active.append(stream_id)
    for stream_id in not_active:
        streams.pop(stream_id)


def decode_url(encoded_url):
    base64_bytes = encoded_url.encode('utf-8')
    url_bytes = base64.urlsafe_b64decode(base64_bytes)
    url = url_bytes.decode('utf-8')
    return url


@app.route("/stream/<encoded_url>")
def proxy_video_stream(encoded_url):
    remove_not_active_streams()

    if encoded_url not in streams:
        mjpeg_url = decode_url(encoded_url)
        stream = Stream(mjpeg_url)
        thread = Thread(target=stream.read)
        thread.start()
        streams[encoded_url] = (stream, thread)
    else:
        stream, thread = streams[encoded_url]

    _listener = Listener(stream)
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache', 'Expires': 'Thu, 01 Dec 1994 16:00:00 GMT',
               'Connection': 'close', 'Content-Type': 'multipart/x-mixed-replace;boundary=boundarySample'}
    return Response(stream_with_context(_listener.gen()), headers=dict(headers))


def main():
    host = '0.0.0.0'
    port = 8080
    socket.run(app, host=host, port=port)


if __name__ == '__main__':
    main()


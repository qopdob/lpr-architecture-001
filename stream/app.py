import logging
import time
from threading import Event, Thread
import requests
from requests.exceptions import ConnectionError
from flask import Flask, Response, stream_with_context, abort, jsonify
from flask_cors import CORS


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

streams = {}


class Stream:
    def __init__(self, url):
        self.url = url
        self.chunk = bytes()
        self.listeners = dict()
        self.timers = dict()
        self.headers = None
        self.active = True
        self.last_update = time.time()

    def read(self):
        try:
            with requests.get(self.url, stream=True) as r:
                for chunk in r.iter_content(chunk_size=1024 * 40):
                    self.chunk = chunk
                    self.last_update = time.time()
                    for listener in self.listeners.values():
                        listener.set()
                    time.sleep(0.01)  # Small delay to prevent CPU overuse
        except requests.exceptions.RequestException as e:
            logger.error(f"Error reading stream {self.url}: {str(e)}")
            self.active = False


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
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + self.stream.chunk + b'\r\n')
            else:
                # Check if the stream is still active
                if not self.stream.active or time.time() - self.stream.last_update > 10:
                    logger.warning(f"Stream {self.stream.url} appears to be inactive")
                    break



def fetch_data(endpoint):
    # Replace this with your actual data fetching logic
    response = requests.get(f"http://acs:8000/api/{endpoint}")
    return response.json()

# Initialize streams
def init_streams():
    logger.debug("Initializing streams...")
    streams_data = fetch_data("streams/")
    logger.debug(f"Fetched streams data: {streams_data}")
    
    for stream_info in streams_data:
        camera_id = stream_info.get('camera_id')
        mjpeg_url = stream_info.get('mjpeg_url')
        
        if not camera_id or not mjpeg_url:
            logger.warning(f"Invalid stream info: {stream_info}")
            continue
        
        logger.debug(f"Initializing stream for camera {camera_id} with URL {mjpeg_url}")
        stream = Stream(mjpeg_url)
        streams[camera_id] = stream
        
        # Start reading stream in a separate thread
        thread = Thread(target=stream.read)
        thread.daemon = True
        thread.start()
    
    logger.info(f"Initialized streams: {list(streams.keys())}")


def create_app():
    app = Flask(__name__)
    CORS(app)

    # Initialize streams when the app is created
    init_streams()

    @app.route('/')
    def hello():
        return "Hello, World!"

    @app.route('/streams')
    def list_streams():
        logger.debug(f"Current streams: {streams}")
        stream_info = {
            camera_id: {
                'url': stream.url,
                'active': stream.active,
                'listeners': len(stream.listeners)
            }
            for camera_id, stream in streams.items()
        }
        logger.debug(f"Returning stream info: {stream_info}")
        return jsonify(stream_info)

    @app.route('/camera/<stream_id>')
    def camera_stream(stream_id):
        if stream_id not in streams:
            abort(404)
    
        stream = streams[stream_id]
        _listener = Listener(stream)
    
        headers = {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Expires': 'Thu, 01 Dec 1994 16:00:00 GMT',
            'Connection': 'close',
            'Content-Type': 'multipart/x-mixed-replace;boundary=boundarySample'
        }
    
        return Response(stream_with_context(_listener.gen()), headers=headers)


    return app

app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8544, debug=True, threaded=True)

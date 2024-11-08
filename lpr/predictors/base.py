from functools import partial

import cv2
import numpy as np
import openvino as ov
from openvino import properties

from predictors.utils import letterbox_image, image_to_tensor, postprocess


class QueuedPredictor:

    _core = ov.Core()

    def __init__(
            self,
            model_path: str,
            callback,
            image_size: tuple[int, int],
            number_classes,
            stride=32,
    ):
        model = self._core.read_model(model_path)

        self._image_size = image_size
        self._stride = stride
        self._number_classes = number_classes
        self._config = {
            properties.hint.performance_mode(): properties.hint.PerformanceMode.CUMULATIVE_THROUGHPUT,
            properties.hint.allow_auto_batching(): True,
            properties.hint.enable_hyper_threading(): True,
            properties.hint.enable_cpu_pinning(): True,
        }
        self._compiled_model = self._core.compile_model(model, 'CPU', config=self._config)
        self._input_layer_name = self._compiled_model.input(0).any_name
        self._queue = ov.AsyncInferQueue(self._compiled_model)

        self._user_callback = callback
        bounded_callback = partial(self._callback)
        self._queue.set_callback(bounded_callback)

    @property
    def is_ready(self):
        return self._queue.is_ready()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.wait_all()

    def _callback(self, request, userdata: dict):
        det, seg = postprocess(
            request,
            original_shape=userdata['original_shape'],
            number_classes=userdata['number_classes'],
        )
        result = {
            'userdata': userdata['userdata'],
            'det': det,
            'seg': seg,
        }
        self._user_callback(result)

    def add_frame(self, frame: np.array, userdata: dict) -> None:
        resized_image = letterbox_image(frame, self._image_size, self._stride)
        input_tensor = image_to_tensor(resized_image)
        self._queue.start_async(
            {self._input_layer_name: input_tensor},
            userdata={
                'userdata': userdata,
                'original_shape': frame.shape,
                'number_classes': self._number_classes,
            }
        )

    def wait_all(self):
        self._queue.wait_all()

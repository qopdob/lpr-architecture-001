_models = {
    'plate': {
        'model_path': './data/weights/plate_n_001_openvino_model/plate_n_001.xml',
        'image_size': (640, 640),
        'number_classes': 6,
        'stride': 32,
    },
    'char': {
        'model_path': './data/weights/char_openvino_model/char.xml',
        'image_size': (320, 320),
        'number_classes': 23,
        'stride': 32,
    },
}

_detector = {
    'starving_delay': 0.5,
    'outdated_delay': 7,
    'conf_threshold': 35,
    'count_threshold': 5,
    'jump_threshold': 0.40,
    'recognition_borders': {
        'x_min': 0.3,
        'x_max': 1,
        'y_min': 0,
        'y_max': 1,
    }
}

_event = {
    'duplicate_delay': 20,
}

_acs = {
    'base_url': 'http://acs:8000/api',
}

config = {
    'models': _models,
    'detector': _detector,
    'event': _event,
    'acs': _acs,
}


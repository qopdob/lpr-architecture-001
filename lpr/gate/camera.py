import logging
from uuid import UUID

from onvif import ONVIFCamera
from datetime import timedelta
import time


class CameraRelay:
    OUTPUT = 0
    DURATION = 1  # Duration in seconds

    def __init__(self, uuid: UUID, ip, port, user, password, output=OUTPUT):
        self.uuid = uuid
        self.camera = ONVIFCamera(ip, port, user, password)
        self.device_service = self.camera.create_devicemgmt_service()

        relay_outputs = self.device_service.GetRelayOutputs()
        if len(relay_outputs) > output:
            self.relay_output_token = relay_outputs[output].token
        else:
            raise ValueError(f'No relay output # {output} found on the camera.')

        self.relay_output_settings = {
            'RelayOutputToken': self.relay_output_token,
            'Properties': {
                'Mode': 'Monostable',
                'DelayTime': timedelta(seconds=1),
                'IdleState': 'closed',
            }
        }

        self.device_service.SetRelayOutputSettings(self.relay_output_settings)

    def activate(self):
        try:
            self.device_service.SetRelayOutputState({
                'RelayOutputToken': self.relay_output_token,
                'LogicalState': 'active'
            })
            logging.info(f'Relay activated.')
            return True
        except Exception as e:
            logging.info(f'Error activating relay: {e}')
            return False


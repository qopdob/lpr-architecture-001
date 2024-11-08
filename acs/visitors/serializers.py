from rest_framework import serializers
from .models import Event, Camera, Gate

class GateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gate
        fields = ['gate_id', 'name', 'ip', 'port', 'username', 'password']

class CameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ['camera_id', 'name', 'stream_ip', 'stream_port', 'stream_path', 'mjpeg_path', 'mjpeg_url', 'username', 'password']

class StreamToGateSerializer(serializers.ModelSerializer):
    gate_id = serializers.UUIDField(source='gate.gate_id')

    class Meta:
        model = Camera
        fields = ['camera_id', 'gate_id']

class EventSerializer(serializers.Serializer):
    camera_id = serializers.UUIDField()
    license_plate = serializers.CharField(max_length=20)
    timestamp = serializers.DateTimeField()
    image = serializers.CharField(required=False)  # Base64 encoded image
    is_new_event = serializers.BooleanField()

class EventResponseSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source='camera.name', read_only=True)
    camera_username = serializers.CharField(source='camera.username', read_only=True)
    rtsp_url = serializers.CharField(source='camera.rtsp_url', read_only=True)
    mjpeg_url = serializers.CharField(source='camera.mjpeg_url', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['camera_name', 'camera_username', 'rtsp_url', 'mjpeg_url', 'license_plate', 'timestamp', 'access_granted', 'reason_for_refuse', 'image_url']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request is not None:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

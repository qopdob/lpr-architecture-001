from django.views.generic import TemplateView
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import Visitor, Event, Camera, Gate, Session
from .serializers import EventSerializer, EventResponseSerializer
from .serializers import GateSerializer, CameraSerializer, StreamToGateSerializer
from django.http import StreamingHttpResponse
from django.views.decorators.http import condition
from django.utils.decorators import method_decorator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.db.models import Q
import base64
import json
import os
from datetime import timedelta
from django.http import HttpResponse
from django.conf import settings


def list_media_files(request):
    media_root = settings.MEDIA_ROOT
    content = f"MEDIA_ROOT: {media_root}\n\n"
    for root, dirs, files in os.walk(media_root):
        level = root.replace(media_root, '').count(os.sep)
        indent = ' ' * 4 * level
        content += f"{indent}{os.path.basename(root)}/\n"
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            content += f"{sub_indent}{f}\n"
    return HttpResponse(content, content_type="text/plain")


class CameraEventsTemplateView(TemplateView):
    template_name = 'camera_events.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        camera_id = self.kwargs['camera_id']
        camera = get_object_or_404(Camera, camera_id=camera_id)
        events = Event.objects.filter(camera=camera).order_by('-timestamp')[:10]

        paginator = Paginator(events, 2)  # 2 events per page
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context['camera'] = camera
        context['events'] = page_obj
        context['has_next'] = page_obj.has_next()
        context['has_previous'] = page_obj.has_previous()
        context['total_pages'] = paginator.num_pages
        context['current_page'] = page_obj.number
        return context


class CameraEventsView(APIView):
    def get(self, request, camera_id):
        camera = get_object_or_404(Camera, camera_id=camera_id)
        events = Event.objects.filter(camera=camera).order_by('-timestamp')[:10]

        paginator = Paginator(events, 2)  # 2 events per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        serializer = EventResponseSerializer(page_obj, many=True)

        response_data = {
            'camera_name': camera.name,
            'mjpeg_url': camera.mjpeg_url,
            'events': serializer.data,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'total_pages': paginator.num_pages,
            'current_page': page_obj.number,
        }

        return Response(response_data)


class EventStream(APIView):
    @method_decorator(condition(etag_func=None))
    def get(self, request, camera_id):
        def event_stream():
            while True:
                # Wait for new events
                event = yield

                # Serialize and send the event data
                serializer = EventResponseSerializer(event)
                data = json.dumps(serializer.data)
                yield f"data: {data}\n\n"

        return StreamingHttpResponse(event_stream(), content_type='text/event-stream')


class GateListView(APIView):
    def get(self, request):
        gates = Gate.objects.all()
        serializer = GateSerializer(gates, many=True)
        return Response(serializer.data)


class StreamListView(APIView):
    def get(self, request):
        cameras = Camera.objects.all()
        serializer = CameraSerializer(cameras, many=True)
        return Response(serializer.data)


class StreamToGateMappingView(APIView):
    def get(self, request):
        cameras = Camera.objects.select_related('gate').filter(gate__isnull=False).all()
        serializer = StreamToGateSerializer(cameras, many=True)
        return Response(serializer.data)


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


class LPREventView(APIView):
    def post(self, request):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            is_new_event = serializer.validated_data['is_new_event']
            camera_id = serializer.validated_data['camera_id']
            timestamp = serializer.validated_data['timestamp']

            if not is_new_event:
                # Update the timestamp of the last event with the same camera_id
                last_event = Event.objects.filter(camera_id=camera_id).order_by('-timestamp').first()
                if last_event:
                    last_event.timestamp = timestamp
                    last_event.save()
                    response_serializer = EventResponseSerializer(last_event)
                    return Response(response_serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({"error": "No existing event found for this camera"},
                                    status=status.HTTP_404_NOT_FOUND)

            # If it's a new event, proceed with the original logic
            license_plate = serializer.validated_data['license_plate']
            image_data = serializer.validated_data.get('image')

            try:
                visitor = Visitor.objects.get(license_plate=license_plate)
                access_granted = not visitor.blacklisted and visitor.access_start <= timestamp.date() <= visitor.access_end
                reason = None if access_granted else "Blacklisted" if visitor.blacklisted else "Access period expired"
            except Visitor.DoesNotExist:
                visitor = None
                access_granted = False
                reason = "Visitor not found"

            event = Event(
                camera_id=camera_id,
                timestamp=timestamp,
                license_plate=license_plate,
                access_granted=access_granted,
                reason_for_refuse=reason,
                visitor=visitor,
            )

            if image_data:
                format, imgstr = image_data.split(';base64,')
                ext = format.split('/')[-1]
                image_content = ContentFile(base64.b64decode(imgstr), name=f'{license_plate}_{timestamp}.{ext}')
                event.image.save(f'{license_plate}_{timestamp}.{ext}', image_content, save=False)

            event.save()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"events_{camera_id}",
                {
                    "type": "new_event",
                    "event": EventResponseSerializer(event).data
                }
            )

            response_serializer = EventResponseSerializer(event)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RecentAccessCheckView(APIView):
    def get(self, request):
        camera_id = request.query_params.get('camera_id')
        duration = request.query_params.get('duration')

        if not camera_id or not duration:
            return Response({"error": "Both camera_id and duration are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            duration = float(duration)
        except ValueError:
            return Response({"error": "Duration must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        end_time = timezone.now()
        start_time = end_time - timedelta(seconds=duration)

        recent_event = Event.objects.filter(
            camera_id=camera_id,
            timestamp__gte=start_time,
            access_granted=True
        ).order_by('-timestamp').first()

        recent_access = bool(recent_event)

        if recent_event:
            # Check if this event is already associated with a session
            existing_session = Session.objects.filter(
                Q(in_event=recent_event) | Q(out_event=recent_event)
            ).first()

            if not existing_session:
                camera = recent_event.camera
                session_type = 'manual' if recent_event.opened_manually else 'auto'

                if camera.is_entrance:
                    # Create new session for entrance event
                    Session.objects.create(
                        in_event=recent_event,
                        in_event_type=session_type
                    )
                else:
                    # Look for existing session to update for exit event
                    open_session = Session.objects.filter(
                        in_event__license_plate=recent_event.license_plate,
                        out_event__isnull=True
                    ).order_by('-in_event__timestamp').first()

                    if open_session:
                        # Update existing session
                        open_session.out_event = recent_event
                        open_session.out_event_type = session_type
                        open_session.save()
                    else:
                        # Create new session with only out event
                        Session.objects.create(
                            out_event=recent_event,
                            out_event_type=session_type
                        )

        return Response({
            "camera_id": camera_id,
            "duration": duration,
            "recent_access": recent_access
        }, status=status.HTTP_200_OK)


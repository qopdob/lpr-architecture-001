from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse
from .models import Visitor, Event, Gate, Camera, Company, Session
from django.urls import path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.html import format_html
from django.urls import reverse
import requests
import logging
import csv


logger = logging.getLogger(__name__)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name',)
    list_filter = []
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ('edit_icon','company_name', 'last_name', 'first_name', 'license_plate', 'access_start', 'access_end', 'has_access')
    list_display_links = ('edit_icon',)
    list_filter = ('blacklisted', 'company')
    search_fields = ('company__name', 'last_name', 'first_name', 'license_plate')
    ordering = ('last_name', 'first_name')

    def edit_icon(self, obj):
        url = reverse('admin:visitors_visitor_change', args=[obj.id])
        return format_html('<a href="{}">✏️</a>', url)
    edit_icon.short_description = ''

    def company_name(self, obj):
        return obj.company.name if obj.company else '-'
    company_name.admin_order_field = 'company__name'
    company_name.short_description = _('Company')

    def has_access(self, obj):
        return obj.has_access
    has_access.boolean = True
    has_access.short_description = _('Has Access')

@admin.register(Gate)
class GateAdmin(admin.ModelAdmin):
    list_display = ('name', 'ip', 'port')
    search_fields = ('name', 'ip')

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ('name', 'image_preview', 'gate_button')
    list_filter = []
    search_fields = []
    actions = None
    readonly_fields = ('rtsp_url', 'mjpeg_url')

    def rtsp_url(self, obj):
        return obj.rtsp_url
    rtsp_url.short_description = 'RTSP URL'

    def mjpeg_url(self, obj):
        return obj.mjpeg_url
    mjpeg_url.short_description = 'MJPEG URL'

    def gate_button(self, obj):
        if obj.gate is None:
            return format_html(
                '<button disabled'
                'style="padding: 10px 20px; font-size: 16px; '
                'min-width: 150px; min-height: 40px;" '
                'class="button">{} - {}</button>',
                _('Open Gate'),
                '',
        )
        return format_html(
            '<button onclick="sendGateRequest(event, \'{}\')" '
            'style="padding: 10px 20px; font-size: 16px; '
            'min-width: 150px; min-height: 40px;" '
            'class="button">{} - {}</button>',
            obj.gate.gate_id,
            _('Open Gate'),
            obj.gate.name,
        )
    gate_button.short_description = _('Gate')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'request_gate/<uuid:gate_id>/',
                self.admin_site.admin_view(self.process_request),
                name='send-gate-request',
            ),
        ]
        return custom_urls + urls

    @csrf_exempt
    def process_request(self, request, gate_id):
        logger.info(f"process_request called with gate_id: {gate_id}")
        if request.method == 'POST':
            try:
                camera = Camera.objects.get(gate__gate_id=gate_id)
                latest_event = Event.objects.filter(camera=camera).order_by('-timestamp').first()

                if latest_event:
                    # Check if the event happened within the last 3 seconds and access was not granted
                    time_threshold = timezone.now() - timezone.timedelta(seconds=3)
                    if latest_event.timestamp >= time_threshold and not latest_event.access_granted:

                        latest_event.opened_manually = True
                        latest_event.access_granted = True
                        latest_event.save()
                        logger.info(f"Event {latest_event.id} updated: opened_manually set to True")
                        return JsonResponse({"status": "success", "message": "Gate opened manually"})
                    else:
                        logger.info("No eligible recent event found for manual opening")
                        return JsonResponse(
                            {"status": "error", "message": "No eligible recent event found for manual opening"},
                            status=400)
                else:
                    logger.info("No events found for this camera")
                    return JsonResponse({"status": "error", "message": "No events found for this camera"}, status=400)

            except Camera.DoesNotExist:
                logger.error(f"No camera found for gate_id: {gate_id}")
                return JsonResponse({"status": "error", "message": f"No camera found for gate {gate_id}"}, status=404)
            except Exception as e:
                logger.exception(f"Error in process_request: {str(e)}")
                return JsonResponse({"status": "error", "message": f"An error occurred: {str(e)}"}, status=500)

        logger.warning(f"Invalid request method: {request.method}")
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

    class Media:
        js = ('admin/js/vendor/jquery/jquery.min.js', 'request_gate.js')

    def has_view_permission(self, request, obj=None):
        if obj is None:
            return True  # Allow viewing the list
        return request.user.has_perm('change_camera')  # Only allow viewing individual cameras if user has edit permission

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['title'] = _('Cameras')  # Remove the "Select camera to view" prompt
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('visitor_title', 'license_plate_image', 'timestamp', 'camera_name', 'access_granted', 'image_preview')
    list_display_links = ('license_plate_image',)
    readonly_fields = ('visitor_title', 'image_preview', 'plate_parsed',)
    list_filter = ('access_granted', 'timestamp', 'camera')
    search_fields = ('license_plate', 'camera__name', 'visitor__first_name', 'visitor__last_name', 'visitor__middle_name', 'visitor__company__name')
    ordering = ('-timestamp',)
    actions = ['export_events']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<a href="{}" target="_blank">{}</a>',
                               obj.image.url,
                               format_html('<img src="{}" width="100vw" />', obj.image.url))
        return _("No Image")
    image_preview.short_description = _('Image Preview')

    def plate_parsed(self, obj):
        return obj.plate_parsed
    plate_parsed.short_description = _('Plate')

    def camera_name(self, obj):
        return obj.camera.name if obj.camera else 'N/A'
    camera_name.short_description = _('Camera')
    camera_name.admin_order_field = 'camera__name'

    def visitor_title(self, obj):
        if not obj.visitor:
            return ''
        return obj.visitor.title
    visitor_title.short_description = _('Visitor')

    def license_plate_image(self, obj):
        if obj.license_plate:
            image_url = f"http://localhost:5050/generate_image?plate={obj.license_plate}"
            return format_html('<img src="{}" alt="{}" style="max-height:25px;">', image_url, obj.license_plate)
        return '-'
    license_plate_image.short_description = _('License Plate')
    
    def export_events(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="events_export.csv"'

        writer = csv.writer(response)
        writer.writerow([_('Visitor Title'), _('License Plate'), _('Timestamp'), _('Camera'), _('Access Granted'), _('Reason for Refuse')])

        for event in queryset:
            writer.writerow([
                event.visitor.last_name+event.visitor.first_name+event.visitor.middle_name if event.visitor else _('N/A'),
                event.license_plate,
                event.timestamp,
                event.camera.name,
                event.access_granted,
                event.reason_for_refuse or _('N/A'),
            ])

        return response
    export_events.short_description = _("Export selected events to CSV")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'visitor_title', 'in_timestamp', 'out_timestamp')
    readonly_fields = ('license_plate', 'visitor_title', 'in_timestamp', 'out_timestamp')
    list_filter = ['in_event__timestamp', 'out_event__timestamp']
    search_fields = ['in_event__license_plate', 'out_event__license_plate', 'in_event__visitor__last_name', 'out_event__visitor__last_name']
    ordering = ('-in_event__timestamp', '-out_event__timestamp')

    def _format_timestamp(self, timestamp):
        if timestamp:
            # Convert to the current timezone (assumes your TIME_ZONE setting is correct)
            local_time = timezone.localtime(timestamp)
            return local_time.strftime("%d.%m.%Y %H:%M")
        return _('N/A')

    def in_timestamp(self, obj):
        if not obj.in_event:
            return _('N/A')
        url = reverse('admin:visitors_event_change', args=[obj.in_event.id])
        formatted_time = self._format_timestamp(obj.in_event.timestamp)
        return format_html('<a href="{}">{}</a>', url, formatted_time)
    in_timestamp.short_description = _('In Timestamp')
    in_timestamp.admin_order_field = 'in_event__timestamp'

    def out_timestamp(self, obj):
        if not obj.out_event:
            return _('N/A')
        url = reverse('admin:visitors_event_change', args=[obj.out_event.id])
        formatted_time = self._format_timestamp(obj.out_event.timestamp)
        return format_html('<a href="{}">{}</a>', url, formatted_time)
    out_timestamp.short_description = _('Out Timestamp')
    out_timestamp.admin_order_field = 'out_event__timestamp'

    def license_plate(self, obj):
        if not obj.in_event and not obj.out_event:
            return _('N/A')
        event = obj.in_event or obj.out_event
        return event.license_plate
    license_plate.short_description = _('License Plate')
    license_plate.admin_order_field = 'in_event__license_plate'

    def visitor_title(self, obj):
        if not obj.in_event and not obj.out_event:
            return _('N/A')
        event = obj.in_event or obj.out_event
        if not event.visitor:
            return _('N/A')
        return event.visitor.title
    visitor_title.short_description = _('Visitor')
    visitor_title.admin_order_field = 'in_event__visitor__last_name'



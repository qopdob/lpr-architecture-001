from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
import os
import re
import uuid
import ipaddress
import base64

LOCALHOST_IP = os.getenv('HOST_IP') or '127.0.0.1'


class IPAddressField(models.Field):
    def db_type(self, connection):
        return 'inet'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return str(ipaddress.ip_address(value))

    def to_python(self, value):
        if isinstance(value, ipaddress.IPv4Address) or value is None:
            return value
        return ipaddress.ip_address(value)

    def get_prep_value(self, value):
        if value is None:
            return None
        return str(self.to_python(value))


def parse_license_plate(plate):
    patterns = [
        (r'^([ABCEHKMOPTXY])(\d{3})([ABCEHKMOPTXY]{2})(\d{2,3})$', "car"),  # 'a000aa00'
        (r'^([ABCEHKMOPTXY]{2})(\d{3})(\d{2,3})$', "public"),  # 'aa00000'
        (r'^(\d{4})([ABCEHKMOPTXY]{2})(\d{2,3})$', "military"),  # '0000aa00'
        (r'^(\d{3})(d)(\d{3})(\d{2,3})$', "diplomatic"),  # '000d00000'
        (r'^([ABCEHKMOPTXY])(\d{4})(\d{2,3})$', "police"),  # 'a000000'
    ]

    for pattern, plate_type in patterns:
        match = re.match(pattern, plate)
        if match:
            parts = match.groups()
            return True, plate_type, parts

    return False, None, None


class Company(models.Model):
    name = models.CharField(_('name'), max_length=200)
    comment = models.TextField(_('comment'), blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('company')
        verbose_name_plural = _('companies')


class Visitor(models.Model):
    first_name = models.CharField(_('first name'), max_length=100, blank=True, null=True)
    middle_name = models.CharField(_('middle name'), max_length=100, blank=True, null=True)
    last_name = models.CharField(_('last name'), max_length=100)
    license_plate = models.CharField(_('license plate'), max_length=20, unique=True)
    access_start = models.DateField(_('beginning of access'))
    access_end = models.DateField(_('end of access'))
    blacklisted = models.BooleanField(_('blacklisted'), default=False)
    comment = models.TextField(_('comment'), blank=True)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_('company'))

    @property
    def has_access(self):
        today = timezone.now().date()
        return not self.blacklisted and self.access_start <= today <= self.access_end

    @property
    def plate_type(self):
        is_valid, _, parts = parse_license_plate(self.license_plate)
        return plate_type if is_valid else None

    @property
    def plate_parts(self):
        is_valid, _, parts = parse_license_plate(self.license_plate)
        return parts if is_valid else None

    @property
    def title(self):
        title = f'{self.company.name + " - " if self.company else ""}{self.last_name}'
        title += f'{" " + self.first_name[0] + "." if self.first_name else ""}'
        title += f'{" " + self.middle_name[0] + "." if self.middle_name else ""}'
        return title

    def __str__(self):
        return _("%(last_name)s, %(first_name)s (%(license_plate)s)") % {
            'last_name': self.last_name,
            'first_name': self.first_name or _('N/A'),
            'license_plate': self.license_plate
        }

    def clean(self):
        if self.access_start and self.access_end:
            if self.access_start > self.access_end:
                raise ValidationError(_("End of access cannot be before beginning of access."))

        if self.license_plate:
            license_plate = self.license_plate.upper()
            cyrillic_to_latin = {
                'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H',
                'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T',
                'Х': 'X', 'У': 'Y'
            }
            for cyrillic, latin in cyrillic_to_latin.items():
                license_plate = license_plate.replace(cyrillic, latin)
            license_plate = license_plate.replace(' ', '')

            patterns = [
                (r'^([A-CE-Z])(\d{3})([A-CE-Z]{2})(\d{2,3})$', "car"),  # 'A000AA00'
                (r'^([A-CE-Z]{2})(\d{3})(\d{2,3})$', "public"),  # 'AA00000'
                (r'^(\d{4})([A-CE-Z]{2})(\d{2,3})$', "military"),  # '0000AA00'
                (r'^(\d{3})(D)(\d{3})(\d{2})$', "diplomatic"),  # '000D00000'
                (r'^([A-CE-Z])(\d{4})(\d{2,3})$', "police"),  # 'A000000'
            ]

            valid_pattern = False
            for pattern, plate_type in patterns:
                if re.match(pattern, license_plate):
                    valid_pattern = True
                    break

            if not valid_pattern:
                raise ValidationError(_("Invalid license plate format."))

            self.license_plate = license_plate

        super().clean()

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = _('visitor')
        verbose_name_plural = _('visitors')


class Gate(models.Model):
    gate_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_('name'), max_length=100)
    ip = IPAddressField(_('IP address'))
    port = models.PositiveIntegerField(_('port'))
    username = models.CharField(_('username'), max_length=100)
    password = models.CharField(_('password'), max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('gate')
        verbose_name_plural = _('gates')

class Camera(models.Model):
    camera_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_('name'), max_length=100)
    stream_ip = IPAddressField(_('stream IP'))
    stream_port = models.PositiveIntegerField(_('stream port'), default=554)  # Default RTSP port
    stream_path = models.CharField(_('stream path'), max_length=255, blank=True)
    mjpeg_path = models.CharField(_('MJPEG path'), max_length=255, blank=True)
    username = models.CharField(_('username'), max_length=100, blank=True)
    password = models.CharField(_('password'), max_length=100, blank=True)
    is_entrance = models.BooleanField(_('is entrance'), default=False)
    gate = models.ForeignKey(Gate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_('gate'))

    def __str__(self):
        return self.name

    def _construct_url(self, protocol, path):
        auth = f'{self.username}:{self.password}@' if self.username or self.password else ''
        return f'{protocol}://{auth}{self.stream_ip}:{self.stream_port if protocol == "rtsp" else 80}/{path.lstrip("/") or ""}'

    def image_preview(self):
        url_bytes = self.mjpeg_url.encode('utf-8')
        base64_bytes = base64.urlsafe_b64encode(url_bytes)
        base64_string = base64_bytes.decode('utf-8')
        return format_html('<img src="http://{}:8080/stream/{}" height="300vw" />', LOCALHOST_IP, base64_string)

    image_preview.short_description = _('Image Preview')

    @property
    def rtsp_url(self):
        return self._construct_url('rtsp', self.stream_path)

    @property
    def mjpeg_url(self):
        return self._construct_url('http', self.mjpeg_path)

    class Meta:
        verbose_name = _('camera')
        verbose_name_plural = _('cameras')


class Event(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, verbose_name=_('camera'))
    timestamp = models.DateTimeField(_('timestamp'))
    license_plate = models.CharField(_('license plate'), max_length=20)
    access_granted = models.BooleanField(_('access granted'))
    opened_manually = models.BooleanField(_('opened manually'), default=False)
    reason_for_refuse = models.CharField(_('reason for refuse'), max_length=255, blank=True, null=True)
    image = models.ImageField(_('image'), upload_to='event_images/', blank=True, null=True)
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_('visitor'))

    def __str__(self):
        return _("%(license_plate)s at %(timestamp)s - %(status)s") % {
            'license_plate': self.license_plate,
            'timestamp': self.timestamp,
            'status': _('Granted') if self.access_granted else _('Refused')
        }

    def image_preview(self):
        if self.image:
            return format_html('<img src="{}" width="100vw" />', self.image.url)
        return _("No Image")

    image_preview.short_description = _('Image Preview')

    @property
    def plate_parsed(self):
        is_valid, plate_type, plate_parts = parse_license_plate(self.license_plate)
        return f'{plate_type}:{":".join(plate_parts)}' if is_valid else None

    class Meta:
        ordering = ['-timestamp']
        verbose_name = _('event')
        verbose_name_plural = _('events')


class Session(models.Model):
    in_event = models.ForeignKey(Event, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_('in event'), related_name='session_in')
    out_event = models.ForeignKey(Event, on_delete=models.SET_NULL, blank=True, null=True, verbose_name=_('out event'), related_name='session_out')
    in_event_type = models.CharField(_('in event type'), max_length=20, blank=True, null=True)
    out_event_type = models.CharField(_('out event type'), max_length=20, blank=True, null=True)

    class Meta:
        verbose_name = _('Session')
        verbose_name_plural = _('Sessionss')

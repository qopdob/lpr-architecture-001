import json
from django.forms.widgets import Widget
from django.utils.safestring import mark_safe
from django.templatetags.static import static

class LicensePlateWidget(Widget):
    template_name = 'admin/widgets/license_plate.html'

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            return ''

        plate_type, *parts = value.split(':')
        context = {
            'widget': {
                'name': name,
                'value': value,
            },
            'plate_type': plate_type,
            'parts_json': mark_safe(json.dumps(parts))
        }
        return mark_safe(renderer.render(self.template_name, context))


    class Media:
        css = {
            'all': (static('admin/css/license_plate.css'),)
        }
        js = (static('admin/js/license_plate.js'),)

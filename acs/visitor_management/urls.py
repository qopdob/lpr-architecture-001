from django.contrib import admin
from django.urls import path, include
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = _("GPark | Administration")
admin.site.site_title = _("GPark")
admin.site.index_title = _("Parking")


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('visitors.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

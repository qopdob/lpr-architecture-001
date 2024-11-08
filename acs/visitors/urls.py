from django.urls import path
from . import views


urlpatterns = [
    path('camera/<uuid:camera_id>/events/', views.CameraEventsTemplateView.as_view(), name='camera_events'),
    path('camera/<uuid:camera_id>/events/stream/', views.EventStream.as_view(), name='event_stream'),
    path('gates/', views.GateListView.as_view(), name='gate-list'),
    path('streams/', views.StreamListView.as_view(), name='stream-list'),
    path('stream-to-gate-mapping/', views.StreamToGateMappingView.as_view(), name='stream-to-gate-mapping'),
    path('lpr-event/', views.LPREventView.as_view(), name='lpr_event'),
    path('debug/media-files/', views.list_media_files, name='list_media_files'),
    path('recent-access-check/', views.RecentAccessCheckView.as_view(), name='recent_access_check'),
]

import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from importlib import import_module

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visitor_management.settings')
django.setup()  # This ensures Django is fully set up

application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Django's ASGI application to serve HTTP requests
    "websocket": AuthMiddlewareStack(  # Django's ASGI app to handle WebSocket
        URLRouter(
            # Import the routing inside to avoid premature loading
            import_module('visitors.routing').websocket_urlpatterns
        )
    ),
})

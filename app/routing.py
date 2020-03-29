from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from .consumers import AuthConsumer, GlobalConsumer

application = ProtocolTypeRouter({
    'websocket': AuthMiddlewareStack(URLRouter([
        path('auth', AuthConsumer),
        path('', GlobalConsumer)
    ]))
})

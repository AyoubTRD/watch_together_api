from .models import User, Room

from rest_framework.serializers import ModelSerializer

class RoomSerializer(ModelSerializer):
    class Meta:
        model = Room
        fields = ('video_url', 'name', 'user', 'users_watching')
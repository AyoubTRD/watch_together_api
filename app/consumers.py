import json

from channels.db import database_sync_to_async as s2as
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError

from .models import User, Room


def format_message(type, data):
    return json.dumps({
        'type': type, 'data': data
    })


def format_message_reverse(json_data):
    data = json.loads(json_data)
    return data['type'], data['data']


class AuthConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print('new connection')
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        type, data = format_message_reverse(text_data)
        if self.scope['user'] == AnonymousUser():
            if type == 'signup':
                await self.handleSignup(data)
            elif type == 'login':
                await self.handleLogin(data)
        else:
            if type == 'logout':
                await self.handleLogout()

    async def handleSignup(self, data):
        try:
            user = await s2as(User.objects.create_user)(email=data['email'], name=data['name'],
                                                        password=data['password'])
            await s2as(user.save)()
            auth_user = await s2as(User.objects.authenticate)(user.email, data['password'])
            await self.send(
                format_message('signup_success', {
                    'user': await s2as(auth_user['user'].as_dict)(),
                    'token': auth_user['token']
                }))
        except IntegrityError:
            await self.send(format_message('signup_error', f'The email {data["email"]} is already taken'))
        except ValueError as exc:
            await self.send(format_message('signup_error', str(exc)))

    async def handleLogin(self, data):
        user = await s2as(User.objects.authenticate)(email=data['email'], password=data['password'])
        if not user:
            print('wrong credentials')
            return await self.send(format_message('login_error', 'No account matches the this email and password'))

        print('user logged in successfully')
        await self.send(format_message('login_success', {
            'user': await s2as(user['user'].as_dict)(),
            'token': user['token']
        }))

    async def handleLogout(self):
        self.scope['user'] = AnonymousUser()
        await self.send(format_message('logout_success', {}))


class GlobalConsumer(AsyncWebsocketConsumer):
    async def websocket_receive(self, message):
        type, data = format_message_reverse(message['text'])
        await self.send(format_message(type, data))
        print(type, data)

    async def connect(self):
        await self.accept()

    async def disconnect(self, code):
        if not self.scope['user'] == AnonymousUser():
            self.scope['user'].is_online = False
            await s2as(self.scope['user'].save)()

    async def receive(self, text_data=None, bytes_data=None):
        type, data = format_message_reverse(text_data)

        if not data.get('token'):
            return await self.send(format_message('auth_error', {}))
        await self.auth_middleware(data['token'])

        if type == 'profile':
            await self.get_profile()
        elif type == 'rooms':
            await self.get_rooms()
        elif type == 'users':
            await self.get_users()
        elif type == 'user':
            if data.get('id'):
                await self.get_user(data['id'])
        elif type == 'add_friend':
            if data.get('id'):
                await self.add_friend(data['id'])
        elif type == 'remove_friend':
            if data.get('id'):
                await self.remove_friend(data['id'])
        elif type == 'create_room':
            if data.get('videoURL') and data.get('name'):
                await self.create_room(data['videoURL'], data['name'])
        elif type == 'join_room':
            if data.get('id'):
                await self.join_room(data['id'])
        elif type == 'leave_room':
            await self.leave_room()
        elif type == 'delete_room':
            await self.delete_room()

    async def delete_room(self):
        user = self.scope['user']  # :type User
        try:
            user = await s2as(user.delete_room)()
            await self.send(format_message('delete_room_success', {
                'user': await s2as(user.as_dict)()
            }))
        except ValueError as err:
            await self.send(format_message('delete_room_error', str(err)))

    async def leave_room(self):
        user = self.scope['user']  # :type User
        try:
            user = await s2as(user.leave_room)()
            await self.send(format_message('leave_room_success', {
                'user': user
            }))
        except ValueError as err:
            await self.send(format_message('leave_room_error', str(err)))

    async def join_room(self, id):
        user = self.scope['user']  # :type User
        try:
            room = await s2as(user.join_room)(id)
            await self.send(format_message('join_room_success', {
                'room': await s2as(room.as_dict)()
            }))
        except User.DoesNotExist:
            await self.send(format_message('join_room_error', 'Room not found'))

    async def create_room(self, video_url, name):
        user = self.scope['user']  # :type User
        try:
            room = await s2as(user.create_room)(video_url, name)
            await self.send(format_message('create_room_success', {
                'room': await s2as(room.as_dict)()
            }))
        except ValueError as err:
            await self.send(format_message('create_room_error', str(err)))

    async def remove_friend(self, id):
        user = self.scope['user']  # :type User
        try:
            friends = await s2as(user.remove_friend)(id)
            await self.send(format_message('remove_friend_success', {
                'friends': [friend.as_min_dict() for friend in friends]
            }))
        except User.DoesNotExist:
            await self.send(format_message('remove_friend_error', 'User not found'))

    async def add_friend(self, id):
        try:
            friends = await s2as(self.scope['user'].add_friend)(id)
            await self.send(format_message('add_friend_success', {
                'friends': [friend.as_min_dict() for friend in friends]
            }))
        except User.DoesNotExist:
            await self.send(format_message('add_friend_error', 'User not found'))

    async def get_user(self, id):
        try:
            user = await s2as(User.objects.get)(pk=id)
            user_dict = await s2as(user.as_dict)()
            await self.send(format_message('user', {'user': user_dict}))
        except User.DoesNotExist:
            await self.send(format_message('user', {}))

    async def get_users(self):
        users = [user.as_min_dict() for user in await s2as(User.objects.all)()]
        await self.send(format_message('users', {'users': users}))

    async def get_profile(self):
        if not self.scope['user'] == AnonymousUser():
            await self.send(format_message('profile', {'user': await s2as(self.scope['user'].as_min_dict)()}))

    async def get_rooms(self):
        rooms = [await s2as(room.as_preview_dict)() for room in await s2as(Room.objects.order_by)('-created_at')]
        await self.send(format_message('rooms', {
            'rooms': rooms
        }))

    async def auth_middleware(self, token):
        is_already_logged_in = self.scope['user'] != AnonymousUser()
        user = await s2as(User.objects.authenticate_with_jwt)(token)

        if user:
            if not is_already_logged_in:
                await self.channel_layer.group_send('global', {
                    'type': 'websocket.send',
                    'text': format_message('online_user', {
                        'user': user['user'].as_min_dict()
                    })
                })
                await self.channel_layer.group_add('global', self.channel_name)
                user['user'].channel_name = self.channel_name
                await s2as(user['user'].save)()
            self.scope['user'] = user['user']
        else:
            self.scope['user'] = AnonymousUser()
            await self.send(format_message('auth_error', {}))

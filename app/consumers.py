import json

from asgiref.sync import sync_to_async as s2as, async_to_sync as as2s
# from channels.db import database_sync_to_async as s2as
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError

from .models import User, Room, Post


def format_message(type, data):
    return json.dumps({
        'type': type, 'data': data
    })


def format_message_reverse(json_data):
    data = json.loads(json_data)
    return data.get('type'), data.get('data')


def users_to_dicts(users, min_dict=True):
    if min_dict:
        return [user.as_min_dict() for user in users]
    return [user.as_dict() for user in users]


def rooms_to_dicts(rooms, min_dict=True):
    if min_dict:
        return [room.as_preview_dict() for room in rooms]
    return [room.as_dict() for room in rooms]


class AuthConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print('new connection')
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        type, data = format_message_reverse(text_data)
        if type == 'signup':
            await self.handleSignup(data)
        elif type == 'login':
            await self.handleLogin(data)

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


class GlobalConsumer(AsyncWebsocketConsumer):
    async def notify_all(self, type, data):
        await self.channel_layer.group_send('global', {
            'type': 'websocket.send',
            'text': format_message(type, data)
        })

    async def connect(self):
        token = self.scope['url_route']['kwargs']['token']
        user = await s2as(User.objects.authenticate_with_jwt)(token)

        if user:
            self.scope['user'] = user['user']
            await self.accept()
            await self.notify_all('online_user', {'user': user['user'].as_min_dict()})
            await self.channel_layer.group_add('global', self.channel_name)
            user['user'].channel_name = self.channel_name
            await s2as(user['user'].save)()
            await self.get_profile()
        else:
            await self.close()

    async def disconnect(self, code=None):
        user = self.scope['user']
        user.is_online = False
        user.channel_name = ''
        await s2as(user.save)()
        await self.channel_layer.group_discard('global', self.channel_name)
        await self.notify_all('offline_user', {'user': user.as_min_dict()})
        await self.close()

    async def logout(self):
        user = self.scope['user']
        token_to_remove = self.scope['url_route']['kwargs']['token']
        tokens = json.loads(user.tokens)
        tokens.remove(token_to_remove)
        user.tokens = json.dumps(tokens)
        await s2as(user.save)()
        await self.disconnect()

    async def websocket_send(self, message):
        type, data = format_message_reverse(message['text'])
        await self.send(format_message(type, data))

    async def receive(self, text_data=None, bytes_data=None):
        type, data = format_message_reverse(text_data)
        if type == 'logout':
            await self.logout()
        elif type == 'profile':
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
        elif type == 'get_posts':
            await self.get_posts()
        elif type == 'create_post':
            if data.get('post'): await self.create_post(data['post'])
        elif type == 'delete_post':
            if data.get('id'): await self.delete_post(data['id'])
        elif type == 'update_post':
            if data.get('id') and data.get('text'): await self.update_post(data['id'], data['text'])
        elif type == 'create_comment':
            if data.get('id') and data.get('comment_text'):
                await self.create_comment(data['id'], data['comment_text'])
        elif type == 'update_comment':
            if data.get('id') and data.get('comment_text'):
                await self.update_comment(data['id'], data['comment_text'])
        elif type == 'delete_comment':
            if data.get('id'): await self.delete_comment(data['id'])
        elif type == 'like_post':
            if data.get('id'): await self.like_post(data['id'])

    async def like_post(self, post_id):
        user = self.scope['user']
        try:
            await s2as(user.like_post)(post_id)
            await self.send(format_message('like_post_success', {'id': post_id}))
        except ValueError as err:
            await self.send('like_post_error', str(err))

    async def delete_comment(self, comment_id):
        user = self.scope['user']
        try:
            await s2as(user.delete_comment)(comment_id)
            await self.send(format_message('delete_comment_success', {}))
        except ValueError as err:
            await self.send('delete_comment_error', str(err))

    async def update_comment(self, comment_id, comment_text):
        user = self.scope['user']
        try:
            comment = await s2as(user.update_comment)(comment_id, comment_text)
            await self.send(format_message('update_comment_success', {
                'comment': await s2as(comment.as_dict)()
            }))
        except ValueError as err:
            await self.send(format_message('update_comment_error', str(err)))

    async def create_comment(self, post_id, comment_text):
        user = self.scope['user']
        try:
            comment = await s2as(user.comment_post)(post_id, comment_text)
            await self.send(format_message('create_comment_success', {
                'comment': await s2as(comment.as_dict)()
            }))
        except ValueError as err:
            await self.send(format_message('create_comment_error', str(err)))

    async def update_post(self, id, new_text):
        user = self.scope['user']
        try:
            post = await s2as(user.update_post)(id, new_text)
            await self.send(format_message('update_post_success', {
                'post': post
            }))
        except ValueError as err:
            await self.send(format_message('update_post_error', str(err)))

    async def delete_post(self, id):
        user = self.scope['user']
        try:
            await s2as(user.delete_post)(id)
            await self.send(format_message('delete_post_success', {}))
        except ValueError as err:
            await self.send(format_message('delete_post_error', str(err)))

    async def create_post(self, post_text):
        user = self.scope['user']
        try:
            post = await s2as(user.create_post)(post_text)
            await self.send(format_message('create_post_success', {
                'post': await s2as(post.as_dict)()
            }))
        except ValueError as err:
            await self.send(format_message('create_post_error', str(err)))

    async def get_posts(self):
        posts = await s2as(Post.objects.order_by)('-posted_at')
        await self.send(format_message('posts', {'posts': users_to_dicts(posts, min_dict=False)}))

    async def delete_room(self):
        user = self.scope['user']
        try:
            room = await s2as(user.room.as_dict)()
            user = await s2as(user.delete_room)()
            await self.send(format_message('delete_room_success', {
                'user': await s2as(user.as_dict)()
            }))
            await self.notify_all('room_deleted', {'room': room})
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
            await self.notify_all('room_created', {'room': await s2as(room.as_dict)()})
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
                'friends': await s2as(users_to_dicts)(friends)
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
        users = await s2as(User.objects.all)()
        await self.send(format_message('users', {'users': await s2as(users_to_dicts)(users)}))

    async def get_profile(self):
        if not self.scope['user'] == AnonymousUser():
            await self.send(format_message('profile', {'user': await s2as(self.scope['user'].as_dict)()}))

    async def get_rooms(self):
        rooms = await s2as(Room.objects.order_by)('-created_at')

        await self.send(format_message('rooms', {
            'rooms': await s2as(rooms_to_dicts)(rooms)
        }))

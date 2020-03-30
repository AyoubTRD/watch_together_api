from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin

from random import choice
# Create your models here.
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    is_staff = models.BooleanField(default=False)
    objects = UserManager()
    USERNAME_FIELD = 'email'

    tokens = models.TextField(max_length=100000, default='[]')
    channel_name = models.CharField(max_length=255, default='')

    email = models.EmailField(max_length=200, unique=True)
    name = models.CharField(default='Anonymous', unique=False, max_length=100)
    created_at = models.DateTimeField(auto_now=True)

    is_online = models.BooleanField(default=False)

    gender = models.CharField(choices=(
        ('male', 'male'), ('female', 'female')
    ), default='male', max_length=15)

    room = models.ForeignKey('Room', on_delete=models.SET_NULL, null=True, related_name='user_room')

    avatar = models.URLField(default='https://robohash.org/anonymous/?set=set4&size=1000x1000')
    preview_avatar = models.URLField(default='https://robohash.org/anonymous/?set=set4&size=350x350')

    friends = models.ManyToManyField('self')

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.get_full_name()

    def __str__(self):
        return self.name

    def as_dict(self):
        return {
            'name': self.name,
            'email': self.email,
            'is_online': self.is_online,
            'friends': [friend.as_min_dict() for friend in self.friends.all()],
            'id': self.pk
        }

    def as_min_dict(self):
        return {
            'name': self.name,
            'is_online': self.is_online,
            'id': self.pk
        }

    def create_room(self, video_url='', name=''):
        if not video_url:
            raise ValueError('A room must have a video')
        if not name:
            raise ValueError('A room must have a name')
        video_url, name = video_url.strip(), name.strip()
        room = Room.objects.create(video_url=video_url, name=name, user=self)
        room.save()
        self.room = room
        self.save()
        return self.room

    def join_room(self, room_pk=None):
        if not room_pk: raise ValueError('Please provide the id of the room')
        room = Room.objects.get(pk=room_pk)
        self.room = room
        room.users_watching.add(self)
        room.save()
        self.save()
        return self.room

    def leave_room(self, user_to_inherit=None):
        if not self.room: raise ValueError('You must in a room first')
        try:
            self.room.users_watching.get(pk=user_to_inherit.pk)
            self.room.user = user_to_inherit
        except:
            if len(self.room.users_watching.all()):
                user_to_inherit = choice(self.room.users_watching.all())
                self.room.user = user_to_inherit
            else:
                self.room.delete()
        self.room.save()
        self.room = None
        self.save()

        return self

    def add_friend(self, user_pk=None):
        if user_pk is None: raise ValueError('You must provide a user')
        user = User.objects.get(pk=user_pk)
        self.friends.add(user)
        user.friends.add(self)
        self.save()
        user.save()
        return self.friends.all()

    def remove_friend(self, user_pk=None):
        if user_pk is None: raise ValueError('You must provide a user')
        self.friends.get(pk=user_pk).delete()
        self.save()
        user = User.objects.get(pk=user_pk)
        user.friends.get(pk=self.pk).delete()
        user.save()
        return self.friends.all()

    def delete_room(self):
        if not self.room:
            raise ValueError('You must be in a room first')
        if not self.room.user.pk == self.pk:
            raise ValueError('You are not the owner of this room')

        self.room.delete()
        self.room = None
        self.save()
        return self

    def send_message(self, message_text=None):
        if not message_text: raise ValueError('You must provide the message text')
        if not self.room:
            raise AttributeError('You aren\'t in any room')

        message_text = message_text.strip()
        message = self.message_set.create(message_text=message_text, room=self.room)
        message.save()
        self.save()
        self.room.save()
        return message

    def create_post(self, post_text=None):
        if not post_text: raise ValueError('You must provide text for your post')
        post = self.post_set.create(post_text=post_text)
        post.save()
        return post

    def delete_post(self, post_pk=None):
        if not post_pk: raise ValueError('You must provide the post you want to delete')
        try:
            post = self.post_set.get(pk=post_pk)
            post.delete()
            return self.post_set.all()
        except Post.DoesNotExist:
            raise ValueError('Post not found')

    def update_post(self, post_pk=None, post_text=None):
        if not post_pk: raise ValueError('You must provide the post you want to update')
        if not post_text: raise ValueError('You must provide the new information for the post')
        try:
            post = self.post_set.get(pk=post_pk)
            post.post_text = post_text
            post.save()
            return post
        except Post.DoesNotExist:
            raise ValueError('Post not found')

    def like_post(self, post_pk=None):
        if not post_pk: raise ValueError('You must provide the post')
        try:
            post = Post.objects.get(pk=post_pk)
            try:
                me = post.likes.get(pk=self.pk)
                me.delete()
            except User.DoesNotExist:
                post.likes.add(self)
            post.save()
        except Post.DoesNotExist:
            raise ValueError('Post not found')

    def comment_post(self, post_pk=None, comment_text=None):
        if not post_pk: raise ValueError('You must provide the post')
        if not comment_text: raise ValueError('You must provide the comment')
        try:
            post = Post.objects.get(pk=post_pk)
            comment = post.comments_set.create(comment_text=comment_text, author=self)
            comment.save()
            return comment
        except Post.DoesNotExist:
            raise ValueError('Post not found')

    def delete_comment(self, comment_pk=None):
        if not comment_pk: raise ValueError('You must provide the comment to delete')
        try:
            comment = self.comment_set.get(pk=comment_pk)
            comment.delete()
        except Comment.DoesNotExist:
            raise ValueError('Comment does not exist')

    def update_comment(self, comment_pk=None, comment_text=None):
        if not comment_pk: raise ValueError('You must provide the comment to update')
        if not comment_text: raise ValueError('You must provide the comment text')
        try:
            comment = self.comment_set.get(pk=comment_pk)
            comment.comment_text = comment_text
            comment.save()
            return comment
        except Comment.DoesNotExist:
            raise ValueError('Comment does not exist')


class Room(models.Model):
    video_url = models.URLField()
    users_watching = models.ManyToManyField(User, related_name='room_watching_users')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_creator', default=None)
    name = models.CharField(max_length=300)

    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'url: {self.video_url}, owner: {self.user.name}'

    def as_preview_dict(self):
        return {
            'name': self.name,
            'number_of_users_watching': len(self.users_watching.all()),
            'user': self.user.as_min_dict(),
            'id': self.pk
        }

    def as_dict(self):
        return {
            'name': self.name,
            'users_watching': [user.as_min_dict() for user in self.users_watching.all()],
            'user': self.user.as_min_dict(),
            'messages': [message.as_dict() for message in self.message_set.all()],
            'id': self.pk
        }


class Message(models.Model):
    author = models.ForeignKey('User', on_delete=models.CASCADE)
    room = models.ForeignKey('Room', on_delete=models.CASCADE)
    message_text = models.CharField(max_length=10000)

    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'author: {self.author}, message: {self.message_text[:30]}'

    def as_dict(self):
        return {
            'message_text': self.message_text,
            'created_at': self.created_at,
            'author': self.author.as_min_dict(),
            'id': self.pk
        }


class Post(models.Model):
    author = models.ForeignKey('User', on_delete=models.CASCADE)
    post_text = models.TextField(max_length=1000000)
    posted_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField('User', on_delete=models.CASCADE)

    def as_dict(self):
        return {
            'author': self.author.as_min_dict(),
            'post_text': self.post_text,
            'posted_at': self.posted_at,
            'likes': [like.as_min_dict() for like in self.likes.all()],
            'comments': [comment.as_dict() for comment in self.comment_set.order_by('-created_at')],
            'id': self.pk
        }


class Comment(models.Model):
    author = models.ForeignKey('User', on_delete=models.CASCADE)
    post = models.ForeignKey('Post', on_delete=models.CASCADE)
    comment_text = models.TextField(max_length=1000000)
    created_at = models.DateTimeField(auto_now=True)

    def as_dict(self):
        return {
            'author': self.author.as_min_dict(),
            'comment_text': self.comment_text,
            'created_at': self.created_at,
            'id': self.pk
        }

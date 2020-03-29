import re
import jwt
import json

JWT_SECRET = '}Ù4651┤74'
JWT_ALGORITHM = 'HS256'

from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.hashers import check_password


class UserManager(BaseUserManager):
    """The manager of the User class"""

    def create_user(self, email=None, name=None, password=None):
        """Create a new User"""
        email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
        if not email: raise ValueError('A user must have an email')
        if not re.fullmatch(email_regex, email): raise ValueError('Invalid Email')
        if not password: raise ValueError('A user must have a password')
        if len(password) < 5: raise ValueError('The password can\'t be less than 5 characters')
        if not name: name = 'Anonymous'

        email = self.normalize_email(email)
        user = self.model(name=name, email=email)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email=None, name='admin', password=None):
        user = self.create_user(email, name, password)
        user.is_superuser = True
        user.is_staff = True
        user.save()

    def authenticate(self, email=None, password=None):
        if not email: raise ValueError('You must provide an email')
        if not password: raise ValueError('You must provide a password')
        try:
            user = self.get(email=email)
            if not check_password(password, user.password):
                return None

            token = jwt.encode({'id': user.pk}, JWT_SECRET, JWT_ALGORITHM).decode('utf-8')
            tokens = json.loads(user.tokens)
            tokens.append(token)
            user.tokens = json.dumps(tokens)
            user.is_online = True
            user.save()
            return {'user': user, 'token': token}
        except self.model.DoesNotExist:
            return None

    def authenticate_with_jwt(self, token):
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user = self.get(pk=payload['id'])
            if not token in json.loads(user.tokens):
                return None
            if not user.is_online:
                user.is_online = True
                user.save()
            return {'user': user, 'token': token}
        except (jwt.DecodeError, self.model.DoesNotExist):
            return None

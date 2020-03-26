from django.contrib.auth.models import BaseUserManager

class UserManager(BaseUserManager):
    """The manager of the User class"""
    def create_user(self, email=None, name=None, password=None):
        """Create a new User"""
        if not email: raise ValueError('A user must have an email')
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
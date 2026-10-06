from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom model from the first migration; profile and email auth follow in S02."""

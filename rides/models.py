"""Data models for the Wingz Ride Management API.

User extends AbstractBaseUser (not AbstractUser) so that the primary key can be
named ``id_user`` and the domain-level ``role`` field replaces Django's
is_staff / is_superuser flags. See TSD-2026-001 Key Design Decision #1.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for the custom email-based ``User`` model."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        # AbstractBaseUser stores a hashed password. set_password(None)
        # produces an unusable password, which is acceptable per spec.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    """A Wingz user with a domain role: admin, rider, or driver."""

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("rider", "Rider"),
        ("driver", "Driver"),
    ]

    id_user = models.AutoField(primary_key=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="rider")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=30, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "role", "phone_number"]

    objects = UserManager()

    class Meta:
        db_table = "rides_user"
        indexes = [
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"


class Ride(models.Model):
    """A single ride lifecycle record."""

    STATUS_CHOICES = [
        ("en-route", "En Route"),
        ("pickup", "Pickup"),
        ("dropoff", "Dropoff"),
    ]

    id_ride = models.AutoField(primary_key=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    id_rider = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="rides_as_rider",
    )
    id_driver = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="rides_as_driver",
    )
    pickup_latitude = models.FloatField()
    pickup_longitude = models.FloatField()
    dropoff_latitude = models.FloatField()
    dropoff_longitude = models.FloatField()
    pickup_time = models.DateTimeField()

    class Meta:
        db_table = "rides_ride"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["pickup_time"]),
            models.Index(fields=["id_rider"]),
            models.Index(fields=["id_driver"]),
        ]

    def __str__(self):
        return f"Ride {self.id_ride} ({self.status})"


class RideEvent(models.Model):
    """An event in a ride's lifecycle (e.g. status transitions)."""

    id_ride_event = models.AutoField(primary_key=True)
    id_ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name="events",
    )
    description = models.CharField(max_length=255)
    # `default` (not auto_now_add) auto-populates the timestamp on create while
    # still allowing an explicit value to be supplied. This is required so that
    # historical events can be backdated (seed data, and the 24h-window tests).
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "rides_rideevent"
        indexes = [
            models.Index(fields=["id_ride", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Event {self.id_ride_event}: {self.description}"

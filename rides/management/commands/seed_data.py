"""Seed the development database with realistic demo data.

Creates:
  - 2 admin users
  - 3 rider users
  - 3 driver users
  - 10 rides, each with lifecycle events (some within the last 24h, some older)

Idempotent: running it repeatedly resets the rides/users it manages.

Usage:
    python manage.py seed_data
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from rides.models import Ride, RideEvent, User

# Defensive execution ceiling — guards the generation loop against an
# accidentally large RIDE_COUNT.
MAX_RIDES = 1000

ADMINS = [
    {
        "email": "admin@wingz.dev",
        "password": "admin123",
        "first_name": "Ada",
        "last_name": "Admin",
        "phone_number": "+10000000001",
    },
    {
        "email": "ops@wingz.dev",
        "password": "ops123",
        "first_name": "Otto",
        "last_name": "Ops",
        "phone_number": "+10000000002",
    },
]

RIDERS = [
    {
        "email": "john@wingz.dev",
        "first_name": "John",
        "last_name": "Doe",
        "phone_number": "+14155550001",
    },
    {
        "email": "alice@wingz.dev",
        "first_name": "Alice",
        "last_name": "Brown",
        "phone_number": "+14155550002",
    },
    {
        "email": "bob@wingz.dev",
        "first_name": "Bob",
        "last_name": "Carter",
        "phone_number": "+14155550003",
    },
]

DRIVERS = [
    {
        "email": "driver1@wingz.dev",
        "first_name": "Chris",
        "last_name": "Howard",
        "phone_number": "+14155550004",
    },
    {
        "email": "driver2@wingz.dev",
        "first_name": "Randy",
        "last_name": "Wilson",
        "phone_number": "+14155550005",
    },
    {
        "email": "driver3@wingz.dev",
        "first_name": "Howard",
        "last_name": "Young",
        "phone_number": "+14155550006",
    },
]

# San Francisco-ish pickup coordinates for variety.
PICKUP_COORDS = [
    (37.7749, -122.4194),
    (37.7849, -122.4094),
    (37.7649, -122.4294),
    (37.8044, -122.2712),  # Oakland
    (37.3382, -121.8863),  # San Jose
    (40.7128, -74.0060),   # NYC (far away — exercises distance sort)
]

STATUSES = ["en-route", "pickup", "dropoff"]


class Command(BaseCommand):
    help = "Seed the development database with demo users, rides, and events."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rides",
            type=int,
            default=10,
            help="Number of rides to create (default: 10).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        ride_count = min(max(options["rides"], 0), MAX_RIDES)

        self._reset()

        admins = [self._create_user(role="admin", **a) for a in ADMINS]
        riders = [self._create_user(role="rider", **r) for r in RIDERS]
        drivers = [self._create_user(role="driver", **d) for d in DRIVERS]

        now = timezone.now()
        for i in range(ride_count):
            rider = riders[i % len(riders)]
            driver = drivers[i % len(drivers)]
            pickup_lat, pickup_lon = PICKUP_COORDS[i % len(PICKUP_COORDS)]
            ride = Ride.objects.create(
                status=STATUSES[i % len(STATUSES)],
                id_rider=rider,
                id_driver=driver,
                pickup_latitude=pickup_lat,
                pickup_longitude=pickup_lon,
                dropoff_latitude=pickup_lat - 0.05,
                dropoff_longitude=pickup_lon - 0.05,
                pickup_time=now - timedelta(hours=i * 3),
            )
            self._create_events(ride, now, i)

        # Surface a ready-to-use admin token for immediate API verification.
        token, _ = Token.objects.get_or_create(user=admins[0])

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self.stdout.write(
            f"  Admin login : {admins[0].email} / {ADMINS[0]['password']}"
        )
        self.stdout.write(f"  Admin token : {token.key}")
        self.stdout.write(
            f"  Users: {len(admins)} admins, {len(riders)} riders, {len(drivers)} drivers"
        )
        self.stdout.write(f"  Rides: {ride_count}")

    # -- helpers ------------------------------------------------------------

    def _reset(self):
        """Remove previously seeded data so the command is idempotent."""
        managed_emails = [u["email"] for u in ADMINS + RIDERS + DRIVERS]
        # RideEvents and Rides cascade/clear before users (PROTECT on users).
        Ride.objects.filter(id_rider__email__in=managed_emails).delete()
        User.objects.filter(email__in=managed_emails).delete()

    @staticmethod
    def _create_user(role, password=None, **fields):
        return User.objects.create_user(
            role=role, password=password or "changeme123", **fields
        )

    @staticmethod
    def _create_events(ride, now, index):
        """Create a small, realistic lifecycle for a ride.

        Even-indexed rides get a recent (within 24h) event plus an older one;
        this gives the list endpoint's ``todays_ride_events`` field something
        to both include and exclude.
        """
        # Older event (outside the 24h window).
        RideEvent.objects.create(
            id_ride=ride,
            description="Status changed to en-route",
            created_at=now - timedelta(hours=30 + index),
        )
        # Recent event (inside the 24h window).
        RideEvent.objects.create(
            id_ride=ride,
            description="Status changed to pickup",
            created_at=now - timedelta(hours=1, minutes=index),
        )
        if ride.status == "dropoff":
            # A dropoff event > 1h after pickup, to exercise the bonus SQL.
            RideEvent.objects.create(
                id_ride=ride,
                description="Status changed to dropoff",
                created_at=now + timedelta(hours=1, minutes=5),
            )

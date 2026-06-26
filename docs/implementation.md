# Implementation Plan
## Wingz Ride Management API — Django REST Framework

**Document ID:** IMP-2026-001
**Date:** 2026-06-26
**References:** TSD-2026-001, BRD-2026-001

---

## Prerequisites

### Required Tools
- Python 3.11+ (`python --version`)
- pip 23+ or pipenv / Poetry
- SQLite 3.38+ (for trig functions in dev — check with `sqlite3 --version`)
- Git

### Python Package Dependencies

```
django>=4.2,<5.0
djangorestframework>=3.14
django-filter>=23.0
python-decouple>=3.8
pytest-django>=4.7
pytest>=7.4
```

**Install:**
```bash
pip install django djangorestframework django-filter python-decouple pytest-django pytest
```

### Environment Variables

Create `.env` in the project root:
```ini
SECRET_KEY=your-secret-key-here
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=127.0.0.1,localhost
```

For production PostgreSQL:
```ini
DATABASE_URL=postgresql://user:password@localhost:5432/wingz
```

---

## Project Directory Layout

```
wingz/
├── manage.py
├── .env
├── requirements.txt
├── pytest.ini
├── README.md                        # Contains bonus SQL query (FR-034)
├── docs/
│   ├── BRD.md
│   ├── techsolution.md
│   ├── implementation.md
│   └── test_plans.md
├── wingz/                           # Django project package
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── rides/                           # Core application
    ├── __init__.py
    ├── admin.py
    ├── apps.py
    ├── models.py                    # User, Ride, RideEvent
    ├── serializers.py               # All serializers
    ├── views.py                     # All ViewSets
    ├── urls.py                      # Router registration
    ├── permissions.py               # IsAdminRole
    ├── pagination.py                # RidePagination
    ├── filters.py                   # RideFilterBackend
    └── migrations/
        ├── __init__.py
        └── 0001_initial.py
```

---

## Phase 1: Django Project Bootstrap

**Estimated Effort: S (1–2 hours)**

### Tasks

#### 1.1 Create Django Project and App
```bash
django-admin startproject wingz .
python manage.py startapp rides
```

**Acceptance Criteria:** `manage.py` exists at project root; `rides/` app directory created.

#### 1.2 Configure `settings.py`

Key settings to add/modify:

```python
# wingz/settings.py

from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# AUTH_USER_MODEL must be set BEFORE first migration
AUTH_USER_MODEL = 'rides.User'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'rides',
]

# DRF global defaults — all endpoints require auth + admin role
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rides.permissions.IsAdminRole',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rides.pagination.RidePageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
```

**Acceptance Criteria:** `python manage.py check` returns no errors.

#### 1.3 Configure `pytest.ini`

```ini
[pytest]
DJANGO_SETTINGS_MODULE = wingz.settings
python_files = tests/test_*.py
python_classes = Test*
python_functions = test_*
```

**Acceptance Criteria:** `pytest --collect-only` runs without import errors.

---

## Phase 2: Models and Migrations

**Estimated Effort: S (1–2 hours)**

### Tasks

#### 2.1 Implement `rides/models.py`

Implement all three models exactly as defined in `techsolution.md` — `User` (extending `AbstractBaseUser`), `Ride`, and `RideEvent`.

Key implementation notes:
- `User.USERNAME_FIELD = 'email'` — DRF Token Auth uses this for `authenticate()`.
- `User.REQUIRED_FIELDS` must include all non-nullable fields except `email` (the USERNAME_FIELD) and `password`.
- `Ride.id_rider` FK: `related_name='rides_as_rider'`; `Ride.id_driver` FK: `related_name='rides_as_driver'`
- `RideEvent.id_ride` FK: `related_name='events'` — this `related_name` must match the `Prefetch` key in the view.
- All `Meta.indexes` as specified in `techsolution.md`.

**Acceptance Criteria:** `python manage.py makemigrations rides` generates a single `0001_initial.py` migration with all three models, no errors.

#### 2.2 Run Migrations

```bash
python manage.py migrate
```

**Acceptance Criteria:** `db.sqlite3` file created; `python manage.py dbshell` shows all tables.

#### 2.3 Create Management Command for Seed Data (optional dev helper)

```python
# rides/management/commands/seed_data.py
from django.core.management.base import BaseCommand
from rides.models import User, Ride, RideEvent
from django.utils import timezone

class Command(BaseCommand):
    help = 'Seed development database with test data'

    def handle(self, *args, **options):
        admin = User.objects.create_user(
            email='admin@wingz.dev',
            password='admin123',
            role='admin',
            first_name='Admin',
            last_name='User',
            phone_number='+10000000000',
        )
        # Create token for admin
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=admin)
        self.stdout.write(f'Admin token: {token.key}')
        # ... create riders, drivers, rides, events
```

**Acceptance Criteria:** `python manage.py seed_data` completes without error and prints admin token.

---

## Phase 3: Authentication and Permissions

**Estimated Effort: S (1 hour)**

### Tasks

#### 3.1 Implement `rides/permissions.py`

```python
# rides/permissions.py

from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Grants access only to authenticated users with role='admin'.
    Returns 401 if unauthenticated, 403 if authenticated but not admin.
    """

    def has_permission(self, request, view):
        # is_authenticated returns False for AnonymousUser -> DRF returns 401
        if not request.user or not request.user.is_authenticated:
            return False
        # role check -> DRF returns 403 when False
        return getattr(request.user, 'role', None) == 'admin'
```

**Acceptance Criteria:**
- Unauthenticated request to any endpoint returns HTTP 401.
- Authenticated request with `role='rider'` returns HTTP 403.
- Authenticated request with `role='admin'` returns HTTP 200/201/204.

#### 3.2 Implement Token Obtain Endpoint

```python
# rides/views.py — token endpoint

from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import permissions

class AdminTokenObtainView(ObtainAuthToken):
    """
    POST /api/v1/auth/token/
    Returns token for any valid user (caller must have valid credentials).
    Authentication not required for this endpoint.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})
```

**Note:** The `ObtainAuthToken` base uses Django's `authenticate()` which calls `AbstractBaseUser`'s `check_password`. This works as long as `User.USERNAME_FIELD = 'email'` and the backend is `ModelBackend`.

Add `AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']` to `settings.py`.

**Acceptance Criteria:** `POST /api/v1/auth/token/` with valid credentials returns `{"token": "..."}`.

---

## Phase 4: Serializers

**Estimated Effort: M (2–3 hours)**

### Tasks

#### 4.1 Implement `rides/serializers.py`

**UserSerializer:**
```python
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id_user', 'role', 'first_name', 'last_name',
                  'email', 'phone_number', 'password']

    def validate_role(self, value):
        valid_roles = [r[0] for r in User.ROLE_CHOICES]
        if value not in valid_roles:
            raise serializers.ValidationError(
                f"Role must be one of: {', '.join(valid_roles)}"
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
```

**RideEventSerializer:**
```python
class RideEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RideEvent
        fields = ['id_ride_event', 'id_ride', 'description', 'created_at']
```

**RideListSerializer** (for list endpoint — uses `todays_ride_events`):
```python
class RideListSerializer(serializers.ModelSerializer):
    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)
    todays_ride_events = RideEventSerializer(many=True, read_only=True)

    class Meta:
        model = Ride
        fields = [
            'id_ride', 'status', 'pickup_latitude', 'pickup_longitude',
            'dropoff_latitude', 'dropoff_longitude', 'pickup_time',
            'id_rider', 'id_driver', 'todays_ride_events',
        ]
```

**Important:** `todays_ride_events` reads from the `to_attr` set by `Prefetch`. DRF will call `instance.todays_ride_events` which is the pre-populated Python list — no extra query.

**RideDetailSerializer** (for retrieve/create/update — full events):
```python
class RideDetailSerializer(serializers.ModelSerializer):
    id_rider = UserSerializer(read_only=True)
    id_driver = UserSerializer(read_only=True)
    ride_events = RideEventSerializer(source='events', many=True, read_only=True)
    # Write-only FK fields for create/update
    id_rider_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='id_rider', write_only=False
    )
    id_driver_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='id_driver', write_only=False
    )

    class Meta:
        model = Ride
        fields = [
            'id_ride', 'status', 'pickup_latitude', 'pickup_longitude',
            'dropoff_latitude', 'dropoff_longitude', 'pickup_time',
            'id_rider', 'id_driver', 'id_rider_id', 'id_driver_id',
            'ride_events',
        ]
```

**Coordinate Validation** (add to `RideDetailSerializer`):
```python
def validate_pickup_latitude(self, value):
    if not (-90 <= value <= 90):
        raise serializers.ValidationError('Latitude must be between -90 and 90.')
    return value

def validate_pickup_longitude(self, value):
    if not (-180 <= value <= 180):
        raise serializers.ValidationError('Longitude must be between -180 and 180.')
    return value

# Repeat for dropoff_latitude and dropoff_longitude
```

**Acceptance Criteria:**
- `RideListSerializer` output includes `todays_ride_events` list; no `ride_events` field.
- `RideDetailSerializer` output includes `ride_events` (all-time); no `todays_ride_events` field.
- Creating a ride with a non-existent `id_rider` returns 400 with field error.
- Creating a ride with `status='invalid'` returns 400 with field error.
- `password` field never appears in any serializer output.

---

## Phase 5: Pagination

**Estimated Effort: XS (30 minutes)**

### Tasks

#### 5.1 Implement `rides/pagination.py`

```python
# rides/pagination.py

from rest_framework.pagination import PageNumberPagination


class RidePageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'
```

**Acceptance Criteria:** Response envelope includes `count`, `next`, `previous`, `results`. `?page_size=5` returns 5 results. `?page_size=200` returns max 100.

---

## Phase 6: ViewSets and URL Routing

**Estimated Effort: L (3–4 hours)**

### Tasks

#### 6.1 Implement `rides/views.py`

**UserViewSet:**
```python
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {'error': 'Cannot delete user referenced by existing rides.'},
                status=status.HTTP_409_CONFLICT
            )
```

**RideViewSet — Core Logic:**

```python
from datetime import timedelta
from django.utils import timezone
from django.db.models import FloatField, ExpressionWrapper, F, Value
from django.db.models.functions import ACos, Cos, Sin, Radians
from django.db.models import Prefetch
from rest_framework import viewsets, status
from rest_framework.response import Response

class RideViewSet(viewsets.ModelViewSet):

    def get_serializer_class(self):
        if self.action == 'list':
            return RideListSerializer
        return RideDetailSerializer

    def get_queryset(self):
        now = timezone.now()
        cutoff = now - timedelta(hours=24)

        todays_events_prefetch = Prefetch(
            'events',
            queryset=RideEvent.objects.filter(created_at__gte=cutoff),
            to_attr='todays_ride_events'
        )

        qs = Ride.objects.select_related('id_rider', 'id_driver') \
                         .prefetch_related(todays_events_prefetch)

        # --- Filters ---
        status_param = self.request.query_params.get('status')
        if status_param:
            valid_statuses = [s[0] for s in Ride.STATUS_CHOICES]
            if status_param not in valid_statuses:
                # Raise ValidationError — handled by DRF exception handler
                from rest_framework.exceptions import ValidationError
                raise ValidationError(
                    {'status': f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}
                )
            qs = qs.filter(status=status_param)

        rider_email = self.request.query_params.get('rider_email')
        if rider_email:
            # Basic email format check
            import re
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', rider_email):
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'rider_email': 'Enter a valid email address.'})
            qs = qs.filter(id_rider__email=rider_email)

        # --- Sort ---
        lat_param = self.request.query_params.get('lat')
        lon_param = self.request.query_params.get('lon')

        if lat_param is not None or lon_param is not None:
            # Both required if either present
            if lat_param is None or lon_param is None:
                from rest_framework.exceptions import ValidationError
                raise ValidationError(
                    {'error': 'Both lat and lon are required for distance sorting.'}
                )
            try:
                lat = float(lat_param)
                lon = float(lon_param)
            except (ValueError, TypeError):
                from rest_framework.exceptions import ValidationError
                raise ValidationError(
                    {'error': 'lat and lon must be numeric values.'}
                )
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                from rest_framework.exceptions import ValidationError
                raise ValidationError(
                    {'error': 'lat must be -90 to 90; lon must be -180 to 180.'}
                )

            distance_expr = ExpressionWrapper(
                Value(6371.0) * ACos(
                    Cos(Radians(Value(lat))) * Cos(Radians(F('pickup_latitude')))
                    * Cos(Radians(F('pickup_longitude')) - Radians(Value(lon)))
                    + Sin(Radians(Value(lat))) * Sin(Radians(F('pickup_latitude')))
                ),
                output_field=FloatField()
            )
            qs = qs.annotate(distance=distance_expr).order_by('distance', 'id_ride')
        else:
            qs = qs.order_by('pickup_time', 'id_ride')

        return qs
```

**RideEventViewSet:**
```python
class RideEventViewSet(viewsets.ModelViewSet):
    serializer_class = RideEventSerializer

    def get_queryset(self):
        qs = RideEvent.objects.all()
        ride_id = self.request.query_params.get('ride')
        if ride_id:
            qs = qs.filter(id_ride_id=ride_id)
        return qs
```

**Acceptance Criteria:**
- `GET /api/v1/rides/` returns paginated list with `todays_ride_events`, no extra DB queries.
- `GET /api/v1/rides/?status=en-route` filters correctly.
- `GET /api/v1/rides/?lat=37.77&lon=-122.41` sorts by distance.
- `GET /api/v1/rides/?lat=abc` returns 400.
- `GET /api/v1/rides/?lat=37.77` (no lon) returns 400.
- `GET /api/v1/rides/1/` returns full `ride_events` (all-time).
- `DELETE /api/v1/users/1/` when user has rides returns 409.

#### 6.2 Implement `rides/urls.py`

```python
# rides/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, RideViewSet, RideEventViewSet, AdminTokenObtainView

router = DefaultRouter()
router.register(r'users',  UserViewSet,      basename='user')
router.register(r'rides',  RideViewSet,      basename='ride')
router.register(r'events', RideEventViewSet, basename='rideevent')

urlpatterns = [
    path('auth/token/', AdminTokenObtainView.as_view(), name='token-obtain'),
    path('', include(router.urls)),
]
```

#### 6.3 Configure `wingz/urls.py`

```python
# wingz/urls.py

from django.urls import path, include

urlpatterns = [
    path('api/v1/', include('rides.urls')),
]
```

**Acceptance Criteria:** `python manage.py show_urls` (or manual review) lists all expected endpoints under `/api/v1/`.

---

## Phase 7: Error Handling

**Estimated Effort: XS (30 minutes)**

### Tasks

#### 7.1 Configure Custom Exception Handler

```python
# rides/views.py — add at top

from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Ensure all errors return JSON, never HTML."""
    response = exception_handler(exc, context)
    if response is not None:
        return response
    # For unhandled exceptions (500), return JSON
    from rest_framework.response import Response
    from rest_framework import status as drf_status
    return Response(
        {'error': 'An internal server error occurred.'},
        status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR
    )
```

Add to `settings.py`:
```python
REST_FRAMEWORK = {
    ...
    'EXCEPTION_HANDLER': 'rides.views.custom_exception_handler',
}
```

**Acceptance Criteria:** All error responses are JSON with `Content-Type: application/json`. No HTML error pages returned for 4xx/5xx.

---

## Phase 8: README with Bonus SQL

**Estimated Effort: XS (30 minutes)**

### Tasks

#### 8.1 Create `README.md`

The README must include:
1. Project overview and setup instructions.
2. API endpoint reference table.
3. Query parameter documentation for the Ride list endpoint.
4. The full analytical SQL query from `techsolution.md` (FR-034, FR-035) with explanatory comments.
5. How to obtain an auth token.

**Acceptance Criteria:** README present at project root; SQL query block is syntactically complete and references correct table and column names matching the implemented schema.

---

## Phase 9: Database Indexes

**Estimated Effort: XS (included in models)**

All indexes are declared in `Meta.indexes` within `models.py` and will be created by the initial migration. No separate migration needed.

**Verify with:**
```bash
python manage.py dbshell
# SQLite
.indexes rides_ride
.indexes rides_rideevent
.indexes rides_user
```

**Acceptance Criteria:** All indexes from `techsolution.md` are present in the schema.

---

## Integration Points

| Integration | Mechanism | Notes |
|---|---|---|
| Django Auth Backend | `ModelBackend` | Required for `ObtainAuthToken` to work with custom `AbstractBaseUser` |
| DRF TokenAuthentication | `authtoken` app in `INSTALLED_APPS` | Token table created by `migrate`; token created per user via `Token.objects.get_or_create(user=user)` |
| `django-filter` | `DjangoFilterBackend` in `DEFAULT_FILTER_BACKENDS` | Used for RideEvent list `ride` filter; Ride filtering is manual in `get_queryset` for precise 400 error control |

---

## Configuration and Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | None | Django secret key |
| `DEBUG` | No | `False` | Enable debug mode (never True in prod) |
| `DATABASE_URL` | No | `sqlite:///db.sqlite3` | Database connection string |
| `ALLOWED_HOSTS` | Yes (prod) | `''` | Comma-separated allowed hostnames |

---

## Database Migration Strategy

This is a greenfield project — only one initial migration (`0001_initial.py`) is needed.

**Rollback procedure:**
```bash
python manage.py migrate rides zero  # Drops all rides app tables
```

**Future migrations:** Any field addition/modification follows standard Django migration workflow (`makemigrations` → `migrate`). For `AUTH_USER_MODEL` changes: these require resetting all migrations and flushing the database — avoid post-launch model changes to `User`.

---

## Deployment Strategy

This is an assessment project; formal deployment is out of scope per BRD. However, production readiness notes:

- Set `DEBUG=False` in production.
- Set `ALLOWED_HOSTS` to the production domain.
- Use PostgreSQL for production (`DATABASE_URL=postgresql://...`).
- Collect static files: `python manage.py collectstatic`.
- Use `gunicorn` as WSGI server: `gunicorn wingz.wsgi:application`.
- Store `SECRET_KEY` in a secret manager (AWS Secrets Manager, Vault), not `.env` files.

---

## Rollback Plan

Since this is greenfield with no production deployment:
1. `git revert` to last known-good commit.
2. `python manage.py migrate rides zero` to drop tables.
3. `python manage.py migrate` to re-apply from clean state.

---

## Estimated Effort Summary

| Phase | Description | Effort |
|---|---|---|
| 1 | Django project bootstrap + settings | S (1–2h) |
| 2 | Models and migrations | S (1–2h) |
| 3 | Authentication and permissions | S (1h) |
| 4 | Serializers | M (2–3h) |
| 5 | Pagination | XS (0.5h) |
| 6 | ViewSets and URL routing | L (3–4h) |
| 7 | Error handling | XS (0.5h) |
| 8 | README with bonus SQL | XS (0.5h) |
| 9 | Index verification | XS (0.25h) |
| **Total** | | **M–L (9–14h)** |

---

## Key Code Patterns — Quick Reference

### Pattern 1: Always use `get_serializer_class()` in RideViewSet
```python
def get_serializer_class(self):
    if self.action == 'list':
        return RideListSerializer
    return RideDetailSerializer
```
This ensures the list endpoint uses `RideListSerializer` (with `todays_ride_events`) and all other actions use `RideDetailSerializer` (with full `ride_events`).

### Pattern 2: Prefetch `to_attr` must match serializer field name
```python
# In view:
Prefetch('events', queryset=RideEvent.objects.filter(...), to_attr='todays_ride_events')

# In RideListSerializer:
todays_ride_events = RideEventSerializer(many=True, read_only=True)
# DRF reads instance.todays_ride_events — set by the Prefetch to_attr
```

### Pattern 3: ValidationError in `get_queryset`
DRF's `ValidationError` raised inside `get_queryset` is caught by the exception handler and returns HTTP 400 automatically. Do not raise plain Python `ValueError`.

### Pattern 4: Secondary sort key for pagination stability
Always append `'id_ride'` as a tiebreaker:
```python
qs.order_by('pickup_time', 'id_ride')
qs.order_by('distance', 'id_ride')
```
Without this, equal `pickup_time` or `distance` values produce non-deterministic pagination.

### Pattern 5: `ProtectedError` handling in UserViewSet
```python
from django.db.models.deletion import ProtectedError

def destroy(self, request, *args, **kwargs):
    try:
        return super().destroy(request, *args, **kwargs)
    except ProtectedError:
        return Response(
            {'error': 'Cannot delete user with associated rides.'},
            status=status.HTTP_409_CONFLICT
        )
```

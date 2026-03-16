import json

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST


User = get_user_model()


@csrf_exempt
@require_POST
def register_view(request):
    payload = json.loads(request.body or "{}")
    username = str(payload.get("username", "")).strip()
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    first_name = str(payload.get("first_name", "")).strip()
    last_name = str(payload.get("last_name", "")).strip()

    if not username or not password:
        return JsonResponse({"detail": "Username and password are required."}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({"detail": "Username already exists."}, status=409)

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        status=201,
    )


@csrf_exempt
@require_POST
def login_view(request):
    payload = json.loads(request.body or "{}")
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"detail": "Invalid credentials."}, status=401)

    login(request, user)
    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }
    )


@csrf_exempt
@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({"detail": "Logged out."})


@require_GET
def current_user_view(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    return JsonResponse(
        {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
        }
    )

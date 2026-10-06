from django.http import JsonResponse
from django.urls import path


def live(request):
    return JsonResponse({"status": "ok", "service": "cryptosniper", "stage": "S01"})


urlpatterns = [path("health/live/", live, name="health-live")]

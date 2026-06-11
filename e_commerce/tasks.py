from django.utils import timezone


def log_task(message):
    print(
        f"[{timezone.now()}] {message}"
    )
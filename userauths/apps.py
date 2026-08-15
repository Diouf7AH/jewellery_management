from django.apps import AppConfig


class UserauthsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "userauths"

    def ready(self):
        from . import signals  # noqa: F401
    

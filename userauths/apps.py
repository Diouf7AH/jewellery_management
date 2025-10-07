from django.apps import AppConfig


class UserauthsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'userauths'    
    
    def ready(self):
        # import userauths.signals  # ← Charge le signal au démarrage
        from . import signals

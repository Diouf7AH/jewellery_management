<<<<<<< HEAD
from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'store'
    
    def ready(self):
        # Import signals
        from . import signals
=======
from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'store'
    
    def ready(self):
        # Import signals
        from . import signals
>>>>>>> fd5f1df121896de34fca9cd3384a1835551776dc

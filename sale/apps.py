<<<<<<< HEAD
from django.apps import AppConfig


class SaleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sale'
    
    def ready(self):
        import sale.signals
=======
from django.apps import AppConfig


class SaleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sale'
    
    def ready(self):
        import sale.signals
>>>>>>> fd5f1df121896de34fca9cd3384a1835551776dc

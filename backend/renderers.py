# from rest_framework import renderers
# import json
import json
from datetime import date, datetime
from rest_framework.renderers import JSONRenderer
from decimal import Decimal

# class UserRenderer(renderers.JSONRenderer):
#   charset='utf-8'
#   def render(self, data, accepted_media_type=None, renderer_context=None):
#     response = ''
#     if 'ErrorDetail' in str(data):
#       response = json.dumps({'errors':data})
#     else:
#       response = json.dumps(data)
    
#     return response

class UserRenderer(JSONRenderer):
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # handle datetime and decimal serialization
        def custom_encoder(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            return str(obj)

        if 'ErrorDetail' in str(data):
            response = json.dumps({'errors': data}, default=custom_encoder)
        else:
            response = json.dumps(data, default=custom_encoder)

        return response.encode('utf-8')

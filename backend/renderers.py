import json
from datetime import date, datetime
from decimal import Decimal

from rest_framework.renderers import JSONRenderer


class UserRenderer(JSONRenderer):
    charset = "utf-8"

    def render(
        self,
        data,
        accepted_media_type=None,
        renderer_context=None,
    ):
        def custom_encoder(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()

            if isinstance(obj, Decimal):
                return str(obj)

            return str(obj)

        renderer_context = renderer_context or {}
        response = renderer_context.get("response")

        payload = (
            {"errors": data}
            if response is not None and response.status_code >= 400
            else data
        )

        return json.dumps(
            payload,
            default=custom_encoder,
        ).encode("utf-8")
        


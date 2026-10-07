# import json
# from datetime import date, datetime
# from decimal import Decimal

# from rest_framework.renderers import JSONRenderer


# class UserRenderer(JSONRenderer):
#     charset = "utf-8"

#     def render(
#         self,
#         data,
#         accepted_media_type=None,
#         renderer_context=None,
#     ):
#         def custom_encoder(obj):
#             if isinstance(obj, (datetime, date)):
#                 return obj.isoformat()

#             if isinstance(obj, Decimal):
#                 return str(obj)

#             return str(obj)

#         renderer_context = renderer_context or {}
#         response = renderer_context.get("response")

#         payload = (
#             {"errors": data}
#             if response is not None and response.status_code >= 400
#             else data
#         )

#         return json.dumps(
#             payload,
#             default=custom_encoder,
#         ).encode("utf-8")
        

# backend/renderer.py

from __future__ import annotations

from rest_framework.renderers import JSONRenderer


class UserRenderer(JSONRenderer):
    """
    Renderer JSON global de l'application.

    Objectifs :
    - conserver l'encodage JSON natif de DRF ;
    - uniformiser les réponses d'erreur ;
    - éviter de refaire manuellement json.dumps() ;
    - laisser DRF gérer Decimal, date, datetime, UUID, etc.

    Réponse succès :
        {
            ...
        }

    Réponse erreur :
        {
            "errors": {
                ...
            }
        }
    """

    charset = "utf-8"

    def render(
        self,
        data,
        accepted_media_type=None,
        renderer_context=None,
    ):
        """
        Sérialise la réponse au format JSON.

        Pour les réponses HTTP >= 400, les erreurs sont
        regroupées sous la clé "errors".

        Si les données possèdent déjà une clé "errors",
        elles ne sont pas encapsulées une seconde fois.
        """

        renderer_context = renderer_context or {}

        response = renderer_context.get("response")

        payload = data

        # ----------------------------------------------------
        # Réponse d'erreur
        # ----------------------------------------------------

        if (
            response is not None
            and response.status_code >= 400
        ):
            if not (
                isinstance(data, dict)
                and "errors" in data
            ):
                payload = {
                    "errors": data,
                }

        # ----------------------------------------------------
        # Sérialisation DRF
        # ----------------------------------------------------

        return super().render(
            payload,
            accepted_media_type=accepted_media_type,
            renderer_context=renderer_context,
        )
        


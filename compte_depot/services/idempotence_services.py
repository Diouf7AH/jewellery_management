# compte_depot/services/idempotence.py
import hashlib
import json
import uuid

from django.db import transaction
from rest_framework.exceptions import ValidationError

from compte_depot.models import DepotIdempotence


def executer_une_seule_fois(
    *,
    cle,
    donnees,
    user,
    traitement,
):
    try:
        cle_uuid = uuid.UUID(str(cle))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({
            "idempotency_key": "Clé UUID invalide."
        })

    contenu = json.dumps(
        donnees,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    empreinte = hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()

    with transaction.atomic():

        operation, created = (
            DepotIdempotence.objects.get_or_create(
                cle=cle_uuid,
                defaults={
                    "empreinte": empreinte,
                    "created_by": user,
                },
            )
        )

        operation = (
            DepotIdempotence.objects
            .select_for_update()
            .get(pk=operation.pk)
        )

        if operation.created_by_id != user.pk:
            raise ValidationError({
                "idempotency_key": (
                    "Cette clé appartient à un autre utilisateur."
                )
            })

        if operation.empreinte != empreinte:
            raise ValidationError({
                "idempotency_key": (
                    "Cette clé a déjà été utilisée "
                    "pour une opération différente."
                )
            })

        if not created:

            if operation.reponse is None:
                raise ValidationError({
                    "idempotency_key": (
                        "Opération en cours ou incomplète."
                    )
                })

            return operation.reponse, operation.code_http

        reponse, code_http = traitement()

        operation.reponse = reponse
        operation.code_http = code_http

        operation.save(
            update_fields=[
                "reponse",
                "code_http",
            ]
        )

        return reponse, code_http
    
    
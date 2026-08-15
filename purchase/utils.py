# purchase/utils.py

from django.utils import timezone

from purchase.models import Lot


def generate_numero_lot() -> str:
    """
    Génère un numéro de lot au format :

        LOT-YYYYMMDD-0001

    La séquence repart à 0001 chaque jour.

    Exemple :
        LOT-20260722-0001
        LOT-20260722-0002
    """

    today = timezone.localdate().strftime("%Y%m%d")
    prefix = f"LOT-{today}-"

    last_numero = (
        Lot.objects
        .filter(numero_lot__startswith=prefix)
        .order_by("-numero_lot")
        .values_list("numero_lot", flat=True)
        .first()
    )

    sequence = 1

    if last_numero:
        try:
            sequence = int(
                last_numero.rsplit("-", 1)[1]
            ) + 1
        except (IndexError, ValueError):
            sequence = 1

    return f"{prefix}{sequence:04d}"


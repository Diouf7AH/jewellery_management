# order/services/commande_matiere_service.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from stock_matiere_premiere.models import (MatierePremiereMovement,
                                           MatierePremiereStock)


@transaction.atomic
def sortir_matiere_pour_ouvrier(*, commande, poids, user=None):
    poids = Decimal(str(poids or "0.000"))

    if poids <= 0:
        raise ValidationError("Le poids envoyé à l'ouvrier doit être supérieur à 0.")

    stock = MatierePremiereStock.objects.select_for_update().get(
        bijouterie=commande.bijouterie,
        matiere=commande.matiere,
        purete=commande.purete,
    )

    if stock.poids_total < poids:
        raise ValidationError("Stock matière première insuffisant.")

    stock.poids_total -= poids
    stock.save(update_fields=["poids_total"])

    MatierePremiereMovement.objects.create(
        bijouterie=commande.bijouterie,
        matiere=commande.matiere,
        purete=commande.purete,
        poids=poids,
        source="commande_atelier_out",
        commande_client=commande,
        created_by=user,
        commentaire="Matière donnée à l’ouvrier.",
    )

    commande.poids_envoye_ouvrier = poids
    commande.save(update_fields=["poids_envoye_ouvrier"])


@transaction.atomic
def retourner_matiere_ouvrier(*, commande, poids_retour, user=None):
    poids_retour = Decimal(str(poids_retour or "0.000"))

    if poids_retour < 0:
        raise ValidationError("Le poids retourné ne peut pas être négatif.")

    if poids_retour > commande.poids_envoye_ouvrier:
        raise ValidationError("Le poids retourné ne peut pas dépasser le poids envoyé.")

    stock, _ = MatierePremiereStock.objects.select_for_update().get_or_create(
        bijouterie=commande.bijouterie,
        matiere=commande.matiere,
        purete=commande.purete,
        defaults={"poids_total": Decimal("0.000")},
    )

    stock.poids_total += poids_retour
    stock.save(update_fields=["poids_total"])

    perte = commande.poids_envoye_ouvrier - poids_retour

    MatierePremiereMovement.objects.create(
        bijouterie=commande.bijouterie,
        matiere=commande.matiere,
        purete=commande.purete,
        poids=poids_retour,
        source="commande_atelier_in",
        commande_client=commande,
        created_by=user,
        commentaire=f"Retour atelier. Perte: {perte} g",
    )

    commande.poids_retour_ouvrier = poids_retour
    commande.poids_perte = perte
    commande.save(update_fields=["poids_retour_ouvrier", "poids_perte"])
    


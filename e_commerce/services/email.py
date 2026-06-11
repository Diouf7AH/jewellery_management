from django.conf import settings
from django.core.mail import EmailMessage


def send_ecommerce_order_paid_email(*, commande):
    if not commande.email_client:
        return False

    facture = commande.facture

    subject = f"Confirmation de commande - {facture.numero_facture if facture else commande.uuid}"

    body = f"""
Bonjour {commande.nom_client},

Votre commande e-commerce a été confirmée avec succès.

Montant payé : {commande.montant_a_payer} FCFA
Statut : Payée

Merci pour votre confiance.

Rio Gold
"""

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[commande.email_client],
    )

    if facture and facture.facture_pdf:
        email.attach_file(facture.facture_pdf.path)

    email.send(fail_silently=False)
    return True


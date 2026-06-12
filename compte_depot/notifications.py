from django.utils import timezone


def build_compte_created_message(compte, montant_initial):
    client = compte.client

    return (
        f"Bonjour {client.prenom} {client.nom},\n\n"
        f"Nous vous informons que votre compte dépôt a été créé avec succès.\n\n"
        f"Numéro de compte : {compte.numero_compte}\n"
        f"Dépôt initial : {montant_initial} FCFA\n"
        f"Solde actuel : {compte.solde} FCFA\n"
        f"Date : {timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Merci de votre confiance.\n"
        f"BIJOUTERIE RIO GOLD"
    )
    

def build_compte_depot_message(tx):
    client = tx.compte.client

    return (
        f"Bonjour {client.prenom} {client.nom},\n\n"
        f"Votre opération de {tx.get_type_transaction_display().lower()} "
        f"a été effectuée avec succès.\n\n"
        f"Montant : {tx.montant} FCFA\n"
        f"Solde actuel : {tx.solde_apres} FCFA\n"
        f"Référence : {tx.reference or '-'}\n"
        f"Date : {timezone.localtime(tx.date_transaction).strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Merci de votre confiance.\n"
        f"BIJOUTERIE RIO GOLD"
    )
    

def send_compte_created_notification(compte, montant_initial):
    client = compte.client
    telephone = client.telephone

    if not telephone:
        return False

    message = build_compte_created_message(
        compte,
        montant_initial
    )

    print("MESSAGE À ENVOYER :", telephone)
    print(message)

    return True

def send_compte_depot_notification(tx):
    client = tx.compte.client
    telephone = client.telephone

    if not telephone:
        return False

    message = build_compte_depot_message(tx)

    # Ici tu branches WhatsApp / SMS / Orange SMS / Twilio / Meta WhatsApp API
    print("MESSAGE À ENVOYER :", telephone, message)

    return True


# Paiement facture
def build_compte_depot_facture_message(tx):
    client = tx.compte.client

    return (
        f"Bonjour {client.prenom} {client.nom},\n\n"
        f"Nous vous informons qu'un montant de {tx.montant} FCFA "
        f"a été prélevé sur votre compte dépôt pour le règlement "
        f"de votre facture N° {tx.reference.replace('FACTURE-', '')}.\n\n"
        f"Solde disponible sur votre compte dépôt : "
        f"{tx.solde_apres} FCFA.\n\n"
        f"Date de l'opération : "
        f"{timezone.localtime(tx.date_transaction).strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Merci de votre confiance.\n\n"
        f"BIJOUTERIE RIO GOLD"
    )
    

def send_compte_depot_facture_notification(tx):
    client = tx.compte.client
    telephone = client.telephone

    if not telephone:
        return False

    message = build_compte_depot_facture_message(tx)

    print("MESSAGE À ENVOYER :", telephone)
    print(message)

    return True

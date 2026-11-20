# sale/services/client_bijouterie_service.py

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from sale.models import Client, ClientBijouterie
from store.models import Bijouterie

# ============================================================
# 1. VALIDATION DU CLIENT
# ============================================================

def _validate_client(
    client: Client,
) -> Client:
    """
    Vérifie que le client existe en base.

    Ne modifie aucune donnée.
    """

    if (
        client is None
        or not isinstance(client, Client)
        or client.pk is None
    ):
        raise ValidationError({
            "client": "Le client est obligatoire."
        })

    if not Client.objects.filter(
        pk=client.pk
    ).exists():
        raise ValidationError({
            "client": "Client introuvable."
        })

    return client


# ============================================================
# 2. VALIDATION DE LA BIJOUTERIE
# ============================================================

def _validate_bijouterie(
    bijouterie: Bijouterie,
) -> Bijouterie:
    """
    Vérifie que la bijouterie existe en base.

    Ne modifie aucune donnée.
    """

    if (
        bijouterie is None
        or not isinstance(bijouterie, Bijouterie)
        or bijouterie.pk is None
    ):
        raise ValidationError({
            "bijouterie": (
                "La bijouterie est obligatoire."
            )
        })

    if not Bijouterie.objects.filter(
        pk=bijouterie.pk
    ).exists():
        raise ValidationError({
            "bijouterie": "Bijouterie introuvable."
        })

    return bijouterie


# ============================================================
# 3. VÉRIFIER L'ASSOCIATION CLIENT / BIJOUTERIE
# ============================================================

def verifier_client_associe(
    *,
    client: Client | None,
    bijouterie: Bijouterie,
) -> None:
    """
    Vérifie qu'un client est associé
    à une bijouterie.

    Règles :

    - client=None est autorisé ;
    - un client existant doit être associé
      à la bijouterie ;
    - aucune association automatique ;
    - aucune modification de données.

    Utilisation :

    - création de vente de bijoux ;
    - paiement ;
    - contrôle des opérations commerciales.

    Attention :
    Cette fonction ne vérifie pas les
    permissions de l'utilisateur connecté.
    """

    # --------------------------------------------------------
    # CLIENT FACULTATIF
    # --------------------------------------------------------

    if client is None:
        return

    # --------------------------------------------------------
    # VALIDATIONS
    # --------------------------------------------------------

    _validate_client(client)
    _validate_bijouterie(bijouterie)

    # --------------------------------------------------------
    # RECHERCHE DE L'ASSOCIATION
    # --------------------------------------------------------

    association_existe = (
        ClientBijouterie.objects
        .filter(
            client_id=client.pk,
            bijouterie_id=bijouterie.pk,
        )
        .exists()
    )

    if not association_existe:
        raise ValidationError({
            "client": (
                "Ce client n'est pas associé "
                "à cette bijouterie."
            )
        })


# ============================================================
# 4. SAVOIR SI UN CLIENT EST ASSOCIÉ
# ============================================================

def client_est_associe(
    *,
    client: Client,
    bijouterie: Bijouterie,
) -> bool:
    """
    Retourne :

        True  : client associé.
        False : client non associé.

    Ne crée aucune association.
    Ne modifie aucune donnée.
    """

    _validate_client(client)
    _validate_bijouterie(bijouterie)

    return (
        ClientBijouterie.objects
        .filter(
            client_id=client.pk,
            bijouterie_id=bijouterie.pk,
        )
        .exists()
    )


# ============================================================
# 5. ASSOCIER UN CLIENT À UNE BIJOUTERIE
# ============================================================

@transaction.atomic
def associer_client_bijouterie(
    *,
    client: Client,
    bijouterie: Bijouterie,
    identite_verifiee: bool = False,
) -> ClientBijouterie:
    """
    Associe un client existant à une bijouterie.

    Règles métier :

    1. Le client doit exister.

    2. La bijouterie doit exister.

    3. L'identité du client doit être vérifiée
       avant toute nouvelle association.

    4. Aucun rattachement automatique
       par téléphone ou nom.

    5. Aucun doublon d'association.

    6. Une association existante est retournée
       sans en créer une deuxième.

    Sécurité :

    identite_verifiee doit provenir
    d'une vérification réalisée côté Django.

    Ne jamais utiliser directement une valeur
    booléenne envoyée par Angular comme preuve
    de vérification d'identité.

    Le service appelant doit aussi vérifier
    les permissions sur la bijouterie.
    """

    # --------------------------------------------------------
    # VALIDATIONS
    # --------------------------------------------------------

    _validate_client(client)
    _validate_bijouterie(bijouterie)

    # --------------------------------------------------------
    # ASSOCIATION DÉJÀ EXISTANTE
    # --------------------------------------------------------

    association = (
        ClientBijouterie.objects
        .filter(
            client_id=client.pk,
            bijouterie_id=bijouterie.pk,
        )
        .first()
    )

    if association is not None:
        return association

    # --------------------------------------------------------
    # VÉRIFICATION D'IDENTITÉ
    # --------------------------------------------------------

    if identite_verifiee is not True:
        raise ValidationError({
            "client": (
                "La vérification d'identité "
                "est obligatoire avant "
                "d'associer un client existant "
                "à une nouvelle bijouterie."
            )
        })

    # --------------------------------------------------------
    # CRÉATION SANS DOUBLON
    # --------------------------------------------------------

    association, _created = (
        ClientBijouterie.objects.get_or_create(
            client=client,
            bijouterie=bijouterie,
        )
    )

    return association


# ============================================================
# 6. RÉCUPÉRER LES CLIENTS D'UNE BIJOUTERIE
# ============================================================

def clients_de_bijouterie(
    *,
    bijouterie: Bijouterie,
):
    """
    Retourne uniquement les clients
    associés à une bijouterie.

    Utilise directement ClientBijouterie.

    Ne dépend pas du related_name
    défini dans le modèle.

    Retourne un QuerySet de Client.

    Important :
    L'utilisateur doit déjà avoir été
    autorisé à accéder à cette bijouterie.
    """

    _validate_bijouterie(bijouterie)

    # --------------------------------------------------------
    # IDENTIFIANTS DES CLIENTS AUTORISÉS
    # --------------------------------------------------------

    client_ids = (
        ClientBijouterie.objects
        .filter(
            bijouterie_id=bijouterie.pk,
        )
        .values_list(
            "client_id",
            flat=True,
        )
    )

    # --------------------------------------------------------
    # CLIENTS DE LA BIJOUTERIE
    # --------------------------------------------------------

    return (
        Client.objects
        .filter(
            pk__in=client_ids,
        )
        .order_by("-pk")
    )

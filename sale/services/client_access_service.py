# sale/services/client_access_service.py

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from sale.models import Client, ClientBijouterie, Facture, Paiement, Vente

# ============================================================
# 1. CLIENTS ACCESSIBLES
# ============================================================

def clients_accessibles(
    bijouteries_autorisees,
) -> QuerySet:
    """
    Retourne uniquement les clients associés
    aux bijouteries autorisées.

    Règles :
        - Admin : toutes les bijouteries autorisées.
        - Manager : ses bijouteries.
        - Vendeur : sa bijouterie.
        - Caissier : sa bijouterie.

    Important :
        bijouteries_autorisees doit être déterminé
        côté Django après vérification des droits.

        Ne jamais utiliser directement une liste
        d'identifiants envoyée par Angular.
    """

    # --------------------------------------------------------
    # IDENTIFIANTS DES CLIENTS ASSOCIÉS
    # --------------------------------------------------------

    client_ids = (
        ClientBijouterie.objects
        .filter(
            bijouterie__in=bijouteries_autorisees,
        )
        .values_list(
            "client_id",
            flat=True,
        )
    )

    # --------------------------------------------------------
    # CLIENTS ACCESSIBLES
    # --------------------------------------------------------

    return (
        Client.objects
        .filter(
            pk__in=client_ids,
        )
        .distinct()
        .order_by("-pk")
    )


# ============================================================
# 2. VENTES ACCESSIBLES D'UN CLIENT
# ============================================================

def ventes_client_accessibles(
    client_id,
    bijouteries_autorisees,
) -> QuerySet:
    """
    Retourne uniquement les ventes d'un client
    dans les bijouteries autorisées.

    Même si le client appartient à plusieurs
    bijouteries, les ventes des autres
    bijouteries restent confidentielles.
    """

    return (
        Vente.objects
        .filter(
            client_id=client_id,
            bijouterie__in=bijouteries_autorisees,
        )
        .select_related(
            "client",
            "bijouterie",
            "vendor",
        )
        .order_by("-pk")
    )


# ============================================================
# 3. FACTURES ACCESSIBLES D'UN CLIENT
# ============================================================

def factures_client_accessibles(
    client_id,
    bijouteries_autorisees,
) -> QuerySet:
    """
    Retourne uniquement les factures d'un client
    dans les bijouteries autorisées.

    Le filtrage s'effectue sur :
        - le client de la vente ;
        - la bijouterie de la facture ;
        - la bijouterie de la vente.

    Cela évite de retourner une facture
    associée à une autre bijouterie.
    """

    return (
        Facture.objects
        .filter(
            vente__client_id=client_id,
            bijouterie__in=bijouteries_autorisees,
            vente__bijouterie__in=bijouteries_autorisees,
        )
        .filter(
            bijouterie_id=(
                # Vérification de cohérence :
                # la facture doit appartenir
                # à la même bijouterie que la vente.
                __import__(
                    "django.db.models",
                    fromlist=["F"],
                ).F("vente__bijouterie_id")
            )
        )
        .select_related(
            "vente",
            "vente__client",
            "bijouterie",
        )
        .order_by("-pk")
    )


# ============================================================
# 4. PAIEMENTS ACCESSIBLES D'UN CLIENT
# ============================================================

def paiements_client_accessibles(
    client_id,
    bijouteries_autorisees,
) -> QuerySet:
    """
    Retourne uniquement les paiements d'un client
    dans les bijouteries autorisées.

    Deux circuits :

    1. Paiement direct d'une prestation :
        Paiement.vente

    2. Paiement d'une facture :
        Paiement.facture.vente

    Les conditions client et bijouterie
    restent regroupées pour chaque circuit.

    Une facture doit appartenir à la même
    bijouterie que sa vente.

    Aucun paiement d'une bijouterie non
    autorisée ne doit être retourné.
    """

    # --------------------------------------------------------
    # PAIEMENTS DIRECTS DES PRESTATIONS
    # --------------------------------------------------------

    paiement_direct = Q(
        vente__client_id=client_id,
        vente__bijouterie__in=bijouteries_autorisees,
        facture__isnull=True,
    )

    # --------------------------------------------------------
    # PAIEMENTS LIÉS AUX FACTURES
    # --------------------------------------------------------

    paiement_facture = Q(
        facture__vente__client_id=client_id,
        facture__bijouterie__in=bijouteries_autorisees,
        facture__vente__bijouterie__in=bijouteries_autorisees,
        facture__bijouterie_id=F(
            "facture__vente__bijouterie_id"
        ),
    )

    # --------------------------------------------------------
    # RÉSULTAT
    # --------------------------------------------------------

    return (
        Paiement.objects
        .filter(
            paiement_direct | paiement_facture
        )
        .select_related(
            "vente",
            "vente__client",
            "vente__bijouterie",
            "facture",
            "facture__vente",
            "facture__vente__client",
            "facture__bijouterie",
        )
        .distinct()
        .order_by("-pk")
    )



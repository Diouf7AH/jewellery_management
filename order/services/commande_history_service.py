from ..models import CommandeClientHistorique


def add_commande_history(*, commande, ancien_statut, nouveau_statut, commentaire="", user=None):
    return CommandeClientHistorique.objects.create(
        commande=commande,
        ancien_statut=ancien_statut or "",
        nouveau_statut=nouveau_statut,
        commentaire=commentaire or "",
        changed_by=user,
    )
    


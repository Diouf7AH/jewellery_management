from django.db.models import Q


# ---- Helpers périmètre (tu peux déplacer dans utils_role.py) ----
def get_manager_bijouterie_id(user):
    """
    Renvoie l'ID de la bijouterie associée au manager.
    Adapte ces chemins si tes relations diffèrent.
    """
    # lien direct éventuel
    if hasattr(user, "bijouterie_id") and user.bijouterie_id:
        return user.bijouterie_id

    # profils possibles
    for attr in ("manager_profile", "staff_manager_profile", "employee_profile"):
        prof = getattr(user, attr, None)
        if prof and getattr(prof, "bijouterie_id", None):
            return prof.bijouterie_id

    return None


def vendor_stock_filter(user) -> Q:
    """
    Construit un Q() qui restreint le stock à 'son' périmètre vendor.
    Cas A/B : vendor rattaché à une bijouterie via un lien direct ou un profil.
    (Si ton vendor est lié via les produits, remplace par un filtre sur produit_line)
    """
    # CAS A : liaison directe
    if hasattr(user, "bijouterie_id") and user.bijouterie_id:
        return Q(bijouterie_id=user.bijouterie_id)

    # CAS B : profils possibles
    for attr in ("vendor_profile", "staff_vendor_profile", "employee_profile"):
        prof = getattr(user, attr, None)
        if prof and getattr(prof, "bijouterie_id", None):
            return Q(bijouterie_id=prof.bijouterie_id)

    # CAS C (exemple à activer si nécessaire) :
    # from purchase.models import ProduitLine
    # pl_ids = ProduitLine.objects.filter(vendor=user.vendor).values_list("id", flat=True)
    # return Q(produit_line_id__in=pl_ids)

    # Sécurité par défaut si on ne sait pas restreindre
    return Q(pk__in=[])


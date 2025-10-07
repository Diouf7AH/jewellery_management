from django.shortcuts import get_object_or_404
from store.models import Bijouterie

def get_user_bijouterie_or_none(user, admin_fallback_id: int | None = None):
    # Vendeur
    vp = getattr(user, "vendor_profile", None)
    if vp and getattr(vp, "verifie", False) and vp.bijouterie_id:
        return vp.bijouterie

    # Manager
    mp = getattr(user, "staff_manager_profile", None)
    if mp and getattr(mp, "verifie", False) and mp.bijouterie_id:
        return mp.bijouterie

    # Admin (facultatif) : autoriser ?bijouterie_id=...
    if admin_fallback_id:
        return get_object_or_404(Bijouterie, pk=int(admin_fallback_id))

    return None

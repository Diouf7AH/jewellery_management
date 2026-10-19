from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from vendor.services.vendor_service import get_connected_vendor


class TestGetConnectedVendor(SimpleTestCase):

    def make_user(
        self,
        *,
        authenticated=True,
        active=True,
    ):
        return SimpleNamespace(
            is_authenticated=authenticated,
            is_active=active,
        )

    def test_user_none(self):
        result = get_connected_vendor(None)

        self.assertIsNone(result)

    def test_utilisateur_non_authentifie(self):
        user = self.make_user(
            authenticated=False,
        )

        result = get_connected_vendor(user)

        self.assertIsNone(result)

    def test_compte_utilisateur_desactive(self):
        user = self.make_user(
            active=False,
        )

        result = get_connected_vendor(user)

        self.assertIsNone(result)

    @patch("vendor.services.vendor_service.Vendor.objects")
    def test_vendeur_actif_trouve(self, mock_objects):
        user = self.make_user()

        vendor = SimpleNamespace(
            pk=10,
            verifie=True,
            bijouterie_id=1,
        )

        queryset = (
            mock_objects
            .select_related.return_value
            .filter.return_value
        )

        queryset.first.return_value = vendor

        result = get_connected_vendor(user)

        self.assertIs(result, vendor)

        mock_objects.select_related.assert_called_once_with(
            "user",
            "bijouterie",
        )

        mock_objects.select_related.return_value.filter.assert_called_once_with(
            user=user,
            verifie=True,
        )

    @patch("vendor.services.vendor_service.Vendor.objects")
    def test_profil_vendeur_introuvable(self, mock_objects):
        user = self.make_user()

        queryset = (
            mock_objects
            .select_related.return_value
            .filter.return_value
        )

        queryset.first.return_value = None

        result = get_connected_vendor(user)

        self.assertIsNone(result)

    @patch("vendor.services.vendor_service.Vendor.objects")
    def test_vendeur_desactive_non_retourne(self, mock_objects):
        """
        Le filtre verifie=True doit être transmis
        au queryset.

        On simule l'absence de résultat pour
        un vendeur désactivé.
        """

        user = self.make_user()

        queryset = (
            mock_objects
            .select_related.return_value
            .filter.return_value
        )

        queryset.first.return_value = None

        result = get_connected_vendor(user)

        self.assertIsNone(result)

        mock_objects.select_related.return_value.filter.assert_called_once_with(
            user=user,
            verifie=True,
        )

    @patch("vendor.services.vendor_service.Vendor.objects")
    def test_aucune_requete_si_user_inactif(self, mock_objects):
        user = self.make_user(active=False)

        result = get_connected_vendor(user)

        self.assertIsNone(result)
        mock_objects.select_related.assert_not_called()

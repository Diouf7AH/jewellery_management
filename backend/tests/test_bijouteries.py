from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from backend.bijouteries import (_get_single_profile_bijouterie_queryset,
                                 _verified_profile, get_accessible_bijouterie,
                                 get_user_bijouteries,
                                 user_has_bijouterie_access)
from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR)


class VerifiedProfileTests(SimpleTestCase):

    def test_profil_actif(self):
        profile = SimpleNamespace(verifie=True)
        self.assertTrue(_verified_profile(profile))

    def test_profil_desactive(self):
        profile = SimpleNamespace(verifie=False)
        self.assertFalse(_verified_profile(profile))

    def test_profil_absent(self):
        self.assertFalse(_verified_profile(None))

    def test_profil_sans_champ_verifie(self):
        self.assertFalse(
            _verified_profile(SimpleNamespace())
        )


class SingleProfileBijouterieTests(SimpleTestCase):

    @patch("backend.bijouteries.Bijouterie.objects")
    def test_profil_valide(self, objects):
        profile = SimpleNamespace(
            verifie=True,
            bijouterie_id=3,
        )

        result = _get_single_profile_bijouterie_queryset(
            profile
        )

        objects.filter.assert_called_once_with(pk=3)
        self.assertEqual(result, objects.filter.return_value)

    @patch("backend.bijouteries.Bijouterie.objects")
    def test_profil_desactive(self, objects):
        profile = SimpleNamespace(
            verifie=False,
            bijouterie_id=3,
        )

        _get_single_profile_bijouterie_queryset(profile)

        objects.none.assert_called_once()

    @patch("backend.bijouteries.Bijouterie.objects")
    def test_profil_sans_bijouterie(self, objects):
        profile = SimpleNamespace(
            verifie=True,
            bijouterie_id=None,
        )

        _get_single_profile_bijouterie_queryset(profile)

        objects.none.assert_called_once()

    @patch("backend.bijouteries.Bijouterie.objects")
    def test_profil_absent(self, objects):
        _get_single_profile_bijouterie_queryset(None)

        objects.none.assert_called_once()


class GetUserBijouteriesTests(SimpleTestCase):

    def setUp(self):
        self.user = SimpleNamespace()

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_admin(self, get_role, objects):
        get_role.return_value = ROLE_ADMIN

        result = get_user_bijouteries(self.user)

        objects.all.return_value.order_by.assert_called_once_with(
            "nom", "pk"
        )
        self.assertEqual(
            result,
            objects.all.return_value.order_by.return_value,
        )

    @patch("backend.bijouteries.get_role_name")
    def test_manager_actif(self, get_role):
        get_role.return_value = ROLE_MANAGER

        manager = SimpleNamespace(
            verifie=True,
            bijouteries=MagicMock(),
        )

        self.user.staff_manager_profile = manager

        result = get_user_bijouteries(self.user)

        manager.bijouteries.all.return_value.order_by.assert_called_once_with(
            "nom", "pk"
        )
        self.assertEqual(
            result,
            manager.bijouteries.all.return_value.order_by.return_value,
        )

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_manager_desactive(self, get_role, objects):
        get_role.return_value = ROLE_MANAGER

        self.user.staff_manager_profile = SimpleNamespace(
            verifie=False
        )

        get_user_bijouteries(self.user)

        objects.none.assert_called_once()

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_manager_sans_profil(self, get_role, objects):
        get_role.return_value = ROLE_MANAGER

        get_user_bijouteries(self.user)

        objects.none.assert_called_once()

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_vendor(self, get_role, objects):
        get_role.return_value = ROLE_VENDOR

        self.user.staff_vendor_profile = SimpleNamespace(
            verifie=True,
            bijouterie_id=1,
        )

        get_user_bijouteries(self.user)

        objects.filter.assert_called_once_with(pk=1)

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_cashier(self, get_role, objects):
        get_role.return_value = ROLE_CASHIER

        self.user.staff_cashier_profile = SimpleNamespace(
            verifie=True,
            bijouterie_id=2,
        )

        get_user_bijouteries(self.user)

        objects.filter.assert_called_once_with(pk=2)

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_buyer(self, get_role, objects):
        get_role.return_value = ROLE_BUYER

        self.user.staff_buyer_profile = SimpleNamespace(
            verifie=True,
            bijouterie_id=4,
        )

        get_user_bijouteries(self.user)

        objects.filter.assert_called_once_with(pk=4)

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_role_absent(self, get_role, objects):
        get_role.return_value = None

        get_user_bijouteries(self.user)

        objects.none.assert_called_once()

    @patch("backend.bijouteries.Bijouterie.objects")
    @patch("backend.bijouteries.get_role_name")
    def test_role_inconnu(self, get_role, objects):
        get_role.return_value = "UNKNOWN"

        get_user_bijouteries(self.user)

        objects.none.assert_called_once()


class UserHasBijouterieAccessTests(SimpleTestCase):

    @patch("backend.bijouteries.get_user_bijouteries")
    def test_acces_autorise(self, get_bijouteries):
        get_bijouteries.return_value.filter.return_value.exists.return_value = True

        self.assertTrue(
            user_has_bijouterie_access(object(), 5)
        )

        get_bijouteries.return_value.filter.assert_called_once_with(
            pk=5
        )

    @patch("backend.bijouteries.get_user_bijouteries")
    def test_acces_refuse(self, get_bijouteries):
        get_bijouteries.return_value.filter.return_value.exists.return_value = False

        self.assertFalse(
            user_has_bijouterie_access(object(), 5)
        )

    def test_id_absent(self):
        self.assertFalse(
            user_has_bijouterie_access(object(), None)
        )

    def test_id_invalide(self):
        self.assertFalse(
            user_has_bijouterie_access(object(), "abc")
        )

    def test_id_negatif(self):
        self.assertFalse(
            user_has_bijouterie_access(object(), -1)
        )

    def test_id_zero(self):
        self.assertFalse(
            user_has_bijouterie_access(object(), 0)
        )

    def test_objet_bijouterie(self):
        bijouterie = SimpleNamespace(pk=7)

        with patch(
            "backend.bijouteries.get_user_bijouteries"
        ) as get_bijouteries:
            get_bijouteries.return_value.filter.return_value.exists.return_value = True

            self.assertTrue(
                user_has_bijouterie_access(
                    object(), bijouterie
                )
            )

            get_bijouteries.return_value.filter.assert_called_once_with(
                pk=7
            )


class GetAccessibleBijouterieTests(SimpleTestCase):

    @patch("backend.bijouteries.get_user_bijouteries")
    def test_bijouterie_accessible(self, get_bijouteries):
        bijouterie = SimpleNamespace(pk=3)

        get_bijouteries.return_value.filter.return_value.first.return_value = bijouterie

        result = get_accessible_bijouterie(
            object(), 3
        )

        self.assertEqual(result, bijouterie)

    @patch("backend.bijouteries.get_user_bijouteries")
    def test_bijouterie_inaccessible(self, get_bijouteries):
        get_bijouteries.return_value.filter.return_value.first.return_value = None

        self.assertIsNone(
            get_accessible_bijouterie(object(), 3)
        )

    def test_id_absent(self):
        self.assertIsNone(
            get_accessible_bijouterie(object(), None)
        )

    def test_id_invalide(self):
        self.assertIsNone(
            get_accessible_bijouterie(object(), "invalide")
        )

    def test_id_zero(self):
        self.assertIsNone(
            get_accessible_bijouterie(object(), 0)
        )

    def test_id_negatif(self):
        self.assertIsNone(
            get_accessible_bijouterie(object(), -5)
        )

    @patch("backend.bijouteries.get_user_bijouteries")
    def test_objet_bijouterie(self, get_bijouteries):
        bijouterie = SimpleNamespace(pk=8)

        get_bijouteries.return_value.filter.return_value.first.return_value = bijouterie

        result = get_accessible_bijouterie(
            object(), bijouterie
        )

        self.assertEqual(result, bijouterie)

        get_bijouteries.return_value.filter.assert_called_once_with(
            pk=8
        )

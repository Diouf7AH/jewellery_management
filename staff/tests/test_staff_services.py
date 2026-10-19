from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from backend.roles import (ROLE_ADMIN, ROLE_BUYER, ROLE_CASHIER, ROLE_MANAGER,
                           ROLE_VENDOR)
from staff.services import (StaffCreationResult, StaffUpdateResult,
                            _check_caller, _check_manager_scope,
                            _validate_bijouterie, _validate_bijouteries,
                            _validate_target_user, create_staff_member,
                            promote_user_to_admin, update_staff_member)
from staff.services.staff_service import ROLE_MODEL_MAP


def make_user(

    *,

    pk=1,

    email="user@example.com",

    is_active=True,

    is_authenticated=True,

    is_email_verified=True,

    is_superuser=False,

):

    return SimpleNamespace(

        pk=pk,

        id=pk,

        email=email,

        is_active=is_active,

        is_authenticated=is_authenticated,

        is_email_verified=is_email_verified,

        is_superuser=is_superuser,

        first_name="Ali",

        last_name="Diop",

        user_role=None,

        save=MagicMock(),

    )

def make_staff(

    *,

    pk=10,

    user=None,

    bijouterie=None,

    verifie=True,

):

    user = user or make_user()

    bijouterie = bijouterie or SimpleNamespace(pk=1)

    staff = SimpleNamespace(

        pk=pk,

        id=pk,

        user=user,

        user_id=user.pk,

        bijouterie=bijouterie,

        bijouterie_id=bijouterie.pk,

        verifie=verifie,

        raison_desactivation=None,

        save=MagicMock(),

        desactiver=MagicMock(),

        reactiver=MagicMock(),

    )

    return staff

class TestStaffPermissions(SimpleTestCase):

    @patch("staff.services.staff_service.get_role_name")

    def test_utilisateur_non_authentifie_refuse(self, mock_role):

        user = make_user(is_authenticated=False)

        with self.assertRaises(PermissionError):

            _check_caller(user, ROLE_VENDOR)

        mock_role.assert_not_called()

    @patch("staff.services.staff_service.get_role_name")

    def test_compte_desactive_refuse(self, mock_role):

        user = make_user(is_active=False)

        with self.assertRaises(PermissionError):

            _check_caller(user, ROLE_VENDOR)

        mock_role.assert_not_called()

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_ADMIN)

    def test_admin_peut_gerer_vendor(self, _):

        user = make_user()

        role, manager = _check_caller(

            user,

            ROLE_VENDOR,

        )

        self.assertEqual(role, ROLE_ADMIN)

        self.assertIsNone(manager)

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_ADMIN)

    def test_admin_peut_gerer_buyer(self, _):

        role, manager = _check_caller(

            make_user(),

            ROLE_BUYER,

        )

        self.assertEqual(role, ROLE_ADMIN)

        self.assertIsNone(manager)

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_MANAGER)

    def test_manager_ne_peut_pas_gerer_buyer(self, _):

        with self.assertRaises(PermissionError):

            _check_caller(

                make_user(),

                ROLE_BUYER,

            )

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_MANAGER)

    def test_manager_ne_peut_pas_gerer_manager(self, _):

        with self.assertRaises(PermissionError):

            _check_caller(

                make_user(),

                ROLE_MANAGER,

            )

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_VENDOR)

    def test_vendor_ne_peut_pas_creer_staff(self, _):

        with self.assertRaises(PermissionError):

            _check_caller(

                make_user(),

                ROLE_CASHIER,

            )

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_ADMIN)

    def test_role_cible_invalide(self, _):

        with self.assertRaises(ValueError):

            _check_caller(

                make_user(),

                "unknown",

            )

    @patch("staff.services.staff_service.Manager.objects")

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_MANAGER)

    def test_manager_actif_autorise(

        self,

        _,

        mock_objects,

    ):

        manager = SimpleNamespace(

            is_active_staff=True,

        )

        mock_objects.select_related.return_value.filter.return_value.first.return_value = manager

        role, result = _check_caller(

            make_user(),

            ROLE_VENDOR,

        )

        self.assertEqual(role, ROLE_MANAGER)

        self.assertIs(result, manager)

    @patch("staff.services.staff_service.Manager.objects")

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_MANAGER)

    def test_manager_desactive_refuse(

        self,

        _,

        mock_objects,

    ):

        manager = SimpleNamespace(

            is_active_staff=False,

        )

        mock_objects.select_related.return_value.filter.return_value.first.return_value = manager

        with self.assertRaises(PermissionError):

            _check_caller(

                make_user(),

                ROLE_VENDOR,

            )

class TestStaffValidations(SimpleTestCase):

    def test_utilisateur_inexistant(self):

        with self.assertRaises(ValueError):

            _validate_target_user(None)

    def test_utilisateur_desactive(self):

        with self.assertRaises(ValueError):

            _validate_target_user(

                make_user(is_active=False)

            )

    def test_email_non_verifie(self):

        with self.assertRaises(ValueError):

            _validate_target_user(

                make_user(is_email_verified=False)

            )

    def test_superuser_refuse(self):

        with self.assertRaises(ValueError):

            _validate_target_user(

                make_user(is_superuser=True)

            )

    def test_utilisateur_valide(self):

        _validate_target_user(make_user())

    @patch("staff.services.staff_service.Bijouterie.objects")

    def test_bijouterie_valide(self, mock_objects):

        bijouterie = SimpleNamespace(pk=1)

        mock_objects.filter.return_value.exists.return_value = True

        result = _validate_bijouterie(bijouterie)

        self.assertIs(result, bijouterie)

    def test_bijouterie_absente(self):

        with self.assertRaises(ValueError):

            _validate_bijouterie(None)

    @patch("staff.services.staff_service.Bijouterie.objects")

    def test_bijouterie_inexistante(self, mock_objects):

        mock_objects.filter.return_value.exists.return_value = False

        with self.assertRaises(ValueError):

            _validate_bijouterie(

                SimpleNamespace(pk=999)

            )

    def test_liste_bijouteries_vide(self):

        with self.assertRaises(ValueError):

            _validate_bijouteries([])

    @patch("staff.services.staff_service.Bijouterie.objects")

    def test_liste_bijouteries_valides(self, mock_objects):

        b1 = SimpleNamespace(pk=1)

        b2 = SimpleNamespace(pk=2)

        mock_objects.filter.return_value.count.return_value = 2

        mock_objects.filter.return_value.__iter__ = MagicMock(

            return_value=iter([b1, b2])

        )

        result = _validate_bijouteries([b1, b2])

        self.assertEqual(len(result), 2)

    def test_manager_hors_perimetre(self):

        manager = MagicMock()

        manager.bijouteries.filter.return_value.exists.return_value = False

        with self.assertRaises(PermissionError):

            _check_manager_scope(

                manager,

                SimpleNamespace(pk=5),

            )

    def test_manager_dans_perimetre(self):

        manager = MagicMock()

        manager.bijouteries.filter.return_value.exists.return_value = True

        _check_manager_scope(

            manager,

            SimpleNamespace(pk=5),

        )

class TestCreateStaffMember(TestCase):

    @patch("staff.services.staff_service._check_caller")

    def test_email_obligatoire(self, mock_check):

        with self.assertRaises(ValueError):

            create_staff_member(

                caller_user=make_user(),

                target_role=ROLE_VENDOR,

                email="",

            )

        mock_check.assert_not_called()

    @patch("staff.services.staff_service._get_existing_staff_flags")

    @patch("staff.services.staff_service._validate_target_user")

    @patch("staff.services.staff_service._check_caller")

    @patch("staff.services.staff_service.User.objects")

    @patch("staff.services.staff_service.get_role_name")

    def test_profil_existant_refuse(

        self,

        mock_role,

        mock_objects,

        mock_check,

        mock_validate,

        mock_flags,

    ):

        user = make_user()

        mock_check.return_value = (ROLE_ADMIN, None)

        mock_objects.select_for_update.return_value.filter.return_value.first.return_value = user

        mock_role.return_value = ROLE_VENDOR

        mock_flags.return_value = {

            ROLE_MANAGER: False,

            ROLE_VENDOR: True,

            ROLE_CASHIER: False,

            ROLE_BUYER: False,

        }

        with self.assertRaises(ValueError):

            create_staff_member(

                caller_user=make_user(),

                target_role=ROLE_VENDOR,

                email=user.email,

                bijouterie=SimpleNamespace(pk=1),

            )

    @patch("staff.services.staff_service.Role.objects")

    @patch("staff.services.staff_service.Vendor.objects")

    @patch("staff.services.staff_service._validate_bijouterie")

    @patch("staff.services.staff_service._get_existing_staff_flags")

    @patch("staff.services.staff_service._validate_target_user")

    @patch("staff.services.staff_service._check_caller")

    @patch("staff.services.staff_service.User.objects")

    @patch("staff.services.staff_service.get_role_name")

    def test_creation_vendor_reussie(

        self,

        mock_role,

        mock_users,

        mock_check,

        mock_validate,

        mock_flags,

        mock_bijouterie,

        mock_vendors,

        mock_roles,

    ):

        user = make_user()

        bijouterie = SimpleNamespace(pk=1)

        staff = make_staff(user=user, bijouterie=bijouterie)

        mock_check.return_value = (ROLE_ADMIN, None)

        mock_users.select_for_update.return_value.filter.return_value.first.return_value = user

        mock_role.return_value = None

        mock_flags.return_value = {

            role: False

            for role in (

                ROLE_MANAGER,

                ROLE_VENDOR,

                ROLE_CASHIER,

                ROLE_BUYER,

            )

        }

        mock_bijouterie.return_value = bijouterie

        mock_vendors.create.return_value = staff

        role_obj = SimpleNamespace(role=ROLE_VENDOR)

        mock_roles.get_or_create.return_value = (role_obj, True)

        result = create_staff_member(

            caller_user=make_user(),

            target_role=ROLE_VENDOR,

            email=user.email,

            bijouterie=bijouterie,

        )

        self.assertIsInstance(result, StaffCreationResult)

        self.assertIs(result.staff, staff)

        self.assertIs(result.user, user)

        self.assertEqual(result.staff_type, ROLE_VENDOR)

        self.assertFalse(result.created_user)

        self.assertIs(user.user_role, role_obj)

        mock_vendors.create.assert_called_once_with(

            user=user,

            bijouterie=bijouterie,

            verifie=True,

        )

        user.save.assert_called_once_with(

            update_fields=["user_role"]

        )

class TestUpdateStaffMember(TestCase):

    def setUp(self):

        self.user = make_user()

        self.staff = make_staff(user=self.user)

    def _mock_queryset(self, mock_model):

        qs = mock_model.objects.select_for_update.return_value

        qs.select_related.return_value = qs
        qs.prefetch_related.return_value = qs
        qs.filter.return_value = qs
        qs.first.return_value = self.staff

        return qs

    @patch("staff.services.staff_service._check_caller")

    def test_verifie_non_booleen_refuse(self, mock_check):

        mock_check.return_value = (ROLE_ADMIN, None)

        with self.assertRaises(ValueError):

            update_staff_member(

                caller_user=make_user(),

                staff_id=10,

                target_role=ROLE_VENDOR,

                verifie="false",

            )

    @patch("staff.services.staff_service._check_caller")

    def test_desactivation_sans_raison_refusee(self, mock_check):

        mock_check.return_value = (ROLE_ADMIN, None)

        with self.assertRaises(ValueError):

            update_staff_member(

                caller_user=make_user(),

                staff_id=10,

                target_role=ROLE_VENDOR,

                verifie=False,

                raison_desactivation="",

            )

    @patch("staff.services.staff_service.User.objects")
    @patch("staff.services.staff_service.Vendor")
    @patch("staff.services.staff_service._check_caller")
    def test_desactivation_vendor(self, mock_check, mock_vendor, mock_users):
        caller = make_user(pk=99)
        mock_check.return_value = (ROLE_ADMIN, None)
        self._mock_queryset(mock_vendor)
        mock_users.select_for_update.return_value.get.return_value = self.user

        with patch.dict(ROLE_MODEL_MAP, {ROLE_VENDOR: mock_vendor}):
            result = update_staff_member(
                caller_user=caller,
                staff_id=10,
                target_role=ROLE_VENDOR,
                verifie=False,
                raison_desactivation="Fin de contrat",
            )

        self.assertIsInstance(result, StaffUpdateResult)
        self.assertIs(result.staff, self.staff)
        self.staff.desactiver.assert_called_once_with(
            by_user=caller, raison="Fin de contrat"
        )
        self.staff.reactiver.assert_not_called()
        self.user.save.assert_not_called()

    @patch("staff.services.staff_service.User.objects")
    @patch("staff.services.staff_service.Vendor")
    @patch("staff.services.staff_service._check_caller")
    def test_reactivation_vendor(self, mock_check, mock_vendor, mock_users):
        self.staff.verifie = False
        mock_check.return_value = (ROLE_ADMIN, None)
        self._mock_queryset(mock_vendor)
        mock_users.select_for_update.return_value.get.return_value = self.user

        with patch.dict(ROLE_MODEL_MAP, {ROLE_VENDOR: mock_vendor}):
            result = update_staff_member(
                caller_user=make_user(),
                staff_id=10,
                target_role=ROLE_VENDOR,
                verifie=True,
            )

        self.assertIsInstance(result, StaffUpdateResult)
        self.assertIs(result.staff, self.staff)
        self.staff.reactiver.assert_called_once_with()
        self.staff.desactiver.assert_not_called()
        self.user.save.assert_not_called()

    @patch("staff.services.staff_service.User.objects")
    @patch("staff.services.staff_service.Vendor")
    @patch("staff.services.staff_service._check_vendor_reassignment")
    @patch("staff.services.staff_service._validate_bijouterie")
    @patch("staff.services.staff_service._check_caller")
    def test_changement_bijouterie_vendor_bloque(
        self, mock_check, mock_validate, mock_reassign, mock_vendor, mock_users
    ):
        nouvelle_bijouterie = SimpleNamespace(pk=2)
        mock_check.return_value = (ROLE_ADMIN, None)
        mock_validate.return_value = nouvelle_bijouterie
        mock_reassign.side_effect = ValueError("Transfert dédié obligatoire.")
        self._mock_queryset(mock_vendor)
        mock_users.select_for_update.return_value.get.return_value = self.user

        with patch.dict(ROLE_MODEL_MAP, {ROLE_VENDOR: mock_vendor}):
            with self.assertRaisesRegex(ValueError, "Transfert dédié obligatoire"):
                update_staff_member(
                    caller_user=make_user(),
                    staff_id=10,
                    target_role=ROLE_VENDOR,
                    bijouterie=nouvelle_bijouterie,
                )

        mock_reassign.assert_called_once_with(self.staff, nouvelle_bijouterie)
        self.staff.save.assert_not_called()


class TestPromoteUserToAdmin(TestCase):

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_VENDOR)

    def test_vendor_ne_peut_pas_promouvoir(self, _):

        with self.assertRaises(PermissionError):

            promote_user_to_admin(

                caller_user=make_user(),

                email="target@example.com",

            )

    def test_admin_inactif_refuse(self):

        with self.assertRaises(PermissionError):

            promote_user_to_admin(

                caller_user=make_user(is_active=False),

                email="target@example.com",

            )

    @patch("staff.services.staff_service.Role.objects")

    @patch("staff.services.staff_service._get_existing_staff_flags")

    @patch("staff.services.staff_service._validate_target_user")

    @patch("staff.services.staff_service.User.objects")

    @patch("staff.services.staff_service.get_role_name", return_value=ROLE_ADMIN)

    def test_promotion_admin_reussie(

        self,

        _,

        mock_users,

        mock_validate,

        mock_flags,

        mock_roles,

    ):

        target = make_user(

            pk=2,

            email="target@example.com",

        )

        mock_users.select_for_update.return_value.filter.return_value.first.return_value = target

        mock_flags.return_value = {

            ROLE_MANAGER: False,

            ROLE_VENDOR: False,

            ROLE_CASHIER: False,

            ROLE_BUYER: False,

        }

        role_obj = SimpleNamespace(role=ROLE_ADMIN)

        mock_roles.get_or_create.return_value = (

            role_obj,

            True,

        )

        result = promote_user_to_admin(

            caller_user=make_user(),

            email=target.email,

        )

        self.assertIs(result, target)

        self.assertIs(target.user_role, role_obj)

        target.save.assert_called_once_with(

            update_fields=["user_role"]

        )


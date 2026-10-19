"""Tests d'intégration des services staff : ORM réel, aucun mock de modèle."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from backend.roles import ROLE_ADMIN, ROLE_MANAGER, ROLE_VENDOR
from staff.models import Manager
from staff.services import (create_staff_member, promote_user_to_admin,
                            update_staff_member)
from store.models import Bijouterie
from userauths.models import Role
from vendor.models import Vendor

User = get_user_model()


class StaffServiceIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_role, _ = Role.objects.get_or_create(role=ROLE_ADMIN)
        cls.admin = cls._user("admin-integration@example.com", role=cls.admin_role)
        cls.target = cls._user("vendor-integration@example.com")
        cls.other = cls._user("other-integration@example.com")
        cls.store_a = Bijouterie.objects.create(nom="Integration A")
        cls.store_b = Bijouterie.objects.create(nom="Integration B")

    @staticmethod
    def _user(email, role=None):
        """Fabrique minimale : adapter ici si le User personnalisé exige d'autres champs."""
        values = {
            "email": email,
            "is_active": True,
            "is_email_verified": True,
            "is_superuser": False,
        }
        if role is not None:
            values["user_role"] = role
        field_names = {f.name for f in User._meta.fields}
        if "username" in field_names:
            values["username"] = email.split("@")[0]
        return User.objects.create(**values)

    def _create_vendor(self):
        return create_staff_member(
            caller_user=self.admin,
            target_role=ROLE_VENDOR,
            email=self.target.email,
            bijouterie=self.store_a,
        )

    def test_creation_vendor_en_base(self):
        result = self._create_vendor()
        vendor = Vendor.objects.get(user=self.target)
        self.assertEqual(result.staff.pk, vendor.pk)
        self.assertEqual(vendor.bijouterie_id, self.store_a.pk)
        self.assertTrue(vendor.verifie)
        self.target.refresh_from_db()
        self.assertEqual(self.target.user_role.role, ROLE_VENDOR)
        self.assertFalse(result.created_user)

    def test_creation_deuxieme_profil_interdite(self):
        self._create_vendor()
        with self.assertRaises(ValueError):
            self._create_vendor()
        self.assertEqual(Vendor.objects.filter(user=self.target).count(), 1)

    def test_desactivation_conserve_compte_actif(self):
        vendor = self._create_vendor().staff
        update_staff_member(
            caller_user=self.admin,
            staff_id=vendor.pk,
            target_role=ROLE_VENDOR,
            verifie=False,
            raison_desactivation="Fin de contrat",
        )
        vendor.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(vendor.verifie)
        self.assertEqual(vendor.raison_desactivation, "Fin de contrat")
        self.assertTrue(self.target.is_active)

    def test_reactivation_vendor_en_base(self):
        vendor = self._create_vendor().staff
        update_staff_member(
            caller_user=self.admin, staff_id=vendor.pk,
            target_role=ROLE_VENDOR, verifie=False,
            raison_desactivation="Suspension",
        )
        update_staff_member(
            caller_user=self.admin, staff_id=vendor.pk,
            target_role=ROLE_VENDOR, verifie=True,
        )
        vendor.refresh_from_db()
        self.assertTrue(vendor.verifie)
        self.assertIsNone(vendor.raison_desactivation)

    def test_transfert_vendor_interdit_et_transaction_annulee(self):
        vendor = self._create_vendor().staff
        ancien_prenom = self.target.first_name
        with self.assertRaisesRegex(ValueError, "transfert"):
            update_staff_member(
                caller_user=self.admin,
                staff_id=vendor.pk,
                target_role=ROLE_VENDOR,
                first_name="Modification annulée",
                bijouterie=self.store_b,
            )
        vendor.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(vendor.bijouterie_id, self.store_a.pk)
        self.assertEqual(self.target.first_name, ancien_prenom)

    def test_raison_obligatoire_aucune_modification(self):
        vendor = self._create_vendor().staff
        with self.assertRaises(ValueError):
            update_staff_member(
                caller_user=self.admin, staff_id=vendor.pk,
                target_role=ROLE_VENDOR, verifie=False,
                raison_desactivation="  ",
            )
        vendor.refresh_from_db()
        self.assertTrue(vendor.verifie)

    def test_promotion_admin_en_base(self):
        promoted = promote_user_to_admin(
            caller_user=self.admin, email=self.other.email,
        )
        self.other.refresh_from_db()
        self.assertEqual(promoted.pk, self.other.pk)
        self.assertEqual(self.other.user_role.role, ROLE_ADMIN)

    def test_promotion_admin_refusee_si_profil_vendor(self):
        self._create_vendor()
        with self.assertRaises(ValueError):
            promote_user_to_admin(
                caller_user=self.admin, email=self.target.email,
            )
        self.target.refresh_from_db()
        self.assertEqual(self.target.user_role.role, ROLE_VENDOR)

    def test_creation_manager_et_bijouteries_en_base(self):
        result = create_staff_member(
            caller_user=self.admin,
            target_role=ROLE_MANAGER,
            email=self.other.email,
            bijouteries=[self.store_a, self.store_b],
        )
        manager = Manager.objects.get(pk=result.staff.pk)
        self.assertEqual(
            set(manager.bijouteries.values_list("pk", flat=True)),
            {self.store_a.pk, self.store_b.pk},
        )

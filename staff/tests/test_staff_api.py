"""Tests API DRF du module staff avec ORM réel et permissions réelles.

L'authentification est simulée avec force_authenticate afin de tester les vues
sans dépendre du mécanisme d'émission de jetons JWT.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from backend.roles import ROLE_ADMIN, ROLE_VENDOR
from staff.services import create_staff_member
from store.models import Bijouterie
from userauths.models import Role
from vendor.models import Vendor

User = get_user_model()


class StaffAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_role, _ = Role.objects.get_or_create(role=ROLE_ADMIN)
        cls.admin = cls.make_user("api-admin@example.com", admin_role)
        cls.target = cls.make_user("api-target@example.com")
        cls.second = cls.make_user("api-second@example.com")
        cls.store = Bijouterie.objects.create(nom="API Rio Gold Dakar")
        cls.other_store = Bijouterie.objects.create(nom="API Rio Gold Thies")

    @staticmethod
    def make_user(email, role=None):
        values = {
            "email": email,
            "is_active": True,
            "is_email_verified": True,
            "is_superuser": False,
        }
        if role is not None:
            values["user_role"] = role
        if "username" in {field.name for field in User._meta.fields}:
            values["username"] = email.split("@")[0]
        return User.objects.create(**values)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def create_vendor(self):
        return create_staff_member(
            caller_user=self.admin,
            target_role=ROLE_VENDOR,
            email=self.target.email,
            bijouterie=self.store,
        ).staff

    def test_anonyme_creation_refusee(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse("staff-c"), {}, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_creation_vendor_en_base(self):
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR,
            "email": self.target.email,
            "bijouterie_id": self.store.pk,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        vendor = Vendor.objects.get(user=self.target)
        self.assertEqual(vendor.bijouterie_id, self.store.pk)
        self.assertTrue(vendor.verifie)
        self.assertEqual(response.data["staff_type"], ROLE_VENDOR)

    def test_creation_email_inexistant_400(self):
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR,
            "email": "absent-api@example.com",
            "bijouterie_id": self.store.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Vendor.objects.exists())

    def test_creation_bijouterie_inexistante_400(self):
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR,
            "email": self.target.email,
            "bijouterie_id": 999999,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_creation_vendor_sans_bijouterie_400(self):
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR, "email": self.target.email,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_creation_profil_deja_existant_409(self):
        self.create_vendor()
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR,
            "email": self.target.email,
            "bijouterie_id": self.store.pk,
        }, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(Vendor.objects.filter(user=self.target).count(), 1)

    def test_vendor_ne_peut_pas_creer_staff(self):
        self.create_vendor()
        self.client.force_authenticate(user=self.target)
        response = self.client.post(reverse("staff-c"), {
            "role": ROLE_VENDOR,
            "email": self.second.email,
            "bijouterie_id": self.store.pk,
        }, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(Vendor.objects.filter(user=self.second).exists())

    def test_desactivation_vendor_par_api(self):
        vendor = self.create_vendor()
        response = self.client.put(reverse("staff-u", kwargs={"staff_id": vendor.pk}), {
            "role": ROLE_VENDOR,
            "verifie": False,
            "raison_desactivation": "Fin de contrat",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        vendor.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(vendor.verifie)
        self.assertEqual(vendor.raison_desactivation, "Fin de contrat")
        self.assertTrue(self.target.is_active)

    def test_desactivation_sans_raison_400(self):
        vendor = self.create_vendor()
        response = self.client.put(reverse("staff-u", kwargs={"staff_id": vendor.pk}), {
            "role": ROLE_VENDOR, "verifie": False,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        vendor.refresh_from_db()
        self.assertTrue(vendor.verifie)

    def test_reactivation_vendor_par_api(self):
        vendor = self.create_vendor()
        deactivation = self.client.put(reverse("staff-u", kwargs={"staff_id": vendor.pk}), {
            "role": ROLE_VENDOR,
            "verifie": False,
            "raison_desactivation": "Suspension",
        }, format="json")
        self.assertEqual(deactivation.status_code, 200, deactivation.data)
        response = self.client.put(reverse("staff-u", kwargs={"staff_id": vendor.pk}), {
            "role": ROLE_VENDOR, "verifie": True,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        vendor.refresh_from_db()
        self.assertTrue(vendor.verifie)
        self.assertIsNone(vendor.raison_desactivation)

    def test_modification_vendor_introuvable_404(self):
        response = self.client.put(reverse("staff-u", kwargs={"staff_id": 999999}), {
            "role": ROLE_VENDOR, "first_name": "Ali",
        }, format="json")
        self.assertEqual(response.status_code, 404, response.data)

    def test_transfert_vendor_refuse(self):
        vendor = self.create_vendor()
        response = self.client.put(reverse("staff-u", kwargs={"staff_id": vendor.pk}), {
            "role": ROLE_VENDOR,
            "bijouterie_nom": self.other_store.nom,
        }, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        vendor.refresh_from_db()
        self.assertEqual(vendor.bijouterie_id, self.store.pk)

    def test_liste_staff_admin(self):
        self.create_vendor()
        response = self.client.get(reverse("staff"))
        self.assertEqual(response.status_code, 200, response.data)

    def test_liste_role_invalide_400(self):
        response = self.client.get(reverse("staff"), {"role": "inconnu"})
        self.assertEqual(response.status_code, 400, response.data)

    def test_detail_vendor_admin(self):
        vendor = self.create_vendor()
        response = self.client.get(reverse("staff-d", kwargs={
            "role": ROLE_VENDOR, "staff_id": vendor.pk,
        }))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["staff_id"], vendor.pk)

    def test_creation_admin_email_vide_400(self):
        response = self.client.post(reverse("create-admin"), {
            "email": "",
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_vendor_ne_peut_pas_promouvoir_admin(self):
        self.create_vendor()
        self.client.force_authenticate(user=self.target)
        response = self.client.post(reverse("create-admin"), {
            "email": self.second.email,
        }, format="json")
        self.assertEqual(response.status_code, 403, response.data)

    def test_promotion_admin_par_api(self):
        response = self.client.post(
            reverse("create-admin"),
            {"email": self.second.email},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            200,
            response.data,
        )

        self.second.refresh_from_db()

        # Vérifier la promotion au rôle administrateur Rio-Gold.
        self.assertIsNotNone(self.second.user_role)

        self.assertEqual(
            self.second.user_role.role,
            ROLE_ADMIN,
        )

        # Vérifier que le compte reste actif.
        self.assertTrue(self.second.is_active)

        # La promotion métier ne doit pas accorder
        # automatiquement les privilèges Django superuser.
        self.assertFalse(self.second.is_superuser)
    def test_dashboard_staff_admin(self):
        response = self.client.get(reverse("staff-dashboard"))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("summary", response.data)

    def test_dashboard_staff_anonyme_refuse(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("staff-dashboard"))
        self.assertIn(response.status_code, (401, 403))

    def test_dashboard_manager_anonyme_refuse(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("manager-dashboard"))
        self.assertIn(response.status_code, (401, 403))

    def test_dashboard_cashier_anonyme_refuse(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("cashier-dashboard"))
        self.assertIn(response.status_code, (401, 403))

    def test_dashboard_manager_admin_sans_profil_refuse(self):
        response = self.client.get(reverse("manager-dashboard"))
        self.assertEqual(response.status_code, 403, response.data)

    def test_dashboard_cashier_admin_sans_profil_refuse(self):
        response = self.client.get(reverse("cashier-dashboard"))
        self.assertEqual(response.status_code, 403, response.data)

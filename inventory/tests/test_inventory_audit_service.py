# inventory/tests/test_inventory_audit_service.py

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase

from inventory.models import Bucket, MovementType
from inventory.services.inventory_audit_service import \
    create_sale_out_consumption


class TestInventoryAuditService(SimpleTestCase):

    def setUp(self):
        self.vendor = SimpleNamespace(
            pk=3,
            id=3,
            bijouterie_id=10,
        )

        self.bijouterie = SimpleNamespace(pk=10, id=10)

        self.produit = SimpleNamespace(pk=5, id=5)
        self.lot = SimpleNamespace(pk=7, id=7)

        self.produit_line = SimpleNamespace(
            pk=6,
            id=6,
            produit_id=5,
            produit=self.produit,
            lot_id=7,
            lot=self.lot,
            uuid="test-produit-line",
        )

        self.vente = SimpleNamespace(
            pk=2,
            id=2,
            vendor_id=3,
            vendor=self.vendor,
            numero_vente="V-TEST-001",
        )

        self.vente_ligne = SimpleNamespace(
            pk=4,
            id=4,
            vente_id=2,
            produit_id=5,
            produit_line_id=6,
            vendor=self.vendor,
        )

        self.facture = SimpleNamespace(
            pk=1,
            id=1,
            vente_id=2,
            bijouterie_id=10,
            bijouterie=self.bijouterie,
            status="paye",
            STAT_PAYE="paye",
            numero_facture="F-TEST-001",
        )

    def call_service(self, **overrides):
        params = {
            "facture": self.facture,
            "vente": self.vente,
            "vente_ligne": self.vente_ligne,
            "produit_line": self.produit_line,
            "qty": 1,
            "by_user": None,
        }
        params.update(overrides)
        return create_sale_out_consumption(**params)

    def test_quantite_zero_interdite(self):
        with self.assertRaises(ValidationError):
            self.call_service(qty=0)

    def test_quantite_negative_interdite(self):
        with self.assertRaises(ValidationError):
            self.call_service(qty=-1)

    def test_facture_obligatoire(self):
        with self.assertRaises(ValidationError):
            self.call_service(facture=None)

    def test_produit_line_incoherente(self):
        self.produit_line.produit_id = 999

        with self.assertRaises(ValidationError):
            self.call_service()

    def test_ligne_vente_incoherente(self):
        self.vente_ligne.vente_id = 999

        with self.assertRaises(ValidationError):
            self.call_service()

    def test_vendeur_autre_bijouterie_interdit(self):
        self.vendor.bijouterie_id = 999

        with self.assertRaises(ValidationError):
            self.call_service()

    def test_facture_non_payee_interdite(self):
        self.facture.status = "non_paye"

        with self.assertRaises(ValidationError):
            self.call_service()

    @patch(
        "inventory.services.inventory_audit_service.log_move"
    )
    def test_sale_out_cree_mouvement_correct(self, mock_log_move):
        result = self.call_service(qty=1)

        self.assertTrue(result)
        mock_log_move.assert_called_once()

        kwargs = mock_log_move.call_args.kwargs

        self.assertEqual(
            kwargs["movement_type"],
            MovementType.SALE_OUT,
        )
        self.assertEqual(kwargs["src_bucket"], Bucket.VENDOR)
        self.assertEqual(kwargs["dst_bucket"], Bucket.EXTERNAL)
        self.assertEqual(kwargs["qty"], 1)
        self.assertEqual(kwargs["produit_line"], self.produit_line)
        self.assertEqual(kwargs["vendor"], self.vendor)
        self.assertEqual(kwargs["vente"], self.vente)
        self.assertEqual(kwargs["facture"], self.facture)
        self.assertTrue(kwargs["stock_consumed"])

    @patch(
        "inventory.services.inventory_audit_service.log_move"
    )
    def test_erreur_integrite_non_masquee(self, mock_log_move):
        mock_log_move.side_effect = IntegrityError(
            "Contrainte unique violée"
        )

        with self.assertRaises(IntegrityError):
            self.call_service()

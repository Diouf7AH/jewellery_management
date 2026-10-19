# inventory/tests/test_return_in_service.py

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import SimpleTestCase

from inventory.models import Bucket, MovementType
from inventory.services.inventory_audit_service import \
    create_return_in_consumption


class TestReturnInService(SimpleTestCase):

    def setUp(self):
        self.vendor = SimpleNamespace(
            pk=3,
            id=3,
            bijouterie_id=10,
        )

        self.produit = SimpleNamespace(pk=5, id=5)
        self.lot = SimpleNamespace(pk=7, id=7)

        self.produit_line = SimpleNamespace(
            pk=6,
            id=6,
            produit_id=5,
            produit=self.produit,
            lot_id=7,
            lot=self.lot,
            uuid="test-pl-6",
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

        return create_return_in_consumption(**params)

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

    @patch(
        "inventory.services.inventory_audit_service.log_move"
    )
    def test_return_in_cree_mouvement_correct(self, mock_log_move):
        result = self.call_service(qty=1)

        self.assertTrue(result)
        mock_log_move.assert_called_once()

        kwargs = mock_log_move.call_args.kwargs

        self.assertEqual(
            kwargs["movement_type"],
            MovementType.RETURN_IN,
        )
        self.assertEqual(
            kwargs["src_bucket"],
            Bucket.EXTERNAL,
        )
        self.assertEqual(
            kwargs["dst_bucket"],
            Bucket.BIJOUTERIE,
        )
        self.assertEqual(kwargs["qty"], 1)
        self.assertEqual(
            kwargs["produit_line"],
            self.produit_line,
        )
        self.assertEqual(kwargs["vendor"], self.vendor)
        self.assertFalse(kwargs["stock_consumed"])

    @patch(
        "inventory.services.inventory_audit_service.log_move"
    )
    def test_erreur_integrite_remontee(self, mock_log_move):
        mock_log_move.side_effect = IntegrityError(
            "Erreur de contrainte"
        )

        with self.assertRaises(IntegrityError):
            self.call_service()


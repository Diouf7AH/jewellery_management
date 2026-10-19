# inventory/tests/test_inventory_movement_service.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from inventory.services.inventory_movement_service import (
    _normalize_qty, _normalize_unit_cost)


class TestInventoryServices(SimpleTestCase):

    def test_quantite_positive(self):
        self.assertEqual(_normalize_qty(5), 5)

    def test_quantite_chaine(self):
        self.assertEqual(_normalize_qty("10"), 10)

    def test_quantite_zero_interdite(self):
        with self.assertRaises(ValidationError):
            _normalize_qty(0)

    def test_quantite_negative_interdite(self):
        with self.assertRaises(ValidationError):
            _normalize_qty(-2)

    def test_quantite_decimale_interdite(self):
        with self.assertRaises(ValidationError):
            _normalize_qty(Decimal("1.5"))

    def test_quantite_booleenne_interdite(self):
        with self.assertRaises(ValidationError):
            _normalize_qty(True)

    def test_cout_unitaire_valide(self):
        self.assertEqual(
            _normalize_unit_cost("15000.00"),
            Decimal("15000.00"),
        )

    def test_cout_unitaire_negatif_interdit(self):
        with self.assertRaises(ValidationError):
            _normalize_unit_cost("-100.00")

    def test_cout_unitaire_nan_interdit(self):
        with self.assertRaises(ValidationError):
            _normalize_unit_cost("NaN")

    def test_cout_unitaire_infini_interdit(self):
        with self.assertRaises(ValidationError):
            _normalize_unit_cost("Infinity")
            


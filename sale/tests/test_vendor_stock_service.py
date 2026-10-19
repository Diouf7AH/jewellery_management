# sale/tests/test_vendor_stock_service.py

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from sale.services.vendor_stock_service import (_available_quantity,
                                                _validate_common,
                                                consume_vendor_stock)


class TestVendorStockService(SimpleTestCase):

    def setUp(self):
        self.bijouterie = SimpleNamespace(id=10)

        self.vendor = SimpleNamespace(
            id=3,
            bijouterie_id=10,
        )

        self.produit_line = SimpleNamespace(
            pk=6,
            id=6,
            produit_id=5,
            lot_id=7,
            uuid="test-pl-6",
        )

        self.stock = SimpleNamespace(
            pk=8,
            quantite_allouee=5,
            quantite_vendue=2,
        )

    def test_disponibilite(self):
        self.assertEqual(
            _available_quantity(self.stock),
            3,
        )

    def test_disponibilite_jamais_negative(self):
        self.stock.quantite_vendue = 8

        self.assertEqual(
            _available_quantity(self.stock),
            0,
        )

    def test_quantite_zero_interdite(self):
        with self.assertRaises(ValidationError):
            _validate_common(
                vendor=self.vendor,
                bijouterie=self.bijouterie,
                produit_line=self.produit_line,
                quantite=0,
            )

    def test_vendeur_autre_bijouterie(self):
        self.vendor.bijouterie_id = 999

        with self.assertRaises(ValidationError):
            _validate_common(
                vendor=self.vendor,
                bijouterie=self.bijouterie,
                produit_line=self.produit_line,
                quantite=1,
            )

    @patch(
        "sale.services.vendor_stock_service.VendorStock.objects"
    )
    @patch(
        "sale.services.vendor_stock_service._get_vendor_stock"
    )
    def test_consommation_reussie(
        self,
        mock_get_stock,
        mock_objects,
    ):
        mock_get_stock.return_value = self.stock

        (
            mock_objects.filter.return_value
            .update.return_value
        ) = 1

        result = consume_vendor_stock(
            vendor=self.vendor,
            bijouterie=self.bijouterie,
            produit_line=self.produit_line,
            quantite=2,
        )

        self.assertEqual(
            result,
            [{"produit_line_id": 6, "qty": 2}],
        )

        mock_get_stock.assert_called_once()
        self.assertTrue(
            mock_get_stock.call_args.kwargs["lock"]
        )

        mock_objects.filter.return_value.update.assert_called_once()

    @patch(
        "sale.services.vendor_stock_service._get_vendor_stock"
    )
    def test_stock_insuffisant(self, mock_get_stock):
        mock_get_stock.return_value = self.stock

        with self.assertRaises(ValidationError):
            consume_vendor_stock(
                vendor=self.vendor,
                bijouterie=self.bijouterie,
                produit_line=self.produit_line,
                quantite=4,
            )

    @patch(
        "sale.services.vendor_stock_service.VendorStock.objects"
    )
    @patch(
        "sale.services.vendor_stock_service._get_vendor_stock"
    )
    def test_conflit_update_atomique(
        self,
        mock_get_stock,
        mock_objects,
    ):
        mock_get_stock.return_value = self.stock

        (
            mock_objects.filter.return_value
            .update.return_value
        ) = 0

        with self.assertRaises(ValidationError):
            consume_vendor_stock(
                vendor=self.vendor,
                bijouterie=self.bijouterie,
                produit_line=self.produit_line,
                quantite=1,
            )


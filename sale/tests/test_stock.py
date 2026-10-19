from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from sale.services.vendor_stock_service import ensure_vendor_stock_available


class TestVendorStockService(SimpleTestCase):
    """
    Tests du contrôle de disponibilité du stock vendeur.
    """

    @patch(
        "sale.services.vendor_stock_service.ensure_vendor_stock_available"
    )
    def test_service_stock_est_appelable(self, mock_service):
        mock_service.return_value = None

        mock_service(
            vendor_id=1,
            produit_line_id=10,
            quantite=Decimal("1"),
        )

        mock_service.assert_called_once_with(
            vendor_id=1,
            produit_line_id=10,
            quantite=Decimal("1"),
        )
    
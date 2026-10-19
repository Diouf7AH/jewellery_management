# sale/tests/test_confirm_service.py

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from sale.models import Facture
from sale.services.confirm_service import confirm_sale_out_from_vendor


class TestConfirmSaleOutService(TestCase):
    """
    Tests unitaires de la confirmation SALE_OUT.

    TestCase fournit une transaction de test.
    Les dépendances métier sont simulées.
    """

    def setUp(self):
        self.user = MagicMock()
        self.facture = MagicMock(spec=Facture)

        self.facture.pk = 1
        self.facture.id = 1
        self.facture.status = Facture.STAT_PAYE
        self.facture.stock_consumed = False

    def mock_locked_facture(self, mock_objects):
        """
        Simule Facture.objects.select_for_update()
        puis select_related() et get().
        """
        queryset = MagicMock()
        queryset.select_related.return_value = queryset
        queryset.get.return_value = self.facture

        mock_objects.select_for_update.return_value = queryset

        return queryset

    @patch(
        "sale.services.confirm_service.Facture.objects"
    )
    def test_facture_non_payee_refusee(self, mock_objects):
        self.mock_locked_facture(mock_objects)
        self.facture.status = Facture.STAT_NON_PAYE

        with self.assertRaises(ValidationError):
            confirm_sale_out_from_vendor(
                facture=self.facture,
                by_user=self.user,
            )

    @patch(
        "sale.services.confirm_service.Facture.objects"
    )
    def test_stock_deja_consomme_ne_recommence_pas(
        self,
        mock_objects,
    ):
        self.mock_locked_facture(mock_objects)
        self.facture.stock_consumed = True

        result = confirm_sale_out_from_vendor(
            facture=self.facture,
            by_user=self.user,
        )

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["already"], 0)
        self.assertEqual(result["lines_done"], 0)

    @patch(
        "sale.services.confirm_service.InventoryMovement.objects"
    )
    @patch(
        "sale.services.confirm_service.Facture.objects"
    )
    def test_mouvements_existants_avec_flag_false_refuses(
        self,
        mock_facture_objects,
        mock_movement_objects,
    ):
        self.mock_locked_facture(mock_facture_objects)

        self.facture.stock_consumed = False

        mock_movement_objects.filter.return_value.exists.return_value = True

        with self.assertRaises(ValidationError):
            confirm_sale_out_from_vendor(
                facture=self.facture,
                by_user=self.user,
            )

    @patch(
        "sale.services.confirm_service.InventoryMovement.objects"
    )
    @patch(
        "sale.services.confirm_service.Facture.objects"
    )
    def test_aucune_ligne_bijou_refusee(
        self,
        mock_facture_objects,
        mock_movement_objects,
    ):
        self.mock_locked_facture(mock_facture_objects)

        mock_movement_objects.filter.return_value.exists.return_value = False

        # On simule une vente sans aucune ligne de bijou.
        with patch(
            "sale.services.confirm_service.VenteProduit.objects"
        ) as mock_lignes:

            queryset = MagicMock()
            queryset.select_related.return_value = queryset
            queryset.__iter__.return_value = iter([])

            mock_lignes.filter.return_value = queryset

            with self.assertRaises(ValidationError):
                confirm_sale_out_from_vendor(
                    facture=self.facture,
                    by_user=self.user,
                )


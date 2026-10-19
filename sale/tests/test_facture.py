# sale/tests/test_facture.py

from decimal import Decimal

from django.test import SimpleTestCase

from sale.models import Facture


class TestCalculFacture(SimpleTestCase):
    """
    Tests unitaires des calculs financiers de Facture.

    Aucun enregistrement en base de données.
    """

    def test_facture_sans_tva_sans_frais(self):
        facture = Facture(
            montant_ht=Decimal("150000.00"),
            appliquer_tva=False,
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        self.assertIsNone(facture.taux_tva)
        self.assertIsNone(facture.montant_tva)
        self.assertEqual(
            facture.montant_total,
            Decimal("150000.00"),
        )

    def test_facture_sans_tva_avec_frais(self):
        facture = Facture(
            montant_ht=Decimal("150000.00"),
            appliquer_tva=False,
            frais_transaction=Decimal("2500.00"),
        )

        facture.recalculer_totaux()

        self.assertEqual(
            facture.montant_total,
            Decimal("152500.00"),
        )

    def test_facture_avec_tva_sans_frais(self):
        facture = Facture(
            montant_ht=Decimal("150000.00"),
            appliquer_tva=True,
            taux_tva=Decimal("18.00"),
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        self.assertEqual(
            facture.montant_tva,
            Decimal("27000.00"),
        )
        self.assertEqual(
            facture.montant_total,
            Decimal("177000.00"),
        )

    def test_facture_avec_tva_et_frais(self):
        facture = Facture(
            montant_ht=Decimal("150000.00"),
            appliquer_tva=True,
            taux_tva=Decimal("18.00"),
            frais_transaction=Decimal("2500.00"),
        )

        facture.recalculer_totaux()

        self.assertEqual(
            facture.montant_tva,
            Decimal("27000.00"),
        )
        self.assertEqual(
            facture.montant_total,
            Decimal("179500.00"),
        )

    def test_tva_desactivee_efface_les_champs_tva(self):
        facture = Facture(
            montant_ht=Decimal("100000.00"),
            appliquer_tva=False,
            taux_tva=Decimal("18.00"),
            montant_tva=Decimal("18000.00"),
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        self.assertIsNone(facture.taux_tva)
        self.assertIsNone(facture.montant_tva)

    def test_tva_activee_sans_taux(self):
        facture = Facture(
            montant_ht=Decimal("100000.00"),
            appliquer_tva=True,
            taux_tva=None,
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        # Le modèle utilise ZERO lorsque taux_tva=None.
        self.assertEqual(
            facture.taux_tva,
            Decimal("0.00"),
        )
        self.assertEqual(
            facture.montant_tva,
            Decimal("0.00"),
        )
        self.assertEqual(
            facture.montant_total,
            Decimal("100000.00"),
        )

    def test_arrondi_tva_half_up(self):
        facture = Facture(
            montant_ht=Decimal("100.03"),
            appliquer_tva=True,
            taux_tva=Decimal("5.00"),
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        # 100.03 × 5 % = 5.0015 -> 5.00
        self.assertEqual(
            facture.montant_tva,
            Decimal("5.00"),
        )
        self.assertEqual(
            facture.montant_total,
            Decimal("105.03"),
        )

    def test_arrondi_tva_exactement_demi_centime(self):
        facture = Facture(
            montant_ht=Decimal("0.05"),
            appliquer_tva=True,
            taux_tva=Decimal("10.00"),
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        # 0.05 × 10 % = 0.005 -> 0.01
        self.assertEqual(
            facture.montant_tva,
            Decimal("0.01"),
        )
        self.assertEqual(
            facture.montant_total,
            Decimal("0.06"),
        )

    def test_montant_zero(self):
        facture = Facture(
            montant_ht=Decimal("0.00"),
            appliquer_tva=False,
            frais_transaction=Decimal("0.00"),
        )

        facture.recalculer_totaux()

        self.assertEqual(
            facture.montant_total,
            Decimal("0.00"),
        )

    def test_type_facture_par_defaut(self):
        facture = Facture()

        self.assertEqual(
            facture.type_facture,
            Facture.TYPE_PROFORMA,
        )

    def test_statut_facture_par_defaut(self):
        facture = Facture()

        self.assertEqual(
            facture.status,
            Facture.STAT_NON_PAYE,
        )

    def test_facture_non_verrouillee_par_defaut(self):
        facture = Facture()

        self.assertFalse(facture.is_locked)

    def test_stock_non_consomme_par_defaut(self):
        facture = Facture()

        self.assertFalse(facture.stock_consumed)
        


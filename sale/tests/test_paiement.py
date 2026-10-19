from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from sale.services.montant_service import calculer_solde_paiement


class TestCalculerSoldePaiement(SimpleTestCase):

    def test_paiement_initial(self):
        solde = calculer_solde_paiement(
            montant_total=Decimal("150000.00"),
            montant_deja_paye=Decimal("0.00"),
        )

        self.assertEqual(
            solde["reste_a_payer"],
            Decimal("150000.00"),
        )
        self.assertFalse(solde["paiement_complet"])

    def test_paiement_partiel(self):
        solde = calculer_solde_paiement(
            montant_total=Decimal("150000.00"),
            montant_deja_paye=Decimal("50000.00"),
        )

        self.assertEqual(
            solde["reste_a_payer"],
            Decimal("100000.00"),
        )
        self.assertFalse(solde["paiement_complet"])

    def test_nouveau_paiement(self):
        solde = calculer_solde_paiement(
            montant_total=Decimal("150000.00"),
            montant_deja_paye=Decimal("50000.00"),
            nouveau_paiement=Decimal("40000.00"),
        )

        self.assertEqual(
            solde["total_paye"],
            Decimal("90000.00"),
        )
        self.assertEqual(
            solde["reste_a_payer"],
            Decimal("60000.00"),
        )

    def test_paiement_complet(self):
        solde = calculer_solde_paiement(
            montant_total=Decimal("150000.00"),
            montant_deja_paye=Decimal("50000.00"),
            nouveau_paiement=Decimal("100000.00"),
        )

        self.assertEqual(
            solde["reste_a_payer"],
            Decimal("0.00"),
        )
        self.assertTrue(solde["paiement_complet"])

    def test_trop_percu_existant_interdit(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("150000.00"),
                montant_deja_paye=Decimal("160000.00"),
            )

    def test_nouveau_paiement_superieur_au_solde(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("150000.00"),
                montant_deja_paye=Decimal("50000.00"),
                nouveau_paiement=Decimal("100001.00"),
            )

    def test_paiement_negatif_interdit(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("150000.00"),
                montant_deja_paye=Decimal("-1000.00"),
            )

    def test_precision_superieure_a_deux_decimales(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("150000.00"),
                montant_deja_paye=Decimal("100.001"),
            )

    def test_montant_nan_interdit(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("NaN"),
                montant_deja_paye=Decimal("0.00"),
            )

    def test_montant_infini_interdit(self):
        with self.assertRaises(ValidationError):
            calculer_solde_paiement(
                montant_total=Decimal("Infinity"),
                montant_deja_paye=Decimal("0.00"),
            )

    def test_paiement_zero_sur_facture_zero(self):
        solde = calculer_solde_paiement(
            montant_total=Decimal("0.00"),
            montant_deja_paye=Decimal("0.00"),
        )

        self.assertEqual(
            solde["reste_a_payer"],
            Decimal("0.00"),
        )
        self.assertTrue(solde["paiement_complet"])
        
        


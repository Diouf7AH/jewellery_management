"""Tests unitaires de la logique de création des ventes Rio-Gold.

Les dépendances ORM sont simulées : ces tests vérifient les règles du
service, mais ne remplacent pas les tests d'intégration en base de données.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from sale.services import sale_service as service


class CreationVenteTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=7)
        self.bijouterie = SimpleNamespace(
            pk=3, appliquer_tva=False, taux_tva=Decimal('0'),
        )
        self.vendor = SimpleNamespace(
            pk=9, verifie=True, bijouterie_id=3,
        )
        self.vente = MagicMock()
        self.vente.montant_total = Decimal('150000.00')
        self.vente.pk = 42
        self.facture = SimpleNamespace(type_facture='proforma')

        self.patches = [
            patch.object(service, 'resolve_vendor_and_bijouterie_for_sale',
                         return_value=(self.vendor, self.bijouterie)),
            patch.object(service.Vente.objects, 'create', return_value=self.vente),
            patch.object(service.VenteProduit.objects, 'create'),
            patch.object(service.VenteAutre.objects, 'create'),
            patch.object(service.Facture.objects, 'create', return_value=self.facture),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for p in reversed(self.patches):
            p.stop()

    def creer(self, produits=None, autres=None):
        return service.create_sale_one_vendor(
            user=self.user,
            role='vendor',
            payload={'produits': produits or [], 'autres': autres or []},
        )

    def prestation(self):
        return {'type_autre': service.VenteAutre.TYPE_CHOICES[0][0],
                'quantite': 1, 'prix_unitaire': '10000.00'}

    def preparer_bijou(self, *, stock=2):
        produit = SimpleNamespace(marque_id=None, purete_id=None)
        achat = SimpleNamespace(bijouterie_id=self.bijouterie.pk)
        ligne = SimpleNamespace(
            pk=15, produit=produit, lot_id=4,
            lot=SimpleNamespace(achat=achat),
            poids_unitaire_achat=Decimal('3.00'),
            pourcentage_occasion=Decimal('0.00'), etat='N',
        )
        stock_obj = SimpleNamespace(quantite_allouee=stock, quantite_vendue=0)
        qs = MagicMock()
        qs.select_related.return_value.filter.return_value = [ligne]
        stock_qs = MagicMock()
        stock_qs.select_for_update.return_value.filter.return_value.order_by.return_value = [stock_obj]
        patches = [
            patch.object(service, 'resolve_produit_line_for_sale', return_value=ligne),
            patch.object(service.ProduitLine, 'objects', qs),
            patch.object(service.VendorStock, 'objects', stock_qs),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return {'produit_line_id': 15, 'quantite': 1,
                'prix_vente_grammes': '50000', 'remise': '0'}

    def test_prestations_seules_sans_facture(self):
        vente, facture, audit = self.creer(autres=[self.prestation()])
        self.assertIs(vente, self.vente)
        self.assertIsNone(facture)
        self.assertEqual(audit, 0)
        self.mocks[3].assert_called_once()
        self.mocks[4].assert_not_called()
        self.mocks[2].assert_not_called()

    def test_bijoux_seuls_creent_proforma(self):
        bijou = self.preparer_bijou()
        vente, facture, _ = self.creer(produits=[bijou])
        self.assertIs(vente, self.vente)
        self.assertIs(facture, self.facture)
        self.mocks[2].assert_called_once()
        self.mocks[4].assert_called_once()
        self.assertEqual(
            self.mocks[4].call_args.kwargs['type_facture'],
            service.Facture.TYPE_PROFORMA,
        )
        self.assertEqual(
            self.mocks[4].call_args.kwargs['status'],
            service.Facture.STAT_NON_PAYE,
        )

    def test_vente_mixte_cree_une_proforma(self):
        bijou = self.preparer_bijou()
        _, facture, _ = self.creer(produits=[bijou], autres=[self.prestation()])
        self.assertIs(facture, self.facture)
        self.mocks[2].assert_called_once()
        self.mocks[3].assert_called_once()
        self.mocks[4].assert_called_once()

    def test_vente_vide_refusee(self):
        with self.assertRaises(ValidationError):
            self.creer()
        self.mocks[1].assert_not_called()

    def test_stock_insuffisant_refuse(self):
        bijou = self.preparer_bijou(stock=0)
        with self.assertRaises(ValidationError):
            self.creer(produits=[bijou])
        self.mocks[1].assert_not_called()
        self.mocks[4].assert_not_called()

    def test_quantite_invalide_refusee(self):
        bijou = self.preparer_bijou()
        bijou['quantite'] = 0
        with self.assertRaises(ValidationError):
            self.creer(produits=[bijou])
        self.mocks[1].assert_not_called()

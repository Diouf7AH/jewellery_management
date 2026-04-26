from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from compte_depot.models import CompteDepot, CompteDepotTransaction
from sale.models import Client, Facture, ModePaiement
from store.models import Bijouterie, Categorie, Marque, Modele, Produit, Purete
from vendor.models import Vendor

from .models import (CommandeClient, CommandeClientHistorique,
                     CommandeProduitClient, Ouvrier)
from .services.commande_finance_service import (
    create_facture_acompte_for_commande, register_facture_payment)
from .services.commande_history_service import add_commande_history

ZERO = Decimal("0.00")


def dec(v) -> Decimal:
    if v in (None, "", "null"):
        return ZERO
    try:
        return Decimal(str(v))
    except Exception:
        raise serializers.ValidationError(f"Valeur décimale invalide : {v}")


class OuvrierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ouvrier
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "specialite",
            "actif",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CommandeProduitClientSerializer(serializers.ModelSerializer):
    produit_id = serializers.PrimaryKeyRelatedField(
        source="produit",
        queryset=Produit.objects.all(),
        required=False,
        allow_null=True,
    )
    categorie_id = serializers.PrimaryKeyRelatedField(
        source="categorie",
        queryset=Categorie.objects.all(),
        required=False,
        allow_null=True,
    )
    marque_id = serializers.PrimaryKeyRelatedField(
        source="marque",
        queryset=Marque.objects.all(),
        required=False,
        allow_null=True,
    )
    modele_id = serializers.PrimaryKeyRelatedField(
        source="modele",
        queryset=Modele.objects.all(),
        required=False,
        allow_null=True,
    )
    purete_id = serializers.PrimaryKeyRelatedField(
        source="purete",
        queryset=Purete.objects.all(),
        required=False,
        allow_null=True,
    )

    produit_nom = serializers.CharField(source="produit.nom", read_only=True)
    categorie_nom = serializers.CharField(source="categorie.nom", read_only=True)
    marque_nom = serializers.CharField(source="marque.nom", read_only=True)
    modele_nom = serializers.CharField(source="modele.nom", read_only=True)
    purete_nom = serializers.CharField(source="purete.nom", read_only=True)

    class Meta:
        model = CommandeProduitClient
        fields = [
            "id",
            "produit_id",
            "produit_nom",
            "nom_modele",
            "categorie_id",
            "categorie_nom",
            "marque_id",
            "marque_nom",
            "modele_id",
            "modele_nom",
            "purete_id",
            "purete_nom",
            "quantite",
            "poids",
            "taille",
            "prix_gramme",
            "sous_total",
            "photo",
            "description",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "produit_nom",
            "categorie_nom",
            "marque_nom",
            "modele_nom",
            "purete_nom",
            "sous_total",
            "created_at",
        ]

    def validate(self, attrs):
        if dec(attrs.get("poids")) <= ZERO:
            raise serializers.ValidationError({"poids": "Le poids doit être > 0."})

        if attrs.get("quantite", 1) < 1:
            raise serializers.ValidationError({"quantite": "La quantité doit être >= 1."})

        if dec(attrs.get("prix_gramme")) < ZERO:
            raise serializers.ValidationError({"prix_gramme": "Le prix gramme ne peut pas être négatif."})

        return attrs


class CommandeClientHistoriqueSerializer(serializers.ModelSerializer):
    changed_by_username = serializers.CharField(source="changed_by.username", read_only=True)

    class Meta:
        model = CommandeClientHistorique
        fields = [
            "id",
            "ancien_statut",
            "nouveau_statut",
            "commentaire",
            "changed_by",
            "changed_by_username",
            "changed_at",
        ]
        read_only_fields = fields


class FactureMiniSerializer(serializers.ModelSerializer):
    total_paye = serializers.SerializerMethodField()
    reste_a_payer = serializers.SerializerMethodField()

    class Meta:
        model = Facture
        fields = [
            "id",
            "numero_facture",
            "type_facture",
            "montant_total",
            "status",
            "total_paye",
            "reste_a_payer",
            "date_creation",
        ]
        read_only_fields = fields

    def get_total_paye(self, obj):
        return obj.total_paye

    def get_reste_a_payer(self, obj):
        return obj.reste_a_payer


class CommandeClientDetailSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source="client.full_name", read_only=True)
    client_telephone = serializers.CharField(source="client.telephone", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)
    vendor_username = serializers.CharField(source="vendor.user.username", read_only=True)

    ouvrier_detail = OuvrierSerializer(source="ouvrier", read_only=True)
    lignes = CommandeProduitClientSerializer(many=True, read_only=True)
    historiques = CommandeClientHistoriqueSerializer(many=True, read_only=True)
    factures = FactureMiniSerializer(many=True, read_only=True)

    acompte_minimum_requis = serializers.SerializerMethodField()
    total_acompte_paye = serializers.SerializerMethodField()
    total_paye_global = serializers.SerializerMethodField()
    reste_global = serializers.SerializerMethodField()
    acompte_regle = serializers.SerializerMethodField()
    peut_passer_en_production = serializers.SerializerMethodField()
    peut_etre_livree = serializers.SerializerMethodField()

    class Meta:
        model = CommandeClient
        fields = [
            "id",
            "numero_commande",
            "client",
            "client_nom",
            "client_telephone",
            "bijouterie",
            "bijouterie_nom",
            "vendor",
            "vendor_username",
            "ouvrier",
            "ouvrier_detail",
            "statut",
            "date_commande",
            "date_debut",
            "date_fin_prevue",
            "date_fin_reelle",
            "date_livraison",
            "date_affectation_ouvrier",
            "date_depot_boutique",
            "montant_total",
            "acompte_minimum_requis",
            "total_acompte_paye",
            "total_paye_global",
            "reste_global",
            "acompte_regle",
            "peut_passer_en_production",
            "peut_etre_livree",
            "notes_client",
            "notes_internes",
            "lignes",
            "factures",
            "historiques",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_acompte_minimum_requis(self, obj):
        return obj.acompte_minimum_requis

    def get_total_acompte_paye(self, obj):
        return obj.total_acompte_paye

    def get_total_paye_global(self, obj):
        return obj.total_paye_global

    def get_reste_global(self, obj):
        return obj.reste_global

    def get_acompte_regle(self, obj):
        return obj.acompte_regle

    def get_peut_passer_en_production(self, obj):
        return obj.peut_passer_en_production

    def get_peut_etre_livree(self, obj):
        return obj.peut_etre_livree


class PaiementLigneInSerializer(serializers.Serializer):
    mode_paiement_id = serializers.PrimaryKeyRelatedField(
        source="mode_paiement",
        queryset=ModePaiement.objects.filter(actif=True),
    )
    montant_paye = serializers.DecimalField(max_digits=10, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    compte_depot_id = serializers.PrimaryKeyRelatedField(
        source="compte_depot",
        queryset=CompteDepot.objects.all(),
        required=False,
        allow_null=True,
    )
    transaction_depot_id = serializers.PrimaryKeyRelatedField(
        source="transaction_depot",
        queryset=CompteDepotTransaction.objects.all(),
        required=False,
        allow_null=True,
    )


class CreateCommandeClientSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=False)
    client_nom = serializers.CharField(required=False, allow_blank=True)
    client_prenom = serializers.CharField(required=False, allow_blank=True)
    client_telephone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    bijouterie_id = serializers.PrimaryKeyRelatedField(
        source="bijouterie",
        queryset=Bijouterie.objects.all(),
    )
    vendor_id = serializers.PrimaryKeyRelatedField(
        source="vendor",
        queryset=Vendor.objects.filter(verifie=True),
    )

    date_debut = serializers.DateField(required=False, allow_null=True)
    date_fin_prevue = serializers.DateField(required=False, allow_null=True)
    notes_client = serializers.CharField(required=False, allow_blank=True)
    notes_internes = serializers.CharField(required=False, allow_blank=True)

    lignes = CommandeProduitClientSerializer(many=True)
    lignes_paiement_acompte = PaiementLigneInSerializer(many=True)

    def validate(self, attrs):
        lignes = attrs.get("lignes") or []
        if not lignes:
            raise serializers.ValidationError({"lignes": "Au moins une ligne est obligatoire."})

        lignes_paiement = attrs.get("lignes_paiement_acompte") or []
        if not lignes_paiement:
            raise serializers.ValidationError({
                "lignes_paiement_acompte": "Au moins une ligne de paiement est obligatoire."
            })

        vendor = attrs["vendor"]
        bijouterie = attrs["bijouterie"]
        if vendor.bijouterie_id and vendor.bijouterie_id != bijouterie.id:
            raise serializers.ValidationError({
                "vendor_id": "Ce vendeur n'appartient pas à cette bijouterie."
            })

        client_id = attrs.get("client_id")
        client_nom = (attrs.get("client_nom") or "").strip()
        client_prenom = (attrs.get("client_prenom") or "").strip()

        if not client_id and (not client_nom or not client_prenom):
            raise serializers.ValidationError({
                "client": "client_id ou bien client_nom + client_prenom sont obligatoires."
            })

        date_debut = attrs.get("date_debut")
        date_fin_prevue = attrs.get("date_fin_prevue")
        if date_debut and date_fin_prevue and date_fin_prevue < date_debut:
            raise serializers.ValidationError({
                "date_fin_prevue": "La date de fin prévue ne peut pas être antérieure à la date de début."
            })

        return attrs

    def _resolve_client(self, validated_data):
        client_id = validated_data.get("client_id")
        client_nom = (validated_data.get("client_nom") or "").strip()
        client_prenom = (validated_data.get("client_prenom") or "").strip()
        client_telephone = (validated_data.get("client_telephone") or "").strip() or None

        if client_id:
            try:
                return Client.objects.get(pk=client_id)
            except Client.DoesNotExist:
                raise serializers.ValidationError({"client_id": "Client introuvable."})

        if client_telephone:
            existing = Client.objects.filter(telephone=client_telephone).first()
            if existing:
                changed = False
                if existing.nom != client_nom:
                    existing.nom = client_nom
                    changed = True
                if existing.prenom != client_prenom:
                    existing.prenom = client_prenom
                    changed = True
                if changed:
                    existing.save()
                return existing

        existing = Client.objects.filter(
            nom__iexact=client_nom,
            prenom__iexact=client_prenom,
        ).first()
        if existing:
            return existing

        return Client.objects.create(
            nom=client_nom,
            prenom=client_prenom,
            telephone=client_telephone,
        )

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        lignes_data = validated_data.pop("lignes", [])
        lignes_paiement = validated_data.pop("lignes_paiement_acompte", [])
        client = self._resolve_client(validated_data)

        # ✅ Création commande
        commande = CommandeClient.objects.create(
            client=client,
            bijouterie=validated_data["bijouterie"],
            vendor=validated_data["vendor"],
            date_debut=validated_data.get("date_debut"),
            date_fin_prevue=validated_data.get("date_fin_prevue"),
            notes_client=validated_data.get("notes_client", ""),
            notes_internes=validated_data.get("notes_internes", ""),
            statut=CommandeClient.STATUT_EN_ATTENTE,
            created_by=user,
            updated_by=user,
        )

        # ✅ Lignes
        for ligne_data in lignes_data:
            CommandeProduitClient.objects.create(
                commande=commande,
                **ligne_data,
            )

        commande.recalculate_total(save=True)

        # 💰 TOTAL PAYÉ
        montant_total_paiement = sum(
            dec(l["montant_paye"]) for l in lignes_paiement
        )

        # ❌ < 50%
        if montant_total_paiement < commande.acompte_minimum_requis:
            raise serializers.ValidationError({
                "acompte": (
                    f"Acompte minimum requis : {commande.acompte_minimum_requis} FCFA"
                )
            })

        # ❌ > 100%
        if montant_total_paiement > commande.montant_total:
            raise serializers.ValidationError({
                "acompte": (
                    f"Le montant payé ({montant_total_paiement}) dépasse le total ({commande.montant_total})"
                )
            })

        # ✅ UNE SEULE FACTURE
        facture_acompte = create_facture_acompte_for_commande(
            commande=commande,
            montant=montant_total_paiement,
        )

        # ✅ PAIEMENT
        register_facture_payment(
            facture=facture_acompte,
            created_by=user,
            lignes=lignes_paiement,
        )

        facture_acompte.refresh_from_db()

        # 🧾 HISTORIQUE
        add_commande_history(
            commande=commande,
            ancien_statut="",
            nouveau_statut=commande.statut,
            commentaire="Commande créée avec acompte",
            user=user,
        )

        return commande


class AssignerOuvrierSerializer(serializers.Serializer):
    ouvrier_id = serializers.PrimaryKeyRelatedField(
        source="ouvrier",
        queryset=Ouvrier.objects.filter(actif=True),
    )
    commentaire = serializers.CharField(required=False, allow_blank=True)


class TerminerCommandeSerializer(serializers.Serializer):
    date_depot_boutique = serializers.DateTimeField(required=False)
    date_fin_reelle = serializers.DateField(required=False)
    commentaire = serializers.CharField(required=False, allow_blank=True)


class PayerSoldeCommandeSerializer(serializers.Serializer):
    lignes_paiement = PaiementLigneInSerializer(many=True)

    def validate(self, attrs):
        if not attrs.get("lignes_paiement"):
            raise serializers.ValidationError({
                "lignes_paiement": "Au moins une ligne de paiement est obligatoire."
            })
        return attrs
    
    
class CommandeDashboardRecentSerializer(serializers.ModelSerializer):
    client_nom = serializers.CharField(source="client.full_name", read_only=True)
    client_telephone = serializers.CharField(source="client.telephone", read_only=True)
    bijouterie_nom = serializers.CharField(source="bijouterie.nom", read_only=True)
    vendor_username = serializers.CharField(source="vendor.user.username", read_only=True)
    ouvrier_nom = serializers.SerializerMethodField()

    acompte_minimum_requis = serializers.SerializerMethodField()
    total_acompte_paye = serializers.SerializerMethodField()
    total_paye_global = serializers.SerializerMethodField()
    reste_global = serializers.SerializerMethodField()

    class Meta:
        model = CommandeClient
        fields = [
            "id",
            "numero_commande",
            "client_nom",
            "client_telephone",
            "bijouterie_nom",
            "vendor_username",
            "ouvrier_nom",
            "statut",
            "date_commande",
            "date_fin_prevue",
            "date_fin_reelle",
            "date_livraison",
            "montant_total",
            "acompte_minimum_requis",
            "total_acompte_paye",
            "total_paye_global",
            "reste_global",
        ]
        read_only_fields = fields

    def get_ouvrier_nom(self, obj):
        if not obj.ouvrier:
            return None
        return f"{obj.ouvrier.prenom} {obj.ouvrier.nom}".strip()

    def get_acompte_minimum_requis(self, obj):
        return obj.acompte_minimum_requis

    def get_total_acompte_paye(self, obj):
        return obj.total_acompte_paye

    def get_total_paye_global(self, obj):
        return obj.total_paye_global

    def get_reste_global(self, obj):
        return obj.reste_global


class OuvrierDashboardSerializer(serializers.ModelSerializer):
    ouvrier_nom = serializers.SerializerMethodField()
    nb_commandes_total = serializers.IntegerField(read_only=True)
    nb_en_production = serializers.IntegerField(read_only=True)
    nb_terminees = serializers.IntegerField(read_only=True)
    nb_livrees = serializers.IntegerField(read_only=True)

    class Meta:
        model = Ouvrier
        fields = [
            "id",
            "ouvrier_nom",
            "telephone",
            "specialite",
            "nb_commandes_total",
            "nb_en_production",
            "nb_terminees",
            "nb_livrees",
        ]
        read_only_fields = fields

    def get_ouvrier_nom(self, obj):
        return f"{obj.prenom} {obj.nom}".strip()


class CommandeDashboardSerializer(serializers.Serializer):
    periode = serializers.DictField(read_only=True)
    kpis = serializers.DictField(read_only=True)
    statuts = serializers.DictField(read_only=True)

    ouvriers = OuvrierDashboardSerializer(many=True, read_only=True)
    recentes = CommandeDashboardRecentSerializer(many=True, read_only=True)
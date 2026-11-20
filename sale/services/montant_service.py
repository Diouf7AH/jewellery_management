# sale/services/montant_service.py

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError

# ============================================================
# 1. CONSTANTES
# ============================================================

ZERO = Decimal("0.00")
CENTIME = Decimal("0.01")
CENT = Decimal("100")

POURCENTAGES_OCCASION = frozenset({
    Decimal("5"),
    Decimal("10"),
    Decimal("15"),
    Decimal("20"),
    Decimal("25"),
    Decimal("30"),
})


# ============================================================
# 2. CONVERSION DÉCIMALE
# ============================================================

def dec(
    value,
    *,
    field: str = "montant",
    default: Decimal = ZERO,
) -> Decimal:
    """
    Convertit une valeur en Decimal.

    None ou chaîne vide :
        retourne default.

    Refuse :
        - booléens ;
        - valeurs non numériques ;
        - NaN ;
        - Infinity.

    Ne réalise aucun arrondi.
    """

    if value is None:
        return default

    if isinstance(value, str) and not value.strip():
        return default

    if isinstance(value, bool):
        raise ValidationError({
            field: "Valeur décimale invalide."
        })

    try:
        result = Decimal(str(value))

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ) as exc:
        raise ValidationError({
            field: "Valeur décimale invalide."
        }) from exc

    if not result.is_finite():
        raise ValidationError({
            field: "La valeur doit être un nombre fini."
        })

    return result


# ============================================================
# 3. ARRONDI MONÉTAIRE
# ============================================================

def money(
    value,
    *,
    field: str = "montant",
) -> Decimal:
    """
    Arrondit un montant à deux décimales.

    Utilise ROUND_HALF_UP.

    Exemple :
        money("1250.456")
        -> Decimal("1250.46")
    """

    montant = dec(
        value,
        field=field,
    )

    try:
        return montant.quantize(
            CENTIME,
            rounding=ROUND_HALF_UP,
        )

    except InvalidOperation as exc:
        raise ValidationError({
            field: "Montant hors limites."
        }) from exc


# ============================================================
# 4. VALIDATION D'UNE QUANTITÉ
# ============================================================

def positive_int(
    value,
    *,
    field: str = "quantite",
) -> int:
    """
    Accepte :
        - entier Python positif ;
        - chaîne contenant un entier positif.

    Refuse :
        - booléens ;
        - flottants ;
        - fractions ;
        - zéro ;
        - nombres négatifs.
    """

    if isinstance(value, bool):
        raise ValidationError({
            field: "Un entier strictement positif est attendu."
        })

    if isinstance(value, int):
        quantite = value

    elif (
        isinstance(value, str)
        and value.strip().isascii()
        and value.strip().isdecimal()
    ):
        quantite = int(value.strip())

    else:
        raise ValidationError({
            field: "Un entier strictement positif est attendu."
        })

    if quantite <= 0:
        raise ValidationError({
            field: "La quantité doit être supérieure à zéro."
        })

    return quantite


# ============================================================
# 5. CALCUL DES MONTANTS
# ============================================================

def calculer_montants(
    *,
    montant_brut_ht,
    montant_reduction=ZERO,
    taux_tva=ZERO,
) -> dict:
    """
    Calcule les montants d'une opération.

    montant_brut_ht :
        montant avant réduction.

    montant_reduction :
        réduction fixe en valeur monétaire.

    taux_tva :
        pourcentage de TVA.

    Retourne :
        montant_brut_ht
        montant_reduction
        montant_ht
        montant_tva
        montant_total

    Tous les montants sont arrondis
    à deux décimales.
    """

    brut = money(
        montant_brut_ht,
        field="montant_brut_ht",
    )

    reduction = money(
        montant_reduction,
        field="montant_reduction",
    )

    taux = dec(
        taux_tva,
        field="taux_tva",
    )

    # --------------------------------------------------------
    # Validation du montant brut
    # --------------------------------------------------------

    if brut < ZERO:
        raise ValidationError({
            "montant_brut_ht": (
                "Le montant brut ne peut pas être négatif."
            )
        })

    # --------------------------------------------------------
    # Validation de la réduction
    # --------------------------------------------------------

    if reduction < ZERO:
        raise ValidationError({
            "montant_reduction": (
                "La réduction ne peut pas être négative."
            )
        })

    if reduction > brut:
        raise ValidationError({
            "montant_reduction": (
                "La réduction ne peut pas dépasser "
                "le montant brut."
            )
        })

    # --------------------------------------------------------
    # Validation de la TVA
    # --------------------------------------------------------

    if not ZERO <= taux <= Decimal("100"):
        raise ValidationError({
            "taux_tva": (
                "Le taux de TVA doit être compris "
                "entre 0 et 100."
            )
        })

    # --------------------------------------------------------
    # Montant HT après réduction
    # --------------------------------------------------------

    montant_ht = money(
        brut - reduction
    )

    # --------------------------------------------------------
    # TVA
    # --------------------------------------------------------

    montant_tva = money(
        montant_ht * taux / CENT
    )

    # --------------------------------------------------------
    # Total TTC
    # --------------------------------------------------------

    montant_total = money(
        montant_ht + montant_tva
    )

    return {
        "montant_brut_ht": brut,
        "montant_reduction": reduction,
        "montant_ht": montant_ht,
        "montant_tva": montant_tva,
        "montant_total": montant_total,
    }


# ============================================================
# 6. CALCUL D'UNE RÉDUCTION EN POURCENTAGE
# ============================================================

def calculer_reduction_pourcentage(
    *,
    montant_brut,
    pourcentage,
) -> Decimal:
    """
    Calcule une réduction à partir
    d'un pourcentage.

    Exemple :
        montant_brut = 100000
        pourcentage = 10

        réduction = 10000
    """

    brut = money(
        montant_brut,
        field="montant_brut",
    )

    taux = dec(
        pourcentage,
        field="pourcentage",
    )

    if brut < ZERO:
        raise ValidationError({
            "montant_brut": (
                "Le montant brut ne peut pas être négatif."
            )
        })

    if not ZERO <= taux <= CENT:
        raise ValidationError({
            "pourcentage": (
                "Le pourcentage doit être compris "
                "entre 0 et 100."
            )
        })

    return money(
        brut * taux / CENT
    )


# ============================================================
# 7. CALCUL DU PRIX D'UN BIJOU
# ============================================================

def calculer_montant_bijou(
    *,
    prix_vente_grammes,
    poids_unitaire,
    quantite,
    etat,
    pourcentage_occasion=ZERO,
    remise=ZERO,
) -> dict:
    """
    Calcule le montant d'une ligne de bijou.

    BIJOU NEUF :
        réduction fixe autorisée ;
        pourcentage occasion = 0.

    BIJOU D'OCCASION :
        réduction selon pourcentage ;
        remise fixe interdite.

    La TVA n'est pas appliquée ici.
    Elle est gérée au niveau de la facture.
    """

    prix = dec(
        prix_vente_grammes,
        field="prix_vente_grammes",
    )

    poids = dec(
        poids_unitaire,
        field="poids_unitaire",
    )

    q = positive_int(
        quantite,
        field="quantite",
    )

    pourcentage = dec(
        pourcentage_occasion,
        field="pourcentage_occasion",
    )

    remise_fixe = money(
        remise,
        field="remise",
    )

    if prix <= ZERO:
        raise ValidationError({
            "prix_vente_grammes": (
                "Le prix au gramme doit être "
                "supérieur à zéro."
            )
        })

    if poids <= ZERO:
        raise ValidationError({
            "poids_unitaire": (
                "Le poids doit être supérieur à zéro."
            )
        })

    if remise_fixe < ZERO:
        raise ValidationError({
            "remise": (
                "La remise ne peut pas être négative."
            )
        })

    montant_brut = money(
        prix * poids * q
    )

    # --------------------------------------------------------
    # Bijou d'occasion
    # --------------------------------------------------------

    if etat == "O":

        if pourcentage not in POURCENTAGES_OCCASION:
            raise ValidationError({
                "pourcentage_occasion": (
                    "Pourcentage autorisé : "
                    "5, 10, 15, 20, 25 ou 30 %."
                )
            })

        if remise_fixe != ZERO:
            raise ValidationError({
                "remise": (
                    "Une remise fixe est interdite "
                    "pour un bijou d'occasion."
                )
            })

        reduction = calculer_reduction_pourcentage(
            montant_brut=montant_brut,
            pourcentage=pourcentage,
        )

    # --------------------------------------------------------
    # Bijou neuf
    # --------------------------------------------------------

    elif etat == "N":

        if pourcentage != ZERO:
            raise ValidationError({
                "pourcentage_occasion": (
                    "Un bijou neuf doit avoir "
                    "un pourcentage occasion égal à zéro."
                )
            })

        reduction = remise_fixe

    else:
        raise ValidationError({
            "etat": (
                "État invalide. Utilisez N ou O."
            )
        })

    return calculer_montants(
        montant_brut_ht=montant_brut,
        montant_reduction=reduction,
        taux_tva=ZERO,
    )


# ============================================================
# 8. CALCUL D'UNE PRESTATION
# ============================================================

def calculer_montant_prestation(
    *,
    prix_unitaire,
    quantite,
) -> Decimal:
    """
    Calcule le montant total d'une prestation.

    Aucun calcul de facture n'est effectué ici.
    """

    prix = dec(
        prix_unitaire,
        field="prix_unitaire",
    )

    q = positive_int(
        quantite,
        field="quantite",
    )

    if prix < ZERO:
        raise ValidationError({
            "prix_unitaire": (
                "Le prix unitaire ne peut pas "
                "être négatif."
            )
        })

    return money(
        prix * q
    )


# ============================================================
# 9. CALCUL DU TOTAL D'UNE VENTE
# ============================================================

def calculer_total_vente(
    *,
    montants_bijoux=None,
    montants_prestations=None,
) -> Decimal:
    """
    Calcule le total d'une vente.

    Accepte deux listes de montants.

    Ne modifie aucune donnée.
    """

    montants_bijoux = (
        montants_bijoux
        if montants_bijoux is not None
        else []
    )

    montants_prestations = (
        montants_prestations
        if montants_prestations is not None
        else []
    )

    total = ZERO

    for montant in montants_bijoux:
        total += money(montant)

    for montant in montants_prestations:
        total += money(montant)

    return money(total)


# ============================================================
# 10. CALCUL DE TVA SUR UNE FACTURE
# ============================================================

def calculer_tva_facture(
    *,
    montant_ht,
    appliquer_tva=False,
    taux_tva=ZERO,
) -> dict:
    """
    Calcule la TVA et le montant TTC
    d'une facture.

    Si appliquer_tva=False :
        TVA = 0.
    """

    ht = money(
        montant_ht,
        field="montant_ht",
    )

    if ht < ZERO:
        raise ValidationError({
            "montant_ht": (
                "Le montant HT ne peut pas être négatif."
            )
        })

    if not isinstance(appliquer_tva, bool):
        raise ValidationError({
            "appliquer_tva": (
                "Une valeur booléenne est attendue."
            )
        })

    taux = (
        dec(
            taux_tva,
            field="taux_tva",
        )
        if appliquer_tva
        else ZERO
    )

    if not ZERO <= taux <= CENT:
        raise ValidationError({
            "taux_tva": (
                "Le taux de TVA doit être compris "
                "entre 0 et 100."
            )
        })

    tva = money(
        ht * taux / CENT
    )

    return {
        "montant_ht": ht,
        "montant_tva": tva,
        "montant_total": money(ht + tva),
        "taux_tva": taux,
    }
    
    

# ============================================================
# 11. CALCUL DU SOLDE D'UN PAIEMENT
# ============================================================

def calculer_solde_paiement(
    montant_total,
    total_paye,
) -> Decimal:
    """
    Calcule le solde restant à payer.

    Règles :
    - Montant total >= 0.
    - Total payé >= 0.
    - Le total payé ne peut pas dépasser le montant dû.
    - Le solde ne peut pas être négatif.
    - Aucun enregistrement en base.

    Retour :
        Decimal à deux décimales.
    """

    montant = money(
        montant_total,
        field="montant_total",
    )

    paye = money(
        total_paye,
        field="total_paye",
    )

    if montant < ZERO:
        raise ValidationError({
            "montant_total": (
                "Le montant total ne peut pas être négatif."
            )
        })

    if paye < ZERO:
        raise ValidationError({
            "total_paye": (
                "Le total payé ne peut pas être négatif."
            )
        })

    if paye > montant:
        raise ValidationError({
            "total_paye": (
                "Le total payé ne peut pas dépasser "
                "le montant total."
            )
        })

    return money(
        montant - paye,
        field="reste_a_payer",
    )


# ============================================================
# 12. CONVERSION DÉCIMALE — COMPATIBILITÉ
# ============================================================

def decimal_value(
    value,
    *,
    field: str = "montant",
    default: Decimal = ZERO,
) -> Decimal:
    """
    Convertit une valeur en Decimal.

    Réutilise la fonction dec() existante.

    - None ou chaîne vide : retourne default.
    - Refuse les booléens.
    - Refuse NaN et Infinity.
    - Ne réalise aucun arrondi.
    """

    return dec(
        value,
        field=field,
        default=default,
    )


# ============================================================
# 13. VALIDATION STRICTE DES MONTANTS
# ============================================================

def money_strict(
    value,
    *,
    field: str = "montant",
) -> Decimal:
    """
    Valide un montant monétaire sans arrondi implicite.

    Règles :
    - Refuse None et les chaînes vides.
    - Refuse les booléens.
    - Refuse NaN et Infinity.
    - Refuse les montants négatifs.
    - Accepte au maximum deux décimales significatives.
    - Retourne un Decimal normalisé à deux décimales.

    Exemples :
        money_strict("10000")    -> Decimal("10000.00")
        money_strict("1500.50")  -> Decimal("1500.50")
        money_strict("12.345")   -> ValidationError
    """

    if value is None:
        raise ValidationError({
            field: "Le montant est obligatoire."
        })

    if isinstance(value, str) and not value.strip():
        raise ValidationError({
            field: "Le montant est obligatoire."
        })

    montant = dec(
        value,
        field=field,
    )

    if montant < ZERO:
        raise ValidationError({
            field: "Le montant ne peut pas être négatif."
        })

    try:
        montant_normalise = montant.quantize(CENTIME)

    except InvalidOperation as exc:
        raise ValidationError({
            field: "Montant hors limites."
        }) from exc

    if montant != montant_normalise:
        raise ValidationError({
            field: (
                "Le montant ne peut pas dépasser "
                "deux décimales."
            )
        })

    return montant_normalise



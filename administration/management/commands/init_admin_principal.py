# administration/management/commands/init_admin_principal.py

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, OperationalError, transaction

from administration.models import AdminProfile
from backend.roles import ROLE_ADMIN

# ============================================================
# INITIALISATION DE L'ADMINISTRATEUR PRINCIPAL — RIO-GOLD
# ============================================================
#
# OBJECTIF :
# Créer le premier administrateur principal de Rio-Gold.
#
# CONDITIONS :
# - L'utilisateur existe dans MySQL.
# - Son compte est actif.
# - Son email est vérifié.
# - Il n'est pas superuser Django.
# - Il ne possède aucun profil staff.
# - Il ne possède aucun profil administrateur.
# - Aucun administrateur principal n'existe déjà.
#
# EXÉCUTION :
#
# python manage.py init_admin_principal --email=admin@riogold.sn
#
# Remplacer l'email par celui de l'utilisateur réel.
#
# IMPORTANT :
# - Commande réservée à l'administration du serveur.
# - Ne jamais exposer cette commande via une API.
# - Utiliser MySQL avec le moteur InnoDB.
# - Le modèle AdminProfile doit garantir l'unicité
#   du principal au niveau de la base de données.
#
# ============================================================


class Command(BaseCommand):

    help = (
        "Initialiser le premier administrateur principal "
        "de Rio-Gold."
    )

    def add_arguments(self, parser):

        parser.add_argument(
            "--email",
            type=str,
            required=True,
            help="Email du compte utilisateur existant.",
        )

    # ========================================================
    # VÉRIFICATION DES PROFILS STAFF
    # ========================================================

    def ensure_no_staff_profile(self, user):
        """
        Refuse la promotion si l'utilisateur possède
        un profil staff autre qu'AdminProfile.

        Recherche les relations OneToOne inverses
        déclarées dans les modèles Django.
        """

        staff_models = {
            "manager.Manager",
            "vendor.Vendor",
            "cashier.Cashier",
            "buyer.Buyer",
        }

        for relation in user._meta.related_objects:

            if not relation.one_to_one:
                continue

            related_model = relation.related_model

            model_label = related_model._meta.label

            if model_label not in staff_models:
                continue

            accessor = relation.get_accessor_name()

            if hasattr(user, accessor):
                raise CommandError(
                    "Cet utilisateur possède déjà "
                    f"un profil staff : {model_label}."
                )

    # ========================================================
    # INITIALISATION
    # ========================================================

    def handle(self, *args, **options):

        email = (options["email"] or "").strip().lower()

        if not email:
            raise CommandError(
                "L'adresse email est obligatoire."
            )

        User = get_user_model()

        try:

            with transaction.atomic():

                # ------------------------------------------------
                # 1. Vérifier l'existence du principal
                # ------------------------------------------------

                if AdminProfile.objects.filter(
                    niveau=AdminProfile.Niveau.PRINCIPAL
                ).exists():

                    raise CommandError(
                        "Un administrateur principal existe déjà. "
                        "Initialisation refusée."
                    )

                # ------------------------------------------------
                # 2. Rechercher et verrouiller l'utilisateur
                # ------------------------------------------------

                try:

                    user = (
                        User.objects
                        .select_for_update()
                        .get(email__iexact=email)
                    )

                except User.DoesNotExist:

                    raise CommandError(
                        "Aucun utilisateur trouvé "
                        "avec cette adresse email."
                    )

                except User.MultipleObjectsReturned:

                    raise CommandError(
                        "Plusieurs utilisateurs possèdent "
                        "cette adresse email."
                    )

                # ------------------------------------------------
                # 3. Vérifier le compte
                # ------------------------------------------------

                if not user.is_active:

                    raise CommandError(
                        "Le compte utilisateur est désactivé."
                    )

                if not user.is_email_verified:

                    raise CommandError(
                        "L'adresse email n'est pas vérifiée."
                    )

                if user.is_superuser:

                    raise CommandError(
                        "Ce compte est déjà superuser Django. "
                        "Utilise un compte applicatif distinct."
                    )

                # ------------------------------------------------
                # 4. Vérifier les profils existants
                # ------------------------------------------------

                if AdminProfile.objects.filter(
                    user=user
                ).exists():

                    raise CommandError(
                        "Cet utilisateur possède déjà "
                        "un profil administrateur."
                    )

                self.ensure_no_staff_profile(user)

                # ------------------------------------------------
                # 5. Attribuer le rôle applicatif admin
                # ------------------------------------------------

                user.user_role = ROLE_ADMIN
                user.is_staff = False
                user.is_superuser = False

                user.save(
                    update_fields=[
                        "user_role",
                        "is_staff",
                        "is_superuser",
                    ]
                )

                # ------------------------------------------------
                # 6. Créer le profil principal
                # ------------------------------------------------

                profile = AdminProfile(
                    user=user,
                    niveau=AdminProfile.Niveau.PRINCIPAL,
                    verifie=True,
                    peut_gerer_bijouteries=True,
                    peut_voir_finances=True,
                    created_by=None,
                )

                profile.full_clean()
                profile.save()

        # ====================================================
        # GESTION DES ERREURS
        # ====================================================

        except CommandError:
            raise

        except ValidationError as exc:

            raise CommandError(
                f"Erreur de validation : {exc}"
            ) from exc

        except IntegrityError as exc:

            raise CommandError(
                "Impossible de créer l'administrateur principal. "
                "Une contrainte d'unicité MySQL a été violée. "
                "Vérifie si un principal existe déjà."
            ) from exc

        except OperationalError as exc:

            raise CommandError(
                "Erreur MySQL pendant l'initialisation. "
                "Vérifie la connexion à la base de données, "
                "les transactions et les éventuels verrouillages."
            ) from exc

        # ====================================================
        # SUCCÈS
        # ====================================================

        self.stdout.write(
            self.style.SUCCESS(
                "Administrateur principal créé avec succès."
            )
        )

        self.stdout.write(
            f"Email : {user.email}"
        )

        self.stdout.write(
            f"Niveau : {profile.niveau}"
        )

        self.stdout.write(
            f"Profil ID : {profile.pk}"
        )

        self.stdout.write(
            f"Principal actif : {profile.est_principal}"
        )



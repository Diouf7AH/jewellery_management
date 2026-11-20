# # reparation/services/ticket_reparation_service.py

# from io import BytesIO
# from xml.sax.saxutils import escape

# from django.core.exceptions import ValidationError
# from django.utils import timezone
# from reportlab.lib import colors
# from reportlab.lib.enums import TA_CENTER, TA_LEFT
# from reportlab.lib.pagesizes import A5
# from reportlab.lib.styles import ParagraphStyle
# from reportlab.lib.units import mm
# from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
#                                 Spacer, Table, TableStyle)

# # ============================================================
# # OUTILS DE FORMATAGE
# # ============================================================

# def _valeur(texte):
#     """Échappe les textes pour ReportLab."""

#     if texte is None or texte == "":
#         return "Non renseigné"

#     return escape(str(texte))


# def _montant(montant):
#     """Formate un montant en FCFA."""

#     if montant is None:
#         return "0 FCFA"

#     return (
#         f"{montant:,.2f}"
#         .replace(",", " ")
#         .replace(".", ",")
#         + " FCFA"
#     )


# def _date(valeur, avec_heure=False):
#     """Formate une date Django."""

#     if valeur is None:
#         return "Non renseignée"

#     if avec_heure:
#         if timezone.is_aware(valeur):
#             valeur = timezone.localtime(valeur)

#         return valeur.strftime("%d/%m/%Y %H:%M")

#     return valeur.strftime("%d/%m/%Y")


# # ============================================================
# # GÉNÉRATION DU TICKET DE DÉPÔT PDF A5
# # ============================================================

# def generer_ticket_depot_pdf(reparation):
#     """
#     Génère le ticket de dépôt PDF A5.

#     Une réparation peut contenir plusieurs bijoux.

#     Chaque bijou affiche :
#     - Numéro de ligne
#     - Type
#     - Description
#     - Poids
#     - Pureté
#     - État à la réception
#     - Travail demandé
#     - Prix de réparation

#     Le ticket :
#     - ne crée aucun enregistrement ;
#     - n'effectue aucun paiement ;
#     - ne modifie aucun statut ;
#     - ne génère aucune facture.
#     """

#     if reparation is None or reparation.pk is None:
#         raise ValidationError({
#             "reparation": "Réparation invalide."
#         })

#     # --------------------------------------------------------
#     # 1. Charger les bijoux
#     # --------------------------------------------------------

#     bijoux = list(
#         reparation.bijoux.all().order_by("numero_ligne")
#     )

#     if not bijoux:
#         raise ValidationError({
#             "bijoux": (
#                 "Impossible de générer le ticket : "
#                 "aucun bijou dans ce dossier."
#             )
#         })

#     # Vérifier que le total est cohérent.
#     reparation.verifier_total_bijoux()

#     # --------------------------------------------------------
#     # 2. Préparer le document
#     # --------------------------------------------------------

#     buffer = BytesIO()

#     document = SimpleDocTemplate(
#         buffer,
#         pagesize=A5,
#         rightMargin=12 * mm,
#         leftMargin=12 * mm,
#         topMargin=12 * mm,
#         bottomMargin=12 * mm,
#         title=(
#             f"Ticket dépôt {reparation.numero_reparation}"
#         ),
#         author="Rio-Gold",
#     )

#     # --------------------------------------------------------
#     # 3. Styles
#     # --------------------------------------------------------

#     normal = ParagraphStyle(
#         "NormalTicket",
#         fontName="Helvetica",
#         fontSize=9,
#         leading=13,
#         spaceAfter=4,
#     )

#     titre = ParagraphStyle(
#         "TitreTicket",
#         parent=normal,
#         fontName="Helvetica-Bold",
#         fontSize=17,
#         leading=21,
#         alignment=TA_CENTER,
#         spaceAfter=8,
#     )

#     sous_titre = ParagraphStyle(
#         "SousTitreTicket",
#         parent=normal,
#         fontName="Helvetica-Bold",
#         fontSize=11,
#         leading=15,
#         alignment=TA_CENTER,
#         spaceAfter=10,
#     )

#     section = ParagraphStyle(
#         "SectionTicket",
#         parent=normal,
#         fontName="Helvetica-Bold",
#         fontSize=10,
#         leading=14,
#         spaceBefore=5,
#         spaceAfter=6,
#     )

#     petit = ParagraphStyle(
#         "PetitTicket",
#         parent=normal,
#         fontSize=8,
#         leading=11,
#         alignment=TA_LEFT,
#     )

#     total_style = ParagraphStyle(
#         "TotalTicket",
#         parent=normal,
#         fontName="Helvetica-Bold",
#         fontSize=11,
#         leading=15,
#         alignment=TA_CENTER,
#         spaceBefore=8,
#         spaceAfter=8,
#     )

#     # --------------------------------------------------------
#     # 4. Fonction pour les lignes d'information
#     # --------------------------------------------------------

#     def champ(nom, contenu):
#         return [
#             Paragraph(
#                 f"<b>{escape(nom)}</b>",
#                 petit,
#             ),
#             Paragraph(
#                 _valeur(contenu),
#                 petit,
#             ),
#         ]

#     def creer_tableau(donnees):
#         tableau = Table(
#             donnees,
#             colWidths=[39 * mm, 84 * mm],
#             hAlign="LEFT",
#         )

#         tableau.setStyle(
#             TableStyle([
#                 (
#                     "VALIGN",
#                     (0, 0),
#                     (-1, -1),
#                     "TOP",
#                 ),
#                 (
#                     "BOTTOMPADDING",
#                     (0, 0),
#                     (-1, -1),
#                     6,
#                 ),
#                 (
#                     "TOPPADDING",
#                     (0, 0),
#                     (-1, -1),
#                     5,
#                 ),
#                 (
#                     "LINEBELOW",
#                     (0, 0),
#                     (-1, -1),
#                     0.25,
#                     colors.lightgrey,
#                 ),
#             ])
#         )

#         return tableau

#     # --------------------------------------------------------
#     # 5. En-tête
#     # --------------------------------------------------------

#     elements = [
#         Paragraph(
#             _valeur(reparation.bijouterie.nom),
#             titre,
#         ),
#         Paragraph(
#             "TICKET DE DÉPÔT - RÉPARATION",
#             sous_titre,
#         ),
#         Paragraph(
#             f"<b>N° dossier :</b> "
#             f"{_valeur(reparation.numero_reparation)}",
#             normal,
#         ),
#         Paragraph(
#             f"<b>Date de dépôt :</b> "
#             f"{_date(reparation.date_depot, True)}",
#             normal,
#         ),
#         Spacer(1, 4 * mm),
#     ]

#     # --------------------------------------------------------
#     # 6. Informations du client
#     # --------------------------------------------------------

#     elements.append(
#         Paragraph(
#             "INFORMATIONS DU CLIENT",
#             section,
#         )
#     )

#     client = reparation.client

#     donnees_client = [
#         champ("Client", str(client)),
#         champ(
#             "Date prévue",
#             _date(reparation.date_prevue),
#         ),
#         champ(
#             "Nombre de bijoux",
#             str(len(bijoux)),
#         ),
#     ]

#     elements.append(
#         creer_tableau(donnees_client)
#     )

#     elements.append(
#         Spacer(1, 5 * mm)
#     )

#     # --------------------------------------------------------
#     # 7. Informations de chaque bijou
#     # --------------------------------------------------------

#     for bijou in bijoux:

#         donnees_bijou = [
#             champ(
#                 "Type de bijou",
#                 bijou.type_bijou,
#             ),
#             champ(
#                 "Description",
#                 bijou.description_bijou,
#             ),
#             champ(
#                 "Poids",
#                 (
#                     f"{bijou.poids} g"
#                     if bijou.poids is not None
#                     else None
#                 ),
#             ),
#             champ(
#                 "Pureté",
#                 bijou.purete,
#             ),
#             champ(
#                 "État à la réception",
#                 bijou.etat_reception,
#             ),
#             champ(
#                 "Travail demandé",
#                 bijou.travail_demande,
#             ),
#             champ(
#                 "Prix de réparation",
#                 _montant(bijou.prix_reparation),
#             ),
#         ]

#         bloc_bijou = [
#             Paragraph(
#                 f"BIJOU N° {bijou.numero_ligne}",
#                 section,
#             ),
#             creer_tableau(donnees_bijou),
#             Spacer(1, 4 * mm),
#         ]

#         elements.append(
#             KeepTogether(bloc_bijou)
#         )

#     # --------------------------------------------------------
#     # 8. Montant total
#     # --------------------------------------------------------

#     elements.append(
#         Spacer(1, 4 * mm)
#     )

#     elements.append(
#         Paragraph(
#             "MONTANT TOTAL DES RÉPARATIONS",
#             sous_titre,
#         )
#     )

#     elements.append(
#         Paragraph(
#             _montant(reparation.prix_convenu),
#             total_style,
#         )
#     )

#     # --------------------------------------------------------
#     # 9. Conditions de récupération
#     # --------------------------------------------------------

#     elements.append(
#         Spacer(1, 4 * mm)
#     )

#     elements.append(
#         Paragraph(
#             "<b>Paiement intégral au retrait.</b>",
#             normal,
#         )
#     )

#     elements.append(
#         Paragraph(
#             "Présentez ce ticket lors de la récupération "
#             "des bijoux. Une vérification de l'identité "
#             "du client ou de la personne autorisée "
#             "sera effectuée avant leur remise.",
#             normal,
#         )
#     )

#     elements.append(
#         Paragraph(
#             "Tous les bijoux figurant sur ce dossier "
#             "seront restitués ensemble après "
#             "confirmation du paiement intégral.",
#             normal,
#         )
#     )

#     # --------------------------------------------------------
#     # 10. Signatures
#     # --------------------------------------------------------

#     elements.extend([
#         Spacer(1, 7 * mm),
#         Paragraph(
#             "Signature du réceptionniste : "
#             "________________________",
#             normal,
#         ),
#         Spacer(1, 5 * mm),
#         Paragraph(
#             "Signature du client : "
#             "________________________",
#             normal,
#         ),
#         Spacer(1, 7 * mm),
#         Paragraph(
#             "Merci de votre confiance.",
#             sous_titre,
#         ),
#     ])

#     # --------------------------------------------------------
#     # 11. Générer le PDF
#     # --------------------------------------------------------

#     document.build(elements)

#     buffer.seek(0)

#     return buffer.getvalue()




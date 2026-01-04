
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        ("purchase", "0002_initial"),
        ("stock", "0003_initial"),
        ("store", "0002_initial"),
    ]

    operations = [
        # ❌ Suppression des DROP qui plantent car objets inexistants dans ta DB :
        # - ck_stock_qty_disp_lte_alloue
        # - stock_stock_bijoute_17bd28_idx
        # - stock_stock_produit_580ef5_idx

        migrations.AlterField(
            model_name="stock",
            name="quantite_allouee",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="stock",
            name="quantite_disponible",
            field=models.PositiveIntegerField(default=0),
        ),

        # ✅ Nouvelles contraintes cohérentes avec ton modèle actuel
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(
                condition=Q(bijouterie__isnull=True) | Q(quantite_allouee__gte=F("quantite_disponible")),
                name="ck_stock_qty_disp_lte_alloue_allocated_only",
            ),
        ),
        migrations.AddConstraint(
            model_name="stock",
            constraint=models.CheckConstraint(
                condition=Q(bijouterie__isnull=False) | Q(quantite_allouee=0),
                name="ck_stock_reserved_allouee_zero",
            ),
        ),
    ]
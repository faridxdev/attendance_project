from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0009_alter_etudiant_photo'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='presence',
            unique_together={('etudiant', 'matiere', 'date')},
        ),
    ]
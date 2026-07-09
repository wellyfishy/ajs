# yourapp/migrations/00XX_enable_pg_trgm.py
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('backend', '0009_alter_profile_foto_alter_teammember_foto'),  # match your last migration
    ]
    operations = [
        TrigramExtension(),
    ]
"""
Management command: seed_emission_factors
Usage: python manage.py seed_emission_factors
"""
from django.core.management.base import BaseCommand
from emissions.factors import seed_emission_factors


class Command(BaseCommand):
    help = "Seed the EmissionFactor table with DEFRA 2023 / GHG Protocol default factors."

    def handle(self, *args, **options):
        created = seed_emission_factors()
        self.stdout.write(
            self.style.SUCCESS(f"Done. {created} new EmissionFactor row(s) created.")
        )

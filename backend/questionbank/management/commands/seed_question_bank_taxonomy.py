"""
Seed the Question Bank SAT taxonomy (domains + skills).

Idempotent: re-running updates display order and fills gaps without creating
duplicates. NOT run automatically by any migration — invoke explicitly:

    python manage.py seed_question_bank_taxonomy

The source of truth mirrors frontend/src/lib/assessmentSatTaxonomy.ts. Keep the
two in sync until the frontend reads this taxonomy from the API (post-M0).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from questionbank.models import BankDomain, BankSkill, Subject

# subject -> [(domain_name, [skill_name, ...]), ...]
TAXONOMY: dict[str, list[tuple[str, list[str]]]] = {
    Subject.ENGLISH: [
        ("Information and Ideas", ["Central Ideas and Details", "Inferences", "Command of Evidence"]),
        ("Craft and Structure", ["Words in Context", "Text Structure and Purpose", "Cross-Text Connections"]),
        ("Expression of Ideas", ["Rhetorical Synthesis", "Transitions"]),
        ("Standard English Conventions", ["Boundaries", "Form, Structure, and Sense"]),
    ],
    Subject.MATH: [
        ("Algebra", [
            "Linear equations in one variable",
            "Linear functions",
            "Linear equations in two variables",
            "Systems of two linear equations in two variables",
            "Linear inequalities in one or two variables",
        ]),
        ("Advanced Math", [
            "Equivalent expressions",
            "Nonlinear equations in one variable and systems of equations in two variables",
            "Nonlinear functions",
        ]),
        ("Problem-Solving and Data Analysis", [
            "Ratios, rates, proportional relationships, and units",
            "Percentages",
            "One-variable data: Distributions and measures of center and spread",
            "Two-variable data: Models and scatterplots",
            "Probability and conditional probability",
            "Inference from sample statistics and margin of error",
            "Evaluating statistical claims: Observational studies and experiments",
        ]),
        ("Geometry and Trigonometry", [
            "Area and volume",
            "Lines, angles, and triangles",
            "Right triangles and trigonometry",
            "Circles",
        ]),
    ],
}


class Command(BaseCommand):
    help = "Seed/refresh Question Bank SAT domains and skills (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        domains_created = skills_created = 0
        for subject, domains in TAXONOMY.items():
            for d_order, (domain_name, skills) in enumerate(domains):
                domain, d_new = BankDomain.objects.update_or_create(
                    subject=subject,
                    name=domain_name,
                    defaults={"code": slugify(domain_name)[:64], "display_order": d_order},
                )
                domains_created += int(d_new)
                for s_order, skill_name in enumerate(skills):
                    _, s_new = BankSkill.objects.update_or_create(
                        domain=domain,
                        name=skill_name,
                        defaults={"code": slugify(skill_name)[:64], "display_order": s_order},
                    )
                    skills_created += int(s_new)

        self.stdout.write(self.style.SUCCESS(
            f"Taxonomy seeded. New domains: {domains_created}, new skills: {skills_created}. "
            f"Totals — domains: {BankDomain.objects.count()}, skills: {BankSkill.objects.count()}."
        ))

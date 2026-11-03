import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from identity.models import User
from identity.security import audit


class Command(BaseCommand):
    help = "Create a platform administrator interactively; MFA enrollment still mandatory."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        validate_email(email)
        if User.objects.filter(email=email).exists():
            raise CommandError("Account exists; refusing automatic privilege escalation")
        password = getpass.getpass("Password (12+ characters): ")
        validate_password(password)
        if password != getpass.getpass("Confirm password: "):
            raise CommandError("Passwords differ")
        user = User.objects.create_superuser(email, password, role="organization_admin")
        audit(user, "admin.bootstrapped")
        self.stdout.write(
            "Administrator created. Login and enroll TOTP before privileged operations."
        )

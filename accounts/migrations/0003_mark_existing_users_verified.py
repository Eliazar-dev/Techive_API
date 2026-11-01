from django.db import migrations


def verify_existing(apps, schema_editor):
    # Everyone who exists before this release signed in with an email code or Google, so their email is already proven.
    apps.get_model('accounts', 'User').objects.update(email_verified=True)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_emailotp_purpose_user_avatar_url_user_email_verified_and_more')]
    operations = [migrations.RunPython(verify_existing, migrations.RunPython.noop)]

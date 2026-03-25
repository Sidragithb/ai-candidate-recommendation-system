from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("candidates", "0002_candidate_resume_hash_candidate_education_level_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="degree_title",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="candidate",
            name="education_institution",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]

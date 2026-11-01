from django.db import migrations

# Draft courses. Staff edit descriptions, price, duration and mode in the Admin > Courses tab,
# then switch a course from "Coming soon" to "Open for registration".
COURSES = [
    ('Certified Prompt Engineering', 'Building with AI', 'Learn to write clear, reliable prompts and get consistent results from AI tools, and earn a Techive certificate. (Draft: edit in Admin.)'),
    ('AI for Startups', 'Building with AI', 'Use AI to validate ideas, speed up product work, marketing and operations in a young company. (Draft: edit in Admin.)'),
    ('AI for Kids', 'Building with AI', 'A safe, hands-on introduction to AI and creative technology for young learners. (Draft: edit in Admin.)'),
    ('AI for Programming: Web Development', 'Building with AI', 'Build modern websites faster by pairing your coding skills with AI assistants. (Draft: edit in Admin.)'),
    ('AI for Programming: Mobile App Development', 'Building with AI', 'Design and build mobile apps with AI-assisted coding workflows. (Draft: edit in Admin.)'),
    ('Cybersecurity', 'Cybersecurity', 'Understand common threats and learn practical ways to protect people, systems and data. (Draft: edit in Admin.)'),
]


def seed(apps, schema_editor):
    Course = apps.get_model('core', 'Course')
    if Course.objects.exists():
        return
    for i, (name, track, desc) in enumerate(COURSES, start=1):
        Course.objects.create(name=name, track=track, description=desc, status='coming_soon', order=i)


class Migration(migrations.Migration):
    dependencies = [('core', '0002_course_sitecontent_visitor_courseregistration')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

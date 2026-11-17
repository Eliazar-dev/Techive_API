from django.db import migrations
from django.utils.text import slugify

OLD_DRAFTS = ['Certified Prompt Engineering', 'AI for Startups', 'AI for Kids', 'AI for Programming: Web Development',
              'AI for Programming: Mobile App Development', 'Cybersecurity']
PLACEHOLDER = 'Add this lesson\'s notes here (Admin > Django admin > Lessons).'

WEB = dict(
    name='Certified Free Website Development with AI', slug='website-development-with-ai', track='Free courses', price=0, certificate_fee=250,
    duration='4 weeks', order=1,
    description='Build and publish your own website with the help of AI, even if you have never coded. Learn to describe what you want, guide an AI tool, fix problems and put your site online for free. Learning is free; you only pay a small fee for your certificate. (Draft: edit in Admin.)',
    project_brief='Build a one-page website about yourself, a business or a cause using AI, publish it for free, and paste the link here.',
    modules=[
        ('Week 1: Plan with AI', ['What a website is made of', 'Writing a clear brief for the AI', 'Choosing your project']),
        ('Week 2: Your first pages', ['Generating your first page', 'HTML and CSS in plain words', 'Making small changes safely']),
        ('Week 3: Make it good', ['Design, colours and text', 'A layout that works on phones', 'Adding contact and WhatsApp buttons']),
        ('Week 4: Publish', ['Checking and fixing your site', 'Putting your site online for free', 'Share your link and take the quiz']),
    ],
    quiz=[
        ('What does HTML do?', ['Structures the content of a page', 'Stores your data', 'Sends emails', 'Makes pages load faster'], 0),
        ('What does CSS control?', ['The look and layout of a page', 'Passwords', 'Hosting', 'Databases'], 0),
        ('Should you paste passwords into an AI tool?', ['Yes, if it asks', 'Never', 'Only on weekends', 'Only for free tools'], 1),
        ('What is the best way to improve an AI-made page?', ['Ask for one change at a time and check the result', 'Ask for everything in one huge request', 'Accept the first answer', 'Delete it and start again'], 0),
        ('What makes a site work well on phones?', ['A responsive layout', 'A bigger monitor', 'More images', 'Longer text'], 0),
    ])

PY = dict(
    name='Certified Free Python Programming', slug='python-programming', track='Free courses', price=0, certificate_fee=250,
    duration='4 weeks', order=2,
    description='Learn Python from zero: variables, decisions, loops, functions and files, then build a small program of your own. Learning is free; you only pay a small fee for your certificate. Continue to Django when you are ready. (Draft: edit in Admin.)',
    project_brief='Write a small Python program (for example a quiz, a budget calculator or a number guessing game), put the code on GitHub or Replit, and paste the link here.',
    modules=[
        ('Week 1: Getting started', ['Install Python and run your first program', 'Variables and data types', 'Numbers, text and input']),
        ('Week 2: Decisions and loops', ['If statements', 'For and while loops', 'Practice: a number guessing game']),
        ('Week 3: Functions and data', ['Functions', 'Lists and dictionaries', 'Reading and writing files']),
        ('Week 4: Your project', ['Plan your project', 'Build and debug', 'Share your code and take the quiz']),
    ],
    quiz=[
        ('Which function prints text on the screen?', ['print()', 'echo()', 'show()', 'write()'], 0),
        ('Which is a valid variable name?', ['2name', 'my_name', 'my-name', 'my name'], 1),
        ('What does len("Techive") return?', ['6', '7', '8', 'An error'], 1),
        ('Which keyword starts a loop over items?', ['for', 'loop', 'each', 'repeat'], 0),
        ('How do you start defining a function?', ['def', 'func', 'function', 'define'], 0),
    ])

CP = dict(
    name='Certified Computer Packages', slug='computer-packages', track='Paid courses', price=3000, certificate_fee=0, referral_reward=400,
    duration='2 months', order=3,
    description='Become confident with the computer applications every job and college needs: Word, Excel, PowerPoint, the internet and email. Taught in live online classes on Google Meet with recordings to watch again. The certificate is included. (Draft: edit in Admin.)',
    project_brief='Create a Word CV, an Excel budget sheet and a short PowerPoint about yourself. Upload them to Google Drive, share the folder link and paste it here.',
    modules=[
        ('Week 1: Computer basics', ['Parts of a computer and files', 'Folders, shortcuts and saving']),
        ('Week 2: Word, part 1', ['Typing, formatting and spelling', 'Pages, margins and printing']),
        ('Week 3: Word, part 2', ['Tables and pictures', 'Writing a CV and a letter']),
        ('Week 4: Excel, part 1', ['Cells, rows and columns', 'Simple formatting and charts']),
        ('Week 5: Excel, part 2', ['Formulas: SUM, AVERAGE, IF', 'Sorting, filtering and a budget sheet']),
        ('Week 6: PowerPoint', ['Slides, themes and layouts', 'Presenting with confidence']),
        ('Week 7: Internet and email', ['Safe browsing and searching', 'Email and Google Drive']),
        ('Week 8: Revision and project', ['Revision session', 'Submit your project and take the quiz']),
    ],
    quiz=[
        ('Which shortcut copies selected text?', ['Ctrl+C', 'Ctrl+V', 'Ctrl+X', 'Ctrl+Z'], 0),
        ('Which Excel formula adds the cells A1 to A5?', ['=SUM(A1:A5)', '=ADD(A1:A5)', '=TOTAL(A1;A5)', '=PLUS(A1:A5)'], 0),
        ('In PowerPoint, each page is called a...', ['Slide', 'Sheet', 'Cell', 'Frame'], 0),
        ('Which file ending is a Word document?', ['.docx', '.xlsx', '.pptx', '.mp3'], 0),
        ('What does Ctrl+Z do?', ['Undo', 'Redo', 'Save', 'Print'], 0),
    ])

DJANGO = dict(
    name='Django Web Development (Advanced)', slug='django-web-development', track='Advanced courses', price=None, certificate_fee=250,
    duration='', order=4, status='coming_soon',
    description='The next step after Python: build real web applications with Django. Price and dates will be announced. (Draft: edit in Admin.)',
    project_brief='', modules=[], quiz=[])


def seed(apps, schema_editor):
    Course = apps.get_model('core', 'Course')
    Module = apps.get_model('core', 'Module')
    Lesson = apps.get_model('core', 'Lesson')
    Question = apps.get_model('core', 'QuizQuestion')

    # 1. every existing course gets a link name
    for c in Course.objects.filter(slug__isnull=True):
        base, n = slugify(c.name)[:70] or 'course', 2
        slug = base
        while Course.objects.filter(slug=slug).exists():
            slug, n = f'{base}-{n}', n + 1
        c.slug = slug
        c.save(update_fields=['slug'])

    # 2. the earlier draft courses are replaced (kept but hidden if anyone already registered)
    for c in Course.objects.filter(name__in=OLD_DRAFTS):
        if c.registrations.exists():
            c.is_published = False
            c.save(update_fields=['is_published'])
        else:
            c.delete()

    # 3. the new courses (skipped if a course with that link name already exists)
    made = {}
    for spec in (WEB, PY, CP, DJANGO):
        spec = dict(spec)
        modules, quiz = spec.pop('modules'), spec.pop('quiz')
        slug = spec['slug']
        existing = Course.objects.filter(slug=slug).first()
        if existing:
            made[slug] = existing
            continue
        spec.setdefault('status', 'coming_soon')
        spec.setdefault('mode', 'online')
        c = Course.objects.create(**spec)
        made[slug] = c
        for mi, (title, lessons) in enumerate(modules, start=1):
            m = Module.objects.create(course=c, title=title, order=mi)
            for li, lt in enumerate(lessons, start=1):
                Lesson.objects.create(module=m, title=lt, kind='text', body=PLACEHOLDER, order=li)
        for qi, (text, options, correct) in enumerate(quiz, start=1):
            Question.objects.create(course=c, text=text, options=options, correct=correct, order=qi)
    py, dj = made.get('python-programming'), made.get('django-web-development')
    if py and dj and not py.next_course_id:
        py.next_course = dj
        py.save(update_fields=['next_course'])


class Migration(migrations.Migration):
    dependencies = [('core', '0004_academy_learning_payments')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

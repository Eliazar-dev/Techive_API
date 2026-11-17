"""Load lessons, quiz questions and project briefs from JSON files.

    python manage.py load_course_content --replace            # all files in core/content/
    python manage.py load_course_content --replace --course python-programming
    python manage.py load_course_content --replace --dir /path/to/json

Without --replace it only fills courses that have no lessons yet. Courses where students already have lesson
progress or quiz attempts are refused unless --force (replacing lessons deletes that progress).
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Course, Lesson, LessonProgress, Module, QuizAttempt, QuizQuestion

KINDS = {'video', 'text', 'file'}


def validate(doc, name):
    errs = []
    if not doc.get('slug'):
        errs.append('missing slug')
    for mi, m in enumerate(doc.get('modules', []), 1):
        if not m.get('title'):
            errs.append(f'module {mi}: no title')
        for li, l in enumerate(m.get('lessons', []), 1):
            if not l.get('title'):
                errs.append(f'module {mi} lesson {li}: no title')
            if l.get('kind', 'text') not in KINDS:
                errs.append(f'module {mi} lesson {li}: bad kind')
    for qi, q in enumerate(doc.get('quiz', []), 1):
        o = q.get('options')
        if not q.get('text') or not isinstance(o, list) or not 2 <= len(o) <= 6:
            errs.append(f'question {qi}: needs text and 2-6 options')
        elif not isinstance(q.get('correct'), int) or not 0 <= q['correct'] < len(o):
            errs.append(f'question {qi}: "correct" must be the index (from 0) of the right option')
    if errs:
        raise CommandError(f'{name}: ' + '; '.join(errs))


class Command(BaseCommand):
    help = 'Load course lessons / quizzes / project briefs from JSON files (see module docstring).'

    def add_arguments(self, p):
        p.add_argument('--dir', default=str(Path(__file__).resolve().parents[2] / 'content'))
        p.add_argument('--course', help='only this slug')
        p.add_argument('--replace', action='store_true', help='replace existing modules, lessons and quiz of the course')
        p.add_argument('--force', action='store_true', help='replace even if students already made progress')

    def handle(self, *a, **o):
        files = sorted(Path(o['dir']).glob('*.json'))
        if not files:
            raise CommandError(f'No .json files in {o["dir"]}')
        docs = []
        for f in files:
            doc = json.loads(f.read_text(encoding='utf-8'))
            if o['course'] and doc.get('slug') != o['course']:
                continue
            validate(doc, f.name)
            docs.append((f.name, doc))
        if not docs:
            raise CommandError('Nothing matched --course')
        for name, doc in docs:
            course = Course.objects.filter(slug=doc['slug']).first()
            if not course:
                raise CommandError(f'{name}: no course with slug "{doc["slug"]}". Create it in the admin first.')
            has = course.modules.exists() or course.questions.exists()
            if has and not o['replace']:
                self.stdout.write(f'SKIP {course.slug}: already has content (use --replace)')
                continue
            used = LessonProgress.objects.filter(lesson__module__course=course).exists() or QuizAttempt.objects.filter(course=course).exists()
            if has and used and not o['force']:
                self.stdout.write(self.style.WARNING(f'SKIP {course.slug}: students already have progress (use --force to replace anyway)'))
                continue
            with transaction.atomic():
                course.modules.all().delete()
                course.questions.all().delete()
                n = 0
                for mi, m in enumerate(doc.get('modules', []), 1):
                    mod = Module.objects.create(course=course, title=m['title'], order=mi)
                    for li, l in enumerate(m.get('lessons', []), 1):
                        Lesson.objects.create(module=mod, order=li, title=l['title'], kind=l.get('kind', 'text'), body=l.get('body', ''),
                                              video_url=l.get('video_url', ''), file_url=l.get('file_url', ''))
                        n += 1
                for qi, q in enumerate(doc.get('quiz', []), 1):
                    QuizQuestion.objects.create(course=course, order=qi, text=q['text'], options=q['options'], correct=q['correct'])
                changed = []
                for field in ('description', 'project_brief', 'rules', 'payment_plan', 'tutor', 'duration'):
                    if doc.get(field):
                        setattr(course, field, doc[field])
                        changed.append(field)
                if 'quiz_pass_mark' in doc:
                    course.quiz_pass_mark = int(doc['quiz_pass_mark']); changed.append('quiz_pass_mark')
                if changed:
                    course.save(update_fields=changed)
            self.stdout.write(self.style.SUCCESS(f'OK   {course.slug}: {len(doc.get("modules", []))} modules, {n} lessons, {len(doc.get("quiz", []))} questions'))

"""All outgoing emails: one branded HTML layout + one function per message."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape


def _layout(title, paragraphs, button=None):
    body = ''.join(f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#3f3f46">{p}</p>' for p in paragraphs)
    btn = (f'<p style="margin:24px 0 0"><a href="{escape(button[1])}" style="background:linear-gradient(90deg,#06c3ff,#a855f7);'
           f'color:#fff;text-decoration:none;padding:12px 28px;border-radius:99px;font-weight:700;font-size:14px;display:inline-block">{escape(button[0])}</a></p>') if button else ''
    return f'''<!doctype html><html><body style="margin:0;background:#f4f4f5;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden" cellspacing="0" cellpadding="0">
<tr><td style="background:#0a0a0b;padding:22px 28px"><span style="color:#fff;font-size:22px;font-weight:800;letter-spacing:-.5px">Techive</span>
<span style="color:#a855f7;font-size:11px;letter-spacing:3px;margin-left:8px">IT SOLUTIONS</span></td></tr>
<tr><td style="height:4px;background:linear-gradient(90deg,#06c3ff,#7c5cff,#a855f7)"></td></tr>
<tr><td style="padding:32px 28px"><h1 style="margin:0 0 18px;font-size:22px;color:#0a0a0b">{escape(title)}</h1>{body}{btn}</td></tr>
<tr><td style="padding:18px 28px;background:#fafafa;color:#8b8b95;font-size:12px">Techive IT Solutions &middot; Archiving Innovation. Coding the Future.</td></tr>
</table></td></tr></table></body></html>'''


def send_html(subject, to, text, title, paragraphs, button=None, fail_silently=False):
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to] if isinstance(to, str) else to)
    msg.attach_alternative(_layout(title, paragraphs, button), 'text/html')
    msg.send(fail_silently=fail_silently)


def first_name(user):
    return user.first_name or user.email.split('@')[0]


PURPOSE_TEXT = {'login': 'sign in to', 'signup': 'verify your email for', 'reset': 'reset your password for'}


def send_otp(email, code, purpose):
    what = PURPOSE_TEXT.get(purpose, 'sign in to')
    ttl = settings.OTP_TTL_MINUTES
    send_html(
        f'{code} is your Techive verification code', email,
        f'Your Techive IT Solutions code is {code}.\nUse it to {what} your account. It expires in {ttl} minutes.\nIf you did not request it, ignore this email.',
        'Your verification code',
        [f'Use this code to {what} your Techive account:',
         f'<span style="display:inline-block;font-size:34px;font-weight:800;letter-spacing:10px;color:#0a0a0b;background:#f4f4f5;padding:12px 22px;border-radius:14px">{code}</span>',
         f'It expires in {ttl} minutes. If you did not request this, you can safely ignore this email.'])


def send_welcome(user):
    url = settings.FRONTEND_URL
    send_html(
        'Welcome to Techive IT Solutions', user.email,
        f'Hi {first_name(user)}, welcome to Techive IT Solutions! Your account is ready: {url}',
        f'Welcome, {first_name(user)}!',
        ['Your Techive account has been created and your email is verified.',
         'You can now request quotes for websites, apps and business systems, and register for courses at Techive Academy.',
         'If you ever need help, just reply to this email.'],
        ('Open Techive', url), fail_silently=True)


def send_password_changed(user):
    send_html('Your Techive password was changed', user.email,
              'Your password was changed. If this was not you, reset it immediately.',
              'Password changed', ['The password for your Techive account was just changed.',
                                   'If you did not do this, reset your password straight away or contact us.'], fail_silently=True)


def send_course_registration(reg, till_number='', payment_note=''):
    c, u = reg.course, reg.user
    price = f'KSh {c.price:,}' if c.price else 'To be announced'
    lines = [f'Hi {first_name(u)}, you are registered for <b>{escape(c.name)}</b>. Here is what happens next.',
             f'<b>Duration:</b> {escape(c.duration or "To be announced")}<br><b>Mode of teaching:</b> {escape(c.get_mode_display())}<br><b>Fee:</b> {price}']
    if c.rules:
        lines.append('<b>Course rules</b><br>' + escape(c.rules).replace('\n', '<br>'))
    pay = c.payment_plan or payment_note
    if pay:
        lines.append('<b>Payment plan</b><br>' + escape(pay).replace('\n', '<br>'))
    if till_number:
        lines.append(f'<b>Till number:</b> {escape(till_number)}')
    lines.append('Our team will contact you with the class schedule. You can follow your progress any time in the Academy section of the website.')
    text = f'Hi {first_name(u)}, you are registered for {c.name}. Duration: {c.duration}. Mode: {c.get_mode_display()}. Fee: {price}.'
    send_html(f'You are registered: {c.name}', u.email, text, 'Registration confirmed', lines,
              ('View my courses', settings.FRONTEND_URL.rstrip('/') + '/academy'), fail_silently=True)

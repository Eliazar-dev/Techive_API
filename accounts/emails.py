"""All outgoing emails: one branded HTML layout + one function per message."""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape


def _layout(title, paragraphs, button=None, is_academy=False, copy_code=None):
    body = ''.join(f'<p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#3f3f46">{p}</p>' for p in paragraphs)
    btn = (f'<p style="margin:24px 0 0"><a href="{escape(button[1])}" style="background:linear-gradient(90deg,#06c3ff,#a855f7);'
           f'color:#fff;text-decoration:none;padding:12px 28px;border-radius:99px;font-weight:700;font-size:14px;display:inline-block">{escape(button[0])}</a></p>') if button else ''
    
    # Copy code button for OTP emails - using pre-selected text for better compatibility
    copy_btn = f'''<div style="margin:20px 0 0;text-align:center;background:#f4f4f5;padding:16px;border-radius:12px;border:2px dashed #06c3ff">
      <p style="margin:0 0 8px;font-size:13px;color:#6b7280">Your code is pre-selected below. Just press Ctrl+C (or Cmd+C on Mac) to copy:</p>
      <input type="text" value="{copy_code}" readonly style="width:200px;padding:10px;text-align:center;font-size:18px;font-weight:800;letter-spacing:8px;border:1px solid #06c3ff;border-radius:8px;background:#fff;color:#0a0a0b;font-family:monospace" />
    </div>''' if copy_code else ''
    
    # Logo URL from Cloudinary
    logo_url = 'https://res.cloudinary.com/myq7pkty/image/upload/v1793739663/Techive_IT_Solutions_Logo_2.png'
    
    # Academy-specific header color (white background with purple accent)
    header_bg = '#ffffff'
    text_color = '#0a0a0b'
    badge_color = '#a855f7'
    badge_text = 'ACADEMY' if is_academy else 'IT SOLUTIONS'
    
    return f'''<!doctype html><html><body style="margin:0;background:#f4f4f5;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">
<table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:20px;overflow:hidden" cellspacing="0" cellpadding="0">
<tr><td style="background:{header_bg};padding:20px 28px;text-align:center;border-bottom:2px solid #f4f4f5">
<img src="{logo_url}" alt="Techive IT Solutions Logo" width="160" style="display:block;margin:0 auto" />
<span style="color:{badge_color};font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;display:block;margin-top:8px">{badge_text}</span>
</td></tr>
<tr><td style="height:4px;background:linear-gradient(90deg,#06c3ff,#7c5cff,#a855f7)"></td></tr>
<tr><td style="padding:32px 28px"><h1 style="margin:0 0 18px;font-size:22px;color:{text_color}">{escape(title)}</h1>{body}{btn}{copy_btn}</td></tr>
<tr><td style="padding:18px 28px;background:#fafafa;color:#8b8b95;font-size:12px">Techive IT Solutions &middot; Archiving Innovation. Coding the Future.</td></tr>
</table></td></tr></table></body></html>'''


def send_html(subject, to, text, title, paragraphs, button=None, fail_silently=False, is_academy=False, copy_code=None):
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to] if isinstance(to, str) else to)
    msg.attach_alternative(_layout(title, paragraphs, button, is_academy, copy_code), 'text/html')
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
         f'It expires in {ttl} minutes. If you did not request this, you can safely ignore this email.'],
        copy_code=code)


def send_welcome(user):
    url = settings.FRONTEND_URL
    send_html(
        'Welcome to Techive IT Solutions', user.email,
        f'Hi {first_name(user)}, welcome to Techive IT Solutions! Your account is ready: {url}',
        f'Welcome, {first_name(user)}!',
        ['Your Techive account has been created and your email is verified.',
         '<b>What you can do now:</b>',
         '• Request quotes for websites, apps and business systems',
         '• Register for courses at Techive Academy',
         '• Track your progress and manage your profile',
         'Our team is here to help you succeed. If you have any questions, just reply to this email.'],
        ('Get Started', url), fail_silently=True)


def send_password_changed(user):
    send_html('Your Techive password was changed', user.email,
              'Your password was changed. If this was not you, reset it immediately.',
              'Password changed', ['The password for your Techive account was just changed.',
                                   'If you did not do this, reset your password straight away or contact us.'], fail_silently=True)


def send_course_registration(reg, till_number='', payment_note=''):
    c, u = reg.course, reg.user
    price = f'KSh {c.price:,}' if c.price else 'To be announced'
    lines = [f'🎉 <b>Congratulations, {first_name(u)}!</b> You are now registered for <b>{escape(c.name)}</b>.',
             f'<b>Track:</b> {escape(c.track)}',
             f'<b>Duration:</b> {escape(c.duration or "To be announced")}',
             f'<b>Mode of teaching:</b> {escape(c.get_mode_display())}',
             f'<b>Fee:</b> {price}']
    if c.rules:
        lines.append('<br><b>📋 Course rules</b><br>' + escape(c.rules).replace('\n', '<br>'))
    pay = c.payment_plan or payment_note
    if pay:
        lines.append('<br><b>💳 Payment plan</b><br>' + escape(pay).replace('\n', '<br>'))
    if till_number:
        lines.append(f'<br><b>📱 Till number:</b> {escape(till_number)}')
    lines.append('<br><b>What happens next:</b><br>Our team will contact you with the class schedule and login details. You can track your progress and access course materials anytime in the Academy section of the website.')
    text = f'Hi {first_name(u)}, you are registered for {c.name}. Duration: {c.duration}. Mode: {c.get_mode_display()}. Fee: {price}.'
    send_html(f'Academy Registration: {c.name}', u.email, text, 'Registration Confirmed', lines,
              ('Go to Academy', settings.FRONTEND_URL.rstrip('/') + '/academy'), fail_silently=True, is_academy=True)

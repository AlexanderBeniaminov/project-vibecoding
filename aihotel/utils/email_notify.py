"""Отправка email-уведомлений через Gmail SMTP."""
import os
import smtplib
from email.mime.text import MIMEText


def send(to_email: str, subject: str, body: str) -> bool:
    smtp_user = os.environ.get('GMAIL_USER', '')
    smtp_pass = os.environ.get('GMAIL_APP_PASSWORD', '')

    if not smtp_user or not smtp_pass or not to_email or to_email == '0':
        print(f'  Email: пропуск (нет учётных данных или to={to_email})')
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From']    = smtp_user
        msg['To']      = to_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as srv:
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f'  Email: ошибка отправки на {to_email}: {e}')
        return False

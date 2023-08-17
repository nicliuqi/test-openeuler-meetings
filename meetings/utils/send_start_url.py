import logging
import smtplib
from django.conf import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .email_templates import webinar_start_url_template

logger = logging.getLogger('log')


def run(date, start, topic, start_url, password, summary, email):
    msg = MIMEMultipart()
    body_of_email = webinar_start_url_template(date, start, topic, start_url, password, summary)
    content = MIMEText(body_of_email, 'html', 'utf-8')
    msg.attach(content)

    # 完善邮件信息
    mailto = email 
    msg['Subject'] = 'Start url for meetup'
    msg['From'] = 'openEuler MiniProgram<public@openeuler.org>'
    msg['To'] = mailto

    # 登录服务器发送邮件
    try:
        gmail_username = settings.GMAIL_USERNAME
        server = smtplib.SMTP(settings.SMTP_SERVER_HOST, settings.SMTP_SERVER_PORT)
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_SERVER_USER, settings.SMTP_SERVER_PASS)
        server.sendmail(gmail_username, mailto.split(','), msg.as_string())
        print('发送成功')
        server.quit()
    except smtplib.SMTPException as e:
        logger.error(e)

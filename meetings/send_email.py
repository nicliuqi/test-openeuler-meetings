import datetime
import icalendar
import logging
import os
import pytz
import re
import smtplib
import uuid
from django.conf import settings
from email import encoders
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from meetings.models import Meeting

logger = logging.getLogger('log')


def sendmail(meeting, record=None, enclosure_paths=None):
    mid = meeting.get('mid')
    mid = str(mid)
    topic = meeting.get('topic')
    date = meeting.get('date')
    start = meeting.get('start')
    end = meeting.get('end')
    join_url = meeting.get('join_url')
    sig_name = meeting.get('sig_name')
    toaddrs = meeting.get('emaillist')
    platform = meeting.get('platform')
    platform = platform.replace('zoom', 'Zoom').replace('welink', 'WeLink')
    etherpad = meeting.get('etherpad')
    summary = meeting.get('agenda')
    start_time = ' '.join([date, start])
    toaddrs = toaddrs.replace(' ', '').replace('，', ',').replace(';', ',').replace('；', ',')
    toaddrs_list = toaddrs.split(',')
    error_addrs = []
    for addr in toaddrs_list:
        if not re.match(r'^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$', addr):
            error_addrs.append(addr)
            toaddrs_list.remove(addr)
    toaddrs_string = ','.join(toaddrs_list)
    # 发送列表去重，排序
    toaddrs_list = sorted(list(set(toaddrs_list)))
    if not toaddrs_list:
        logger.info('Event of creating meeting {} has no email to send.'.format(mid))
        return

    # 构造邮件
    msg = MIMEMultipart()

    # 添加邮件主体
    body_of_email = None
    if not summary and not record:
        print(platform)
        with open('templates/template_without_summary_without_recordings.txt', 'r', encoding='utf-8') as fp:
            body = fp.read()
            body_of_email = body.replace('{{sig_name}}', '{0}').replace('{{start_time}}', '{1}').\
                replace('{{join_url}}', '{2}').replace('{{topic}}', '{3}').\
                replace('{{platform}}', '{4}').replace('{{etherpad}}', '{5}').\
                format(sig_name, start_time, join_url, topic, platform, etherpad)
    if summary and not record:
        print(platform)
        with open('templates/template_with_summary_without_recordings.txt', 'r', encoding='utf-8') as fp:
            body = fp.read()
            body_of_email = body.replace('{{sig_name}}', '{0}').replace('{{start_time}}', '{1}').\
                replace('{{join_url}}', '{2}').replace('{{topic}}', '{3}').\
                replace('{{summary}}', '{4}').replace('{{platform}}', '{5}').\
                replace('{{etherpad}}', '{6}').\
                format(sig_name, start_time, join_url, topic, summary, platform, etherpad)
    if not summary and record:
        with open('templates/template_without_summary_with_recordings.txt', 'r', encoding='utf-8') as fp:
            body = fp.read()
            body_of_email = body.replace('{{sig_name}}', '{0}').replace('{{start_time}}', '{1}').\
                replace('{{join_url}}', '{2}').replace('{{topic}}', '{3}').replace('{{platform}}', '{4}').\
                replace('{{etherpad}}', '{5}').\
                format(sig_name, start_time, join_url, topic, platform, etherpad)
    if summary and record:
        with open('templates/template_with_summary_with_recordings.txt', 'r', encoding='utf-8') as fp:
            body = fp.read()
            body_of_email = body.replace('{{sig_name}}', '{0}').replace( '{{start_time}}', '{1}').\
                replace('{{join_url}}', '{2}').replace('{{topic}}', '{3}').\
                replace('{{summary}}', '{4}').replace('{{platform}}', '{5}').\
                replace('{{etherpad}}', '{6}').\
                format(sig_name, start_time, join_url, topic, summary, platform, etherpad)
    content = MIMEText(body_of_email, 'plain', 'utf-8')
    msg.attach(content)

    # 添加图片
    for file in os.listdir('templates/images'):
        if os.path.join('images', file) in body_of_email:
            f = open(os.path.join('templates', 'images', file), 'rb')
            msgImage = MIMEImage(f.read())
            f.close()
            msgImage.add_header('Content-ID', '<{}>'.format(os.path.join('images', file)))
            msg.attach(msgImage)

    # 添加邮件附件
    paths = enclosure_paths
    if paths:
        for file_path in paths:
            file = MIMEApplication(open(file_path, 'rb').read())
            file.add_header('Content-Disposition', 'attachment', filename=file_path)
            msg.attach(file)

    # 添加日历
    dt_start = (datetime.datetime.strptime(date + ' ' + start, '%Y-%m-%d %H:%M') - datetime.timedelta(hours=8)).replace(tzinfo=pytz.utc)
    dt_end = (datetime.datetime.strptime(date + ' ' + end, '%Y-%m-%d %H:%M') - datetime.timedelta(hours=8)).replace(tzinfo=pytz.utc)

    cal = icalendar.Calendar()
    cal.add('prodid', '-//openeuler conference calendar')
    cal.add('version', '2.0')
    cal.add('method', 'REQUEST')

    event = icalendar.Event()
    event.add('attendee', ','.join(sorted(list(set(toaddrs_list)))))
    event.add('summary', topic)
    event.add('dtstart', dt_start)
    event.add('dtend', dt_end)
    event.add('dtstamp', dt_start)
    event.add('uid', platform + mid)

    alarm = icalendar.Alarm()
    alarm.add('action', 'DISPLAY')
    alarm.add('description', 'Reminder')
    alarm.add('TRIGGER;RELATED=START', '-PT15M')
    event.add_component(alarm)

    cal.add_component(event)

    filename = 'invite.ics'
    part = MIMEBase('text', 'calendar', method='REQUEST', name=filename)
    part.set_payload(cal.to_ical())
    encoders.encode_base64(part)
    part.add_header('Content-Description', filename)
    part.add_header('Content-class', 'urn:content-classes:calendarmessage')
    part.add_header('Filename', filename)
    part.add_header('Path', filename)

    msg.attach(part)

    # 完善邮件信息
    msg['Subject'] = topic
    msg['From'] = 'openEuler conference<public@openeuler.org>'
    msg['To'] = toaddrs_string

    # 登录服务器发送邮件
    try:
        gmail_username = settings.GMAIL_USERNAME
        server = smtplib.SMTP(settings.SMTP_SERVER_HOST, settings.SMTP_SERVER_PORT)
        server.ehlo()
        server.starttls()
        server.login(settings.SMTP_SERVER_USER, settings.SMTP_SERVER_PASS)
        server.sendmail(gmail_username, toaddrs_list, msg.as_string())
        logger.info('email string: {}'.format(toaddrs))
        logger.info('error addrs: {}'.format(error_addrs))
        logger.info('email sent: {}'.format(toaddrs_string))
        server.quit()
    except smtplib.SMTPException as e:
        logger.error(e)

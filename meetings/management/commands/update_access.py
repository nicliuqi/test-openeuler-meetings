import logging
import requests
from django.core.management import BaseCommand
from django.conf import settings
from meetings.models import Zoom

logger = logging.getLogger('log')


class Command(BaseCommand):
    def handle(self, *args, **options):
        refresh()


def refresh():
    refresh_token = Zoom.objects.get(id=1).refresh
    url = settings.ZOOM_AUTH_URL
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    headers = {
        'Host': 'zoom.us',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': settings.ZOOM_AUTH_HEADER
    }
    r = requests.post(url, data=payload, headers=headers)
    if r.status_code != 200:
        logger.error('Fail to refresh access: {}'.format(r.json())) 
    access_token, refresh_token = r.json().get('access_token'), r.json().get('refresh_token')
    Zoom.objects.filter(id=1).update(access=access_token, refresh=refresh_token)
    logger.info('Refresh access successfully.')

import logging
import json
import requests
from django.conf import settings
from meetings.models import Activity


logger = logging.getLogger('log')

def invite_panelists(mid):
    activity = Activity.objects.get(mid=mid)
    schedules = json.loads(activity.schedules)
    speakers = [x['speakerList'] for x in schedules]
    speakers_lst = []
    for i in speakers:
        for j in i:
            speakers_lst.append({'name': j['name'], 'email': j['mail']})
    data = {'panelists': speakers_lst}
    post(data, mid)


def add_panelists(mid, new_schedules):
    new_schedules = json.loads(new_schedules)
    activity = Activity.objects.get(mid=mid)
    schedules = json.loads(activity.schedules)
    speakers = [x['speakerList'] for x in schedules]
    new_speakers = [x['speakerList'] for x in new_schedules]
    speakers_lst = []
    new_speakers_lst = []
    add_speaker_lst = []
    speaker_dict = {}
    new_speaker_dict = {}
    for i in speakers:
        for j in i:
            speakers_lst.append({'name': j['name'], 'email': j['mail']})
    for i in new_speakers:
        for j in i:
            new_speakers_lst.append({'name': j['name'], 'email': j['mail']})
    for i in new_speakers_lst:
        if i not in speakers_lst:
            add_speaker_lst.append(i)
    data = {'panelists': add_speaker_lst}
    post(data, mid)


def post(data, mid):
    access_token = settings.ZOOM_TOKEN
    url = 'https://api.zoom.us/v2/webinars/{}/panelists'.format(mid)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer {}'.format(access_token)
    }
    r = requests.post(url, headers=headers, data=json.dumps(data))
    if r.status_code != 201:
        logger.error(r.json())

import base64
import datetime
import logging
import json
import random
import requests
from django.conf import settings

logger = logging.getLogger('log')


def createMeeting(date, start, end, topic, host, record):
    start_time = (datetime.datetime.strptime(date + start, '%Y-%m-%d%H:%M') - datetime.timedelta(hours=8)).strftime(
        '%Y-%m-%dT%H:%M:%SZ')
    end_time = (datetime.datetime.strptime(date + end, '%Y-%m-%d%H:%M') - datetime.timedelta(hours=8)).strftime(
        '%Y-%m-%dT%H:%M:%SZ')
    duration = int((datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%SZ') -
                    datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%SZ')).seconds / 60)
    password = str(random.randint(100000, 999999))
    headers = {
        "content-type": "application/json",
        "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)
    }
    payload = {
        'start_time': start_time,
        'duration': duration,
        'topic': topic,
        'password': password,
        'settings': {
            'waiting_room': False,
            'auto_recording': record,
            'join_before_host': True,
            'jbh_time': 5
        }
    }
    url = "https://api.zoom.us/v2/users/{}/meetings".format(host)
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    resp_dict = {}
    if response.status_code != 201:
        return response.status_code, resp_dict
    resp_dict['mid'] = response.json()['id']
    resp_dict['start_url'] = response.json()['start_url']
    resp_dict['join_url'] = response.json()['join_url']
    resp_dict['host_id'] = response.json()['host_id']
    return response.status_code, resp_dict


def cancelMeeting(mid):
    url = "https://api.zoom.us/v2/meetings/{}".format(mid)
    headers = {
        "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)
    }
    response = requests.request("DELETE", url, headers=headers)
    return response.status_code


def getParticipants(mid):
    url = "https://api.zoom.us/v2/past_meetings/{}/participants?page_size=300".format(mid)
    headers = {
        "authorization": "Bearer {}".format(settings.ZOOM_TOKEN)}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        total_records = r.json()['total_records']
        participants = r.json()['participants']
        resp = {'total_records': total_records, 'participants': participants}
        return r.status_code, resp
    else:
        return r.status_code, r.json()


def getOauthToken(account_id, client_id, client_secret):
    url = 'https://zoom.us/oauth/token'
    payload = {
        'grant_type': 'account_credentials',
        'account_id': account_id
    }
    headers = {
        'Host': 'zoom.us',
        'Authorization': 'Basic {}'.format(base64.b64encode((client_id + ':' + client_secret).encode()).decode())
    }
    r = requests.post(url, data=payload, headers=headers)
    if r.status_code != 200:
        logger.error('Fail to get zoom token.')
        logger.error(r.json())
        return None
    return r.json().get('access_token')
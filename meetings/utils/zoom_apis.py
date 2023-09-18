import datetime
import logging
import json
import random
import requests
from django.conf import settings
from obs import ObsClient

logger = logging.getLogger('log')


def createMeeting(date, start, end, topic, host, record):
    start_time = (datetime.datetime.strptime(date + start, '%Y-%m-%d%H:%M') - datetime.timedelta(hours=8)).strftime(
        '%Y-%m-%dT%H:%M:%SZ')
    end_time = (datetime.datetime.strptime(date + end, '%Y-%m-%d%H:%M') - datetime.timedelta(hours=8)).strftime(
        '%Y-%m-%dT%H:%M:%SZ')
    duration = int((datetime.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%SZ') -
                    datetime.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%SZ')).seconds / 60)
    password = str(random.randint(100000, 999999))
    token = getOauthToken()
    headers = {
        "content-type": "application/json",
        "authorization": "Bearer {}".format(token)
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
    token = getOauthToken()
    headers = {
        "authorization": "Bearer {}".format(token)
    }
    response = requests.request("DELETE", url, headers=headers)
    return response.status_code


def getParticipants(mid):
    url = "https://api.zoom.us/v2/past_meetings/{}/participants?page_size=300".format(mid)
    token = getOauthToken()
    headers = {
        "authorization": "Bearer {}".format(token)}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        total_records = r.json()['total_records']
        participants = r.json()['participants']
        resp = {'total_records': total_records, 'participants': participants}
        return r.status_code, resp
    else:
        return r.status_code, r.json()


def getOauthToken():
    access_key_id = settings.DEFAULT_CONF.get('ACCESS_KEY_ID_2')
    secret_access_key = settings.DEFAULT_CONF.get('SECRET_ACCESS_KEY_2')
    endpoint = settings.DEFAULT_CONF.get('OBS_ENDPOINT_2')
    bucketName = settings.DEFAULT_CONF.get('OBS_BUCKETNAME_2')
    object_key = settings.DEFAULT_CONF.get('ZOOM_TOKEN_OBJECT')
    obs_client = ObsClient(access_key_id=access_key_id, secret_access_key=secret_access_key, server=endpoint)
    res = obs_client.getObjectMetadata(bucketName, object_key)
    token = ''
    if res.get('status') != 200:
        logger.error('Fail to get zoom token')
        return token
    for k, v in res.get('header'):
        if k == 'access_token':
            token = v
            break
    return token

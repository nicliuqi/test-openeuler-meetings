import base64
import hashlib
import hmac
import json
import logging
import random
import requests
import time
from django.conf import settings
from meetings.models import Meeting

logger = logging.getLogger('log')


def get_signature(method, uri, body):
    """获取签名"""
    AppId = str(settings.TX_MEETING_APPID)
    SdkId = str(settings.TX_MEETING_SDKID)
    secretKey = settings.TX_MEETING_SECRETKEY
    secretId = settings.TX_MEETING_SECRETID
    timestamp = str(int(time.time()))
    nonce = str(int(random.randint(0, 1000000)))
    headers = {
        "X-TC-Key": secretId,
        "X-TC-Nonce": nonce,
        "X-TC-Timestamp": timestamp,
        "X-TC-Signature": "",
        "AppId": AppId,
        "SdkId": SdkId,
        "X-TC-Registered": "1"
    }
    headerString = 'X-TC-Key=' + secretId + '&X-TC-Nonce=' + nonce + '&X-TC-Timestamp=' + timestamp
    msg = (method + '\n' + headerString + '\n' + uri + '\n' + body).encode('utf-8')
    key = secretKey.encode('utf-8')
    signature = base64.b64encode(hmac.new(key, msg, digestmod=hashlib.sha256).hexdigest().encode('utf-8')).decode(
        'utf-8')
    headers['X-TC-Signature'] = signature
    return signature, headers


def get_records():
    """获取有效录像"""
    uri = '/v1/corp/records'
    url = get_url(uri)
    end_time = int(time.time())
    start_time = end_time - 3600 * 24 * 2
    signature, headers = get_signature('GET', uri, "")
    page = 1
    records = []
    while True:
        params = {
            'start_time': start_time,
            'end_time': end_time,
            'page_size': 20,
            'page': page
        }
        r = requests.get(url, params=params, headers=headers)
        if r.status_code != 200:
            logger.error(r.json())
            return []
        if 'record_meetings' not in r.json().keys():
            break
        record_meetings = r.json().get('record_meetings')
        records.extend(record_meetings)
        page += 1
    return records


def get_video_download(record_file_id, userid):
    """获取录像下载地址"""
    uri = '/v1/addresses/{}?userid={}'.format(record_file_id, userid)
    url = get_url(uri)
    signature, headers = get_signature('GET', uri, "")
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()['download_address']
    else:
        logger.error(r.text)
        return


def get_url(uri):
    """获取请求url"""
    return 'https://api.meeting.qq.com' + uri


def createMeeting(date, start, end, topic, host_id, record):
    start_time = date + ' ' + start
    end_time = date + ' ' + end
    start_time = str(int(time.mktime(time.strptime(start_time, '%Y-%m-%d %H:%M'))))
    end_time = str(int(time.mktime(time.strptime(end_time, '%Y-%m-%d %H:%M'))))
    payload = {
        "userid": host_id,
        "instanceid": 1,
        "subject": topic,
        "type": 0,
        "start_time": start_time,
        "end_time": end_time,
        "settings": {
            "mute_enable_join": True
        }
    }
    if record == 'cloud':
        payload['settings']['auto_record_type'] = 'cloud'
        payload['settings']['participant_join_auto_record'] = True
        payload['settings']['enable_host_pause_auto_record'] = True
    uri = '/v1/meetings'
    url = get_url(uri)
    payload = json.dumps(payload)
    signature, headers = get_signature('POST', uri, payload)
    r = requests.post(url, headers=headers, data=payload)
    resp_dict = {
        'host_id': host_id
    }
    if r.status_code != 200:
        logger.error('Fail to create meeting, status_code is {}'.format(r.status_code))
        return r.status_code, resp_dict
    resp_dict['mid'] = r.json()['meeting_info_list'][0]['meeting_code']
    resp_dict['mmid'] = r.json()['meeting_info_list'][0]['meeting_id']
    resp_dict['join_url'] = r.json()['meeting_info_list'][0]['join_url']
    return r.status_code, resp_dict


def cancelMeeting(mid):
    meeting = Meeting.objects.get(mid=mid)
    host_id = meeting.host_id
    mmid = meeting.mmid
    payload = json.dumps({
        "userid": host_id,
        "instanceid": 1,
        "reason_code": 1
    })
    uri = '/v1/meetings/' + str(mmid) + '/cancel'
    url = get_url(uri)
    signature, headers = get_signature('POST', uri, payload)
    r = requests.post(url, headers=headers, data=payload)
    if r.status_code != 200:
        logger.error('Fail to cancel meeting {}'.format(mid))
        logger.error(r.json())
        return r.status_code
    logger.info('Cancel meeting {}'.format(mid))
    return r.status_code


def getParticipants(mid):
    meeting = Meeting.objects.get(mid=mid)
    mmid = meeting.mmid
    host_id = meeting.host_id
    uri = '/v1/meetings/{}/participants?userid={}'.format(mmid, host_id)
    url = get_url(uri)
    signature, headers = get_signature('GET', uri, "")
    r = requests.get(url, headers=headers)
    return r.status_code, r.json()
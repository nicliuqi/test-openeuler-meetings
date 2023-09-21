import datetime
import json
import logging
import requests
from django.core.management import BaseCommand
from meetings.models import Collect, Meeting, User
from meetings.utils import wx_apis

logger = logging.getLogger('log')


def send_subscribe_msg():
    logger.info('start to search meetings...')
    # 获取当前日期
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    t1 = datetime.datetime.now().strftime('%H:%M')
    t2 = (datetime.datetime.now() + datetime.timedelta(minutes=10)).strftime('%H:%M')
    # 查询当日在t1到t2时段存在的会议
    meetings = Meeting.objects.filter(is_delete=0, date=date, start__gt=t1, start__lte=t2)
    # 若存在符合条件的会议,遍历meetings对每个会议的创建人与收藏者发送订阅消息
    if meetings:
        logger.info('no meeting found, skip meeting notify.')
        return
    # 获取access_token
    access_token = wx_apis.get_token()
    for meeting in meetings:
        topic = meeting.topic
        start_time = meeting.start
        meeting_id = meeting.id
        time = date + ' ' + start_time
        mid = meeting.mid
        creater_id = meeting.user_id
        creater_openid = User.objects.get(id=creater_id).openid
        send_to_list = [creater_openid]
        # 查询该会议的收藏
        collections = Collect.objects.filter(meeting_id=meeting.id)
        # 若存在collections,遍历collections将openid添加入send_to_list
        if collections:
            for collection in collections:
                user_id = collection.user_id
                openid = User.objects.get(id=user_id).openid
                send_to_list.append(openid)
            # 发送列表去重
            send_to_list = list(set(send_to_list))
        else:
            logger.info('the meeting {} had not been added to Favorites'.format(mid))
        for openid in send_to_list:
            # 获取模板
            content = wx_apis.get_start_template(openid, meeting_id, topic, time)
            # 发送订阅消息
            url = 'https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={}'.format(
                access_token)
            r = requests.post(url, json.dumps(content))
            if r.status_code != 200:
                logger.error('status code: {}'.format(r.status_code))
                logger.error('content: {}'.format(r.json()))
            else:
                nickname = User.objects.get(openid=openid).nickname
                if r.json()['errcode'] != 0:
                    logger.warning('Error Code: {}'.format(r.json()['errcode']))
                    logger.warning('Error Msg: {}'.format(r.json()['errmsg']))
                    logger.warning('receiver: {}'.format(nickname))
                else:
                    logger.info('meeting {} subscription message sent to {}.'.format(mid, nickname))


class Command(BaseCommand):
    def handle(self, *args, **options):
        logger.info('start task')
        send_subscribe_msg()

import datetime
import json
import random
import re
import requests
import logging
import time
import sys
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.filters import SearchFilter
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin, RetrieveModelMixin, DestroyModelMixin, \
    UpdateModelMixin
from rest_framework_simplejwt import authentication
from meetings.models import User, Group, Meeting, GroupUser, Collect, Video, Record, Activity, ActivityCollect, \
    Feedback
from meetings.permissions import MaintainerPermission, AdminPermission, ActivityAdminPermission, SponsorPermission, \
        QueryPermission
from meetings.serializers import LoginSerializer, GroupsSerializer, MeetingSerializer, UsersSerializer, \
    UserSerializer, GroupUserAddSerializer, GroupSerializer, UsersInGroupSerializer, UserGroupSerializer, \
    MeetingListSerializer, GroupUserDelSerializer, UserInfoSerializer, SigsSerializer, MeetingsDataSerializer, \
    AllMeetingsSerializer, CollectSerializer, SponsorSerializer, SponsorInfoSerializer, ActivitySerializer, \
    ActivitiesSerializer, ActivityDraftUpdateSerializer, ActivityUpdateSerializer,  ActivityCollectSerializer, \
    FeedbackSerializer, ActivityRetrieveSerializer
from rest_framework.response import Response
from multiprocessing import Process
from meetings.send_email import sendmail
from rest_framework import permissions
from meetings.utils import gene_wx_code, send_feedback, invite, send_start_url, drivers
from rest_framework_simplejwt.tokens import RefreshToken
from meetings.auth import CustomAuthentication

logger = logging.getLogger('log')
offline = 1
online = 2


def refresh_access(user):
    refresh = RefreshToken.for_user(user)
    access = str(refresh.access_token)
    User.objects.filter(id-user.id).update(signature=access)
    return access


class LoginView(GenericAPIView, CreateModelMixin, ListModelMixin):
    """用户注册与授权登陆"""
    serializer_class = LoginSerializer
    queryset = User.objects.all()

    @swagger_auto_schema(operation_summary='用户注册与授权登陆')
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()


class GroupsView(GenericAPIView, ListModelMixin):
    """查询所有SIG组的名称"""
    serializer_class = GroupsSerializer
    queryset = Group.objects.all().order_by('group_name')
    filter_backends = [SearchFilter]
    search_fields = ['group_name']

    @swagger_auto_schema(operation_summary='查询所有SIG组')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class SigsView(GenericAPIView, ListModelMixin):
    """查询所有SIG组的名称、首页、邮件列表、IRC频道及成员的nickname、gitee_name、avatar"""
    serializer_class = SigsSerializer
    queryset = Group.objects.all()

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class GroupView(GenericAPIView, RetrieveModelMixin):
    """查询单个SIG组"""
    serializer_class = GroupSerializer
    queryset = Group.objects.all()

    @swagger_auto_schema(operation_summary='查询单个SIG组')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class UsersIncludeView(GenericAPIView, ListModelMixin):
    """查询所选SIG组的所有成员"""
    serializer_class = UsersInGroupSerializer
    queryset = User.objects.all()
    filter_backends = [SearchFilter]
    search_fields = ['nickname']
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='查询所选SIG组的所有成员')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            groupusers = GroupUser.objects.filter(group_id=self.kwargs['pk']).all()
            ids = [x.user_id for x in groupusers]
            user = User.objects.filter(id__in=ids)
            return user
        except KeyError:
            pass


class UsersExcludeView(GenericAPIView, ListModelMixin):
    """查询不在该组的所有成员"""
    serializer_class = UsersSerializer
    queryset = User.objects.all().order_by('nickname')
    filter_backends = [SearchFilter]
    search_fields = ['nickname']
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='查询不在该组的所有用户')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            groupusers = GroupUser.objects.filter(group_id=self.kwargs['pk']).all()
            ids = [x.user_id for x in groupusers]
            user = User.objects.filter().exclude(id__in=ids)
            return user
        except KeyError:
            pass


class UserGroupView(GenericAPIView, ListModelMixin):
    """查询该用户的SIG组以及该组的etherpad"""
    serializer_class = UserGroupSerializer
    queryset = GroupUser.objects.all()

    @swagger_auto_schema(operation_summary='查询该用户的SIG组以及该组的etherpad')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        try:
            usergroup = GroupUser.objects.filter(user_id=self.kwargs['pk']).all()
            return usergroup
        except KeyError:
            pass


class UserView(GenericAPIView, UpdateModelMixin):
    """更新用户gitee_name"""
    serializer_class = UserSerializer
    queryset = User.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='更新用户gitee_name')
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        access = refresh_access(self.request.user)
        data = serializer.data
        data['access'] = access
        response = Response()
        response.data = data
        return response


class GroupUserAddView(GenericAPIView, CreateModelMixin):
    """SIG组批量新增成员"""
    serializer_class = GroupUserAddSerializer
    queryset = GroupUser.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (AdminPermission,)

    @swagger_auto_schema(operation_summary='SIG组批量新增成员')
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        access = refresh_access(self.request.user)
        data = serializer.data
        data['access'] = access
        response = Response()
        response.data = data
        response.status = status.HTTP_201_CREATED
        response.headers = headers
        return response


class GroupUserDelView(GenericAPIView, CreateModelMixin):
    """批量删除组成员"""
    serializer_class = GroupUserDelSerializer
    queryset = GroupUser.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (AdminPermission,)

    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        group_id = self.request.data.get('group_id')
        ids = self.request.data.get('ids')
        ids_list = [int(x) for x in ids.split('-')]
        GroupUser.objects.filter(group_id=group_id, user_id__in=ids_list).delete()
        return JsonResponse({'code': 204, 'msg': '删除成功', 'access': access})


class MeetingsWeeklyView(GenericAPIView, ListModelMixin):
    """查询前后一周的所有会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.filter(is_delete=0)
    filter_backends = [SearchFilter]
    search_fields = ['topic', 'group_name']

    @swagger_auto_schema(operation_summary='查询前后一周的所有会议')
    def get(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter((Q(
            date__gte=str(datetime.datetime.now() - datetime.timedelta(days=7))[:10]) & Q(
            date__lte=str(datetime.datetime.now() + datetime.timedelta(days=7))[:10]))).order_by('-date', 'start')
        return self.list(request, *args, **kwargs)


class MeetingsDailyView(GenericAPIView, ListModelMixin):
    """查询本日的所有会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.filter(is_delete=0)

    @swagger_auto_schema(operation_summary='查询本日的所有会议')
    def get(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(date=str(datetime.datetime.now())[:10]).order_by('start')
        return self.list(request, *args, **kwargs)


class MeetingsRecentlyView(GenericAPIView, ListModelMixin):
    """查询最近的会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.filter(is_delete=0)

    @swagger_auto_schema(operation_summary='查询最近的会议')
    def get(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(date__gte=datetime.datetime.now().strftime('%Y-%m-%d')).order_by('date','start')
        return self.list(request, *args, **kwargs)


class MeetingView(GenericAPIView, RetrieveModelMixin):
    """查询会议(id)"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.filter(is_delete=0)

    @swagger_auto_schema(operation_summary='查询会议')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class MeetingDelView(GenericAPIView, DestroyModelMixin):
    """删除会议(mid)"""
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (MaintainerPermission,)

    @swagger_auto_schema(operation_summary='删除会议')
    def delete(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        mid = kwargs.get('mid')
        if not Meeting.objects.filter(mid=mid):
            resp = JsonResponse({'code': 404, 'msg': 'Not Found', 'access': access})
            resp.status_code = 404
            return resp
        if not (Meeting.objects.filter(mid=mid, user_id=self.request.user.id) or User.objects.filter(id=self.request.user.id, level=3)):
            resp = JsonResponse({'code': 401, 'msg': 'Unauthorized', 'access': access})
            resp.status_code = 401
            return resp

        mplatform = Meeting.objects.get(mid=mid).mplatform
        drivers.cancelMeeting(mid)

        # 会议作软删除
        meeting = Meeting.objects.get(mid=mid)
        Meeting.objects.filter(mid=mid).update(is_delete=1)
        meeting_id = meeting.id
        mid = meeting.mid
        logger.info('{} has canceled the meeting which mid was {}'.format(request.user.gitee_name, mid))

        # 发送删除通知邮件
        from meetings.utils.send_cancel_email import sendmail
        sendmail(mid)

        # 发送会议取消通知
        collections = Collect.objects.filter(meeting_id=meeting_id)
        if collections:
            access_token = self.get_token()
            topic = meeting.topic
            date = meeting.date
            start_time = meeting.start
            time = date + ' ' + start_time
            for collection in collections:
                user_id = collection.user_id
                user = User.objects.get(id=user_id)
                nickname = user.nickname
                openid = user.openid
                content = self.get_remove_template(openid, topic, time, mid)
                r = requests.post(
                    'https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={}'.format(access_token),
                    data=json.dumps(content))
                if r.status_code != 200:
                    logger.error('status code: {}'.format(r.status_code))
                    logger.error('content: {}'.format(r.json()))
                else:
                    if r.json()['errcode'] != 0:
                        logger.warning('Error Code: {}'.format(r.json()['errcode']))
                        logger.warning('Error Msg: {}'.format(r.json()['errmsg']))
                        logger.warning('receiver: {}'.format(nickname))
                    else:
                        logger.info('meeting {} cancel message sent to {}.'.format(mid, nickname))
                # 删除收藏
                collection.delete()
        return JsonResponse({"code": 204, "message": "Delete successfully.", "access": access})

    def get_remove_template(self, openid, topic, time, mid):
        if len(topic) > 20:
            topic = topic[:20]
        content = {
            "touser": openid,
            "template_id": "UpxRbZf8Z9QiEPlZeRCgp_MKvvqHlo6tcToY8fToK50",
            "page": "/pages/index/index",
            "miniprogram_state": "developer",
            "lang": "zh-CN",
            "data": {
                "thing1": {
                    "value": topic
                },
                "time2": {
                    "value": time
                },
                "thing4": {
                    "value": "会议{}已被取消".format(mid)
                }
            }
        }
        return content

    def get_token(self):
        appid = settings.APP_CONF['appid']
        secret = settings.APP_CONF['secret']
        url = 'https://api.weixin.qq.com/cgi-bin/token?appid={}&secret={}&grant_type=client_credential'.format(appid,
                                                                                                               secret)
        r = requests.get(url)
        if r.status_code == 200:
            try:
                access_token = r.json()['access_token']
                return access_token
            except KeyError as e:
                logger.error(e)
        else:
            logger.error(r.json())
            logger.error('fail to get access_token,exit.')
            sys.exit(1)


class UserInfoView(GenericAPIView, RetrieveModelMixin):
    """查询本机用户的level和gitee_name"""
    serializer_class = UserInfoSerializer
    queryset = User.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)

    def get(self, request, *args, **kwargs):
        user_id = kwargs.get('pk')
        if user_id != request.user.id:
            logger.warning('user_id did not match.')
            logger.warning('user_id:{}, request.user.id:{}'.format(user_id, request.user.id))
            return JsonResponse({"code": 400, "message": "错误操作，信息不匹配！"})
        return self.retrieve(request, *args, **kwargs)


class MeetingsDataView(GenericAPIView, ListModelMixin):
    """网页日历数据"""
    serializer_class = MeetingsDataSerializer
    queryset = Meeting.objects.filter(is_delete=0).order_by('start')

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset()).filter(
            date__gte=(datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d'),
            date__lte=(datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')).values()
        tableData = []
        date_list = []
        for query in queryset:
            date_list.append(query.get('date'))
        date_list = sorted(list(set(date_list)))
        records = Record.objects.all().values()
        record_dict = {}
        for record in records:
            if record['platform'] == 'bilibili' and record['url']:
                record_dict[record['mid']] = record['url']
        for date in date_list:
            timeData = []
            for meeting in queryset:
                if meeting['date'] != date:
                    continue
                timeData.append({
                    'id': meeting['id'],
                    'group_name': meeting['group_name'],
                    'startTime': meeting['start'],
                    'endTime': meeting['end'],
                    'duration_time': meeting['start'] + '-' + meeting['end'],
                    'name': meeting['topic'],
                    'creator': meeting['sponsor'],
                    'detail': meeting['agenda'],
                    'join_url': meeting['join_url'],
                    'meeting_id': meeting['mid'],
                    'etherpad': meeting['etherpad'],
                    'platform': meeting['mplatform'],
                    'video_url': record_dict.get(meeting['mid'], '')
                })
            tableData.append({
                'date': date,
                'timeData': timeData
            })
        return Response({'tableData': tableData})


class SigMeetingsDataView(GenericAPIView, ListModelMixin):
    """网页SIG组日历数据"""
    serializer_class = MeetingsDataSerializer
    queryset = Meeting.objects.filter(is_delete=0).order_by('date', 'start')

    def get(self, request, *args, **kwargs):
        group_name = kwargs.get('gn')
        queryset = self.filter_queryset(self.get_queryset()).filter(group_name=group_name).filter((Q(
            date__gte=str(datetime.datetime.now() - datetime.timedelta(days=180))[:10]) & Q(
            date__lte=str(datetime.datetime.now() + datetime.timedelta(days=30))[:10]))).values()
        tableData = []
        date_list = []
        for query in queryset:
            date_list.append(query.get('date'))
        date_list = sorted(list(set(date_list)))
        records = Record.objects.all().values()
        record_dict = {}
        for record in records:
            if record['platform'] == 'bilibili' and record['url']:
                record_dict[record['mid']] = record['url']
        for date in date_list:
            timeData = []
            for meeting in queryset:
                if meeting['date'] != date:
                    continue
                timeData.append({
                    'id': meeting['id'],
                    'group_name': meeting['group_name'],
                    'startTime': meeting['start'],
                    'endTime': meeting['end'],
                    'duration_time': meeting['start'] + '-' + meeting['end'],
                    'name': meeting['topic'],
                    'creator': meeting['sponsor'],
                    'detail': meeting['agenda'],
                    'join_url': meeting['join_url'],
                    'meeting_id': meeting['mid'],
                    'etherpad': meeting['etherpad'],
                    'platform': meeting['mplatform'],
                    'video_url': record_dict.get(meeting['mid'], '')
                })
            tableData.append({
                'date': date,
                'timeData': timeData
            })
        return Response({'tableData': tableData})


class MeetingsView(GenericAPIView, CreateModelMixin):
    """创建会议"""
    serializer_class = MeetingSerializer
    queryset = Meeting.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (MaintainerPermission,)

    @swagger_auto_schema(operation_summary='创建会议')
    def post(self, request, *args, **kwargs):
        t1 = time.time()
        access = refresh_access(self.request.user)
        # 获取data
        data = self.request.data
        try:
            platform = data['platform'] if 'platform' in data else 'zoom'
            platform = platform.lower()
            host_dict = settings.MEETING_HOSTS[platform]
            date = data['date']
            start = data['start']
            end = data['end']
            topic = data['topic']
            sponsor = data['sponsor']
            sig_name = data['group_name']
            community = data['community'] if 'community' in data else 'openeuler'
            emaillist = data['emaillist'] if 'emaillist' in data else ''
            summary = data['agenda'] if 'agenda' in data else ''
            user_id = request.user.id
            group_id = data['group_id']
            record = data['record'] if 'record' in data else ''
            etherpad = data['etherpad']
        except KeyError:
            return JsonResponse({'code': 400, 'msg': 'Bad Request', 'access': access})
        start_time = ' '.join([date, start])
        if start_time < datetime.datetime.now().strftime('%Y-%m-%d %H:%M'):
            logger.warning('The start time should not be earlier than the current time.')
            return JsonResponse({'code': 1005, 'message': '请输入正确的开始时间', 'access': access})
        if start >= end:
            logger.warning('The end time must be greater than the start time.')
            return JsonResponse({'code': 1001, 'message': '请输入正确的结束时间', 'access': access})
        start_search = datetime.datetime.strftime(
            (datetime.datetime.strptime(start, '%H:%M') - datetime.timedelta(minutes=30)),
            '%H:%M')
        end_search = datetime.datetime.strftime(
            (datetime.datetime.strptime(end, '%H:%M') + datetime.timedelta(minutes=30)),
            '%H:%M')
        # 查询待创建的会议与现有的预定会议是否冲突
        unavailable_host_id = []
        available_host_id = []
        meetings = Meeting.objects.filter(is_delete=0, date=date, end__gt=start_search, start__lt=end_search, mplatform=platform).values()
        try:
            for meeting in meetings:
                host_id = meeting['host_id']
                unavailable_host_id.append(host_id)
            logger.info('unavilable_host_id:{}'.format(unavailable_host_id))
        except KeyError:
            pass
        host_list = list(host_dict.keys())
        logger.info('host_list:{}'.format(host_list))
        for host_id in host_list:
            if host_id not in unavailable_host_id:
                available_host_id.append(host_id)
        logger.info('avilable_host_id:{}'.format(available_host_id))
        if len(available_host_id) == 0:
            logger.warning('{}暂无可用host'.format(platform))
            return JsonResponse({'code': 1000, 'message': '暂无可用host,请前往官网查看预定会议', 'access': access})
        # 从available_host_id中随机生成一个host_id,并在host_dict中取出
        host_id = random.choice(available_host_id)
        host = host_dict[host_id]
        logger.info('host_id:{}'.format(host_id))
        logger.info('host:{}'.format(host))

        status, content = drivers.createMeeting(platform, date, start, end, topic, host, record)
        if status not in [200, 201]:
            return JsonResponse({'code': 400, 'msg': 'Bad Request', 'access': access})
        mid = content['mid']
        start_url = content['start_url']
        join_url = content['join_url']
        host_id = content['host_id']
        timezone = content['timezone'] if 'timezone' in content else 'Asia/Shanghai'

        # 数据库生成数据
        Meeting.objects.create(
            mid=mid,
            topic=data['topic'],
            community=community,
            sponsor=data['sponsor'],
            group_name=data['group_name'],
            date=date,
            start=start,
            end=end,
            etherpad=data['etherpad'],
            emaillist=emaillist,
            timezone=timezone,
            agenda=data['agenda'] if 'agenda' in data else '',
            host_id=host_id,
            join_url=join_url,
            start_url=start_url,
            user_id=user_id,
            group_id=group_id,
            mplatform=platform
        )
        logger.info('{} has created a {} meeting which mid is {}.'.format(sponsor, platform, mid))
        logger.info('meeting info: {},{}-{},{}'.format(date, start, end, topic))

        # 发送email
        m = {
            'mid': mid,
            'topic': topic,
            'date': date,
            'start': start,
            'end': end,
            'join_url': join_url,
            'sig_name': sig_name,
            'emaillist': emaillist,
            'platform': platform,
            'etherpad': etherpad,
            'agenda': summary
        }
        p1 = Process(target=sendmail, args=(m, record))
        p1.start()

        # 如果开启录制功能，则在Video表中创建一条数据
        if record == 'cloud':
            Video.objects.create(
                mid=mid,
                topic=data['topic'],
                community=community,
                group_name=data['group_name'],
                agenda=data['agenda'] if 'agenda' in data else ''
            )
            logger.info('meeting {} was created with auto recording.'.format(mid))

        # 返回请求数据
        resp = {'code': 201, 'message': '创建成功', 'access': access}
        meeting = Meeting.objects.get(mid=mid)
        resp['id'] = meeting.id
        t3 = time.time()
        print('total waste: {}'.format(t3 - t1))
        return JsonResponse(resp)


class MyMeetingsView(GenericAPIView, ListModelMixin):
    """查询我创建的所有会议"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.all().filter(is_delete=0)
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (authentication.JWTAuthentication,)

    @swagger_auto_schema(operation_summary='查询我创建的所有会议')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        user_id = self.request.user.id
        queryset = Meeting.objects.filter(is_delete=0, user_id=user_id).order_by('-date', 'start')
        if User.objects.get(id=user_id).level == 3:
            queryset = Meeting.objects.filter(is_delete=0).order_by('-date', 'start')
        return queryset


class AllMeetingsView(GenericAPIView, ListModelMixin):
    """列出所有会议"""
    serializer_class = AllMeetingsSerializer
    queryset = Meeting.objects.all()
    filter_backends = [SearchFilter]
    search_fields = ['is_delete', 'group_name', 'sponsor', 'date', 'start', 'end']
    permission_classes = (QueryPermission,)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class CollectView(GenericAPIView, ListModelMixin, CreateModelMixin):
    """收藏会议"""
    serializer_class = CollectSerializer
    queryset = Collect.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (CustomAuthentication,)

    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        user_id = self.request.user.id
        meeting_id = self.request.data['meeting']
        if not meeting_id:
            return JsonResponse({'code': 400, 'msg': 'meeting不能为空', 'access': access})
        if not Collect.objects.filter(meeting_id=meeting_id, user_id=user_id):
            Collect.objects.create(meeting_id=meeting_id, user_id=user_id)
        collection_id = Collect.objects.get(meeting_id=meeting_id, user_id=user_id).id
        resp = {'code': 201, 'msg': 'collect successfully', 'collection_id': collection_id, 'access': access}
        return JsonResponse(resp)

    def get_queryset(self):
        queryset = Collect.objects.filter(user_id=self.request.user.id)
        return queryset


class CollectDelView(GenericAPIView, DestroyModelMixin):
    """取消收藏"""
    serializer_class = CollectSerializer
    queryset = Collect.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (CustomAuthentication,)

    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        access = refresh_access(self.request.user)
        response = Response()
        response.data = {'access': access}
        response.status = status.HTTP_204_NO_CONTENT
        return response

    def get_queryset(self):
        queryset = Collect.objects.filter(user_id=self.request.user.id)
        return queryset


class MyCollectionsView(GenericAPIView, ListModelMixin):
    """我收藏的会议(列表)"""
    serializer_class = MeetingListSerializer
    queryset = Meeting.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (authentication.JWTAuthentication,)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        user_id = self.request.user.id
        collection_lst = Collect.objects.filter(user_id=user_id).values_list('meeting', flat=True)
        queryset = Meeting.objects.filter(is_delete=0, id__in=collection_lst).order_by('-date', 'start')
        return queryset


class ParticipantsView(GenericAPIView, RetrieveModelMixin):
    """查询会议的参会者"""
    permission_classes = (QueryPermission,)

    def get(self, request, *args, **kwargs):
        mid = kwargs.get('mid')
        status, res = drivers.getParticipants(mid)
        if status == 200:
            return JsonResponse(res)
        else:
            resp = JsonResponse(res)
            resp.status_code = 400
            return resp


class SponsorsView(GenericAPIView, ListModelMixin):
    """活动发起人列表"""
    serializer_class = SponsorSerializer
    queryset = User.objects.filter(activity_level=2)
    filter_backends = [SearchFilter]
    search_fields = ['nickname']
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='活动发起人列表')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class NonSponsorView(GenericAPIView, ListModelMixin):
    """非活动发起人列表"""
    serializer_class = SponsorSerializer
    queryset = User.objects.filter(activity_level=1)
    filter_backends = [SearchFilter]
    search_fields = ['nickname']
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='非活动发起人列表')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class SponsorAddView(GenericAPIView, CreateModelMixin):
    """批量添加活动发起人"""
    queryset = User.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='批量添加活动发起人')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        ids = self.request.data.get('ids')
        ids_list = [int(x) for x in ids.split('-')]
        User.objects.filter(id__in=ids_list, activity_level=1).update(activity_level=2)
        return JsonResponse({'code': 201, 'msg': '添加成功', 'access': access})


class SponsorDelView(GenericAPIView, CreateModelMixin):
    """批量删除组成员"""
    queryset = GroupUser.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='批量删除活动发起人')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        ids = self.request.data.get('ids')
        ids_list = [int(x) for x in ids.split('-')]
        User.objects.filter(id__in=ids_list, activity_level=2).update(activity_level=1)
        return JsonResponse({'code': 204, 'msg': '删除成功', 'access': access})


class SponsorInfoView(GenericAPIView, UpdateModelMixin):
    """修改活动发起人信息"""
    serializer_class = SponsorInfoSerializer
    queryset = User.objects.filter(activity_level=2)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='修改活动发起人信息')
    def put(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        access = refresh_access(self.request.user)
        data = serializer.data
        data['access'] = access
        response = Response()
        response.data = data
        return response


class DraftsView(GenericAPIView, ListModelMixin):
    """审核列表"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.filter(is_delete=0, status=2)
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='审核列表')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class DraftView(GenericAPIView, RetrieveModelMixin):
    """待发布详情"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.filter(is_delete=0, status=2)
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='待发布详情')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class ActivityView(GenericAPIView, CreateModelMixin):
    """创建活动并申请发布"""
    serializer_class = ActivitySerializer
    queryset = Activity.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='创建活动并申请发布')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        data = self.request.data
        title = data['title']
        date = data['date']
        if date < (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d'):
            return JsonResponse({'code': 400, 'msg': '请最早提前一天申请活动', 'access': access})
        activity_type = data['activity_type']
        synopsis = data['synopsis'] if 'synopsis' in data else None
        poster = data['poster']
        user_id = self.request.user.id
        enterprise = User.objects.get(id=user_id).enterprise
        register_url = data.get('register_url', '')
        # 线下活动
        if activity_type == offline:
            address = data['address']
            detail_address = data['detail_address']
            longitude = data['longitude']
            latitude = data['latitude']
            Activity.objects.create(
                title=title,
                date=date,
                activity_type=activity_type,
                synopsis=synopsis,
                address=address,
                detail_address=detail_address,
                longitude=longitude,
                latitude=latitude,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                user_id=user_id,
                status=2,
                enterprise=enterprise,
                register_url=register_url
            )
        # 线上活动
        if activity_type == online:
            start = data['start']
            end = data['end']
            Activity.objects.create(
                title=title,
                date=date,
                start=start,
                end=end,
                activity_type=activity_type,
                synopsis=synopsis,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                user_id=user_id,
                status=2,
                enterprise=enterprise,
                register_url=register_url
            )
        return JsonResponse({'code': 201, 'msg': '活动申请发布成功！', 'access': access})


class ActivitiesView(GenericAPIView, ListModelMixin):
    """活动列表"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.filter(is_delete=0, status__gt=2).order_by('-date', 'id')
    filter_backends = [SearchFilter]
    search_fields = ['title', 'enterprise']

    @swagger_auto_schema(operation_summary='活动列表')
    def get(self, request, *args, **kwargs):
        activity_status = self.request.GET.get('activity')
        activity_type = self.request.GET.get('activity_type')
        if activity_status == 'registering':
            self.queryset = self.queryset.filter(status__in=[3, 4])
        if activity_status == 'going':
            self.queryset = self.queryset.filter(status=4)
        if activity_status == 'completed':
            self.queryset = self.queryset.filter(status=5)
        if activity_type:
            try:
                if int(activity_type) == 1:
                    self.queryset = self.queryset.filter(activity_type=1)
                if int(activity_type) == 2:
                    self.queryset = self.queryset.filter(activity_type=2)
                if int(activity_type) == 1 and activity_status == 'registering':
                    self.queryset = self.queryset.filter(activity_type=1, status__in=[3, 4])
                if int(activity_type) == 1 and activity_status == 'going':
                    self.queryset = self.queryset.filter(activity_type=1, status=4)
                if int(activity_type) == 1 and activity_status == 'completed':
                    self.queryset = self.queryset.filter(activity_type=1, status=5)
                if int(activity_type) == 2 and activity_status == 'registering':
                    self.queryset = self.queryset.filter(activity_type=2, status__in=[3, 4])
                if int(activity_type) == 2 and activity_status == 'going':
                    self.queryset = self.queryset.filter(activity_type=2, status=4)
                if int(activity_type) == 2 and activity_status == 'completed':
                    self.queryset = self.queryset.filter(activity_type=2, status=5)
            except TypeError:
                pass
        return self.list(request, *args, **kwargs)


class RecentActivitiesView(GenericAPIView, ListModelMixin):
    """最近的活动列表"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.filter(is_delete=0)
    filter_backends = [SearchFilter]
    search_fields = ['enterprise']

    @swagger_auto_schema(operation_summary='最近的活动列表')
    def get(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(status__gt=2, date__gt=datetime.datetime.now().strftime('%Y-%m-%d')).order_by('-date', 'id')
        return self.list(request, *args, **kwargs)


class SponsorActivitiesView(GenericAPIView, ListModelMixin):
    """活动发起人的活动列表"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='我(活动发起人)的活动列表')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Activity.objects.filter(is_delete=0, status__gt=2, user_id=self.request.user.id)
        return queryset


class ActivityRetrieveView(GenericAPIView, RetrieveModelMixin):
    """查询单个活动"""
    serializer_class = ActivityRetrieveSerializer
    queryset = Activity.objects.filter(is_delete=0, status__gt=2)

    @swagger_auto_schema(operation_summary='查询一个活动')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class ActivityUpdateView(GenericAPIView, UpdateModelMixin):
    """修改一个活动"""
    serializer_class = ActivityUpdateSerializer
    queryset = Activity.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='修改活动')
    def put(self, request, *args, **kwargs):
        activity_id = self.kwargs.get('pk')
        mid = Activity.objects.get(id=activity_id).mid
        schedules = self.request.data['schedules']
        invite.add_panelists(mid, schedules)
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        access = refresh_access(self.request.user)
        data = serializer.data
        data['access'] = access
        response = Response()
        response.data = data
        return response

    def get_queryset(self):
        user_id = self.request.user.id
        activity_level = User.objects.get(id=user_id).activity_level
        queryset = Activity.objects.filter(is_delete=0, status__in=[3, 4], user_id=self.request.user.id)
        if activity_level == 3:
            queryset = Activity.objects.filter(is_delete=0, status__in=[3, 4])
        return queryset


class ActivityPublishView(GenericAPIView, UpdateModelMixin):
    """通过申请"""
    queryset = Activity.objects.filter(is_delete=0, status=2)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='活动过审')
    def put(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        activity_id = self.kwargs.get('pk')
        appid = settings.APP_CONF['appid']
        secret = settings.APP_CONF['secret']
        if activity_id in self.queryset.values_list('id', flat=True):
            logger.info('活动id: {}'.format(activity_id))
            img_url = gene_wx_code.run(appid, secret, activity_id)
            logger.info('生成活动页面二维码: {}'.format(img_url))
            Activity.objects.filter(id=activity_id, status=2).update(status=3, wx_code=img_url)
            logger.info('活动通过审核')
            return JsonResponse({'code': 201, 'msg': '活动通过审核，已发布', 'access': access})
        else:
            return JsonResponse({'code': 404, 'msg': '无此数据', 'access': access})


class ActivityRejectView(GenericAPIView, UpdateModelMixin):
    """驳回申请"""
    queryset = Activity.objects.filter(is_delete=0, status=2)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='驳回申请')
    def put(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        activity_id = self.kwargs.get('pk')
        if activity_id in self.queryset.values_list('id', flat=True):
            Activity.objects.filter(id=activity_id, status=2).update(status=1)
            return JsonResponse({'code': 201, 'msg': '活动申请已驳回', 'access': access})
        else:
            return JsonResponse({'code': 404, 'msg': '无此数据', 'access': access})


class ActivityDelView(GenericAPIView, UpdateModelMixin):
    """删除一个活动"""
    queryset = Activity.objects.filter(is_delete=0, status__gt=2)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (ActivityAdminPermission,)

    @swagger_auto_schema(operation_summary='删除活动')
    def put(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        activity_id = self.kwargs.get('pk')
        Activity.objects.filter(id=activity_id).update(is_delete=1)
        return JsonResponse({'code': 204, 'msg': '成功删除活动', 'access': access})


class ActivityDraftView(GenericAPIView, CreateModelMixin):
    """创建活动草案"""
    serializer_class = ActivitySerializer
    queryset = Activity.objects.all()
    authentication_classes = (CustomAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='创建活动草案')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        data = self.request.data
        title = data['title']
        date = data['date']
        if date < (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d'):
            return JsonResponse({'code': 400, 'msg': '请最早提前一天申请活动', 'access': access})
        activity_type = data['activity_type']
        synopsis = data['synopsis'] if 'synopsis' in data else None
        poster = data['poster']
        user_id = self.request.user.id
        enterprise = User.objects.get(id=user_id).enterprise
        register_url = data.get('register_url')
        # 线下活动
        if activity_type == offline:
            address = data['address']
            detail_address = data['detail_address']
            longitude = data['longitude']
            latitude = data['latitude']
            Activity.objects.create(
                title=title,
                date=date,
                activity_type=activity_type,
                synopsis=synopsis,
                address=address,
                detail_address=detail_address,
                longitude=longitude,
                latitude=latitude,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                user_id=user_id,
                enterprise=enterprise,
                register_url=register_url
            )
        # 线上活动
        if activity_type == online:
            start = data['start']
            end = data['end']
            Activity.objects.create(
                title=title,
                date=date,
                start=start,
                end=end,
                activity_type=activity_type,
                synopsis=synopsis,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                user_id=user_id,
                enterprise=enterprise,
                register_url=register_url
            )
        return JsonResponse({'code': 201, 'msg': '活动草案创建成功！', 'access': access})


class ActivitiesDraftView(GenericAPIView, ListModelMixin):
    """活动草案列表"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='我(活动发起人)的活动草案列表')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Activity.objects.filter(is_delete=0, status=1, user_id=self.request.user.id).order_by('-date', 'id')
        return queryset


class SponsorActivityDraftView(GenericAPIView, RetrieveModelMixin, DestroyModelMixin):
    """查询、删除活动草案"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='查询一个活动草案')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    @swagger_auto_schema(operation_summary='删除活动草案')
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        access = refresh_access(self.request.user)
        response = Response()
        response.data = {'access': access}
        response.status = status.HTTP_204_NO_CONTENT
        return response

    def get_queryset(self):
        queryset = Activity.objects.filter(is_delete=0, status=1, user_id=self.request.user.id).order_by('-date', 'id')
        return queryset


class DraftUpdateView(GenericAPIView, UpdateModelMixin):
    """修改活动草案"""
    serializer_class = ActivityDraftUpdateSerializer
    queryset = Activity.objects.filter(is_delete=0, status=1)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (SponsorPermission,)

    def put(self, reuqest, *args, **kwargs):
        access = refresh_access(self.request.user)
        activity_id = self.kwargs.get('pk')
        data = self.request.data
        title = data['title']
        date = data['date']
        activity_type = data['activity_type']
        synopsis = data['synopsis'] if 'synopsis' in data else None
        poster = data['poster']
        user_id = self.request.user.id
        register_url = data.get('register_url')
        if activity_type == offline:
            address = data['address']
            detail_address = data['detail_address']
            longitude = data['longitude']
            latitude = data['latitude']
            Activity.objects.filter(id=activity_id, user_id=user_id).update(
                title=title,
                date=date,
                activity_type=activity_type,
                synopsis=synopsis,
                address=address,
                detail_address=detail_address,
                longitude=longitude,
                latitude=latitude,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                register_url=register_url
            )
        if activity_type == online:
            start = data['start']
            end = data['end']
            Activity.objects.filter(id=activity_id, user_id=user_id).update(
                title=title,
                date=date,
                start=start,
                end=end,
                activity_type=activity_type,
                synopsis=synopsis,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                register_url=register_url
            )
        return JsonResponse({'code': 201, 'msg': '修改并保存活动草案', 'access': access})


class DraftPublishView(GenericAPIView, UpdateModelMixin):
    """修改活动草案并申请发布"""
    serializer_class = ActivityDraftUpdateSerializer
    queryset = Activity.objects.filter(is_delete=0, status=1)
    authentication_classes = (CustomAuthentication,)
    permission_classes = (SponsorPermission,)

    def put(self, reuqest, *args, **kwargs):
        access = refresh_access(self.request.user)
        activity_id = self.kwargs.get('pk')
        data = self.request.data
        title = data['title']
        date = data['date']
        activity_type = data['activity_type']
        synopsis = data['synopsis'] if 'synopsis' in data else None
        poster = data['poster']
        user_id = self.request.user.id
        if activity_type == offline:
            address = data['address']
            detail_address = data['detail_address']
            longitude = data['longitude']
            latitude = data['latitude']
            Activity.objects.filter(id=activity_id, user_id=user_id).update(
                title=title,
                date=date,
                activity_type=activity_type,
                synopsis=synopsis,
                address=address,
                detail_address=detail_address,
                longitude=longitude,
                latitude=latitude,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                status=2
            )
        if activity_type == online:
            start = data['start']
            end = data['end']
            Activity.objects.filter(id=activity_id, user_id=user_id).update(
                title=title,
                date=date,
                start=start,
                end=end,
                activity_type=activity_type,
                synopsis=synopsis,
                schedules=json.dumps(data['schedules']),
                poster=poster,
                status=2
            )
        return JsonResponse({'code': 201, 'msg': '申请发布活动', 'access': access})


class SponsorActivitiesPublishingView(GenericAPIView, ListModelMixin):
    """发布中的活动"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.all()
    authentication_classes = (authentication.JWTAuthentication,)
    permission_classes = (SponsorPermission,)

    @swagger_auto_schema(operation_summary='发布中(个人)的活动')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Activity.objects.filter(is_delete=0, status=2, user_id=self.request.user.id).order_by('-date', 'id')
        return queryset


class ActivityCollectView(GenericAPIView, CreateModelMixin):
    """收藏活动"""
    serializer_class = ActivityCollectSerializer
    queryset = ActivityCollect.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (CustomAuthentication,)

    @swagger_auto_schema(operation_summary='收藏活动')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        user_id = self.request.user.id
        activity_id = self.request.data['activity']
        ActivityCollect.objects.create(activity_id=activity_id, user_id=user_id)
        return JsonResponse({'code': 201, 'msg': '收藏活动', 'access': access})


class ActivityCollectDelView(GenericAPIView, DestroyModelMixin):
    """取消收藏活动"""
    serializer_class = ActivityCollectSerializer
    queryset = ActivityCollect.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (CustomAuthentication,)

    @swagger_auto_schema(operation_summary='取消收藏活动')
    def delete(self, request, *args, **kwargs):
        return self.destroy(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        access = refresh_access(self.request.user)
        response = Response()
        response.data = {'access': access}
        response.status = status.HTTP_204_NO_CONTENT
        return response

    def get_queryset(self):
        queryset = ActivityCollect.objects.filter(user_id=self.request.user.id)
        return queryset


class MyActivityCollectionsView(GenericAPIView, ListModelMixin):
    """我收藏的活动(列表)"""
    serializer_class = ActivitiesSerializer
    queryset = Activity.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (authentication.JWTAuthentication,)

    @swagger_auto_schema(operation_summary='我收藏的活动')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        user_id = self.request.user.id
        collection_lst = ActivityCollect.objects.filter(user_id=user_id).values_list('activity', flat=True)
        queryset = Activity.objects.filter(is_delete=0, id__in=collection_lst).order_by('-date', 'id')
        return queryset


class FeedbackView(GenericAPIView, CreateModelMixin):
    """意见反馈"""
    serializer_class = FeedbackSerializer
    queryset = Feedback.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (CustomAuthentication,)

    @swagger_auto_schema(operation_summary='意见反馈')
    def post(self, request, *args, **kwargs):
        access = refresh_access(self.request.user)
        data = self.request.data
        try:
            feedback_type = data['feedback_type']
            feedback_content = data['feedback_content']
            feedback_email = data['feedback_email']
            if not re.match(r'^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$', feedback_email):
                return JsonResponse({'code': 400, 'msg': '请填入正确的收件邮箱', 'access': access})
            user_id = self.request.user.id
            Feedback.objects.create(
                feedback_type=feedback_type,
                feedback_content=feedback_content,
                feedback_email=feedback_email,
                user_id=user_id
            )
            if feedback_type == 1:
                feedback_type = '问题反馈'
            if feedback_type == 2:
                feedback_type = '产品建议'
            send_feedback.run(feedback_type, feedback_email, feedback_content)
            return JsonResponse({'code': 201, 'msg': '反馈意见已收集', 'access': access})
        except KeyError:
            return JsonResponse(
                {'code': 400, 'msg': 'feedback_type, feedback_content and feedback_email are all required!', 'access':
                 access})


class CountActivitiesView(GenericAPIView, ListModelMixin):
    """各类活动计数"""
    queryset = Activity.objects.filter(is_delete=0, status__gt=2).order_by('-date', 'id')
    filter_backends = [SearchFilter]
    search_fields = ['title', 'enterprise']

    @swagger_auto_schema(operation_summary='各类活动计数')
    def get(self, request, *args, **kwargs):
        search = self.request.GET.get('search')
        activity_type = self.request.GET.get('activity_type')
        if search and not activity_type:
            self.queryset = self.queryset.filter(Q(title__icontains=search) | Q(enterprise__icontains=search))
        if activity_type:
            try:
                if int(activity_type) == 1:
                    self.queryset = self.queryset.filter(activity_type=1)
                if int(activity_type) == 2:
                    self.queryset = self.queryset.filter(activity_type=2)
                if int(activity_type) == 1 and search:
                    self.queryset = self.queryset.filter(activity_type=1).filter(
                        Q(title__icontains=search) | Q(enterprise__icontains=search))
                if int(activity_type) == 2 and search:
                    self.queryset = self.queryset.filter(activity_type=2).filter(
                        Q(title__icontains=search) | Q(enterprise__icontains=search))
            except TypeError:
                pass
        all_activities_count = len(self.queryset.filter(is_delete=0, status__gt=2).values())
        registering_activities_count = len(self.queryset.filter(is_delete=0, status__in=[3, 4]).values())
        going_activities_count = len(self.queryset.filter(is_delete=0, status=4).values())
        completed_activities_count = len(self.queryset.filter(is_delete=0, status=5).values())
        res = {'all_activities_count': all_activities_count,
               'registering_activities_count': registering_activities_count,
               'going_activities_count': going_activities_count,
               'completed_activities_count': completed_activities_count}
        return JsonResponse(res)


class MyCountsView(GenericAPIView, ListModelMixin):
    """我的各类计数"""
    queryset = Activity.objects.all()
    permission_classes = (permissions.IsAuthenticated,)
    authentication_classes = (authentication.JWTAuthentication,)

    @swagger_auto_schema(operation_summary='我的各类计数')
    def get(self, request, *args, **kwargs):
        user_id = self.request.user.id
        user = User.objects.get(id=user_id)
        level = user.level
        activity_level = user.activity_level

        # shared
        collected_meetings_count = len(Meeting.objects.filter(is_delete=0, id__in=(
            Collect.objects.filter(user_id=user_id).values_list('meeting_id', flat=True))).values())
        collected_activities_count = len(Activity.objects.filter(is_delete=0, id__in=(
            ActivityCollect.objects.filter(user_id=user_id).values_list('activity_id', flat=True))).values())
        res = {'collected_meetings_count': collected_meetings_count,
               'collected_activities_count': collected_activities_count}
        # permission limited
        if level == 2:
            created_meetings_count = len(Meeting.objects.filter(is_delete=0, user_id=user_id).values())
            res['created_meetings_count'] = created_meetings_count
        if level == 3:
            created_meetings_count = len(Meeting.objects.filter(is_delete=0).values())
            res['created_meetings_count'] = created_meetings_count
        if activity_level == 2:
            published_activities_count = len(
                Activity.objects.filter(is_delete=0, status__gt=2, user_id=user_id).values())
            drafts_count = len(Activity.objects.filter(is_delete=0, status=1, user_id=user_id).values())
            publishing_activities_count = len(Activity.objects.filter(is_delete=0, status=2, user_id=user_id).values())
            res['published_activities_count'] = published_activities_count
            res['drafts_count'] = drafts_count
            res['publishing_activities_count'] = publishing_activities_count
        if activity_level == 3:
            published_activities_count = len(Activity.objects.filter(is_delete=0, status__gt=2).values())
            drafts_count = len(Activity.objects.filter(is_delete=0, status=1, user_id=user_id).values())
            publishing_activities_count = len(Activity.objects.filter(is_delete=0, status=2).values())
            res['published_activities_count'] = published_activities_count
            res['drafts_count'] = drafts_count
            res['publishing_activities_count'] = publishing_activities_count
        return JsonResponse(res)


class ActivitiesDataView(GenericAPIView, ListModelMixin):
    """活动日历数据"""
    queryset = Activity.objects.filter(is_delete=0, status__in=[3, 4, 5])

    def get(self, request, *args, **kwargs):
        self.queryset = self.queryset.filter(
            date__gte=(datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d'),
            date__lte=(datetime.datetime.now() + datetime.timedelta(days=180)).strftime('%Y-%m-%d'))
        queryset = self.filter_queryset(self.get_queryset()).values()
        tableData = [] 
        date_list = [] 
        for query in queryset:
            date_list.append(query.get('date'))
        date_list = sorted(list(set(date_list)))
        for date in date_list:
            tableData.append(
                {    
                    'start_date': date,
                    'timeData': [{
                        'id': activity.id,
                        'title': activity.title,
                        'start_date': activity.date,
                        'end_date': activity.date,
                        'activity_type': activity.activity_type,
                        'address': activity.address,
                        'detail_address': activity.detail_address,
                        'longitude': activity.longitude,
                        'latitude': activity.latitude,
                        'synopsis': activity.synopsis,
                        'sign_url': activity.sign_url,
                        'replay_url': activity.replay_url,
                        'register_url': activity.register_url,
                        'poster': activity.poster,
                        'wx_code': activity.wx_code,
                        'schedules': json.loads(activity.schedules)
                    } for activity in Activity.objects.filter(is_delete=0, date=date)]
                }    
            )    
        return Response({'tableData': tableData})


class AgreePrivacyPolicyView(GenericAPIView, UpdateModelMixin):
    authentication_classes = (CustomAuthentication,)
    permission_classes = (permissions.IsAuthenticated,)

    def put(self, request, *args, **kwargs):
        now_time = datetime.datetime.now()
        access = refresh_access(self.request.user)
        if User.objects.get(id=self.request.user.id).agree_privacy_policy:
            resp = JsonResponse({
                'code': 400,
                'msg': 'The user has signed privacy policy agreement already.',
                'access': access
            })
            return resp
        User.objects.filter(id=self.request.user.id).update(agree_privacy_policy=True,
                                                            agree_privacy_policy_time=now_time)
        resp = JsonResponse({
            'code': 201,
            'msg': 'Updated',
            'access': access
        })
        return resp
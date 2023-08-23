from meetings.models import Meeting
from meetings.utils import zoom_apis, welink_apis, tencent_apis


def createMeeting(platform, date, start, end, topic, host, record):
    status, content = (None, None)
    if platform == 'zoom':
        status, content = zoom_apis.createMeeting(date, start, end, topic, host, record)
    elif platform == 'welink':
        status, content = welink_apis.createMeeting(date, start, end, topic, host, record)
    elif platform == 'tencent':
        status, content = tencent_apis.createMeeting(date, start, end, topic, host, record)
    return status, content


def cancelMeeting(mid):
    meeting = Meeting.objects.get(mid=mid)
    mplatform = meeting.mplatform
    host_id = meeting.host_id
    status = None
    if mplatform == 'zoom':
        status = zoom_apis.cancelMeeting(mid)
    elif mplatform == 'welink':
        status = welink_apis.cancelMeeting(mid, host_id)
    elif mplatform == 'tencent':
        status = tencent_apis.cancelMeeting(mid)
    return status


def getParticipants(mid):
    meeting = Meeting.objects.get(mid=mid)
    mplatform = meeting.mplatform
    status, res = (None, None)
    if mplatform == 'zoom':
        status, res = zoom_apis.getParticipants(mid)
    elif mplatform == 'welink':
        status, res = welink_apis.getParticipants(mid)
    elif mplatform == 'tencent':
        status, res = tencent_apis.getParticipants(mid)
    return status, res


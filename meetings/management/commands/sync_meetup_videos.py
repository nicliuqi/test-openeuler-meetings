import logging
import os
import sys
import tempfile
from django.core.management import BaseCommand
from obs import ObsClient
from bilibili_api.user import get_videos_g
from bilibili_api import video, Verify
from meetings.models import Activity
from meetings.utils.meetup_html_template import cover_content

logger = logging.getLogger('log')


def download_video(obs_client, bucketName, objectKey):
    partSize = 10 * 1024 * 1024
    taskNum = 5
    enableCheckpoint = True
    tmpdir = tempfile.gettempdir()
    videoFile = os.path.join(tmpdir, os.path.basename(objectKey))
    try:
        res = obs_client.downloadFile(bucketName, objectKey, videoFile, partSize, taskNum, enableCheckpoint)
        if res.status < 300:
            return videoFile
        else:
            logger.error('下载失败')
            logger.error(res.errorCode, res.errorMessage)
    except Exception as e:
        logger.error(e)


def generate_cover(topic):
    tmpdir = tempfile.gettempdir()
    html_path = os.path.join(tmpdir, topic) + '.html'
    logger.info(html_path)
    f = open(html_path, 'w')
    content = cover_content(topic)
    f.write(content)
    f.close()
    if os.system('cp meetings/images/meetup.png {}'.format(tmpdir)) != 0:
        logger.error('fail to copy meetup cover image')
        sys.exit(1)
    imageFile = os.path.join(tmpdir, 'meetup.png')
    if os.system('wkhtmltoimage --enable-local-file-access {} {}'.format(html_path, imageFile)) != 0:
        logger.error('fail to convert html to image')
        sys.exit(1)
    logger.info('生成封面')
    return imageFile


def upload_to_bilibili(videoFile, imageFile, topic):
    sessdata = os.getenv('SESSDATA', '')
    bili_jct = os.getenv('BILI_JCT', '')
    if not sessdata or not bili_jct:
        logger.error('both sessdata and bili_jct required, please check!')
        sys.exit(1)
    verify = Verify(sessdata, bili_jct)
    # 上传视频
    filename = video.video_upload(videoFile, verify=verify)
    logger.info('视频上传B站')
    # 上传封面
    cover_url = video.video_cover_upload(imageFile, verify=verify)
    logger.info('封面上传B站')
    # 提交投稿
    data = {
        "copyright": 1,
        "cover": cover_url,
        "desc": "openEuler meetup",
        "desc_format_id": 0,
        "dynamic": "",
        "no_reprint": 1,
        "subtitles": {
            "lan": "",
            "open": 0
        },
        "tag": "openEuler, openeuler, meetup",
        "tid": 124,
        "title": topic,
        "videos": [
            {
                "desc": "openEuler meetup Record",
                "filename": os.path.basename(filename),
                "title": "P1"
            }
        ]
    }
    result = video.video_submit(data, verify=verify)
    logger.info('视频提交成功')
    return result['bvid']


class Command(BaseCommand):
    def handle(self, *args, **options):
        uid = int(os.getenv('BILI_UID', ''))
        if not uid:
            logger.error('uid is required')
            sys.exit(1)

        access_key_id = os.getenv('ACCESS_KEY_ID', '')
        secret_access_key = os.getenv('SECRET_ACCESS_KEY', '')
        endpoint = os.getenv('OBS_ENDPOINT', '')
        bucketName = os.getenv('OBS_BUCKETNAME', '')
        if not access_key_id or not secret_access_key or not endpoint or not bucketName:
            logger.error('losing required arguments for ObsClient')
            sys.exit(1)
        # 获取OBS openeuler/meetup/下的MP4列表
        obs_client = ObsClient(access_key_id=access_key_id, secret_access_key=secret_access_key,
                               server='https://{}'.format(endpoint))
        objs = obs_client.listObjects(bucketName=bucketName)['body']['contents']
        meetup_videos = []
        for obj in objs:
            if obj['key'].startswith('openeuler/meetup/') and obj['key'].endswith('.mp4'):
                meetup_videos.append(obj['key'])
        if len(meetup_videos) == 0:
            logger.info('no meetup videos in OBS')
            return
        logger.info('meetup_videos: {}'.format(meetup_videos))
        videos = get_videos_g(uid)
        bvs = [x['bvid'] for x in videos]

        遍历meetup_videos，若obj的metadata无bvid，则下载上传B站
        for video in meetup_videos:
            metadata = obs_client.getObjectMetadata(bucketName, video)
            metadata_dict = {x: y for x, y in metadata['header']}
            topic = os.path.basename(video)[:-4]
            activity_id = int(video.split('/')[2])
            replay_url = 'https://{}.{}/{}'.format(bucketName, endpoint, video)
            Activity.objects.filter(id=activity_id).update(replay_url=replay_url)
            logger.info('meetup回放视频同步小程序，回放链接: {}'.format(replay_url))
            if 'bvid' not in metadata_dict.keys():
                # 下载视频
                logger.info('开始下载视频')
                videoFile = download_video(obs_client, bucketName, video)
                logger.info('视频已下载: {}'.format(videoFile))
                # 生成封面
                logger.info('开始生成封面')
                logger.info('topic: {}'.format(topic))
                imageFile = generate_cover(topic)
                logger.info('封面已生成: {}'.format(imageFile))
                # 上传B站
                logger.info('开始上传B站')
                bvid = upload_to_bilibili(videoFile, imageFile, topic)
                logger.info('B站上传成功，bvid: {}'.format(bvid))
                # 更新metadata
                metadata = {
                    'bvid': bvid
                }
                r = obs_client.setObjectMetadata(bucketName, video, metadata)
                if r.status < 300:
                    logger.info('更新metadata')
                else:
                    logger.error(r.errorCode, r.errorMessage)


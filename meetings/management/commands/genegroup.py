import requests
import lxml
import time
import logging
import os
import sys
import yaml
from lxml.etree import HTML
from meetings.models import Group
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import connection


class Command(BaseCommand):
    logger = logging.getLogger('log')

    def handle(self, *args, **options):
        os.system('test -d community && rm -rf community')
        os.system('git clone https://gitee.com/openeuler/community.git')
        access_token = settings.CI_BOT_TOKEN
        genegroup_auth = os.getenv('GENEGROUP_AUTH', '')
        if not access_token:
            self.logger.error('missing CI_BOT_TOKEN, exit...')
            sys.exit(1)
        if not genegroup_auth:
            self.logger.error('missing GENEGROUP_AUTH, exit...')
            sys.exit(1)
        t1 = time.time()
        self.logger.info('Starting to genegroup...')
        mail_lists = []
        headers = {
            'Authorization': os.getenv('GENEGROUP_AUTH', '')
        }
        r = requests.get('https://www.openeuler.org/api/mail/list', headers=headers)
        if r.status_code == 401:
            self.logger.error('401 Unauthorized. Do check GENEGROUP_AUTH!')
            sys.exit(1)
        if r.status_code == 200:
            mail_lists = [x['fqdn_listname'] for x in r.json()['entries']]

        sigs = []
        for i in os.listdir('community/sig'):
            if i in ['README.md', 'sig-recycle', 'sig-template', 'create_sig_info_template.py']:
                continue
            sigs.append({'name': i})
        sigs_list = []
        for sig in sigs:
            sig_name = sig['name']
            sig_page = 'https://gitee.com/openeuler/community/tree/master/sig/{}'.format(sig_name)
            etherpad = 'https://etherpad.openeuler.org/p/{}-meetings'.format(sig_name)
            if Group.objects.filter(group_name=sig_name):
                etherpad = Group.objects.get(group_name=sig_name).etherpad
            sigs_list.append([sig_name, sig_page, etherpad])
        sigs_list = sorted(sigs_list)
        t2 = time.time()
        self.logger.info('Has got sigs_list, wasted time: {}'.format(t2 - t1))

        # 获取所有owner对应sig的字典owners_sigs
        # 定义owners集合
        owners = set()
        owners_sigs = {}
        maintainer_dict = {}
        for sig in sigs_list:
            maintainers = []
            owner_file = 'community/sig/{}/OWNERS'.format(sig[0])
            if os.path.exists(owner_file):
                with open('community/sig/{}/OWNERS'.format(sig[0]), 'r') as f:
                    user_infos = yaml.load(f.read(), Loader=yaml.Loader)['maintainers']
            else:
                sig_info_file = 'community/sig/{}/sig-info.yaml'.format(sig[0])
                if not os.path.exists(sig_info_file):
                    self.logger.error('sig-info.yaml is required when OWNERS file does not exist.')
                    sys.exit(1)
                with open(sig_info_file, 'r') as f:
                    sig_info = yaml.load(f.read(), Loader=yaml.Loader)
                    user_infos = [maintainer['gitee_id'] for maintainer in sig_info['maintainers']]
            for maintainer in user_infos:
                maintainers.append(maintainer)
                owners.add(maintainer)
            maintainer_dict[sig[0]] = maintainers
        # 初始化owners_sigs
        for owner in owners:
            owners_sigs[owner] = []
        # 遍历sigs_list,添加在该sig中的owner所对应的sig
        for sig in sigs_list:
            for owner in owners:
                if owner in maintainer_dict[sig[0]]:
                    owners_sigs[owner].append(sig[0])

        t3 = time.time()
        self.logger.info('Has got owners_sigs, wasted time: {}'.format(t3 - t2))

        for sig in sigs_list:
            # 获取邮件列表
            r = requests.get(sig[1])
            html = HTML(r.text)
            assert isinstance(html, lxml.etree._Element)
            try:
                maillist = html.xpath('//li[contains(text(), "邮件列表")]/a/@href')[0].rstrip('/').split('/')[-1].replace('mailto:', '')
            except IndexError:
                try:
                    maillist = html.xpath('//a[contains(text(), "邮件列表")]/@href')[0].rstrip('/').split('/')[-1].replace('mailto:', '')
                    if '@' not in maillist:
                        maillist = html.xpath('//a[contains(@href, "@openeuler.org")]/text()')[0]
                except IndexError:
                    maillist = 'dev@openeuler.org'
            if html.xpath('//*[contains(text(), "maillist")]/a'):
                maillist = html.xpath('//*[contains(text(), "maillist")]/a')[0].text
            elif html.xpath('//*[contains(text(), "Mail")]/a'):
                maillist = html.xpath('//*[contains(text(), "Mail")]/a')[0].text
            if mail_lists and maillist and maillist.endswith('@openeuler.org') and maillist not in mail_lists:
                maillist = 'dev@openeuler.org'
            if not maillist:
                maillist = 'dev@openeuler.org'
            sig.append(maillist)

            # 获取IRC频道
            try:
                irc = html.xpath('//a[contains(text(), "IRC频道")]/@href')[0]
            except IndexError:
                try:
                    irc = html.xpath('//a[contains(text(), "IRC")]/@href')[0]
                except IndexError:
                    try:
                        irc = html.xpath('//*[contains(text(), "IRC")]/text()')[0].split(':')[1].strip().rstrip(')')
                    except IndexError:
                        irc = '#openeuler-dev'
            if '#' not in irc:
                irc = '#openeuler-dev'
            sig.append(irc)

            # 获取owners
            maintainers = []
            owner_file = 'community/sig/{}/OWNERS'.format(sig[0])
            if os.path.exists(owner_file):
                with open('community/sig/{}/OWNERS'.format(sig[0]), 'r') as f:
                    user_infos = yaml.load(f.read(), Loader=yaml.Loader)['maintainers']
                for maintainer in user_infos:
                    maintainers.append(maintainer)
            else:
                sig_info_file = 'community/sig/{}/sig-info.yaml'.format(sig[0])
                if not os.path.exists(sig_info_file):
                    self.logger.error('sig-info.yaml is required when OWNERS file does not exist.')
                    sys.exit(1)
                with open(sig_info_file, 'r') as f:
                    sig_info = yaml.load(f.read(), Loader=yaml.Loader)
                    maintainers = [maintainer['gitee_id'] for maintainer in sig_info['maintainers']]
            maintainer_dict[sig[0]] = maintainers
            owners = []
            for maintainer in maintainers:
                params = {
                    'access_token': access_token
                }
                r = requests.get('https://gitee.com/api/v5/users/{}'.format(maintainer), params=params)
                owner = {}
                if r.status_code == 200:
                    owner['gitee_id'] = maintainer
                    owner['avatar_url'] = r.json()['avatar_url']
                    owner['home_page'] = 'https://gitee.com/{}'.format(maintainer)
                    owner['sigs'] = owners_sigs[maintainer]
                    if r.json()['email']:
                        owner['email'] = r.json()['email']
                    owners.append(owner)
                if r.status_code == 404:
                    pass
            sig.append(owners)

            # 获取description
            description = None
            if 'sig-info.yaml' in os.listdir('community/sig/{}'.format(sig[0])):
                with open('community/sig/{}/sig-info.yaml'.format(sig[0]), 'r') as f:
                    sig_info = yaml.load(f.read(), Loader=yaml.Loader)
                    if 'description' in sig_info.keys():
                        description = sig_info['description']
            sig.append(description)
            sig[5] = str(sig[5]).replace("'", '"')
            group_name = sig[0]
            home_page = sig[1]
            etherpad = sig[2]
            maillist = sig[3]
            irc = sig[4]
            owners = sig[5]
            description = sig[6]
            # 查询数据库，如果sig_name不存在，则创建sig信息；如果sig_name存在,则更新sig信息
            if not Group.objects.filter(group_name=group_name):
                Group.objects.create(group_name=group_name, home_page=home_page, maillist=maillist,
                                     irc=irc, etherpad=etherpad, owners=owners, description=description)
                self.logger.info("Create sig: {}".format(group_name))
                self.logger.info(sig)
            else:
                Group.objects.filter(group_name=group_name).update(irc=irc, etherpad=etherpad, owners=owners,
                                                                   description=description)
                self.logger.info("Update sig: {}".format(group_name))
                self.logger.info(sig)
        t4 = time.time()
        self.logger.info('Has updated database, wasted time: {}'.format(t4 - t3))
        db_sigs = list(Group.objects.all().values_list('group_name', flat=True))
        for sig in [x['name'] for x in sigs]:
            db_sigs.remove(sig)
        if db_sigs:
            try:
                cursor = connection.cursor()
                self.logger.info('Find useless data in database, use cursor to connect database.')
                cursor.execute('set foreign_key_checks=0')
                self.logger.info('Turn off foreign_key_check.')
                for sig in db_sigs:
                    Group.objects.filter(group_name=sig).delete()
                    self.logger.info(
                        'Sig {} had been removed from database because it does not exist in sig directory.'.format(sig))
                cursor.execute('set foreign_key_checks=1')
                self.logger.info('Turn on foreign_key_checks.')
            except Exception as e:
                self.logger.error(e)
        self.logger.info('All done. Wasted time: {}'.format(t4 - t1))

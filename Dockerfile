FROM openeuler/openeuler:22.03

MAINTAINER TommyLike<tommylikehu@gmail.com>

RUN yum install -y vim wget git xz tar make automake autoconf libtool gcc gcc-c++ kernel-devel libmaxminddb-devel pcre-devel openssl openssl-devel tzdata \
readline-devel libffi-devel python3-devel mariadb-devel python3-pip net-tools.x86_64 iputils libXext libjpeg xorg-x11-fonts-75dpi xorg-x11-fonts-Type1

RUN pip3 install uwsgi

WORKDIR /work/app-meeting-server
COPY . /work/app-meeting-server
COPY ./deploy/fonts/simsun.ttc /usr/share/fonts

RUN cd /work/app-meeting-server && pip3 install -r requirements.txt
RUN wget https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6-1/wkhtmltox-0.12.6-1.centos8.x86_64.rpm && \
    rpm -i wkhtmltox-0.12.6-1.centos8.x86_64.rpm && \
    rm -f wkhtmltox-0.12.6-1.centos8.x86_64.rpm

RUN cp /usr/bin/python3 /usr/bin/python
ENV LANG=en_US.UTF-8
ARG user=meetingserver
ARG group=meetingserver
ARG uid=1000
ARG gid=1000
RUN groupadd -g ${gid} ${group}
RUN useradd -u ${uid} -g ${group} -s /bin/sh -m ${user}
RUN chown -R ${user}:${group} /work/app-meeting-server
USER ${uid}:${gid}

EXPOSE 8080
ENTRYPOINT ["uwsgi", "--ini", "/work/app-meeting-server/deploy/production/uwsgi.ini"]

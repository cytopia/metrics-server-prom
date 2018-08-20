ARG PYTHON_VERSION=3
FROM python:${PYTHON_VERSION}-slim

ENV USER=prometheus
ENV GROUP=prometheus

ENV APT_BUILD_DEPS \
	curl \
	g++ \
	gcc \
	libnewlib-arm-none-eabi

ENV APT_RUN_DEPS \
	python-pip \
	supervisor

ENV PIP_RUN_DEPS \
	virtualenv \
	uwsgi

RUN set -x \
	&& apt-get update \
	&& apt-get install --no-install-recommends --no-install-suggests -y \
		${APT_BUILD_DEPS} \
		${APT_RUN_DEPS} \
	&& pip install \
		${PIP_RUN_DEPS} \
	&& curl -L https://storage.googleapis.com/kubernetes-release/release/$(curl \
		-s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl \
		-o /usr/bin/kubectl \
	&& chmod +x /usr/bin/kubectl \
	&& apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
		${APT_BUILD_DEPS} \
	&& rm -rf /var/lib/apt/lists/*

RUN set -x \
	&& groupadd --gid 1000 ${GROUP} \
	&& useradd --gid 1000 --uid 1000 --create-home --shell /bin/bash ${USER}

ENV PIP_RUN_DEPS \
	flask \
	requests

USER ${USER}
RUN set -x \
	&& mkdir /home/${USER}/transform \
	&& cd /home/${USER}/transform \
	&& virtualenv transformenv \
	&& . transformenv/bin/activate \
	&& pip install ${PIP_RUN_DEPS}

USER root

COPY --chown=1000:1000 data/src/transform.py /home/${USER}/transform/
COPY --chown=1000:1000 data/uwsgi/uwsgi.ini /home/${USER}/transform/
COPY data/supervisord.conf /etc/supervisor/supervisord.conf
COPY data/docker-entrypoint.sh /docker-entrypoint.sh

EXPOSE 9100
ENTRYPOINT ["/docker-entrypoint.sh"]

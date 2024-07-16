FROM python:3.11-slim

ARG APP_USER_ID=10010
ARG APP_GROUP_ID=10010
ARG WORK_HOME=/opt/mycgan
ARG APP_DIR=/opt/app
ARG VENV_DIR=/opt/venv
ARG DATA_STORE_DIR=${APP_DIR}/store

# install system libraries
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends git ca-certificates curl wget pkg-config \
    libgdal-dev libgeos-dev libproj-dev gdal-bin libcgal-dev libxml2-dev libsqlite3-dev  \
    gcc g++ texlive openssl dvipng texlive-latex-extra texlive-fonts-recommended cm-super \
    libfreetype-dev libfontconfig-dev libjpeg-dev libspng-dev libx11-dev libgbm-dev libeccodes-dev libeccodes-tools

# service runtime filesystem directories
RUN mkdir -p ${WORK_HOME} ${APP_DIR} ${DATA_STORE_DIR} ${VENV_DIR} && \
    git clone --depth 1 https://github.com/mljar/mercury.git /tmp/src-code && \
    cp -rf /tmp/src-code/mercury ${WORK_HOME} && rm -rf /tmp/src-code && \
    git clone --depth 1 https://github.com/Fenwick-Cooper/show-forecasts.git -b for-mercury ${WORK_HOME}/show-forecasts


RUN groupadd --gid ${APP_GROUP_ID} mycgan && \ 
    useradd --home-dir ${WORK_HOME} --uid ${APP_USER_ID} --gid ${APP_GROUP_ID} mycgan && \
    chown -Rf mycgan:mycgan ${WORK_HOME} ${APP_DIR} ${DATA_STORE_DIR} ${VENV_DIR}

USER mycgan
WORKDIR ${APP_DIR}

COPY --chown=mycgan:root --chmod=0754 poetry.lock pyproject.toml README.md welcome.md ${APP_DIR}/
COPY --chown=mycgan:root --chmod=0754 ./cgan_ui ${APP_DIR}/cgan_ui
COPY --chown=mycgan:root --chmod=0754 ./webapps ${APP_DIR}/webapps
COPY --chmod=0754 --chown=mycgan:root ./docker/webapp/entrypoint.sh ${APP_DIR}/

ENV PATH=${WORK_HOME}/bin:${VENV_DIR}/bin:$PATH \
    WORK_HOME=${WORK_HOME} APP_DIR=${APP_DIR} \
    DATA_STORE_DIR=${DATA_STORE_DIR} VENV_DIR=${VENV_DIR}

RUN python -m venv ${VENV_DIR} && . ${VENV_DIR}/bin/activate && \
    cd ${WORK_HOME}/show-forecasts && pip install --no-cache -e .&& \
    cd ${APP_DIR} && pip install --no-cache -e . && \
    pyppeteer-install

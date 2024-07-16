FROM python:3.10-slim

ARG APP_USER_ID=10010
ARG APP_GROUP_ID=10010
ARG WORK_HOME=/opt/mycgan
ARG APP_DIR=/opt/app
ARG VENV_DIR=/opt/venv
ARG LOGS_DIR=/opt/logs
ARG DATA_STORE_DIR=/opt/store

# install system libraries
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends git rsync ssh ca-certificates pkg-config \
    libgdal-dev libgeos-dev libproj-dev gdal-bin libcgal-dev libxml2-dev libsqlite3-dev  \
    gcc g++ dvipng libfontconfig-dev libjpeg-dev libspng-dev libx11-dev libgbm-dev \
    libeccodes-dev libeccodes-tools

# service runtime filesystem directories
RUN mkdir -p ${WORK_HOME} ${APP_DIR} ${DATA_STORE_DIR} ${VENV_DIR} && \
    git clone --depth 1 -b Jurre_brishti https://github.com/jaysnm/ensemble-cgan.git ${WORK_HOME}/ensemble-cgan

RUN groupadd --gid ${APP_GROUP_ID} mycgan && \ 
    useradd --home-dir ${WORK_HOME} --uid ${APP_USER_ID} --gid ${APP_GROUP_ID} mycgan && \
    chown -Rf mycgan:mycgan ${WORK_HOME} ${APP_DIR} ${DATA_STORE_DIR} ${VENV_DIR}

USER mycgan
WORKDIR ${APP_DIR}

COPY --chown=mycgan:root --chmod=0754 poetry.lock pyproject.toml README.md welcome.md ${APP_DIR}
COPY --chown=mycgan:root --chmod=0754 ./cgan_ui ${APP_DIR}/cgan_ui
COPY --chmod=0754 --chown=mycgan:root ./docker/jobs/entrypoint.sh ${APP_DIR}/

ENV PATH=${WORK_HOME}/bin:${VENV_DIR}/bin:$PATH WORK_HOME=${WORK_HOME} APP_DIR=${APP_DIR} \
    LOGS_DIR=${LOGS_DIR} DATA_STORE_DIR=${DATA_STORE_DIR} VENV_DIR=${VENV_DIR}

RUN python -m venv ${VENV_DIR} && \
    . ${VENV_DIR}/bin/activate && \
    cd ${WORK_HOME}/ensemble-cgan && pip install --no-cache -e . && \
    cd ${APP_DIR} && pip install --no-cache -e . && mkdir ${WORK_HOME}/.ssh



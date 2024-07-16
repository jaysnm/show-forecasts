FROM python:3.10-slim

ARG LAB_USER_ID=10010
ARG LAB_GROUP_ID=10010
ARG WORK_HOME=/opt/mycgan
ARG SRC_DIR=/opt/src
ARG VENV_DIR=/opt/venv
ARG DATA_STORE_DIR=${WORK_HOME}/store

# install system libraries
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends git ca-certificates pkg-config \
    libgdal-dev libgeos-dev libproj-dev gdal-bin libcgal-dev libxml2-dev libsqlite3-dev  \
    gcc g++ texlive openssl dvipng texlive-latex-extra texlive-fonts-recommended cm-super \
    libfreetype-dev libfontconfig-dev libjpeg-dev libspng-dev libx11-dev libgbm-dev libeccodes-dev libeccodes-tools

# service runtime filesystem directories
RUN mkdir -p ${WORK_HOME}/.local ${DATA_STORE_DIR} ${SRC_DIR} ${VENV_DIR}

RUN groupadd --gid ${LAB_GROUP_ID} mycgan && \ 
    useradd --home-dir ${WORK_HOME} --uid ${LAB_USER_ID} --gid ${LAB_GROUP_ID} mycgan && \
    chown -Rf mycgan:mycgan ${WORK_HOME} ${SRC_DIR} ${DATA_STORE_DIR} ${VENV_DIR}

USER mycgan

ENV PATH=${VENV_DIR}/bin:${WORK_HOME}/.local/bin:$PATH WORK_HOME=${WORK_HOME} \
    DATA_STORE_DIR=${DATA_STORE_DIR} VENV_DIR=${VENV_DIR}

COPY --chown=mycgan:root --chmod=0754 poetry.lock pyproject.toml README.md welcome.md ${SRC_DIR}/ui/
COPY --chown=mycgan:root --chmod=0754 ./cgan_ui ${SRC_DIR}/ui/cgan_ui

RUN git clone --depth 1 https://github.com/jaysnm/ensemble-cgan.git -b Jurre_brishti ${SRC_DIR}/model && \
    git clone --depth 1 https://github.com/Fenwick-Cooper/show-forecasts.git -b for-mercury ${SRC_DIR}/show-forecasts && \
    python -m venv ${VENV_DIR} && . ${VENV_DIR}/bin/activate && \
    cd ${SRC_DIR}/model && pip install --no-cache -e . && \
    cd ${SRC_DIR}/show-forecasts && pip install --no-cache -e . && \
    pip install jupyterlab && cd ${SRC_DIR}/ui && pip install --no-cache -e .

WORKDIR ${WORK_HOME}
CMD ["jupyter-lab", "--IdentityProvider.token=''", "--no-browser"]

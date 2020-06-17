FROM python:3-alpine
RUN apk update && apk add --no-cache attr
ADD requirements.txt /
RUN pip install -r /requirements.txt
ADD dropboxignore.py /
RUN python /dropboxignore.py -h
ENTRYPOINT ["python", "/dropboxignore.py"]
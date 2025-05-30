FROM python:3.12

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

COPY requirements.txt /code/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /code/

COPY entrypoint.sh /code/entrypoint.sh
RUN chmod +x /code/entrypoint.sh

EXPOSE 8007

ENTRYPOINT ["/code/entrypoint.sh"]

CMD ["gunicorn", "competitions_service.wsgi:application", "--bind", "0.0.0.0:8007", "--workers", "3", "--timeout", "120"]

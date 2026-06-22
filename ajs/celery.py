import os
from dotenv import load_dotenv
from celery import Celery

# Load .env BEFORE anything else — critical for Celery worker process
load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ajs.settings')

app = Celery('ajs')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.broker_transport_options = {
    'socket_timeout': 10,
    'socket_connect_timeout': 10,
}
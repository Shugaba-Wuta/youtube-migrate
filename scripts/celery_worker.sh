#!/bin/sh

# wait for RabbitMQ server to start
# sleep 5

# Replace * with name of Django Project
su -m myuser -c "celery -A background_app.celery.celery_app worker --loglevel=info"
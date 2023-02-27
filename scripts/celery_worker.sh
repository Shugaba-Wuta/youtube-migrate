#!/bin/sh

# wait for RabbitMQ server to start
# sleep 5

# Replace * with name of Django Project
sudo -c "celery -A core.celery_app worker -l FATAL -P solo -f celery.log"
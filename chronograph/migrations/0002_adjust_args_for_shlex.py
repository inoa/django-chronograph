# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.db.models import Q


def safe_print(msg):
    try:
        print msg
    except:
        pass

def adjust_args_forwards(apps, schema_editor):
    Job = apps.get_model('chronograph', 'Job')
    jobs = Job.objects.filter(Q(args__contains='"') | Q(args__contains='\\'))
    if not jobs:
        return
    print u"Migration chronograph.0002_adjust_args_for_shlex forwards will update %s jobs:" % len(jobs)
    for job in jobs:
        prev_args = job.args
        new_args = job.args.replace('\\', '\\\\').replace('"', '\\"')
        safe_print(u"- #%s %s" % (job.pk, job.command))
        safe_print(u"  Name: %s" % job.name)
        safe_print(u"  [from] %s" % prev_args)
        safe_print(u"  [ to ] %s" % new_args)
        job.args = new_args
        job.save()

def adjust_args_backwards(apps, schema_editor):
    Job = apps.get_model('chronograph', 'Job')
    jobs = Job.objects.filter(Q(args__contains='\\"') | Q(args__contains='\\\\'))
    if not jobs:
        return
    print u"Migration chronograph.0002_adjust_args_for_shlex backwards will update %s jobs:" % len(jobs)
    for job in jobs:
        prev_args = job.args
        new_args = job.args.replace('\\"', '"').replace('\\\\', '\\')
        safe_print(u"- #%s %s" % (job.pk, job.command))
        safe_print(u"  Name: %s" % job.name)
        safe_print(u"  [from] %s" % prev_args)
        safe_print(u"  [ to ] %s" % new_args)
        job.args = new_args
        job.save()

class Migration(migrations.Migration):

    dependencies = [
        ('chronograph', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(adjust_args_forwards, adjust_args_backwards),
    ]


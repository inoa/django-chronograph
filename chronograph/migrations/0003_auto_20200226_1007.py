# -*- coding: utf-8 -*-
# Generated by Django 1.11.26 on 2020-02-26 10:07
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('chronograph', '0002_adjust_args_for_shlex'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='job',
            options={'ordering': ['name', 'id']},
        ),
        migrations.AlterModelOptions(
            name='log',
            options={'ordering': ['-pk']},
        ),
    ]
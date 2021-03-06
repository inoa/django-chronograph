from .models import Job, Log
from django import forms
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin, messages
from django.core.urlresolvers import reverse
from django.db import models
from django.forms import Textarea
from django.forms.utils import flatatt
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import redirect
from django.template.defaultfilters import linebreaks
from django.utils import dateformat, formats
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.timesince import timesince
from django.utils.timezone import now as tz_now
from django.utils.translation import ungettext, ugettext, ugettext_lazy as _


class HTMLWidget(forms.Widget):
    def __init__(self, rel=None, attrs=None):
        self.rel = rel
        super(HTMLWidget, self).__init__(attrs)

    def render(self, name, value, attrs=None):
        if self.rel is not None:
            key = self.rel.get_related_field().name
            obj = self.rel.to._default_manager.get(**{key: value})
            related_url = '../../../%s/%s/%d/' % (self.rel.to._meta.app_label, self.rel.to._meta.object_name.lower(), value)
            value = "<a href='%s'>%s</a>" % (related_url, escape(obj))
        else:
            value = escape(value)

        final_attrs = self.build_attrs(attrs, name=name)
        return mark_safe("<div%s>%s</div>" % (flatatt(final_attrs), linebreaks(value)))

class JobForm(forms.ModelForm):
    class Meta:
        widgets = {
            'command': Textarea(attrs={'cols': 80, 'rows': 6}),
            'shell_command': Textarea(attrs={'cols': 80, 'rows': 6}),
            'args': Textarea(attrs={'cols': 80, 'rows': 6}),
        }

    def clean_shell_command(self):
        if self.cleaned_data.get('command', '').strip() and \
                self.cleaned_data.get('shell_command', '').strip():
            raise forms.ValidationError(_("Can't specify a shell_command if "
                              "a django admin command is already specified"))
        return self.cleaned_data['shell_command']

    def clean(self):
        cleaned_data = super(JobForm, self).clean()
        if len(cleaned_data.get('command', '').strip()) and \
                len(cleaned_data.get('shell_command', '').strip()):
            raise forms.ValidationError(_("Must specify either command or "
                                        "shell command"))
        return cleaned_data

class JobAdmin(admin.ModelAdmin):
    ordering =['-is_running', '-adhoc_run', 'disabled', 'next_run']
    actions = ['disable_jobs', 'enable_jobs', 'reset_jobs']
    form = JobForm
    list_display = (
        '_enabled', 'id', 'name', 'command', '_frequency',
        '_job_success', '_last_run_with_link', '_next_run',
        '_is_running', '_run_button', '_view_logs_button',
    )
    list_display_links = ('id', 'name')
    list_filter = ('last_run_successful', 'command', 'frequency', 'disabled', 'is_running')
    search_fields = ('name', 'command')
    if not getattr(settings, 'CHRONOGRAPH_DISABLE_EMAIL_SUBSCRIPTION', False):
        filter_horizontal = ('subscribers', 'info_subscribers')

    fieldsets = (
        (_('Job Details'), {
            'classes': ('wide',),
            'fields': ('name', 'disabled', 'command', 'args', 'atomic',)
                      if getattr(settings, 'CHRONOGRAPH_DISABLE_SHELL_OPTIONS', False) else
                      ('name', 'disabled', 'command', 'shell_command', 'run_in_shell', 'args', 'atomic')
        }),
        (_('Frequency options'), {
            'classes': ('wide',),
            'fields': ('frequency', 'next_run', 'params',)
        }),
        (_('E-mail subscriptions'), {
            'classes': ('wide',),
            'fields': ('info_subscribers', 'subscribers',)
        }),
    )
    if getattr(settings, 'CHRONOGRAPH_DISABLE_EMAIL_SUBSCRIPTION', False):
        fieldsets = (fieldsets[0], fieldsets[1])

    def enable_jobs(self, request, queryset):
        return queryset.update(disabled=False)

    def disable_jobs(self, request, queryset):
        return queryset.update(disabled=True)

    def reset_jobs(self, request, queryset):
        return queryset.update(is_running=False, started_on=None)

    def _enabled(self, obj):
        return not obj.disabled
    _enabled.short_description = _('Enabled')
    _enabled.boolean = True

    def _job_success(self, obj):
        return obj.last_run_successful
    _job_success.short_description = _(u'Healthy')
    _job_success.boolean = True

    def _frequency(self, obj):
        return obj.get_actual_frequency()
    _frequency.short_description = _('Frequency')
    _frequency.admin_order_field = 'frequency'

    def _is_running(self, obj):
        if not obj.is_running:
            return "⚪"
        value = "▶️"
        if obj.started_on:
            now = tz_now()
            delta = now - obj.started_on
            if delta.seconds < 60:
                # Adapted from django.utils.timesince
                count = lambda n: ungettext('second', 'seconds', n)
                time_since_text = ugettext('%(number)d %(type)s') % {
                    'number': delta.seconds,
                    'type': count(delta.seconds)
                }
            else:
                time_since_text = timesince(obj.started_on, now)
            format_ = formats.get_format('DATETIME_FORMAT')
            started_on_text = capfirst(dateformat.format(obj.started_on, format_))
            value = "<span title=\"Started on: {}\" style=\"white-space: nowrap;\">{} {}</span>".format(
                    started_on_text, value, time_since_text)
        return value
    _is_running.short_description = _('Running')
    _is_running.allow_tags = True

    def _next_run(self, obj):
        value = obj.get_timeuntil()
        if obj.next_run:
            format_ = formats.get_format('DATETIME_FORMAT')
            scheduled_text = capfirst(dateformat.format(obj.next_run, format_))
            value = "<span title=\"Scheduled time: {}\">{}</span>".format(
                    scheduled_text, value)
        return value
    _next_run.short_description = _('Next run')
    _next_run.admin_order_field = 'next_run'
    _next_run.allow_tags = True

    def _last_run_with_link(self, obj):
        if not obj.last_run:
            return None
        format_ = formats.get_format('DATETIME_FORMAT')
        value = capfirst(dateformat.format(obj.last_run, format_))
        reversed_url = reverse('admin:chronograph_job_latest_log', args=[obj.pk])
        return '<a href="%s">%s</a>' % (reversed_url, value)
    _last_run_with_link.allow_tags = True
    _last_run_with_link.short_description = _('Last run')
    _last_run_with_link.admin_order_field = 'last_run'

    def _run_button(self, obj):
        if obj.adhoc_run or obj.is_running:
            return '-'
        reversed_url = reverse('admin:chronograph_job_run', args=[obj.pk]) + '?inline=1'
        return '<a href="%s" class="btn btn-default">Run</a>' % reversed_url
    _run_button.allow_tags = True
    _run_button.short_description = _('Run')

    def _view_logs_button(self, obj):
        reversed_url = reverse('admin:chronograph_log_changelist') + '?job=%d' % obj.pk
        return '<a href="%s" class="btn btn-default">View Logs</a>' % reversed_url
    _view_logs_button.allow_tags = True
    _view_logs_button.short_description = _('Logs')
    
    def latest_log_job_view(self, request, pk):
        log_qs = Log.objects.filter(job_id=pk).exclude(end_date=None).order_by('-run_date')[0:1]
        if log_qs:
            return redirect('admin:chronograph_log_change', log_qs[0].pk)
        else:
            job = Job.objects.get(pk=pk)
            messages.error(request, 'The job "%(job)s" has no log entries.' % {'job': job.name})
            return redirect('admin:chronograph_job_changelist')

    def run_job_view(self, request, pk):
        """
        Runs the specified job.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            raise Http404
        job.adhoc_run = True
        job.save()
        messages.success(request, 'The job "%(job)s" has been queued for running' % {'job': job.name})

        if 'inline' in request.GET:
            redirect = request.path + '../../'
        else:
            redirect = request.GET.get('next', request.path + "../")

        return HttpResponseRedirect(redirect)

    def get_urls(self):
        urls = super(JobAdmin, self).get_urls()
        my_urls = [
            url(r'^(.+)/run/$', self.admin_site.admin_view(self.run_job_view), name="chronograph_job_run"),
            url(r'^(.+)/latest-log/$', self.admin_site.admin_view(self.latest_log_job_view), name="chronograph_job_latest_log"),
        ]
        return my_urls + urls

class LogAdmin(admin.ModelAdmin):
    ordering = ['-run_date']
    list_display = ('job_name', 'run_date', 'end_date', 'job_duration', 'job_success', 'output', 'errors',)
    list_select_related = ('job',)
    list_filter = ('job', 'run_date', 'end_date', 'success')
    search_fields = ('stdout', 'stderr', 'job__name', 'job__command')
    date_hierarchy = 'run_date'
    fieldsets = (
        (None, {
            'fields': ('job', 'run_date', 'end_date', 'job_duration', 'job_success')
        }),
        (_('Output'), {
            'fields': ('stdout_pre', 'stderr_pre',)
        }),
    )
    readonly_fields = ['job', 'run_date', 'end_date', 'job_duration', 'job_success', 'stdout_pre', 'stderr_pre']
    LOG_TEXT_TRUNCATE_CHARS = 40
    
    def get_list_select_related(self, request):
        # Do not perform select_related to Job (see the comment in get_queryset below).
        return ()

    def get_queryset(self, request):
        qs = super(LogAdmin, self).get_queryset(request)
        # Use prefetch_related instead of select_related because SQL Server sometimes doesn't use
        # the run_date index when an INNER JOIN is made to Job, and performs a slow full table scan instead.
        qs = qs.select_related(None).prefetch_related('job')
        if request.resolver_match.func.__name__ == 'changelist_view':
            chars = self.LOG_TEXT_TRUNCATE_CHARS + 1
            extra_select = {'stdout_trunc': 'left(stdout, %s)' % chars, 'stderr_trunc': 'left(stderr, %s)' % chars}
            qs = qs.defer('stdout', 'stderr').extra(select=extra_select)
        return qs

    def job_duration(self, obj):
        return "%s" % (obj.get_duration())
    job_duration.short_description = _(u'Duration')

    def job_name(self, obj):
        return obj.job.name
    job_name.short_description = _(u'Name')

    def job_success(self, obj):
        return obj.success
    job_success.short_description = _(u'OK')
    job_success.boolean = True

    def output(self, obj):
        result = (obj.stdout_trunc if hasattr(obj, 'stdout_trunc') else obj.stdout) or ''
        if len(result) > self.LOG_TEXT_TRUNCATE_CHARS:
            result = result[:self.LOG_TEXT_TRUNCATE_CHARS] + '...'
        return result or _('(No output)')

    def errors(self, obj):
        result = (obj.stderr_trunc if hasattr(obj, 'stderr_trunc') else obj.stderr) or ''
        if len(result) > self.LOG_TEXT_TRUNCATE_CHARS:
            result = result[:self.LOG_TEXT_TRUNCATE_CHARS] + '...'
        return result or _('(No errors)')
    
    def stdout_pre(self, obj):
        if not obj.stdout:
            return _('(No output)')
        return "<pre>%s</pre>" % escape(obj.stdout).replace('\n', '<br/>')
    stdout_pre.short_description = _('output')
    stdout_pre.allow_tags = True
    
    def stderr_pre(self, obj):
        if not obj.stderr:
            return _('(No errors)')
        return "<pre>%s</pre>" % escape(obj.stderr).replace('\n', '<br/>')
    stderr_pre.short_description = _('errors')
    stderr_pre.allow_tags = True

    def has_add_permission(self, request):
        return False

    def formfield_for_dbfield(self, db_field, **kwargs):
        request = kwargs.pop("request", None)

        if isinstance(db_field, models.TextField):
            kwargs['widget'] = HTMLWidget()
            return db_field.formfield(**kwargs)

        if isinstance(db_field, models.ForeignKey):
            kwargs['widget'] = HTMLWidget(db_field.rel)
            return db_field.formfield(**kwargs)

        return super(LogAdmin, self).formfield_for_dbfield(db_field, **kwargs)

admin.site.register(Job, JobAdmin)
admin.site.register(Log, LogAdmin)

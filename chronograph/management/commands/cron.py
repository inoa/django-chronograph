from ...models import Job
from django.core.management.base import BaseCommand
from django.conf import settings
import os
import datetime
import traceback

class Command(BaseCommand):
    help = 'Runs all jobs that are due.'
    
    def handle(self, *args, **options):
        log_filename = getattr(settings, 'CHRONOGRAPH_CRON_LOG_FILENAME', None)
        self.init_log(log_filename)

        stuck_jobs = Job.objects.reset_stuck_jobs()
        if stuck_jobs:
            self.write_log("{} stuck job(s) reset:".format(len(stuck_jobs)))
            counter = 0
            for job in stuck_jobs:
                counter += 1
                self.write_log("{}. {}".format(counter, job))


        initially_due_jobs = list(Job.objects.due())
        if not initially_due_jobs:
            self.write_log("No due jobs at this time.")
            return

        self.write_log("{} due job(s) at startup:".format(len(initially_due_jobs)))
        counter = 0
        for job in initially_due_jobs:
            counter += 1
            self.write_log("{}. {}".format(counter, job))

        for job in initially_due_jobs:
            job_name_str = str(job)
            if not Job.objects.is_job_due(job):
                # This might happen if the previous job took a long time to run,
                # and another instance of Cron executed this job in the meantime.
                self.write_log("This job is no longer due and will be skipped: {}.".format(job_name_str))
                continue

            self.write_log("Running job {}.".format(job_name_str))
            try:
                job.run()
                self.write_log("Done running job {}.".format(job_name_str))
            except Exception as ex:
                self.write_log("Unhandled exception while running job {}: {}".format(job_name_str, str(ex)))
                self.write_log(traceback.format_exc())

        self.write_log("Finished running all due jobs.")

    def init_log(self, filename):
        self.log_filename = filename
        if not self.log_filename:
            return
        if not self.write_log("Starting up."):
            self.stderr.write("Failed to open log file: {}".format(filename))
            self.log_filename = None

    def write_log(self, text):
        pid = os.getpid()
        now = datetime.datetime.now()
        formatted_text = "(PID-{})[{:%H-%M-%S.%f}] {}".format(pid, now, text)
        self.stdout.write(formatted_text)
        if not self.log_filename:
            return True
        try:
            with open(self.log_filename, 'a') as log_file:
                log_file.write(formatted_text + "\n")
        except:
            return False
        return True

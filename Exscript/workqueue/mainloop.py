#
# Copyright (C) 2010-2017 Samuel Abels
# The MIT License (MIT)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
from __future__ import print_function, absolute_import
import threading
import multiprocessing
from ..util.event import Event
from .job import Job

# See http://bugs.python.org/issue1731717
multiprocessing.process._cleanup = lambda: None


class MainLoop(threading.Thread):

    def __init__(self, collection, job_cls):
        threading.Thread.__init__(self)
        self.job_init_event = Event()
        self.job_started_event = Event()
        self.job_error_event = Event()
        self.job_succeeded_event = Event()
        self.job_aborted_event = Event()
        self.queue_empty_event = Event()
        self.collection = collection
        self.job_cls = job_cls
        self.debug = 5
        self.daemon = True

    def _dbg(self, level, msg):
        if self.debug >= level:
            print(msg)

    def enqueue(self, function, name, times, data):
        job = Job(function, name, times, data)
        job.id = self.collection.append(job)
        return job.id

    def enqueue_or_ignore(self, function, name, times, data):
        def conditional_append(queue):
            if queue.get_from_name(name) is not None:
                return None
            job = Job(function, name, times, data)
            job.id = queue.append(job, name)
            return job.id
        return self.collection.with_lock(conditional_append)

    def priority_enqueue(self, function, name, force_start, times, data):
        job = Job(function, name, times, data)
        job.id = self.collection.appendleft(job, name, force=force_start)
        return job.id

    def priority_enqueue_or_raise(self,
                                  function,
                                  name,
                                  force_start,
                                  times,
                                  data):
        def conditional_append(queue):
            job = queue.get_from_name(name)
            if job is None:
                job = Job(function, name, times, data)
                job.id = queue.append(job, name)
                return job.id
            queue.prioritize(job, force=force_start)
            return None
        return self.collection.with_lock(conditional_append)

    def wait_for(self, job_id):
        self.collection.wait_for_id(job_id)

    def get_queue_length(self):
        return len(self.collection)

    def _on_job_completed(self, job, exc_info):
        # This function is called in a sub-thread, so we need to be
        # careful that we are not in a lock while sending an event.
        self._dbg(1, 'Job "%s" called completed()' % job.name)

        try:
            # Notify listeners of the error
            # *before* removing the job from the queue.
            # This is because wait_until_done() depends on
            # get_queue_length() being 0, and we don't want a listener
            # to get a signal from a queue that already already had
            # wait_until_done() completed.
            if exc_info:
                self._dbg(1, 'Error in job "%s"' % job.name)
                job.failures += 1
                self.job_error_event(job.child, exc_info)
                if job.failures >= job.times:
                    self._dbg(1, 'Job "%s" finally failed' % job.name)
                    self.job_aborted_event(job.child)
            else:
                self._dbg(1, 'Job "%s" succeeded.' % job.name)
                self.job_succeeded_event(job.child)

        finally:
            # Remove the watcher from the queue, and re-enque if needed.
            if exc_info and job.failures < job.times:
                self._dbg(1, 'Restarting job "%s"' % job.name)
                job.start(self.job_cls, self._on_job_completed)
                self.job_started_event(job.child)
            else:
                self.collection.task_done(job)

    def run(self):
        while True:
            # Get the next job from the queue. This blocks until a task
            # is available or until self.collection.stop() is called.
            job = next(self.collection)
            if len(self.collection) <= 0:
                self.queue_empty_event()
            if job is None:
                break  # self.collection.stop() was called.

            self.job_init_event(job)
            job.start(self.job_cls, self._on_job_completed)
            self.job_started_event(job.child)
            self._dbg(1, 'Job "%s" started.' % job.name)
        self._dbg(2, 'Main loop terminated.')

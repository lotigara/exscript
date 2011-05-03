# Copyright (C) 2007-2010 Samuel Abels.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
import os
import logging
from functools import partial
from collections import defaultdict
from threading import Thread
from Exscriptd.util import synchronized
from Exscriptd import Task

class _AsyncFunction(Thread):
    def __init__ (self, function, *args, **kwargs):
        Thread.__init__(self)
        self.function = function
        self.args     = args
        self.kwargs   = kwargs

    def run(self):
        self.function(*self.args, **self.kwargs)

class OrderDispatcher(object):
    def __init__(self, order_db, queues, logger, logdir):
        self.order_db = order_db
        self.queues   = queues
        self.logger   = logger
        self.logdir   = logdir
        self.services = {}
        self.daemons  = {}
        self.loggers  = defaultdict(dict) # Map order id to name/logger pairs.
        self.logger.info('Closing all open orders.')
        self.order_db.close_open_orders()

    def get_logger(self, order, name, level = logging.INFO):
        """
        Creates a logger that logs to a file in the order's log directory.
        """
        if name in self.loggers[order.id]:
            return self.loggers[order.id][name]
        service_logdir = os.path.join(self.logdir, order.get_service_name())
        order_logdir   = os.path.join(service_logdir, str(order.get_id()))
        logfile        = os.path.join(order_logdir, name)
        logger         = logging.getLogger(logfile)
        handler        = logging.FileHandler(logfile)
        format         = r'%(asctime)s - %(levelname)s - %(message)s'
        formatter      = logging.Formatter(format)
        logger.setLevel(logging.INFO)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        self.loggers[order.id][name] = logger
        return logger

    def _free_loggers(self, order_id):
        for logger in self.loggers[order_id]:
            # hack to work around the fact that Python's logging module
            # provides no documented way to delete loggers.
            del logger.manager.loggerDict[logger.name]
            logger.manager = None
        del self.loggers[order_id]

    def service_added(self, service):
        """
        Called by a service when it is initialized.
        """
        service.parent = self
        self.services[service.name] = service

    def daemon_added(self, daemon):
        """
        Called by a daemon when it is initialized.
        """
        daemon.parent = self
        self.daemons[daemon.name] = daemon
        daemon.order_incoming_event.listen(self.place_order, daemon.name)

    def log(self, order, message):
        msg = '%s/%s: %s' % (order.get_service_name(),
                             order.get_id(),
                             message)
        self.logger.info(msg)

    def get_order_db(self):
        return self.order_db

    def _update_order_status(self, order):
        remaining = self.order_db.count_tasks(order_id = order.id,
                                              closed   = None)
        if remaining == 0:
            order.close()
            self._free_loggers(order.id)
            self.set_order_status(order, 'completed')

    def _run_task(self, order, task):
        service = self.services[order.get_service_name()]
        task.set_status('in-progress')
        try:
            service.run_function(task.func_name, order, task)
        except Exception, e:
            task.close('internal-error')
            raise
        else:
            if not task.get_closed_timestamp():
                task.completed()

    @synchronized
    def _on_qtask_done(self, qtask, task, order):
        qtask.done_event.disconnect_all()
        self._fill_queue(task.queue_name)
        self._update_order_status(order)

    @synchronized
    def _fill_queue(self, queue_name):
        # Count the number of free slots in the queue.
        queue      = self.queues[queue_name]
        n_tasks    = queue.workqueue.get_length()
        free_slots = max(0, 100 - n_tasks)
        if free_slots == 0:
            return

        # Load the tasks from the database.
        self.logger.info('restoring %d persistent tasks' % free_slots)
        tasks = self.order_db.mark_tasks('loading',
                                         limit = free_slots,
                                         queue = queue_name,
                                         status = 'go')
        self.logger.info('%d tasks restored' % len(tasks))

        # Enqueue them. We pause the queue to avoid that a done_event
        # is sent at a time where we have not yet connected the
        # signal.
        self.logger.info('filling queue ' + queue_name)
        queue.workqueue.pause()
        for task in tasks:
            self.logger.info('enqueuing task ' + repr(task.name))
            task.changed_event.listen(self._on_task_changed)
            task.closed_event.listen(self._on_task_closed)
            order = self.order_db.get_order(id = task.order_id)
            run   = partial(self._run_task, order, task)
            qtask = queue.enqueue(run, task.name)
            qtask.done_event.listen(self._on_qtask_done, qtask, task, order)
            task.set_status('queued')
        queue.workqueue.unpause()
        self.logger.info('queue filled')

    def _on_task_go(self, task):
        task.go_event.disconnect_all()
        task.closed_event.disconnect_all()
        task.changed_event.disconnect_all()
        self._fill_queue(task.queue_name)

    def _on_task_changed(self, task):
        self.order_db.save_task(task)

    def _on_task_closed(self, task):
        task.go_event.disconnect_all()
        task.closed_event.disconnect_all()
        task.changed_event.disconnect_all()

    def create_task(self, order, name, queue_name, func):
        task = Task(order.id, name, queue_name, func)
        task.go_event.listen(self._on_task_go)
        task.changed_event.listen(self._on_task_changed)
        return task

    def set_order_status(self, order, status):
        order.status = status
        self.order_db.save_order(order)
        self.log(order, 'Status is now "%s"' % status)

    def place_order(self, order, daemon_name):
        self.logger.debug('Incoming order from ' + daemon_name)

        # Store it in the database.
        self.set_order_status(order, 'incoming')

        # Loop the requested service up.
        service = self.services.get(order.get_service_name())
        if not service:
            order.close()
            self.set_order_status(order, 'service-not-found')
            return

        # Notify the service of the new order.
        try:
            accepted = service.check(order)
        except Exception, e:
            self.log(order, 'Exception: %s' % e)
            order.close()
            self.set_order_status(order, 'error')
            raise

        if not accepted:
            order.close()
            self.set_order_status(order, 'rejected')
            return
        self.set_order_status(order, 'accepted')

        # Save the order, including the data that was passed.
        # For performance reasons, use a new thread.
        func = _AsyncFunction(self._enter_order, service, order)
        func.start()

    def _enter_order(self, service, order):
        # Note: This method is called asynchronously.
        # Store the order in the database.
        self.set_order_status(order, 'saving')
        self.order_db.save_order(order)

        self.set_order_status(order, 'enter-start')
        try:
            result = service.enter(order)
        except Exception, e:
            self.log(order, 'Exception: %s' % e)
            order.close()
            self.set_order_status(order, 'enter-exception')
            raise

        if not result:
            self.log(order, 'Error: enter() returned False')
            order.close()
            self.set_order_status(order, 'enter-error')
            return
        self.set_order_status(order, 'entered')

        # If the service did not enqueue anything, it may already be completed.
        self._update_order_status(order)

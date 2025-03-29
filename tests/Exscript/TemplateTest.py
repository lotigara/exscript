from __future__ import print_function
import sys
import unittest
import re
import os
dirname = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(dirname, '..', '..'))

from Exscript import Queue, Account, Logger, protocols
from Exscript.util import template
from Exscript.util.decorator import bind
from Exscript.util.log import log_to
from Exscript.util.report import format
from Exscript.protocols import Dummy
from Exscript.emulators import IOSEmulator

test_dir = os.path.join(os.path.dirname(dirname), 'templates')


class Log(object):
    data = ''

    def collect(self, data):
        self.data += data
        return data


def dummy_cb(job, host, conn, template_test):
    # Warning: Assertions raised in this function happen in a subprocess!
    # Create a log object.
    log = Log()
    conn.data_received_event.connect(log.collect)

    # Connect and load the test template.
    conn.connect(host.get_address(), host.get_tcp_port())
    test_name = host.get_address()
    if host.get_protocol() == 'ios':
        dirname = os.path.join(test_dir, test_name)
    else:
        dirname = os.path.dirname(test_name)
    tmpl = os.path.join(dirname, 'test.exscript')
    expected = os.path.join(dirname, 'expected')

    # Go.
    conn.login(flush=True)
    try:
        template.eval_file(conn, tmpl, slot=10)
    except Exception as e:
        print(log.data)
        raise
    log.data = log.data.replace('\r\n', '\n')
    if sys.version_info[0] == 2:
        with open(expected) as fp:
            expected_data = fp.read()
    else:
        with open(expected, newline='') as fp:
            expected_data = fp.read()
    #open(expected, 'w').write(log.data)
    #open('output', 'w').write(log.data)
    #open('exp', 'w').write(expected_data)
    template_test.assertEqual(log.data, expected_data)


class IOSDummy(Dummy):

    def __init__(self, *args, **kwargs):
        device = IOSEmulator('dummy', strict=False)
        Dummy.__init__(self, device=device, **kwargs)
protocols.protocol_map['ios'] = IOSDummy


class TemplateTest(unittest.TestCase):

    def setUp(self):
        account = Account('sab', '')
        self.queue = Queue(verbose=0, max_threads=1)
        self.logger = Logger()
        self.queue.add_account(account)
        self.maxDiff = None

    def tearDown(self):
        self.queue.destroy()

    def testTemplates(self):
        callback = bind(log_to(self.logger)(dummy_cb), self)
        for test in os.listdir(test_dir):
            pseudo = os.path.join(test_dir, test, 'pseudodev.py')
            if os.path.exists(pseudo):
                self.queue.run('pseudo://' + pseudo, callback)
            else:
                self.queue.run('ios://' + test, callback)
        self.queue.shutdown()

        # Unfortunately, unittest.TestCase does not fail if self.assert()
        # was called from a subthread, so this is our workaround...
        failed = self.logger.get_aborted_logs()
        report = format(self.logger, show_successful=False)
        self.assertTrue(not failed, report)


def suite():
    return unittest.TestLoader().loadTestsFromTestCase(TemplateTest)
if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())

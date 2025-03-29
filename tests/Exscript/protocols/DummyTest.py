from __future__ import absolute_import
import sys
import unittest
import re
import os.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from .ProtocolTest import ProtocolTest
from Exscript.emulators import VirtualDevice
from Exscript.protocols import Dummy


class DummyTest(ProtocolTest):
    CORRELATE = Dummy

    def createProtocol(self):
        self.protocol = Dummy(device=self.device, timeout=1)

    def testConstructor(self):
        self.assertIsInstance(self.protocol, Dummy)

    def testIsDummy(self):
        self.assertTrue(self.protocol.is_dummy())

    def _create_dummy_and_eat_banner(self, device, port=None):
        protocol = Dummy(device=device)
        protocol.connect(device.hostname, port)
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, None)
        protocol.expect(re.compile(re.escape(self.banner)))
        self.assertEqual(protocol.response, '')
        return protocol

    def testDummy(self):
        # Test simple instance with banner.
        protocol = Dummy(device=self.device)
        protocol.connect('testhost')
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, None)
        protocol.close()

        # Test login.
        protocol = Dummy(device=self.device)
        protocol.connect('testhost')
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, None)
        protocol.login(self.account, flush=False)
        self.assertEqual(protocol.buffer.tail(len(self.prompt)), self.prompt)
        protocol.close()

        # Test login with user prompt.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_USERONLY)
        protocol = self._create_dummy_and_eat_banner(device)
        self.assertEqual(str(protocol.buffer), 'User: ')
        protocol.login(self.account, flush=False)
        self.assertEqual(protocol.buffer.tail(len(self.prompt)), self.prompt)
        protocol.close()

        # Test login with password prompt.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_PASSWORDONLY)
        protocol = self._create_dummy_and_eat_banner(device)
        self.assertEqual(str(protocol.buffer), 'Password: ')
        protocol.login(self.account, flush=False)
        self.assertEqual(protocol.buffer.tail(len(self.prompt)), self.prompt)
        protocol.close()

        # Test login without user/password prompt.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_NONE)
        protocol = self._create_dummy_and_eat_banner(device)
        self.assertEqual(str(protocol.buffer), self.prompt)
        protocol.close()

        # Test login with user prompt and wait parameter.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_USERONLY)
        protocol = self._create_dummy_and_eat_banner(device)
        self.assertEqual(str(protocol.buffer), 'User: ')
        protocol.login(self.account)
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, self.user + '\r')
        protocol.close()

        # Test login with password prompt and wait parameter.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_PASSWORDONLY)
        protocol = self._create_dummy_and_eat_banner(device)
        self.assertEqual(str(protocol.buffer), 'Password: ')
        protocol.login(self.account)
        self.assertEqual(str(protocol.buffer),   '')
        self.assertEqual(protocol.response, self.password + '\r')
        protocol.close()

        # Test login with port number.
        protocol = self._create_dummy_and_eat_banner(device, 1234)
        self.assertEqual(str(protocol.buffer), 'Password: ')
        protocol.login(self.account)
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, self.password + '\r')
        protocol.close()

        # Test a custom response.
        device = VirtualDevice(self.hostname,
                               echo=True,
                               login_type=VirtualDevice.LOGIN_TYPE_NONE)
        protocol = Dummy(device=device)
        command = re.compile(r'testcommand')
        response = 'hello world\r\n%s> ' % self.hostname
        device.add_command(command, response, prompt=False)
        protocol.set_prompt(re.compile(r'> $'))
        protocol.connect('testhost')
        protocol.expect(re.compile(re.escape(self.banner)))
        self.assertEqual(protocol.response, '')
        self.assertEqual(str(protocol.buffer), self.prompt)
        protocol.expect_prompt()
        self.assertEqual(str(protocol.buffer), '')
        self.assertEqual(protocol.response, self.hostname)
        protocol.execute('testcommand')
        expected = 'testcommand\rhello world\r\n' + self.hostname
        self.assertEqual(protocol.response, expected)
        self.assertEqual(str(protocol.buffer), '')
        protocol.close()


def suite():
    return unittest.TestLoader().loadTestsFromTestCase(DummyTest)
if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())

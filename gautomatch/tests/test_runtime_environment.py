"""Gautomatch CUDA library-path subprocess contract (no CUDA binary needed)."""

import os
import shlex
import subprocess
import sys
import unittest
from unittest.mock import patch

from gautomatch import Plugin


class TestGautomatchRuntimeEnvironment(unittest.TestCase):
    """The actual process started by the shell must inherit CUDA libraries."""

    TEST_CONDA_PREFIX = '/tmp/gautomatch-runtime-contract'

    def _runChildAndReadLibraryPath(self, originalPath=None):
        env = os.environ.copy()
        env['CONDA_PREFIX'] = self.TEST_CONDA_PREFIX
        env.pop('LD_LIBRARY_PATH', None)
        env.pop('BASH_ENV', None)
        if originalPath is not None:
            env['LD_LIBRARY_PATH'] = originalPath

        probe = 'import os; print(os.environ.get("LD_LIBRARY_PATH", "<MISSING>"))'
        probeCommand = '%s -c %s' % (
            shlex.quote(sys.executable), shlex.quote(probe)
        )

        # Replace conda activation and Gautomatch with inert/safe commands.
        # The actual Plugin.getProgram() joins these pieces; only its shell
        # environment handling is under test.
        with patch.object(Plugin, 'getCondaActivationCmd', return_value='true &&'), \
             patch.object(Plugin, 'getGautomatchEnvActivation', return_value='true'), \
             patch.object(Plugin, 'getVar', return_value=probeCommand):
            command = Plugin.getProgram()

        result = subprocess.run(
            ['bash', '-c', command], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=True,
        )
        return result.stdout.strip()

    def test_ExportsCudaLibrariesWhenLibraryPathWasUnset(self):
        self.assertEqual(
            self._runChildAndReadLibraryPath(),
            self.TEST_CONDA_PREFIX + '/lib',
            'The Gautomatch child must inherit Conda CUDA libraries even '
            'when LD_LIBRARY_PATH is initially absent/unexported.',
        )

    def test_PrependsCudaLibrariesAndKeepsAnExistingLibraryPath(self):
        self.assertEqual(
            self._runChildAndReadLibraryPath('/existing/libraries'),
            self.TEST_CONDA_PREFIX + '/lib:/existing/libraries',
        )

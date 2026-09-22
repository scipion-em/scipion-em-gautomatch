# ***************************************************************************
# *
# * Regression tests for Gautomatch streaming/Continue behaviour.
# *
# ***************************************************************************

import os
import tempfile
import unittest
from unittest.mock import patch

from gautomatch.protocols.protocol_gautomatch import ProtGautomatch


class _Value:
    def __init__(self, value=None):
        self._value = value

    def get(self):
        return self._value


class _Mic:
    def __init__(self, obj_id, file_name):
        self._obj_id = obj_id
        self._file_name = file_name

    def getObjId(self):
        return self._obj_id

    def getFileName(self):
        return self._file_name


class _PickingHarness:
    def __init__(self, tmp_dir):
        self.tmp_dir = tmp_dir
        self.inputBadCoords = _Value(None)
        self.exclusive = False
        self.failed_ids = []
        self.errors = []

    def _getMicrographDir(self, mic):
        return os.path.join(self.tmp_dir, "work")

    def _getReferencesFn(self):
        return None

    def getMicrographsDir(self):
        return os.path.join(self.tmp_dir, "extra")

    def runJob(self, *args, **kwargs):
        raise AssertionError("runJob should be intercepted by patched runGautomatch")

    def error(self, message):
        self.errors.append(message)

    def _writeFailedList(self, mic_list):
        self.failed_ids.extend(mic.getObjId() for mic in mic_list)


class TestGautomatchStreamingRegression(unittest.TestCase):
    def testPickingFailureIsRecordedBeforeContinuing(self):
        with tempfile.TemporaryDirectory() as tmp:
            mic_fn = os.path.join(tmp, "mic_001.mrc")
            with open(mic_fn, "w") as handle:
                handle.write("micrograph\n")

            protocol = _PickingHarness(tmp)
            mic = _Mic(1, mic_fn)

            with patch(
                "gautomatch.protocols.protocol_gautomatch.gautomatch.Plugin.runGautomatch",
                side_effect=RuntimeError("simulated Gautomatch failure"),
            ), patch(
                "gautomatch.protocols.protocol_gautomatch.gautomatch.Plugin.getEnviron",
                return_value={},
            ):
                ProtGautomatch._pickMicrographList(protocol, [mic], "args")

            self.assertEqual(
                protocol.failed_ids,
                [1],
                "A Gautomatch execution failure must be recorded as FAILED so "
                "it is not indistinguishable from a valid zero-pick micrograph.",
            )


if __name__ == "__main__":
    unittest.main()

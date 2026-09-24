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
    def testProtocolFailsWhenAllInputMicrographsFailed(self):
        class _InputMics:
            def __init__(self, ids):
                self._mics = [_Mic(obj_id, 'mic_%03d.mrc' % obj_id)
                              for obj_id in ids]

            def __iter__(self):
                return iter(self._mics)

        class _OutputHarness:
            def __init__(self, tmp_dir):
                self.tmp_dir = tmp_dir
                self.input_mics = _InputMics([1, 2])

            def _getAllFailed(self):
                return os.path.join(self.tmp_dir, 'FAILED_all.TXT')

            def getInputMicrographs(self):
                return self.input_mics

        with tempfile.TemporaryDirectory() as tmp:
            protocol = _OutputHarness(tmp)
            with open(protocol._getAllFailed(), 'w') as handle:
                handle.write('1\n2\n')

            with self.assertRaisesRegex(
                RuntimeError,
                'Gautomatch failed for all input micrographs',
            ):
                ProtGautomatch.createOutputStep(protocol)

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


    def testRejectedCoordinatesDoNotCreateUnusedAuxiliarySet(self):
        class _RejectedHarness:
            def __init__(self):
                self.writeCC = False
                self.writeFilt = False
                self.writeBg = False
                self.writeBgSub = False
                self.writeSigma = False
                self.writeMsk = False

            def getInputMicrographs(self):
                return object()

            def _getPath(self, name):
                return "/tmp/" + name

            def _createSetOfCoordinates(self, *args, **kwargs):
                raise AssertionError(
                    "Unused rejected-coordinate auxiliary Set must not be created."
                )

            def getMicrographsDir(self):
                return "/tmp"

            def _getBoxSize(self):
                return 100

        protocol = _RejectedHarness()

        with patch(
            "gautomatch.protocols.protocol_gautomatch.os.path.exists",
            return_value=False,
        ):
            ProtGautomatch.readRejectedCoordsFromMics(protocol, [])



    def testRestartClearsFailuresFromPreviousExecution(self):
        class _RestartHarness:
            def __init__(self, tmp_dir):
                self.tmp_dir = tmp_dir
                self.exclusive = False

            def getMicrographsDir(self):
                return os.path.join(self.tmp_dir, "micrographs")

            def _getReferencesFn(self):
                return None

            def convertReferences(self, ref_stack):
                pass

            def _getAllFailed(self):
                return os.path.join(self.tmp_dir, "FAILED_all.TXT")

            def isContinued(self):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            protocol = _RestartHarness(tmp)
            failed_fn = protocol._getAllFailed()

            with open(failed_fn, "w") as handle:
                handle.write("1\n2\n")

            ProtGautomatch.convertInputStep(protocol)

            self.assertFalse(
                os.path.exists(failed_fn),
                "Restart must not inherit failures from a previous execution.",
            )



if __name__ == "__main__":
    unittest.main()

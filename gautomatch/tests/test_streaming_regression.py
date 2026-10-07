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
    # Gautomatch is handed links named after these, so the harness uses
    # the real naming rather than a guess at it.
    _itemScopedName = ProtGautomatch._itemScopedName
    _getScopedMicName = ProtGautomatch._getScopedMicName
    _getRubbishCoordsFn = ProtGautomatch._getRubbishCoordsFn

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


SAME_BASENAME_A = '/data/sessionA/mic001.mrc'
SAME_BASENAME_B = '/data/sessionB/mic001.mrc'


class _NamedMic:
    def __init__(self, objId, fileName):
        self._objId = objId
        self._fileName = fileName

    def getObjId(self):
        return self._objId

    def getFileName(self):
        return self._fileName

    def setFileName(self, fileName):
        self._fileName = fileName


class _NamingHarness(ProtGautomatch):
    def __init__(self, micsDir):
        self._micsDir = micsDir

    def getMicrographsDir(self):
        return self._micsDir

    def _getExtraPath(self, *parts):
        return os.path.join(self._micsDir, *parts)


class TestGautomatchArtefactNamesDoNotCollide(unittest.TestCase):
    """Gautomatch names its output after each input file, and those
    outputs are collected into one flat directory for the whole run.

    A Set can hold /data/sessionA/mic001.mrc and /data/sessionB/mic001.mrc
    at once: different micrographs, one basename. Keyed on that alone the
    second one's coordinates overwrite the first's, and both micrographs
    read the survivor's particles back.
    """

    def setUp(self):
        self.micsDir = tempfile.mkdtemp()
        self.harness = _NamingHarness(self.micsDir)

    def test_TheInputNameHandedToGautomatchIsDistinct(self):
        first = self.harness._getScopedMicName(_NamedMic(1, SAME_BASENAME_A))
        second = self.harness._getScopedMicName(_NamedMic(2, SAME_BASENAME_B))

        self.assertNotEqual(
            first,
            second,
            "Gautomatch is handed two inputs with the same name, so it "
            "writes one set of coordinates for both.",
        )

    def test_TheOriginalBasenameStaysInTheName(self):
        """Keep it recognisable in gautomatch's own logs and output."""
        self.assertIn(
            'mic001',
            self.harness._getScopedMicName(_NamedMic(1, SAME_BASENAME_A)),
        )

    def test_TheRubbishCoordinatesFileIsDistinct(self):
        first = self.harness._getRubbishCoordsFn(
            self.micsDir, _NamedMic(1, SAME_BASENAME_A))
        second = self.harness._getRubbishCoordsFn(
            self.micsDir, _NamedMic(2, SAME_BASENAME_B))

        self.assertNotEqual(
            first,
            second,
            "The bad coordinates excluded from one micrograph would be "
            "applied to the other.",
        )

    def test_TheDebugOutputNameIsDistinct(self):
        first = self.harness.getOutputName(_NamedMic(1, SAME_BASENAME_A),
                                           '_ccmax')
        second = self.harness.getOutputName(_NamedMic(2, SAME_BASENAME_B),
                                            '_ccmax')

        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith('.mrc'))

    def test_TheNameIsStableForTheSameMicrograph(self):
        """Resume re-derives these and has to land on the same files."""
        mic = _NamedMic(7, SAME_BASENAME_A)

        self.assertEqual(
            self.harness._getScopedMicName(mic),
            self.harness._getScopedMicName(_NamedMic(7, SAME_BASENAME_A)),
        )


class _RealMicHarness(ProtGautomatch):
    """Drives the real batch preparation against a temporary workspace."""

    _itemScopedName = ProtGautomatch._itemScopedName

    def __init__(self, root):
        self._root = root
        self.inputBadCoords = _Value(None)
        self.exclusive = False
        self.handedToGautomatch = None
        self.errors = []

    def _getMicrographDir(self, mic):
        return os.path.join(self._root, 'work')

    def getMicrographsDir(self):
        return os.path.join(self._root, 'extra')

    def _getReferencesFn(self):
        return None

    def runJob(self, *args, **kwargs):
        pass

    def error(self, message):
        self.errors.append(message)

    def _writeFailedList(self, micList):
        pass


class TestGautomatchIsHandedUnambiguousInputs(unittest.TestCase):
    """It is the batch preparation, not the naming helper, that decides
    what gautomatch actually sees."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, 'extra'))

    def _realMic(self, objId, name):
        session = os.path.join(self.root, 'session%d' % objId)
        os.makedirs(session, exist_ok=True)
        path = os.path.join(session, name)
        with open(path, 'w') as handle:
            handle.write('micrograph')
        return _NamedMic(objId, path)

    def test_BothMicrographsReachGautomatch(self):
        mics = [self._realMic(1, 'mic001.mrc'), self._realMic(2, 'mic001.mrc')]
        harness = _RealMicHarness(self.root)
        seen = {}

        def _runGautomatch(micFnList, *args, **kwargs):
            seen['files'] = list(micFnList)

        with patch('gautomatch.Plugin.runGautomatch', _runGautomatch):
            with patch('gautomatch.Plugin.getEnviron', lambda: {}):
                ProtGautomatch._pickMicrographList(harness, mics)

        self.assertEqual(
            len(set(os.path.basename(f) for f in seen['files'])),
            2,
            "Gautomatch was handed two inputs under one name, so it "
            "writes a single set of coordinates for both micrographs.",
        )


class _CoordsReadHarness(ProtGautomatch):
    _itemScopedName = ProtGautomatch._itemScopedName

    def __init__(self, micsDir):
        self._micsDir = micsDir

    def getMicrographsDir(self):
        return self._micsDir


class TestGautomatchReadsBackWhatItWrote(unittest.TestCase):
    """The name coordinates are read back under has to match the name
    gautomatch wrote them under - including for a run picked before
    those names carried the micrograph id."""

    def setUp(self):
        self.micsDir = tempfile.mkdtemp()
        self.harness = _CoordsReadHarness(self.micsDir)

    def _write(self, name):
        with open(os.path.join(self.micsDir, name + '_automatch.star'),
                  'w') as handle:
            handle.write('')

    def test_TheScopedNameIsUsedWhenThisRunWroteIt(self):
        mic = _NamedMic(1, SAME_BASENAME_A)
        scoped = os.path.splitext(self.harness._getScopedMicName(mic))[0]
        self._write(scoped)

        self.assertEqual(self.harness._getCoordsBaseName(mic), scoped)

    def test_AnOlderRunsCoordinatesAreStillFound(self):
        mic = _NamedMic(1, SAME_BASENAME_A)
        self._write('mic001')

        self.assertEqual(
            self.harness._getCoordsBaseName(mic),
            'mic001',
            "Coordinates an earlier run already picked must still be the "
            "ones this run reads.",
        )

    def test_TheReaderIsGivenThatName(self):
        """readCoordsFromMics is the call site that has to pass it."""
        mic = _NamedMic(1, SAME_BASENAME_A)
        self._write('mic001')
        seen = {}

        def _read(workDir, micSet, coordSet, suffix=None, nameFunc=None):
            seen['nameFunc'] = nameFunc

        class _Coords:
            def getBoxSize(self):
                return 1

        with patch('gautomatch.protocols.protocol_gautomatch'
                   '.readSetOfCoordinates', _read):
            with patch.object(_CoordsReadHarness,
                              'readRejectedCoordsFromMics',
                              lambda self, micList: None):
                ProtGautomatch.readCoordsFromMics(
                    self.harness, self.micsDir, [mic], _Coords())

        self.assertIsNotNone(
            seen['nameFunc'],
            "Without a namer the reader falls back to the basename and "
            "reads the wrong micrograph's coordinates.",
        )
        self.assertEqual(seen['nameFunc'](mic), 'mic001')


class TestGautomatchConvertDefaultIsUnchanged(unittest.TestCase):
    """The conversion helper is shared; its default must keep naming
    exactly as it always did."""

    def test_TheDefaultNamerIsThePlainBasename(self):
        from gautomatch import convert

        micsDir = tempfile.mkdtemp()
        mic = _NamedMic(1, SAME_BASENAME_A)
        with open(os.path.join(micsDir, 'mic001_automatch.star'),
                  'w') as handle:
            handle.write('')

        read = []

        def _readCoordinates(mic, fileName, coordsSet):
            read.append(fileName)

        with patch.object(convert, 'readCoordinates', _readCoordinates):
            convert.readSetOfCoordinates(micsDir, [mic], None)

        self.assertEqual(
            [os.path.join(micsDir, 'mic001_automatch.star')],
            read,
            "Without an explicit namer the helper must keep reading the "
            "plain basename.",
        )


if __name__ == "__main__":
    unittest.main()

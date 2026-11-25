# ***************************************************************************
# *
# * Gautomatch picking in streaming: no micrograph is lost to batching, a
# * failed one is left out and picked again on Continue, a micrograph is
# * published whole, and the run fails only when every micrograph failed.
# *
# ***************************************************************************

import json
import os
import tempfile
import unittest
from collections import OrderedDict
from unittest.mock import patch

import gautomatch.protocols.protocol_gautomatch as module
from gautomatch.protocols.protocol_gautomatch import ProtGautomatch


class _Mic:
    def __init__(self, objId):
        self._objId = objId

    def getObjId(self):
        return self._objId

    def getMicName(self):
        return "mic_%03d" % self._objId

    def getFileName(self):
        return "/data/mic_%03d.mrc" % self._objId


class _StoredValue:
    def __init__(self, value):
        self._value = value

    def get(self, default=None):
        return self._value


class _PickStep:
    def __init__(self, micName):
        self.funcName = _StoredValue("pickMicrographListStep")
        self.argsStr = _StoredValue(json.dumps([[micName]]))

    def isFinished(self):
        return True


class _Coords:
    def __init__(self):
        self.items = []

    def getBoxSize(self):
        return 64

    def append(self, coord):
        self.items.append(coord)

    def getSize(self):
        return len(self.items)


class _Gautomatch(ProtGautomatch):
    def __init__(self, root, batchSize=1):
        self._root = root
        os.makedirs(os.path.join(root, 'extra', 'micrographs'), exist_ok=True)
        self.micDict = OrderedDict()
        self._steps = []
        self._prevSteps = []
        self.streamClosed = False
        self.errors = []
        self.batches = []
        self.published = []
        self._batchSize = batchSize
        self.initialIds = []
        self.inputBadCoords = _StoredValue(None)

    def _getExtraPath(self, *paths):
        return os.path.join(self._root, 'extra', *paths)

    def getMicrographsDir(self):
        return self._getExtraPath('micrographs')

    def _getCoordsBaseName(self, mic):
        return 'mic_%03d' % mic.getObjId()

    def _getStreamingBatchSize(self):
        return self._batchSize

    def _getPickArgs(self):
        return []

    def _insertPickMicrographListStep(self, micList, prerequisites, *args):
        self.batches.append([mic.getObjId() for mic in micList])
        return len(self.batches)

    def _insertPickMicrographStep(self, mic, prerequisites, *args):
        return self._insertPickMicrographListStep([mic], prerequisites)

    def _updateOutputCoordSet(self, micList, streamMode):
        self.published.append([mic.getObjId() for mic in micList])
        self.readCoordsFromMics(None, micList, self.outputCoordinates)

    def _updateStreamState(self, streamMode):
        pass

    def _getFirstJoinStep(self):
        return None

    def _streamingSleepOnWait(self):
        pass

    def readRejectedCoordsFromMics(self, micList):
        pass

    def error(self, message):
        self.errors.append(message)

    def debug(self, *args):
        pass

    def _write(self, micId, rows=1):
        with open(os.path.join(self.getMicrographsDir(),
                               'mic_%03d_automatch.star' % micId), 'w') as fh:
            fh.write("rows: %d" % rows)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()


class TestNoMicrographIsLostToBatching(_Base):
    def test_TheRemainderOfABatchWaitsForTheNextPoll(self):
        protocol = _Gautomatch(self._tmp.name, batchSize=2)

        protocol._insertNewMicsSteps([_Mic(1), _Mic(2), _Mic(3)])
        protocol._insertNewMicsSteps([_Mic(4)])

        self.assertEqual([[1, 2], [3, 4]], protocol.batches)


def _readRows(mic, fileName, coordSet):
    with open(fileName) as fh:
        rows = int(fh.read().split(':')[1])

    for row in range(rows):
        coordSet.append((mic.getObjId(), row))

    if mic.getObjId() == 2:
        raise ValueError("corrupted row")


class TestAMicrographIsPublishedWhole(_Base):
    def test_AStarThatFailsHalfWayPublishesNothingOfItsMicrograph(self):
        protocol = _Gautomatch(self._tmp.name)
        protocol._write(1, rows=2)
        protocol._write(2, rows=2)
        coords = _Coords()

        with patch.object(module, 'readCoordinates', _readRows):
            protocol.readCoordsFromMics(None, [_Mic(1), _Mic(2)], coords)

        self.assertEqual([(1, 0), (1, 1)], coords.items)
        self.assertEqual({2}, protocol._failedPickingMicIds())

    def test_AMissingStarIsAFailureNotAnEmptyMicrograph(self):
        protocol = _Gautomatch(self._tmp.name)
        coords = _Coords()

        protocol.readCoordsFromMics(None, [_Mic(1)], coords)

        self.assertEqual({1}, protocol._failedPickingMicIds())

    def test_GautomatchLeavingOneOutputOutFailsOnlyThatMicrograph(self):
        protocol = _Gautomatch(self._tmp.name)

        def run(micFnList, refs, micPath, *args, **kwargs):
            open(os.path.join(micPath, 'mic_001_automatch.star'), 'w').close()

        protocol._getMicrographDir = lambda mic: os.path.join(
            self._tmp.name, 'work')
        protocol._getReferencesFn = lambda: None
        protocol.exclusive = False

        with patch.object(module.gautomatch.Plugin, 'runGautomatch', run), \
                patch.object(module.gautomatch.Plugin, 'getEnviron',
                             lambda: {}):
            protocol._pickMicrographList([_Mic(1), _Mic(2)])

        self.assertEqual({2}, protocol._failedPickingMicIds())


class TestPickingAlwaysEnds(_Base):
    def _closing(self):
        protocol = _Gautomatch(self._tmp.name)
        protocol.streamClosed = True
        protocol.outputCoordinates = _Coords()
        protocol.micDict["mic_001"] = _Mic(1)
        protocol._steps = [_PickStep("mic_001")]
        protocol._getPublishedPickingMicIds = lambda: set()
        return protocol

    def test_AMicrographWithoutCoordinatesIsReadOnceAndTheRunEnds(self):
        protocol = self._closing()
        protocol.streamClosed = False
        protocol._write(1, rows=0)

        with patch.object(module, 'readCoordinates', _readRows):
            protocol._checkNewOutput()
            protocol._checkNewOutput()
            protocol.streamClosed = True
            protocol._checkNewOutput()

        self.assertEqual([[1]], protocol.published)
        self.assertTrue(protocol.finished)

    def test_EveryMicrographFailedFailsTheRun(self):
        protocol = self._closing()

        with self.assertRaisesRegex(Exception, "failed for every one"):
            protocol._checkNewOutput()


class TestFailedMicrographsArePickedAgain(_Base):
    def test_ContinueRunsTheStepOfAFailedMicrographAgain(self):
        protocol = _Gautomatch(self._tmp.name)
        protocol.micDict["mic_001"] = _Mic(1)
        protocol.micDict["mic_002"] = _Mic(2)
        results = protocol._pickingStepResults(["mic_001", "mic_002"])
        marker = protocol._getExtraPath('DONE', 'mic_000002.TXT')
        os.makedirs(os.path.dirname(marker))
        open(marker, 'w').close()
        protocol._recordFailedPicking([2])

        ProtGautomatch._prepareFailedForRetry(protocol)

        self.assertEqual([True, False], [os.path.exists(r) for r in results])
        self.assertFalse(os.path.exists(marker))

    def test_ItsOldFinishedStepDoesNotPublishIt(self):
        protocol = _Gautomatch(self._tmp.name)
        protocol._recordFailedPicking([2])
        protocol._failedPickingMicIdsCache = None
        protocol.micDict["mic_001"] = _Mic(1)
        protocol.micDict["mic_002"] = _Mic(2)
        protocol._prevSteps = [_PickStep("mic_001"), _PickStep("mic_002")]

        self.assertEqual({"mic_001"}, protocol._getFinishedPickingMicNames())

        protocol._steps.append(_PickStep("mic_002"))

        self.assertEqual({"mic_001", "mic_002"},
                         protocol._getFinishedPickingMicNames())

    def test_AMicrographPickedWellIsNoLongerFailed(self):
        protocol = _Gautomatch(self._tmp.name)
        protocol._recordFailedPicking([1])

        protocol._forgetFailedPicking([1])

        self.assertEqual(set(), _Gautomatch(self._tmp.name)._failedPickingMicIds())


if __name__ == '__main__':
    unittest.main()

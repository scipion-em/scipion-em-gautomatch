# **************************************************************************
# *
# * Cost of one streaming poll, and completion without sidecar files.
# *
# **************************************************************************

"""A poll must cost what just arrived, not everything seen so far.

These protocols run for as long as their producer does and their input
Sets keep growing, so anything done per poll over every item seen makes
them slower the longer they run - exactly when there is most data.
"""

import unittest

from gautomatch.protocols.protocol_gautomatch import ProtGautomatch
from gautomatch.protocols.protocol_streaming_base import GautomatchStreamingBase

from .logical_set_fakes import LogicalSetFake


class _Mic:
    def __init__(self, objId, micName=None):
        self._objId = objId
        self._micName = micName or "mic_%03d" % objId

    def getObjId(self):
        return self._objId

    def getMicName(self):
        return self._micName

    def clone(self):
        return _Mic(self._objId, self._micName)


class _StaleCloseSet(LogicalSetFake):
    """Its closed flag only becomes visible after a reload."""

    def __init__(self, items, closedAfterReloads=2):
        super().__init__(items, streamClosed=False)
        self.closedAfterReloads = closedAfterReloads

    def loadAllProperties(self):
        super().loadAllProperties()

        if self.reloads >= self.closedAfterReloads:
            self._streamClosed = True


class _DiscoveryHarness(ProtGautomatch):
    def __init__(self, inputSet):
        self.micDict = {}
        self._inputSet = inputSet
        self.streamClosed = False
        self.insertedMicNames = []
        self.updateStepsCalls = 0

    def getInputMicrographs(self):
        return self._inputSet

    def _insertNewMicsSteps(self, newMics):
        newMics = list(newMics)
        self.insertedMicNames.extend(mic.getMicName() for mic in newMics)

        for mic in newMics:
            self.micDict[mic.getMicName()] = mic

        return []

    def _getFirstJoinStep(self):
        return None

    def updateSteps(self):
        self.updateStepsCalls += 1

    def debug(self, *args, **kwargs):
        pass


def _mics(firstId, count):
    return [_Mic(objId) for objId in range(firstId, firstId + count)]


class TestGautomatchStreamingPollCost(unittest.TestCase):
    def testPollOnlyHydratesMicrographsThatJustArrived(self):
        inputSet = LogicalSetFake(_mics(1, 500))
        protocol = _DiscoveryHarness(inputSet)

        protocol._checkNewInput()

        self.assertEqual(500, inputSet.hydratedItems)

        inputSet.addItems(_mics(501, 3))
        hydratedBefore = inputSet.hydratedItems

        protocol._checkNewInput()

        self.assertEqual(3, inputSet.hydratedItems - hydratedBefore)
        self.assertEqual(0, inputSet.fullScans)

    def testIdlePollHydratesNothingAtAll(self):
        inputSet = LogicalSetFake(_mics(1, 500))
        protocol = _DiscoveryHarness(inputSet)

        protocol._checkNewInput()
        hydratedBefore = inputSet.hydratedItems

        protocol._checkNewInput()

        self.assertEqual(hydratedBefore, inputSet.hydratedItems)

    def testDiscoveryNeverLooksAtAStorageFilename(self):
        # LogicalSetFake.getFileName() raises, so this passes only if
        # discovery goes entirely through the Set API.
        inputSet = LogicalSetFake(_mics(1, 4), streamClosed=True)
        protocol = _DiscoveryHarness(inputSet)

        protocol._checkNewInput()

        self.assertEqual(4, len(protocol.insertedMicNames))
        self.assertTrue(protocol.streamClosed)

    def testStreamClosingIsSeenEvenWhenNothingNewArrives(self):
        # isStreamClosed() reads a Set property, so a poll that skipped the
        # reload would never notice the producer closing.
        inputSet = _StaleCloseSet(_mics(1, 2))
        protocol = _DiscoveryHarness(inputSet)

        protocol._checkNewInput()
        self.assertFalse(protocol.streamClosed)

        protocol._checkNewInput()
        self.assertTrue(protocol.streamClosed)


class _CoordOutput(LogicalSetFake):
    def __init__(self, micIds):
        super().__init__([], streamClosed=False)
        self._micIds = list(micIds)

    def getUniqueValues(self, attributes, where=None):
        if attributes == '_micId':
            return list(self._micIds)

        return super().getUniqueValues(attributes, where=where)


class _JoinStep:
    """Stands in for the createOutputStep scheduled with wait=True."""

    def __init__(self):
        self.status = 'waiting'

    def isWaiting(self):
        return self.status == 'waiting'

    def setStatus(self, value):
        self.status = value


class _FinishedPickStep:
    funcName = 'pickMicrographListStep'

    def __init__(self, argsStr):
        self.argsStr = argsStr

    def isFinished(self):
        return True


class _OutputHarness(ProtGautomatch):
    """Fails loudly if completion is read from or written to a DONE file."""

    def __init__(self, streamClosed=True, publishedMicIds=()):
        self.micDict = {mic.getMicName(): mic for mic in _mics(1, 2)}
        self._steps = [_FinishedPickStep('["mic_001", {}]'),
                       _FinishedPickStep('["mic_002", {}]')]
        self.streamClosed = streamClosed
        self.published = []
        self.streamStates = []
        self.joinStep = _JoinStep()
        self.outputCoordinates = _CoordOutput(publishedMicIds)

    def _readDoneList(self):
        raise AssertionError("Completion must not be read from DONE/all.TXT.")

    def _writeDoneList(self, micList):
        raise AssertionError("Completion must not be written to DONE/all.TXT.")

    def _isMicDone(self, mic):
        raise AssertionError(
            "Completion must not depend on a per-micrograph DONE file.")

    def _updateOutputCoordSet(self, micList, streamMode):
        self.published.append([mic.getMicName() for mic in micList])
        return list(micList)

    def _updateStreamState(self, streamMode):
        self.streamStates.append(streamMode)

    def _getFirstJoinStep(self):
        return self.joinStep

    def _streamingSleepOnWait(self):
        pass

    def debug(self, *args, **kwargs):
        pass


class TestGautomatchCompletionWithoutSidecars(unittest.TestCase):
    def testCompletionComesFromTheStepGraph(self):
        protocol = _OutputHarness()

        protocol._checkNewOutput()

        self.assertEqual([["mic_001", "mic_002"]], protocol.published)

    def testAlreadyPublishedMicrographIsNotPublishedTwice(self):
        protocol = _OutputHarness(publishedMicIds=[1, 2])

        protocol._checkNewOutput()

        self.assertEqual([], protocol.published)

    def testFinishingReleasesTheWaitingOutputStep(self):
        # createOutputStep is scheduled with wait=True and stays WAITING
        # until this releases it; forget that and the protocol hangs with
        # its output complete.
        protocol = _OutputHarness()

        protocol._checkNewOutput()

        self.assertTrue(protocol.finished)
        self.assertEqual('new', protocol.joinStep.status)

    def testOutputStepIsNotReleasedWhileTheStreamIsStillOpen(self):
        protocol = _OutputHarness(streamClosed=False)

        protocol._checkNewOutput()

        self.assertFalse(protocol.finished)
        self.assertEqual('waiting', protocol.joinStep.status)


class TestGautomatchStepGraphScan(unittest.TestCase):
    def testScanReadsStepsRestoredOnResume(self):
        # Work finished before a Continue lives in _prevSteps; reading only
        # _steps would make it invisible and schedule it all over again.
        protocol = _OutputHarness()
        protocol._steps = [_FinishedPickStep('["mic_002", {}]')]
        protocol._prevSteps = [_FinishedPickStep('["mic_001", {}]')]

        self.assertEqual(
            {"mic_001", "mic_002"},
            protocol._getFinishedPickingMicNames(),
        )

    def testScanDoesNotReparseStepsItAlreadyRead(self):
        protocol = _OutputHarness()
        parsed = []
        original = GautomatchStreamingBase._parseStepArgKeys

        def countingParse(step, dictField, keyType):
            parsed.append(step)
            return original(step, dictField, keyType)

        # A plain function, not staticmethod(): an instance attribute is
        # never bound, and a staticmethod object is only callable itself
        # from Python 3.10 on.
        protocol._parseStepArgKeys = countingParse
        protocol._steps = [_FinishedPickStep('["mic_%03d", {}]' % i)
                           for i in range(1, 201)]

        self.assertEqual(200, len(protocol._getFinishedPickingMicNames()))
        self.assertEqual(200, len(parsed))

        protocol._steps.append(_FinishedPickStep('["mic_201", {}]'))

        self.assertEqual(201, len(protocol._getFinishedPickingMicNames()))
        self.assertEqual(201, len(parsed))


if __name__ == "__main__":
    unittest.main()


class _StuckClosedSet:
    """A producer that closed declaring more items than it ever shows.

    The declared size never comes down and the missing row never turns
    up: the view is terminally inconsistent, for good.
    """

    def __init__(self, declaredSize=100, visibleIds=None):
        self._declaredSize = declaredSize
        self._visibleIds = list(visibleIds if visibleIds is not None
                                else range(1, 100))

    def getSize(self):
        return self._declaredSize

    def isStreamClosed(self):
        return True

    def getUniqueValues(self, attributes, where=None):
        return list(self._visibleIds) if where is None else []

    def close(self):
        pass


class _TerminalStallHarness(GautomatchStreamingBase):
    """Reconciles a closed-but-inconsistent stream, poll after poll."""

    def __init__(self, activeWork=False):
        self._lastInputId = 0
        self._activeWork = activeWork

    def _hasActiveStreamingWork(self):
        return self._activeWork

    def poll(self, inputSet):
        return self._reconcileClosedStreamIds(inputSet, [], set(), True, '_lastInputId')


class TestTerminalInconsistencyDoesNotHangForever(unittest.TestCase):
    """A closed producer whose view never becomes consistent must not
    leave the protocol polling for the rest of time."""

    def _pollUntilRaises(self, harness, inputSet, limit=200):
        for poll in range(limit):
            try:
                harness.poll(inputSet)
            except RuntimeError as error:
                return poll + 1, str(error)

        return None, None

    def testAPermanentlyInconsistentViewEventuallyFails(self):
        polls, message = self._pollUntilRaises(_TerminalStallHarness(),
                                               _StuckClosedSet())

        self.assertIsNotNone(
            polls,
            "The producer closed declaring 100 items and only 99 are ever "
            "visible: polling for that hundredth row never ends.",
        )
        self.assertIn('99', message)
        self.assertIn('100', message)

    def testItGivesTheViewSeveralChancesFirst(self):
        """A lagging view usually catches up; do not fail on poll one."""
        polls, _ = self._pollUntilRaises(_TerminalStallHarness(),
                                         _StuckClosedSet())

        self.assertGreater(
            polls,
            3,
            "Giving up almost immediately would turn an ordinary lag into "
            "a failed protocol.",
        )

    def testProgressResetsTheCount(self):
        harness = _TerminalStallHarness()
        inputSet = _StuckClosedSet()

        for _ in range(5):
            harness.poll(inputSet)

        inputSet._visibleIds.append(100)
        harness.poll(inputSet)

        self.assertEqual(
            harness._terminalStallCount,
            0,
            "The view did become consistent; nothing is stalled.",
        )

    def testWorkInFlightIsAlsoProgress(self):
        """A long scientific round must not be mistaken for a stall."""
        polls, _ = self._pollUntilRaises(
            _TerminalStallHarness(activeWork=True), _StuckClosedSet(),
            limit=60)

        self.assertIsNone(
            polls,
            "Work was in flight the whole time: that is progress, however "
            "long it takes.",
        )

    def testAConsistentViewIsNeverAffected(self):
        harness = _TerminalStallHarness()
        inputSet = _StuckClosedSet(declaredSize=99)

        for _ in range(50):
            _, consistent = harness.poll(inputSet)

        self.assertTrue(consistent)

# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk)
# *
# * MRC Laboratory of Molecular Biology (MRC-LMB)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************

import os
from glob import glob

import pyworkflow.utils as pwutils
from pyworkflow.constants import PROD
import pyworkflow.protocol.params as params
from pyworkflow.utils.properties import Message
from pyworkflow.protocol import STEPS_PARALLEL
from pwem.constants import RELATION_CTF
from pwem.objects import SetOfCoordinates
from pwem.protocols import ProtParticlePickingAuto

import gautomatch
from gautomatch.convert import (readSetOfCoordinates, writeDefectsFile,
                                writeMicCoords)
from gautomatch.constants import MICS_ALL, MICS_SUBSET


class ProtGautomatch(ProtParticlePickingAuto):
    """ Automated particle picker for SPA.

    Gautomatch is a GPU accelerated program for accurate, fast, flexible and
    fully automatic particle picking from cryo-EM micrographs with or without
    templates.
    """
    _label = 'auto-picking'
    _devStatus = PROD
    stepsExecutionMode = STEPS_PARALLEL


    # --------------------------- DEFINE param functions ----------------------
    def _defineParams(self, form):

        ProtParticlePickingAuto._defineParams(self, form)
        form.addParam('inputReferences', params.PointerParam,
                      pointerClass='SetOfAverages',
                      label='Input References', important=True,
                      allowsNull=True,
                      help="Template images (2D class averages or "
                           "reprojections from a reference volume) to be used "
                           "in picking.\n "
                           "If not provided, references will be "
                           "auto-generated. This is fine for *spherical "
                           "particles* like virus or ribosome.")
        form.addParam('invertTemplatesContrast',
                      params.BooleanParam, default=True,
                      label='References have inverted contrast',
                      help='Set to Yes to indicate that the reference have '
                           'inverted contrast with respect to the particles '
                           'in the micrographs.\n'
                           'Keep in mind that auto-generated templates will '
                           'be WHITE.')
        form.addParam('angStep', params.IntParam, default=5,
                      label='Angular step size',
                      help='Angular step size for picking, in degrees')
        form.addParam('micrographsSelection', params.EnumParam,
                      default=MICS_ALL,
                      choices=['All', 'Subset'],
                      display=params.EnumParam.DISPLAY_HLIST,
                      label='Micrographs for wizard',
                      help='Select which micrographs will be used for '
                           'optimizing the parameters in the wizard. '
                           'By default, ALL micrograph are used. '
                           'You can select to use a subset based on '
                           'defocus values (where micrographs will be '
                           'taken from different defocus). ')
        form.addParam('micrographsNumber', params.IntParam, default='10',
                      condition='micrographsSelection==%d' % MICS_SUBSET,
                      label='Micrographs for optimization:',
                      help='Select the number of micrographs that you want '
                           'to be used for the parameters optimization. ')
        form.addParam('ctfRelations', params.RelationParam,
                      relationName=RELATION_CTF,
                      attributeName='getInputMicrographs',
                      condition='micrographsSelection==%d' % MICS_SUBSET,
                      label='CTF estimation',
                      help='Choose some CTF estimation related to the '
                           'input micrographs to create the subset '
                           'by defocus values.')

        form.addParam('threshold', params.FloatParam, default=0.1,
                      label='Threshold',
                      help='Particles with CCC above the threshold will be '
                           'picked')
        form.addParam('particleSize', params.IntParam, default=-1,
                      label='Particle radius (A)',
                      allowsPointers=True,
                      help="Particle radius in Angstrom. Default -1 means "
                           "it will be equal to 75% of references size if they "
                           "were provided, otherwise 250 A.")
        form.addHidden(params.GPU_LIST, params.StringParam, default='0',
                       label="Choose GPU IDs")

        form.addSection(label='Advanced')
        form.addParam('advanced', params.BooleanParam, default=True,
                      label='Guess advanced parameters?',
                      help="By default, the program will optimize advanced "
                           "parameters by itself, however if you want to "
                           "modify them, select No")
        form.addParam('boxSize', params.IntParam, default=-1,
                      label='Box size (pix)', condition='not advanced', allowsPointers=True,
                      help="Box size, in pixels; a suggested value will be "
                           "automatically calculated using pixel size and "
                           "particle size")
        form.addParam('minDist', params.IntParam, default=300,
                      label='Min inter-particle distance (A)',
                      condition='not advanced',
                      allowsPointers=True,
                      help='Minimum distance between particles in Angstrom\n '
                           'Use value of 0.9~1.1X diameter; '
                           'can be 0.3~0.5X for filament-like particle')
        form.addParam('speed', params.IntParam, default=2,
                      label='Speed', condition='not advanced',
                      help='Speed level {0,1,2,3,4}. The bigger the faster, '
                           'but less accurate.\n'
                           'Suggested values: 2 for >1 MDa complex, 1 for <500 '
                           'kD complex, 1 or 2 for 500~1000 kD.\n'
                           '0 is not suggested, because the accuracy is simply '
                           'fitting noise, unless for special noise-free '
                           'micrographs. Use 3 for huge viruses, but 2 is '
                           'still preferred. Probably do not use 4 at all, '
                           'it is not accurate in general.')

        form.addSection(label='Sigma & avg')
        form.addParam('advLabel', params.LabelParam,
                      important=True,
                      label='To adjust these parameters, select "No" for the '
                            '"Guess advanced parameters?" on the Advanced tab.')
        group = form.addGroup('Local sigma parameters',
                              condition='not advanced')
        group.addParam('localSigmaCutoff', params.FloatParam, default=1.2,
                       label='Local sigma cut-off',
                       help='Local sigma cut-off (relative value), 1.2~1.5 '
                            'should be a good range\n'
                            'Normally a value >1.2 will be ice, protein '
                            'aggregation or contamination.\n'
                            'This option is designed to get rid of sharp '
                            'carbon/ice edges or sharp metal particles.')
        group.addParam('localSigmaDiam', params.IntParam, default=100,
                       label='Local sigma diameter (A)',
                       allowsPointers=True,
                       help='Diameter for estimation of local sigma, '
                            'in Angstrom.\n'
                            'Usually this diameter could be 0.5-2x of your '
                            'particle diameter according to several factors. '
                            'When using bigger values, normally you should '
                            'decrease *Local sigma cut-off*. For smaller and '
                            'sharper high density contamination/ice/metal '
                            'particles you could use a smaller diameter and '
                            'larger *Local sigma cut-off*')

        group = form.addGroup('Local average parameters',
                              condition='not advanced')
        line = group.addLine('Local average range',
                             help="Local average cut-off (relative value), "
                                  "any pixel values outside the range will be "
                                  "considered as ice/aggregation/carbon etc.\n"
                                  "Min parameter is used to reject the central "
                                  "parts of ice, carbon etc. which normally "
                                  "have lower density than the particles.\n"
                                  "Max parameter is usually not useful for "
                                  "cryo-EM micrograph with black particles, "
                                  "but might be helpfull to get rid of 'hot' "
                                  "area. For negative stain micrograph, if it "
                                  "rejects most of the true particles, just "
                                  "set Max to very big value like 10.0.")
        line.addParam('localAvgMin', params.FloatParam, default=-1.0,
                      label='Min')
        line.addParam('localAvgMax', params.FloatParam, default=1.0,
                      label='Max')
        group.addParam('localAvgDiam', params.IntParam, default=100,
                       label='Local average diameter (A)',
                       allowsPointers=True,
                       help='Diameter for estimation of local average, in '
                            'Angstrom. 1.5~2.0X particle diameter suggested.\n'
                            'However, if you have sharp/small ice or any '
                            'dark/bright dots, using a smaller value will be '
                            'much better to get rid of these areas')

        form.addSection(label='Filter')
        line = form.addLine('Micrograph band-pass filter range (A)',
                            help="Apply band-pass filter on the micrographs:\n"
                                 "low-pass filter to increase the contrast of "
                                 "raw micrographs, suggested range 20~50 A\n"
                                 "high-pass filter to get rid of the global "
                                 "background of raw micrographs, suggested "
                                 "range 200~2000 A. This filter is applied "
                                 "after ice/carbon/ contamination detection, "
                                 "but before true particle detection")
        line.addParam('lowPass', params.IntParam, default=30,
                      label='Min')
        line.addParam('highPass', params.IntParam, default=1000,
                      label='Max')

        form.addParam('preFilt', params.BooleanParam, default=False,
                      label='Pre-filter micrographs?',
                      help="This band-pass pre-filter is normally not "
                           "suggested, because it can affect ice/carbon "
                           "detection. Use it only if you have a severe ice "
                           "gradient.")
        line = form.addLine('Pre-filter range (A)', condition='preFilt')
        line.addParam('prelowPass', params.IntParam, default=8,
                      label='Min')
        line.addParam('prehighPass', params.IntParam, default=1000,
                      label='Max')

        if gautomatch.Plugin.getActiveVersion() != '0.53':
            form.addParam('detectIce', params.BooleanParam, default=True,
                          label='Detect ice/aggregates/carbon?')
            form.addParam('templateNorm', params.IntParam, default=1,
                          validators=[params.Range(1, 3, "value should be "
                                                         "1, 2 or 3. ")],
                          label='Template normalization type',
                          help='Template normalization: 1, 2 or 3 allowed.')
            form.addParam('doBandpass', params.BooleanParam, default=True,
                          label='Do band-pass?',
                          help='Choose No to skip band-pass filtering.')

        form.addSection(label='Exclusive picking')
        form.addParam('exclusive', params.BooleanParam, default=False,
                      label='Exclusive picking?',
                      help='Exclude user-provided areas. This can be useful in '
                           'the following cases:\n\n'
                           '(a) Another cycle of auto-picking after 2D '
                           'classification: in this case, usually you are '
                           'pretty sure that some of the particles are '
                           'completely rubbish, it will be much better to '
                           'exclude them during picking.\n'
                           '(b) Picking for partial structure: sometimes, '
                           'you might have two/multiple domain complex, '
                           'one is severely dominant and affect picking of the '
                           'other (the rest). If you want to focus on another '
                           'domain, it might be quite helpful to exclude such '
                           'good particles from 2D classification.\n'
                           '(c) Strong orientation preference: if your '
                           'templates were severely biased and mainly picked '
                           'the preferred views, then it might be nice to '
                           'exclude the preferred views and focused on '
                           'rare views.')
        form.addParam('inputBadCoords', params.PointerParam, allowsNull=True,
                      pointerClass='SetOfCoordinates', condition='exclusive',
                      label='Coordinates to be excluded',
                      help='Coordinates can be imported beforehand or '
                           'generated from particles using scipion - extract '
                           'coordinates protocol.')
        form.addParam('inputDefects', params.PointerParam, allowsNull=True,
                      pointerClass='SetOfCoordinates', condition='exclusive',
                      label='Detector defects coordinates',
                      help='Occasionally you might have detector defects, e.g. '
                           'a black/white stripe. This will help to get rid of '
                           'these bad areas.')

        form.addSection(label='Debug')
        form.addParam('writeCC', params.BooleanParam, default=False,
                      label='Write CC files?',
                      help='Specify to write out cross-correlation files '
                           'in MRC stack')
        form.addParam('writeFilt', params.BooleanParam, default=False,
                      condition='preFilt',
                      label='Write pre-filtered micrographs?',
                      help='Specify to write out pre-filted micrographs')
        form.addParam('writeBg', params.BooleanParam, default=False,
                      label='Write estimated background?',
                      help='Specify to write out estimated background of '
                           'the micrographs')
        form.addParam('writeBgSub', params.BooleanParam, default=False,
                      label='Write background-subtracted micrographs?',
                      help='Specify to write out background-subtracted '
                           'micrographs')
        form.addParam('writeSigma', params.BooleanParam, default=False,
                      label='Write local sigma?',
                      help='Specify to write out local sigma micrographs')
        form.addParam('writeMsk', params.BooleanParam, default=False,
                      label='Write detected mask?',
                      help='Specify to write out the auto-detected mask (ice, '
                           'contamination, aggregation, carbon edges etc.)')

        self._defineStreamingParams(form)

        # Allow many threads if we can put more than one in a GPU
        # or several GPUs
        form.addParallelSection(threads=1, mpi=1)

    # --------------------------- INSERT steps functions ----------------------
    def _insertInitialSteps(self):
        convId = self._insertFunctionStep(self.convertInputStep, needsGPU=False)
        return [convId]

    # --------------------------- STEPS functions -----------------------------
    def convertInputStep(self):
        """ This step will take of the conversions from the inputs.
        Micrographs: they will be linked if are in '.mrc' format,
            converted otherwise.
        References: will always be converted to '.mrcs' format
        """
        # put output and mics in extra dir
        pwutils.makePath(self.getMicrographsDir())
        # We will always convert the templates to mrcs stack
        self.convertReferences(self._getReferencesFn())
        # Write defects star file if necessary
        if self.exclusive and self.inputDefects.get():
            writeDefectsFile(self.inputDefects.get(), self._getDefectsFn())

    def _pickMicrograph(self, mic, *args):
        self._pickMicrographList([mic], *args)

    def _pickMicrographList(self, micList, *args):
        """ Pick several micrographs at once, probably a bit more efficient."""
        micPath = self._getMicrographDir(micList[0])
        if len(micList) > 1:
            micPath += ('-%06d' % micList[-1].getObjId())
        pwutils.makePath(micPath)

        micFnList = []

        for mic in micList:
            micFn = mic.getFileName()
            micFnList.append(micFn)
            # The coordinates conversion is done for each micrograph
            # and not in convertInputStep, this is needed for streaming
            badCoords = self.inputBadCoords.get()

            if self.exclusive and badCoords:
                fnCoords = os.path.join(micPath, '%s_rubbish.star'
                                        % pwutils.removeBaseExt(micFn))
                writeMicCoords(mic, badCoords.iterCoordinates(mic), fnCoords)

        try:
            gautomatch.Plugin.runGautomatch(micFnList,
                                            self._getReferencesFn(),
                                            micPath,
                                            *args,
                                            env=gautomatch.Plugin.getEnviron(),
                                            runJob=self.runJob)

            # Move output from micPath (tmp) to extra
            for f in glob(os.path.join(micPath, '*.star')):
                pwutils.moveFile(f, self.getMicrographsDir())

            # Move debug output to extra
            debugSuffixes = ['*_ccmax.mrc', '*_pref.mrc', '*_bg.mrc',
                             '*_bgfree.mrc', '*_lsigma.mrc', '*_mask.mrc']
            for p in debugSuffixes:
                for f in glob(os.path.join(micPath, p)):
                    pwutils.moveFile(f, self.getMicrographsDir())

            pwutils.cleanPath(micPath)

        except Exception as e:
            self.error("ERROR: Gautomatch has failed for %s. %s" % (
                micFnList, e))

    def createOutputStep(self):
        pass

    # --------------------------- INFO functions ------------------------------
    def _validate(self):
        errors = []
        if not self.localAvgMin < self.localAvgMax:
            errors.append('Wrong values of local average cut-off!')

        if self.exclusive and not self.inputBadCoords.get() and not self.inputDefects.get():
            errors.append("You have to provide at least "
                          "one set of coordinates ")
            errors.append("for exclusive picking!")

        nprocs = max(self.numberOfMpi.get(), self.numberOfThreads.get())

        if nprocs < len(self.getGpuList()):
            errors.append("Multiple GPUs can not be used by a single process. "
                          "Make sure you specify more processors than GPUs. ")

        return errors

    def _summary(self):
        summary = []
        if self.getInputMicrographs() is not None:
            summary.append("Number of input micrographs: %d"
                           % self.getInputMicrographs().getSize())
        if self.getOutputsSize() > 0:
            summary.append("Number of particles picked: %d"
                           % self.getCoords().getSize())
            summary.append("Particle size: %d px"
                           % self.getCoords().getBoxSize())
            summary.append("Threshold min: %0.2f" % self.threshold)
        else:
            summary.append(Message.TEXT_NO_OUTPUT_CO)
        return summary

    def _methods(self):
        methodsMsgs = []
        if self.getInputMicrographs() is None:
            return ['Input micrographs not available yet.']
        methodsMsgs.append("Input micrographs %s."
                           % (self.getObjectTag(self.getInputMicrographs())))

        if self.getOutputsSize() > 0:
            output = self.getCoords()
            methodsMsgs.append("%s: User picked %d particles with a particle "
                               "size of %d px and minimal threshold %0.2f."
                               % (self.getObjectTag(output), output.getSize(),
                                  output.getBoxSize(), self.threshold))
        else:
            methodsMsgs.append(Message.TEXT_NO_OUTPUT_CO)

        return methodsMsgs

    # --------------------------- UTILS functions -----------------------------
    def readCoordsFromMics(self, workingDir, micList, coordSet):
        if coordSet.getBoxSize() is None:
            coordSet.setBoxSize(self._getBoxSize())

        readSetOfCoordinates(self.getMicrographsDir(), micList, coordSet)
        self.readRejectedCoordsFromMics(micList)

    def readRejectedCoordsFromMics(self, micList):
        micSet = self.getInputMicrographs()

        rejectedCoordSqlite = self._getPath('coordinates_rejected.sqlite')

        if not os.path.exists(rejectedCoordSqlite):
            coordSetAux = self._createSetOfCoordinates(micSet,
                                                       suffix='_rejected')
        else:
            coordSetAux = SetOfCoordinates(filename=rejectedCoordSqlite)
            coordSetAux.enableAppend()

        coordSetAux.setBoxSize(self._getBoxSize())
        readSetOfCoordinates(self.getMicrographsDir(), micList,
                             coordSetAux, suffix='_rejected.star')
        coordSetAux.write()
        coordSetAux.close()

        # debug output
        if self.writeCC:
            self.createDebugOutput(suffix='_ccmax')

        if self.writeFilt:
            self.createDebugOutput(suffix='_pref')

        if self.writeBg:
            self.createDebugOutput(suffix='_bg')

        if self.writeBgSub:
            self.createDebugOutput(suffix='_bgfree')

        if self.writeSigma:
            self.createDebugOutput(suffix='_lsigma')

        if self.writeMsk:
            self.createDebugOutput(suffix='_mask')

    def createDebugOutput(self, suffix):
        micSet = self.getInputMicrographs()
        pixSize = micSet.getSamplingRate()
        outputDebugMics = self._createSetOfMicrographs(suffix=suffix)
        # debug output images are downsampled by a factor of 4
        outputDebugMics.setSamplingRate(float(pixSize * 4))
        for mic in micSet:
            micFn = self.getOutputName(mic.getFileName(), suffix)
            mic.setFileName(micFn)
            outputDebugMics.append(mic)
        outputDebugMics.write()

    def _getPickArgs(self):
        return [self.getArgs()]

    def getArgs(self, threshold=True, mindist=True):
        """ Return the Gautomatch parameters for picking one micrograph.
         The command line will depends on the protocol selected parameters.
         Params:
            micFn: micrograph filename
            refStack: filename with the references stack (.mrcs)
        """
        args = ' --apixM %0.2f' % self.inputMicrographs.get().getSamplingRate()
        args += ' --ang_step %d' % self.angStep
        args += ' --diameter %d' % self._getDiameter()
        args += ' --lp %d' % self.lowPass
        args += ' --hp %d' % self.highPass
        args += ' --gid %(GPU)s'

        if self.inputReferences.get():
            args += ' --apixT %0.2f' % self.inputReferences.get().getSamplingRate()

        if not self.invertTemplatesContrast:
            args += ' --dont_invertT'

        if threshold:
            args += ' --cc_cutoff %0.2f' % self.threshold

        if not self.advanced:
            args += ' --speed %d' % self.speed
            args += ' --boxsize %d' % self._getBoxSize()
            if mindist:
                args += ' --min_dist %d' % self.minDist
            args += ' --lsigma_cutoff %0.2f' % self.localSigmaCutoff
            args += ' --lsigma_D %d' % self.localSigmaDiam
            args += ' --lave_max %0.2f' % self.localAvgMax
            args += ' --lave_min %0.2f' % self.localAvgMin
            args += ' --lave_D %d' % self.localAvgDiam

        if self.preFilt:
            args += ' --do_pre_filter --pre_lp %d' % self.prelowPass
            args += ' --pre_hp %d' % self.prehighPass

        if gautomatch.Plugin.getActiveVersion() != '0.53':
            args += ' --detect_ice %d' % (1 if self.detectIce else 0)
            args += ' --T_norm_type %d' % self.templateNorm.get()
            args += ' --do_bandpass %d' % (1 if self.doBandpass else 0)

        if self.exclusive:
            if self.inputBadCoords.get():
                args += ' --exclusive_picking --excluded_suffix _rubbish.star'
            if self.inputDefects.get():
                args += (' --global_excluded_box %s' % self._getDefectsFn())

        if self.writeCC:
            args += ' --write_ccmax_mic'
        if self.writeFilt:
            args += ' --write_pref_mic'
        if self.writeBg:
            args += ' --write_bg_mic'
        if self.writeBgSub:
            args += ' --write_bgfree_mic'
        if self.writeSigma:
            args += ' --write_lsigma_mic'
        if self.writeMsk:
            args += ' --write_mic_mask'

        return args

    def _getBoxSize(self):
        if self.boxSize and self.boxSize > 0:
            return self.boxSize.get()

        inputRefs = self.inputReferences.get()

        if inputRefs and inputRefs.getXDim():
            return inputRefs.getXDim()

        return 100

    def _getMicrographDir(self, mic):
        """ Return an unique dir name for results of the micrograph. """
        return self._getTmpPath('mic_%06d' % mic.getObjId())

    def getMicrographsDir(self):
        return self._getExtraPath('micrographs')

    def convertReferences(self, refStack):
        """ Write input references as an .mrcs stack. """
        if refStack:  # refStack should be None when not using references
            self.inputReferences.get().writeStack(refStack)

    def getOutputName(self, fn, key):
        """ Give a key, append the mrc extension
        and prefix the protocol working dir.
        """
        template = pwutils.removeBaseExt(fn) + key + '.mrc'

        return os.path.join(self.getMicrographsDir(), template)

    def _getDefectsFn(self):
        """ Return the filename for the defects star file. """
        return self._getExtraPath('micrographs', 'defects.star')

    def _getReferencesFn(self):
        if self.inputReferences.get():
            return self._getExtraPath('references.mrcs')
        return None

    def _getDiameter(self):
        """ Return 75% of references size"""
        refs = self.inputReferences.get()

        if self.particleSize and self.particleSize > 0:
            return 2 * self.particleSize.get()
        else:
            if refs:
                pix = refs.getSamplingRate()
                dim = refs.getXDim()
                return int(0.75 * dim * pix)
            else:
                return 250

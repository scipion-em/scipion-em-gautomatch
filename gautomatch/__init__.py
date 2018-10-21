# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk)
# *
# * MRC Laboratory of Molecular Biology (MRC-LMB)
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
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

import pyworkflow.em
import pyworkflow.utils as pwutils

from .constants import *


_logo = "gautomatch_logo.png"
_references = ['Zhang2016b']


class Plugin(pyworkflow.em.Plugin):
    _homeVar = GAUTOMATCH_HOME
    _pathVars = [GAUTOMATCH_HOME]
    _supportedVersions = ['0.53', '0.56']

    @classmethod
    def _defineVariables(cls):
        cls._defineEmVar(GAUTOMATCH_HOME, 'gautomatch-0.53')
        cls._defineVar(GAUTOMATCH, 'Gautomatch-v0.53_sm_20_cu8.0_x86_64')

    @classmethod
    def defineBinaries(cls, env):
        env.addPackage('gautomatch', version='0.53',
                       tar='Gautomatch_v0.53.tgz',
                       default=True)

        env.addPackage('gautomatch', version='0.56',
                       tar='Gautomatch_v0.56.tgz')

    @classmethod
    def getEnviron(cls):
        """ Return the environ settings to run Gautomatch programs. """
        environ = pwutils.Environ(os.environ)
        # Take Scipion CUDA library path
        cudaLib = environ.getFirst((GAUTOMATCH_CUDA_LIB, CUDA_LIB))
        environ.addLibrary(cudaLib)

        return environ

    @classmethod
    def getProgram(cls):
        """ Return the program binary that will be used. """
        return os.path.join(cls.getHome('bin'), cls.getVar(GAUTOMATCH))

    @classmethod
    def runGautomatch(cls, micNameList, refStack, workDir, extraArgs, env=None,
                      runJob=None):
        """ Run Gautomatch with the given parameters.
        If micrographs are not .mrc, they will be converted.
        If runJob=None, it will use pwutils.runJob.
        """
        args = ''

        ih = pyworkflow.em.ImageHandler()

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            args += ' %s' % outMic
            if micName.endswith('.mrc'):
                pwutils.createLink(micName, outMic)
            else:
                ih.convert(micName, outMic)

        if refStack is not None:
            args += ' -T %s' % refStack

        args += ' %s' % extraArgs

        environ = env if env is not None else cls.getEnviron()
        if runJob is None:
            pwutils.runJob(None, cls.getProgram(), args, env=environ)
        else:
            runJob(cls.getProgram(), args, env=environ)

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            # After picking we can remove the temporary file.
            pwutils.cleanPath(outMic)

pyworkflow.em.Domain.registerPlugin(__name__)
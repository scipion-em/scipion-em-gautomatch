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

import pwem
import pyworkflow.utils as pwutils
from pwem.emlib.image import ImageHandler

from .constants import *


__version__ = '3.0.13'
_logo = "gautomatch_logo.png"
_references = ['Zhang']


class Plugin(pwem.Plugin):
    _homeVar = GAUTOMATCH_HOME
    _pathVars = [GAUTOMATCH_HOME]
    _supportedVersions = ['0.53', '0.56']
    _url = "https://github.com/scipion-em/scipion-em-gautomatch"

    @classmethod
    def _defineVariables(cls):
        cls._defineEmVar(GAUTOMATCH_HOME, 'gautomatch-0.56')
        cls._defineVar(GAUTOMATCH, 'Gautomatch_v0.56_sm30-75_cu10.1')
        cls._defineVar(GAUTOMATCH_CUDA_LIB, pwem.Config.CUDA_LIB)

    @classmethod
    def defineBinaries(cls, env):
        env.addPackage('gautomatch', version='0.53',
                       tar='Gautomatch_v0.53.tgz')

        env.addPackage('gautomatch', version='0.56',
                       tar='gautomatch_v0.56.tgz',
                       default=True)

    @classmethod
    def getEnviron(cls):
        """ Return the environ settings to run Gautomatch programs. """
        environ = pwutils.Environ(os.environ)
        # Get Gautomatch CUDA library path if defined
        cudaLib = cls.getVar(GAUTOMATCH_CUDA_LIB, pwem.Config.CUDA_LIB)
        environ.addLibrary(cudaLib)

        return environ

    @classmethod
    def getProgram(cls):
        """ Return the program binary that will be used. """
        return os.path.join(cls.getHome('bin'),
                            os.path.basename(cls.getVar(GAUTOMATCH)))

    @classmethod
    def runGautomatch(cls, micNameList, refStack, workDir, extraArgs, env=None,
                      runJob=None):
        """ Run Gautomatch with the given parameters.
        If micrographs are not .mrc, they will be converted.
        If runJob=None, it will use pwutils.runJob.
        """
        args = ''

        ih = ImageHandler()

        for micName in micNameList:
            # We convert the input micrograph on demand if not in .mrc
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            if micName.endswith('.mrc'):
                pwutils.createAbsLink(os.path.abspath(micName), outMic)
            else:
                ih.convert(micName, outMic)

        args += ' %s/*.mrc' % workDir

        if refStack is not None:
            args += ' -T %s' % refStack

        args += ' %s' % extraArgs

        environ = env if env is not None else cls.getEnviron()
        if runJob is None:
            pwutils.runJob(None, cls.getProgram(), args, env=environ)
        else:
            runJob(cls.getProgram(), args, env=environ)

        for micName in micNameList:
            outMic = os.path.join(workDir, pwutils.replaceBaseExt(micName, 'mrc'))
            # After picking we can remove the temporary file.
            pwutils.cleanPath(outMic)

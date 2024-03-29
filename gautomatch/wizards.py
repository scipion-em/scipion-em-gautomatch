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

import pwem.wizards as emwiz
import pyworkflow.utils as pwutils
import pyworkflow.gui.dialog as dialog
from pwem.viewers import CoordinatesObjectView
from pwem.constants import UNIT_ANGSTROM, FILTER_NO_DECAY
from pwem.convert import getSubsetByDefocus

from gautomatch.protocols import ProtGautomatch


# =============================================================================
# MASKS
# =============================================================================
class GautomatchParticleWizard(emwiz.ParticleMaskRadiusWizard):
    _targets = [(ProtGautomatch, ['particleSize'])]
    
    def _getParameters(self, protocol):
        
        label, value = self._getInputProtocol(self._targets, protocol)
        
        protParams = dict()
        protParams['input'] = protocol.inputReferences
        protParams['label'] = label
        protParams['value'] = value
        return protParams
    
    def _getProvider(self, protocol):
        _objs = self._getParameters(protocol)['input'] 
        return emwiz.ParticleMaskRadiusWizard._getListProvider(self, _objs)
    
    def show(self, form, *args):
        params = self._getParameters(form.protocol)
        _value = params['value']
        _label = params['label']
        emwiz.ParticleMaskRadiusWizard.show(self, form, _value, _label,
                                            UNIT_ANGSTROM)

# ===============================================================================
# FILTERS
# ===============================================================================


class GautomatchBandpassWizard(emwiz.FilterParticlesWizard):
    _targets = [(ProtGautomatch, ['lowPass', 'highPass'])]

    def _getParameters(self, protocol):

        label, value = self._getInputProtocol(self._targets, protocol)

        protParams = dict()
        protParams['input'] = protocol.inputMicrographs
        protParams['label'] = label
        protParams['value'] = value
        protParams['mode'] = FILTER_NO_DECAY
        return protParams

    def _getProvider(self, protocol):
        _objs = self._getParameters(protocol)['input']
        return emwiz.FilterParticlesWizard._getListProvider(self, _objs)

    def show(self, form):
        protocol = form.protocol
        provider = self._getProvider(protocol)
        params = self._getParameters(protocol)

        if provider is not None:

            args = {'mode': params['mode'],
                    'lowFreq': params['value'][1],
                    'highFreq': params['value'][0],
                    'unit': UNIT_ANGSTROM
                    }

            args['showDecay'] = False

            d = emwiz.BandPassFilterDialog(form.root, provider, **args)

            if d.resultYes():
                form.setVar('lowPass', d.getHighFreq())
                form.setVar('highPass', d.getLowFreq())

        else:
            dialog.showWarning("Input micrographs", "Select micrographs first",
                               form.root)
        
# =============================================================================
# PICKER
# =============================================================================


class GautomatchPickerWizard(emwiz.EmWizard):
    _targets = [(ProtGautomatch, ['threshold'])]

    def show(self, form):
        prot = form.protocol
        micSet = prot.getInputMicrographs()

        gpus = prot.getGpuList()

        if not gpus:
            form.showWarning("You should select at least one GPU.")
            return

        if not micSet:
            form.showWarning("You should select input micrographs "
                             "before opening the wizard.")
            return

        project = prot.getProject()

        if prot.micrographsSelection == 0:  # all micrographs
            micFn = micSet.getFileName()
        else:
            # Create a subset based on defocus values
            ctfs = prot.ctfRelations.get()
            if ctfs is None:
                form.showWarning("You should select CTFs if using a defocus "
                                 "subset. ")
                return
            micSubset = prot._createSetOfMicrographs(suffix='subset')
            for mic in getSubsetByDefocus(ctfs, micSet,
                                          prot.micrographsNumber.get()):
                micSubset.append(mic)
            micSubset.write()
            micSubset.close()
            micFn = micSubset.getFileName()

        # Prepare a temporary folder to convert some input files
        # and put some of the intermediate result files
        coordsDir = project.getTmpPath(micSet.getName())
        pwutils.cleanPath(coordsDir)
        pwutils.makePath(coordsDir)

        if prot.inputReferences.get():
            refStack = os.path.join(coordsDir, 'references.mrcs')
            prot.convertReferences(refStack)
        else:
            refStack = None

        # Get current values of the properties
#         micFn = os.path.join(coordsDir, 'micrographs.xmd')
#         writeSetOfMicrographs(micSet, micFn)
        pickerConfig = os.path.join(coordsDir, 'picker.conf')
        pickScript = os.path.join(os.path.dirname(__file__), 'run_gautomatch.py')

        # Let's use the first selected gpu for the wizard
        pickCmd = prot.getArgs(threshold=False,
                               mindist=False) % {'GPU': gpus[0]}

        args = {
            "pickScript": "python " + pickScript,
            "pickCmd": pickCmd,
            "convertCmd": "emconvert",
            'coordsDir': coordsDir,
            'micsSqlite': micSet.getFileName(),
            'threshold': prot.threshold.get(),
            "mindist": prot.minDist.get(),
            "refStack": refStack
          }

        # If Gautomatch will guess advanced parameter we don't need to send
        # the min distance to the wizard.
        with open(pickerConfig, "w") as f:
            if prot.advanced:
                f.write("""
                parameters = threshold
                threshold.value =  %(threshold)s
                threshold.label = Threshold
                threshold.help = Particles with CCC above the threshold will be picked
                autopickCommand = %(pickScript)s %%(micrograph) %(refStack)s %(coordsDir)s %(pickCmd)s --cc_cutoff %%(threshold)
                convertCommand = %(convertCmd)s --coordinates --from gautomatch --to xmipp --input  %(micsSqlite)s --output %(coordsDir)s
                """ % args)

            else:
                f.write("""
                parameters = threshold,mindist
                threshold.value =  %(threshold)s
                threshold.label = Threshold
                threshold.help = Particles with CCC above the threshold will be picked
                mindist.value = %(mindist)s
                mindist.label = Min distance (A)
                mindist.help = Use value of 0.9~1.1X particle diameter
                autopickCommand = %(pickScript)s %%(micrograph) %(refStack)s %(coordsDir)s %(pickCmd)s --cc_cutoff %%(threshold) --min_dist %%(mindist)
                convertCommand = %(convertCmd)s --coordinates --from gautomatch --to xmipp --input %(micsSqlite)s --output %(coordsDir)s
                """ % args)

        process = CoordinatesObjectView(project, micFn, coordsDir, prot,
                                        mode=CoordinatesObjectView.MODE_AUTOMATIC,
                                        pickerProps=pickerConfig).show()
        process.wait()
        myprops = pwutils.readProperties(pickerConfig)

        if myprops['applyChanges'] == 'true':
            form.setVar('threshold', myprops['threshold.value'])
            if not prot.advanced:
                form.setVar('minDist', myprops['mindist.value'])
            else:
                pass  # TODO: We could even in future parse the 'guessed' params

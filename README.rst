Gautomatch plugin
=================

This plugin provides a wrapper for Gautomatch picker developed by Kai Zhang at MRC LMB.

.. image:: https://img.shields.io/pypi/v/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: PyPI release

.. image:: https://img.shields.io/pypi/l/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: License

.. image:: https://img.shields.io/pypi/pyversions/scipion-em-gautomatch.svg
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: Supported Python versions

.. image:: https://img.shields.io/sonar/quality_gate/scipion-em_scipion-em-gautomatch?server=https%3A%2F%2Fsonarcloud.io
        :target: https://sonarcloud.io/dashboard?id=scipion-em_scipion-em-gautomatch
        :alt: SonarCloud quality gate

.. image:: https://img.shields.io/pypi/dm/scipion-em-gautomatch
        :target: https://pypi.python.org/pypi/scipion-em-gautomatch
        :alt: Downloads

Installation
------------

You will need to use 3.0+ version of Scipion to be able to run these protocols. To install the plugin, you have two options:

a) Stable version
   
   .. code-block::
   
      scipion installp -p scipion-em-gautomatch

b) Developer's version

   * download repository 
   
   .. code-block::
   
      git clone -b devel https://github.com/scipion-em/scipion-em-gautomatch.git

   * install 

   .. code-block::
   
      scipion installp -p /path/to/scipion-em-gautomatch --devel

Gautomatch binaries will be installed automatically with the plugin, but you can also link an existing installation. 

Configuration variables
-----------------------
- CONDA_ACTIVATION_CMD: If undefined, it will rely on conda being in the PATH. An example of a conda activation cmd can be **eval "$(/extra/miniconda3/bin/conda shell.bash hook)"**.
- GAUTOMATCH_ENV_ACTIVATION: Command to activate the Gautomatch environment. This environment must have CUDA installed (cudatoolkit=10.1).
- GAUTOMATCH_HOME: Path to gautomatch binary containing folder (default = software/em/gautomatch-0.56)
- GAUTOMATCH_BIN: Specific binary to use (default = Gautomatch_v0.56_sm30-75_cu10.1)

Verifying
------------

To check the installation, simply run the following Scipion test:

``scipion test gautomatch.tests.test_protocols_gautomatch.TestGautomatchAutomaticPicking``

Supported versions
------------------

0.56

Protocols
---------

* `auto-picking <https://github.com/scipion-em/scipion-em-gautomatch/wiki/ProtGautomatch>`_

References
----------

1. Kai Zhang. Unpublished. 

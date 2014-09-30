
from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext
import numpy as np                           # <---- New line

_I = ['gnl']

ext_modules = [Extension("gnl.gslrand",
    sources = ["gnl/gslrand.pyx"],
    libraries = ['gsl', 'gslcblas'],
    include_dirs = ["gnl"] # This line is crucial
    )]

setup(
    name = 'gnl',
    cmdclass = {'build_ext': build_ext},
    # include_dirs = [np.get_include()],         # <---- New line
    ext_modules = ext_modules,
    packages    = ['gnl'],
    # package_dir = {'': ''},
    package_data = {'gnl':['*.pxd',]}

)
# -lmkl_intel_lp64 -lmkl_sequential -lmkl_core -lpthread -lm

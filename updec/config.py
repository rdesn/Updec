import os
import jax

RBF = None          ## Default radial basis function
MAX_DEGREE = None              ## Max degree for monomials
DIM = None                     ## Default problem dimension
__version__ = "0.1.0"       ## Package version  ## TODO check if okay to do this here

PREALLOCATE = False
if not PREALLOCATE:
    os.environ['XLA_PYTHON_CLIENT_PREALLOCATE'] = "false"       ## Preallocate 90% of memory


FLOAT64 = True
jax.config.update("jax_enable_x64", FLOAT64)   ## Use double precision by default

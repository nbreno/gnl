from collections import Iterable
import dask.array as da
from scipy.ndimage import correlate1d
import numpy as np
import xarray as xr
from xarray import apply_ufunc
import attr

from functools import wraps

import logging

logger = logging.getLogger(__file__)


def get_dz(z):
    zext = np.hstack((-z[0],  z,  2.0*z[-1] - 1.0*z[-2]))
    zw = .5 * (zext[1:] + zext[:-1])
    dz = zw[1:] - zw[:-1]

    return xr.DataArray(dz, z.coords)


def layer_mass(rho):
    dz = get_dz(rho.z)
    return rho*dz


def layer_mass_from_p(p, ps=None):
    if ps is None:
        ps = 2*p[0] - p[1]

    ptop = p[-1]*2 - p[-2]

    pext = np.hstack((ps, p, ptop))
    pint = (pext[1:] + pext[:-1])/2
    dp = - np.diff(pint*100)/grav

    return xr.DataArray(dp, p.coords)


def _blocks_view(U, blocks=None):
    nt, nz, ny, nx = U.shape
    return U.reshape((nt, nz, ny//blocks[2], blocks[2], nx//blocks[3], blocks[3]))


def _diff(x, axis=-1, mode='wrap'):
    return correlate1d(x, [-1, 1], axis=axis, mode=mode, origin=-1)


def _divergence(fx, fy):
    ux = diff(fx, axis=-1)
    vy = diff(fy, axis=-2)
    return ux + vy


def _slice_to_range(s: slice, n=None):
    start, stop, step = s.start, s.stop, s.step
    if start is None:
        start = 0
    if stop is None:
        raise ValueError("Need to explicitly give the stop")
    if step is None:
        step = 1
    return range(start, stop, step)


def isel_bc(da: xr.DataArray, idx, dim, boundary='wrap'):
    """Select points along axis with ghosting given by a boundary condition
    """

    n = da.shape[da.get_axis_num(dim)]
    if isinstance(idx, slice):
        if idx.stop is None:
            idx = slice(idx.start, n, idx.step)
        idx = _slice_to_range(idx)
    elif not isinstance(idx, Iterable):
        idx = [idx]

    idx = np.asarray(idx)

    if boundary == 'wrap':
        idx = idx % n
    elif boundary == 'extrap':
        idx[idx < 0] = 0
        idx[idx >= n] = n-1
    else:
        raise ValueError("Received unknown boundary condition value")

    return da.isel(**{dim: idx})


def get_center_coords(x, block_size):
    x = np.r_[x, 2*x[-1] - x[-2]]
    left = x[0:-1:block_size]
    right = x[block_size::block_size]
    return (left+right)/2


def staggered_to_left(f, block_size, dim):
    """Move staggered variable to the left interface

    Parameters
    ----------
    f : xr.DataArray
    block_size : size of the coarse graining block
    dim : str
    boundary : str, optional
        A boundary condition which is passed to `isel_bc`

    Returns
    -------
    interface : xr.DataArray
        The value of f along the left interfaces of the coarse-grain blocks
    """
    new_coord = get_center_coords(f[dim].values, block_size)
    f = isel_bc(f, slice(0, None, block_size), dim)
    return f.assign_coords(**{dim: new_coord})


def staggered_to_right(f: xr.DataArray, block_size, dim, boundary='wrap'):
    """Move staggered variable to the right interface

    Parameters
    ----------
    f : xr.DataArray
    block_size : size of the coarse graining block
    dim : str
    boundary : str, optional
        A boundary condition which is passed to `isel_bc`

    Returns
    -------
    interface : xr.DataArray
        The value of f along the right interfaces of the coarse-grain blocks
    """
    n = f.shape[f.get_axis_num(dim)]
    new_coord = get_center_coords(f[dim].values, block_size)

    idx = slice(block_size, n+block_size, block_size)
    f = isel_bc(f, idx, dim, boundary=boundary)
    return f.assign_coords(**{dim: new_coord})


def centered_to_left(f: xr.DataArray, block_size, dim, boundary='wrap'):
    """Move centered variable to the left interface

    Parameters
    ----------
    f : xr.DataArray
    block_size : size of the coarse graining block
    dim : str
    boundary : str, optional
        A boundary condition which is passed to `isel_bc`

    Returns
    -------
    interface : xr.DataArray
        The value of f along the left interfaces of the coarse-grain blocks
    """
    new_coord = get_center_coords(f[dim].values, block_size)
    n = f.shape[f.get_axis_num(dim)]

    f = (isel_bc(f, slice(0, n, block_size), dim, boundary=boundary) +
         isel_bc(f, slice(-1, n-1, block_size), dim, boundary=boundary)) / 2

    return f.assign_coords(**{dim: new_coord})


def centered_to_right(f: xr.DataArray, block_size, dim, boundary='wrap'):
    """Move centered variable to the right interface

    Parameters
    ----------
    f : xr.DataArray
    block_size : size of the coarse graining block
    dim : str
    boundary : str, optional
        A boundary condition which is passed to `isel_bc`

    Returns
    -------
    interface : xr.DataArray
        The value of f along the right interfaces of the coarse-grain blocks
    """
    new_coord = get_center_coords(f[dim].values, block_size)
    n = f.shape[f.get_axis_num(dim)]

    left_idx = slice(block_size, n+1, block_size)
    right_idx = slice(block_size-1, n, block_size)
    f = (isel_bc(f, left_idx, dim, boundary=boundary) +
         isel_bc(f, right_idx, dim, boundary=boundary)) / 2

    return f.assign_coords(**{dim: new_coord})


def dfun(func):
    @wraps(func)
    def f(x, *args, **kwargs):
        if isinstance(x, xr.DataArray):
            return func(x, *args, **kwargs)
        elif isinstance(x, xr.Dataset):
            return x.apply(lambda x: func(x, *args, **kwargs))
    return f


def coarsen_destagger_dask(x, blocks, stagger=None, mode='wrap'):
    """


    Examples
    --------
    >>> x = da.arange(6, chunks=6)
    >>> xc = coarsen_destagger_dask(x, {0: 2}, stagger=0)
    >>> xc.compute()
    array([ 1. ,  3. ,  3.5])
    >>> x = da.from_array(x, chunks=x.shape)
    >>> xc = coarsen_destagger_dask(x, {0: 2}, stagger=0)
    >>> xc.compute()
    array([ 1. ,  3. ,  3.5])
    """
    output_numpy = False

    try:
        x._keys
    except AttributeError:
        output_numpy = True
        x = da.from_array(x, x.shape)

    xcoarse = da.coarsen(np.sum, x, blocks)
    # TODO refactor this code to another function
    if stagger is not None:
        blk = {key: val
               for key, val in blocks.items()
               if key != stagger}

        left_inds = np.arange(0, x.shape[stagger], blocks[stagger])
        left = da.coarsen(np.sum, da.take(x, left_inds, stagger), blk)
        n = left.shape[stagger]
        # handle boundary conditions
        if mode == 'wrap':
            bc = da.take(left, [0], axis=stagger)
        if mode == 'clip':
            bc = da.take(left, [-1], axis=stagger)

        right = da.take(left, np.arange(1, n), axis=stagger)
        right = da.concatenate((right, bc), axis=stagger)
        xcoarse = xcoarse + (right - left)/2

    n = np.prod(list(blocks.values()))
    ans = xcoarse/n

    if output_numpy:
        return ans.compute()
    else:
        return ans


@dfun
def coarsen(A, blocks=None, stagger_dim=None, mode='wrap'):
    """coarsen and potentially destagger a 
    """
    if stagger_dim is not None and stagger_dim not in blocks:
        raise ValueError(f"stagger_dim \"{stagger_dim}\" is not in blocks")

    blocks = {k:blocks[k] for k in blocks
              if k in A.dims}

    if len(blocks) == 0:
        return A

    kwargs = {'mode': mode}
    if stagger_dim is not None:
        kwargs['stagger'] = A.get_axis_num(stagger_dim)

    np_blocks = {A.get_axis_num(dim): val for dim, val in blocks.items()}
    vals = coarsen_destagger_dask(A.data, np_blocks, **kwargs)

    # coarsen dimension
    coords = {}
    for k in A.coords:
        if k in blocks:
            c  = A[k].data
            dim = da.from_array(c, chunks=(len(c), ))

            q = blocks[k]
            dim = da.coarsen(np.mean, dim, {0: q}).compute()
            coords[k] = dim
        else:
            coords[k] = A.coords[k]

    return xr.DataArray(vals, dims=A.dims, coords=coords, attrs=A.attrs,
                        name=A.name)


def boundary_points(x, blocks, stagger_dim=None):
    """
    """



def destagger_dask(darr, mode='wrap'):
    ind = np.arange(darr.shape[-1]) + 1
    r = (np.take(darr, ind, axis=-1, mode=mode) +darr)/2
    return r

@dfun
def destagger(xarr, dim, **kwargs):
    """Destagger an inteface located variable along a dimension

    Parameters
    ----------
    xarr : xr.Dataset
        input datarray
    dim : str
        dimension to destagger the data along
    mode : str
        Passed to np.take

    Returns
    -------
    destaggered : xr.Dataset
        cell centered DataArray

    See Also
    --------
    numpy.take

    Examples
    --------
    >>> x = xr.DataArray(np.arange(0, 5), [('x', np.arange(0, 5))])
    >>> destagger(x, 'x')
    <xarray.DataArray (x: 5)>
    array([ 0.5,  1.5,  2.5,  3.5,  2. ])
    Coordinates:
      * x        (x) int64 0 1 2 3 4
    """
    return apply_ufunc(destagger_dask, xarr,
                       input_core_dims=[[dim]],
                       output_core_dims=[[dim]],
                       dask='parallelized',
                       output_dtypes=[xarr.dtype],
                       kwargs=kwargs)


def main(input, output, **kwargs):
    ds = xr.open_dataset(input)
    coarsen(ds, **kwargs).to_netcdf(output)


def snakemake(input, output, params):
    ds = xr.open_dataset(input[0])
    params = dict(params)
    logger.info(f"Coarse-graining {input[0]} with params:", params)

    def mycoarsen(x):
        if x.name[0] == 'U':
            stagger_dim = 'x'
            mode = 'wrap'
        elif x.name[0] == 'V':
            stagger_dim = 'y'
            mode = 'clip'
        else:
            stagger_dim = None
            mode = None
        logger.debug("Stagger options for ", x.name," : ", stagger_dim, mode)
        return coarsen(x, stagger_dim=stagger_dim, mode=mode, **params)

    ds.apply(mycoarsen).to_netcdf(output[0])

def test_coarsen():
    import os
    file = "NG_5120x2560x34_4km_10s_QOBS_EQX_1280_0000173880_TABS.nc"
    folder = "~/.datasets/id/1381d73c091f2ea34ef8ea303c94e998/"
    path = os.path.join(folder, file)
    main(path, "coarse.nc", {'x': 40, 'y': 40}, stagger_dim=None, mode='wrap')


# import sys
# main(sys.argv[1], sys.argv[2])
if __name__ == '__main__':
    test_coarsen()

import numpy as np
import matplotlib.pyplot as plt

article_style = {
    'axes.titlesize': 'medium',
    'axes.labelsize': 'small'
}

def figlabel(*args, fig=None, **kwargs):
    """Put label in figure coords"""
    if fig is None:
        fig = plt.gcf()
    plt.text(*args, transform=fig.transFigure, **kwargs)


def loghist(x, logy=True, gaussian_comparison=True, ax=None,
            lower_percentile=1e-5, upper_percentile=100-1e-5,
            label='Sample'):
    """
    Plot log histogram of given samples with normal comparison using
    kernel density estimation
    """
    from scipy.stats import gaussian_kde, norm
    from numpy import percentile

    if ax is None:
        ax = plt.axes()

    p = gaussian_kde(x)

    npts = 100

    p1 = percentile(x, lower_percentile)
    p2 = percentile(x, upper_percentile)
    xx = np.linspace(p1, p2, npts)

    if logy:
        y = np.log(p(xx))
    else:
        y = p(xx)

    ax.plot(xx, y, label=label)

    if gaussian_comparison:
        mles = norm.fit(x)
        gpdf = norm.pdf(xx, *mles)
        if logy:
            ax.plot(xx, np.log(gpdf),  label='Gauss')
        else:
            ax.plot(xx, gpdf,  label='Gauss')

    ax.set_xlim([p1, p2])


def test_loghist():
    from numpy.random import normal

    x = normal(size=1000)
    loghist(x)
    plt.legend()
    plt.show()

def plot2d(x, y, z, ax=None, cmap='RdGy'):
    """ Plot dataset using NonUniformImage class
    
    Args:
        x (nx,)
        y (ny,)
        z (nx,nz)
        
    """
    from matplotlib.image import NonUniformImage
    if ax is None:
        fig, ax= plt.subplots()
        
   
    xlim = (x.min(), x.max())
    ylim = (y.min(), y.max()) 
    
    im = NonUniformImage(ax, interpolation='bilinear', extent=xlim + ylim,
                        cmap=cmap)
   
    im.set_data(x,y,z)
    ax.images.append(im)
    #plt.colorbar(im)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    
    return im

def test_plot2d():
    x = np.arange(10)
    y = np.arange(20)
    
    z = x[None,:]**2 + y[:,None]**2
    plot2d(x,y,z)
    plt.show()

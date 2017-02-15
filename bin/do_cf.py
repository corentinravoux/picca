import scipy as sp
import fitsio
import argparse
import glob
import healpy
import sys
from scipy import random 

from pylya import constants
from pylya import cf
from pylya.data import delta

from multiprocessing import Pool,Process,Lock,Manager,cpu_count,Value


def corr_func(p):
    cf.fill_neighs(p)
    tmp = cf.cf(p)
    return tmp

if __name__ == '__main__':

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--out', type = str, default = None, required=True,
                        help = 'output file name')

    parser.add_argument('--in-dir', type = str, default = None, required=True,
                        help = 'data directory')

    parser.add_argument('--rp-max', type = float, default = 200, required=False,
                        help = 'max rp')

    parser.add_argument('--rt-max', type = float, default = 200, required=False,
                        help = 'max rt')

    parser.add_argument('--np', type = int, default = 50, required=False,
                        help = 'number of r-parallel bins')

    parser.add_argument('--nt', type = int, default = 50, required=False,
                        help = 'number of r-transverse bins')

    parser.add_argument('--lambda-abs', type = float, default = constants.lya, required=False,
                        help = 'wavelength of absorption')

    parser.add_argument('--fid-Om', type = float, default = 0.315, required=False,
                    help = 'Om of fiducial cosmology')

    parser.add_argument('--nside', type = int, default = 16, required=False,
                    help = 'healpix nside')

    parser.add_argument('--nproc', type = int, default = None, required=False,
                    help = 'number of processors')

    parser.add_argument('--z-ref', type = float, default = 2.25, required=False,
                    help = 'reference redshift')

    parser.add_argument('--z-evol', type = float, default = 2.9, required=False,
                    help = 'exponent of the redshift evolution of the delta field')

    parser.add_argument('--no-project', action="store_true", required=False,
                    help = 'do not project out continuum fitting modes')

    parser.add_argument('--from-image', action="store_true", required=False,
                    help = 'use image format to read deltas')

    parser.add_argument('--nspec', type=int,default=None, required=False,
                    help = 'maximum spectra to read')

    args = parser.parse_args()

    if args.nproc is None:
        args.nproc = cpu_count()/2

    cf.rp_max = args.rp_max
    cf.rt_max = args.rt_max
    cf.np = args.np
    cf.nt = args.nt
    cf.nside = args.nside
    cf.zref = args.z_ref
    cf.alpha = args.z_evol

    cosmo = constants.cosmo(args.fid_Om)

    cf.angmax = sp.arcsin(cf.rt_max/cosmo.r_comoving(constants.boss_lambda_min/args.lambda_abs-1))

    data = {}
    ndata = 0
    dels = []
    if not args.from_image:
        fi = glob.glob(args.in_dir+"/*.fits.gz")
        sys.stderr.write("\rread {} of {} {}".format(i,len(fi),ndata))
        hdus = fitsio.FITS(f)
        dels = [delta.from_fitsio(h) for h in hdus[1:]]
        ndata+=len(dels)
        hdus.close()
        if not args.nspec is None:
            if ndata>args.nspec:break
    else:
        dels = delta.from_image(args.in_dir)

    phi = [d.ra for d in dels]
    th = [sp.pi/2-d.dec for d in dels]
    pix = healpy.ang2pix(cf.nside,th,phi)
    for d,p in zip(dels,pix):
        if not p in data:
            data[p]=[]
        data[p].append(d)

        z = 10**d.ll/args.lambda_abs-1
        d.z = z
        d.r_comov = cosmo.r_comoving(z)
        d.we *= ((1+z)/(1+args.z_ref))**(cf.alpha-1)
        if not args.no_project:
            d.project()

    sys.stderr.write("\n")

    cf.npix = len(data)
    cf.data = data
    cf.ndata=ndata
    print "done, npix = {}".format(cf.npix)

    cf.counter = Value('i',0)

    cf.lock = Lock()
    cpu_data = {}
    for p in data.keys():
        cpu_data[p] = [p]

    pool = Pool(processes=args.nproc)

    cfs = pool.map(corr_func,cpu_data.values())
    pool.close()

    cfs=sp.array(cfs)
    wes=cfs[:,0,:]
    rps=cfs[:,2,:]
    rts=cfs[:,3,:]
    zs=cfs[:,4,:]
    cfs=cfs[:,1,:]

    rp = (rps*wes).sum(axis=0)/wes.sum(axis=0)
    rt = (rts*wes).sum(axis=0)/wes.sum(axis=0)
    z = (zs*wes).sum(axis=0)/wes.sum(axis=0)

    out = fitsio.FITS(args.out,'rw',clobber=True)
    head = {}
    head['RPMAX']=cf.rp_max
    head['RTMAX']=cf.rt_max
    head['NT']=cf.nt
    head['NP']=cf.np

    out.write([rp,rt,z],names=['RP','RT','Z'],header=head)
    out.write([wes,cfs],names=['WE','DA'])
    out.close()

    

"""This module defines the abstract class Data from which all
classes loading data must inherit
"""
import os
import warnings
import glob
import numpy as np
import fitsio
import healpy

from picca.delta_extraction.data import Data
from picca.delta_extraction.errors import DataError, DataWarning
from picca.delta_extraction.userprint import userprint

from picca.delta_extraction.astronomical_objects.desi_forest import DesiForest

from picca.delta_extraction.quasar_catalogues.ztruth_catalogue import ZtruthCatalogue

defaults = {
    "delta lambda": 1.0,
    "lambda max": 5500.0,
    "lambda max rest frame": 1200.0,
    "lambda min": 3600.0,
    "lambda min rest frame": 1040.0,
    "mini SV": False,
}

class DesiData(Data):
    """Reads the spectra from Quickquasars and formats its data as a list of
    Forest instances.

    Methods
    -------
    get_forest_list (from Data)
    __init__
    _parse_config


    Attributes
    ----------
    forests: list of Forest (from Data)
    A list of Forest from which to compute the deltas.

    delta_lambda: float
    Variation of the wavelength (in Angs) between two pixels.

    in_dir: str
    Directory to spectra files.

    lambda_max: float
    Maximum wavelength (in Angs) to be considered in a forest.

    lambda_min: float
    Minimum wavelength (in Angs) to be considered in a forest.

    lambda_max_rest_frame: float
    As lambda_max but for rest-frame wavelength.

    lambda_min_rest_frame: float
    As lambda_min but for rest-frame wavelength.
    """
    def __init__(self, config):
        """Initialize class instance

        Arguments
        ---------
        config: configparser.SectionProxy
        Parsed options to initialize class
        """
        super().__init__(config)

        # load variables from config
        self.input_directory = None
        self.mini_sv = None
        self._parse_config(config)

        # load z_truth catalogue
        catalogue = ZtruthCatalogue(config)

        # setup DesiForest class variables
        DesiForest.delta_lambda = self.delta_lambda
        DesiForest.lambda_max = self.lambda_max
        DesiForest.lambda_max_rest_frame = self.lambda_max_rest_frame
        DesiForest.lambda_min = self.lambda_min
        DesiForest.lambda_min_rest_frame = self.lambda_min_rest_frame

        # read data
        if self.mini_sv:
            self.read_from_minisv_desi(catalogue)
        else:
            self.read_from_desi(catalogue)

    def _parse_config(self, config):
        """Parse the configuration options

        Arguments
        ---------
        config: configparser.SectionProxy
        Parsed options to initialize class

        Raise
        -----
        DataError upon missing required variables
        """
        self.delta_lambda = config.get("delta lambda")
        if self.delta_lambda is None:
            self.delta_lambda = defaults.get("delta lambda")
        self.input_directory = config.get("input directory")
        if self.input_directory is None:
            raise DataError("Missing argument 'input directory' required by SdssData")
        self.lambda_max = config.get("lambda max")
        if self.lambda_max is None:
            self.lambda_max = defaults.get("lambda max")
        self.lambda_max_rest_frame = config.get("lambda max rest frame")
        if self.lambda_max_rest_frame is None:
            self.lambda_max_rest_frame = defaults.get("lambda max rest frame")
        self.lambda_min = config.get("lambda min")
        if self.lambda_min is None:
            self.lambda_min = defaults.get("lambda min")
        self.lambda_min_rest_frame = config.get("lambda min rest frame")
        if self.lambda_min_rest_frame is None:
            self.lambda_min_rest_frame = defaults.get("lambda min rest frame")
        self.mini_sv = config.getboolean("mini SV")
        if self.mini_sv is None:
            self.mini_sv = defaults.get("mini SV")

    def read_from_desi(self, catalogue):
        """Reads the spectra and formats its data as Forest instances.

        Arguments
        ---------
        catalogue: astropy.Table
        Table with the quasar catalogue
        """
        in_nside = int(self.input_directory.split('spectra-')[-1].replace('/', ''))

        ra = catalogue['RA'].data
        dec = catalogue['DEC'].data
        in_healpixs = healpy.ang2pix(in_nside, np.pi / 2. - dec, ra, nest=True)
        unique_in_healpixs = np.unique(in_healpixs)

        forests_by_targetid = {}
        for index, healpix in enumerate(unique_in_healpixs):
            filename = (f"{self.input_directory}/{healpix//100}/{healpix}/spectra"
                        f"-{in_nside}-{healpix}.fits")

            userprint(f"Read {index} of {len(unique_in_healpixs)}. "
                      f"num_data: {len(self.forests)}")
            try:
                hdul = fitsio.FITS(filename)
            except IOError:
                warnings.warn(f"Error reading pix {healpix}. Ignoring file",
                              DataWarning)
                continue

            # Read targetid from fibermap to match to catalogue later
            fibermap = hdul['FIBERMAP'].read()
            targetid_spec = fibermap["TARGETID"]

            # First read all wavelength, flux, ivar, mask, and resolution
            # from this file
            spectrographs_data = {}
            colors = ["B", "R"]
            if "Z_FLUX" in hdul:
                colors.append("Z")
            for color in colors:
                spec = {}
                try:
                    spec["WAVELENGTHL"] = hdul[f"{color}_WAVELENGTH"].read()
                    spec["FLUX"] = hdul[f"{color}_FLUX"].read()
                    spec["IVAR"] = (hdul[f"{color}_IVAR"].read() *
                                    (hdul[f"{color}_MASK"].read() == 0))
                    w = np.isnan(spec["FLUX"]) | np.isnan(spec["IVAR"])
                    for key in ["FLUX", "IVAR"]:
                        spec[key][w] = 0.
                    spectrographs_data[color] = spec
                except OSError:
                    warnings.warn(f"Error while reading {color} band from {filename}."
                                  "Ignoring color.",
                                  DataWarning)
            hdul.close()

            # Get the quasars in this healpix pixel
            select = np.where(in_healpixs == healpix)[0]

            # Loop over quasars in catalogue inside this healpixel
            for entry in catalogue[select]:
                # Find which row in tile contains this quasar
                # It should be there by construction
                targetid = entry["TARGETID"]
                w_t = np.where(targetid_spec == targetid)[0]
                if len(w_t) == 0:
                    warnings.warn(f"Error reading {targetid}. Ignoring object",
                                  DataWarning)
                    continue
                if len(w_t) > 1:
                    warnings.warn("Warning: more than one spectrum in this file "
                                  f"for {targetid}", DataWarning)
                else:
                    w_t = w_t[0]

                # Construct DesiForest instance
                # Fluxes from the different spectrographs will be coadded
                for spec in spectrographs_data.values():
                    ivar = spec['IV'][w_t].copy()
                    flux = spec['FL'][w_t].copy()

                    forest = DesiForest(**{"lambda": spec['WAVELENGTH'],
                                           "flux": flux,
                                           "ivar": ivar,
                                           "targetid": targetid,
                                           "ra": entry['RA'],
                                           "dec": entry['DEC'],
                                           "z": entry['Z'],
                                           "petal": entry["PETAL_LOC"],
                                           "tile": entry["TILEID"],
                                           "night": entry["NIGHT"]})

                    if targetid in forests_by_targetid:
                        forests_by_targetid[targetid].coadd(forest)
                    else:
                        forests_by_targetid[targetid] = forest

        self.forests = list(forests_by_targetid.values())

    def read_from_minisv_desi(self, catalogue):
        """Reads the spectra and formats its data as Forest instances.
        Unlike the read_from_desi routine, this orders things by tile/petal
        Routine used to treat the DESI mini-SV data.

        Arguments
        ---------
        catalogue: astropy.Table
        Table with the quasar catalogue
        """

        forests_by_targetid = {}
        num_data = 0

        files_in = glob.glob(os.path.join(self.input_directory, "**/coadd-*.fits"),
                             recursive=True)
        petal_tile_night = [
            f"{entry['PETAL_LOC']}-{entry['TILEID']}-{entry['NIGHT']}"
            for entry in catalogue
        ]
        petal_tile_night_unique = np.unique(petal_tile_night)
        filenames = []
        for f_in in files_in:
            for ptn in petal_tile_night_unique:
                if ptn in os.path.basename(f_in):
                    filenames.append(f_in)
        filenames = np.unique(filenames)

        for index, filename in enumerate(filenames):
            userprint("read tile {} of {}. ndata: {}".format(
                index, len(filenames), num_data))
            try:
                hdul = fitsio.FITS(filename)
            except IOError:
                warnings.warn(f"Error reading file {filename}. Ignoring file",
                              DataWarning)
                continue

            fibermap = hdul['FIBERMAP'].read()
            fibermap_colnames = hdul["FIBERMAP"].get_colnames()
            # pre-Andes
            if 'TARGET_RA' in fibermap_colnames:
                ra = fibermap['TARGET_RA']
                dec = fibermap['TARGET_DEC']
                tile_spec = fibermap['TILEID'][0]
                night_spec = fibermap['NIGHT'][0]
                colors = ['BRZ']
                if index == 0:
                    warnings.warn("Reading all-band coadd as in minisv pre-Andes "
                                  "dataset", DataWarning)
            # Andes
            elif 'RA_TARGET' in fibermap_colnames:
                ra = fibermap['RA_TARGET']
                dec = fibermap['DEC_TARGET']
                tile_spec = filename.split('-')[-2]
                night_spec = int(filename.split('-')[-1].split('.')[0])
                colors = ['B', 'R', 'Z']
                if index == 0:
                    warnings.warn("Couldn't read the all band-coadd, trying "
                                  "single band as introduced in Andes reduction",
                                  DataWarning)
            ra = np.radians(ra)
            dec = np.radians(dec)

            petal_spec = fibermap['PETAL_LOC'][0]

            targetid_spec = fibermap['TARGETID']

            spectrographs_data = {}
            for color in colors:
                try:
                    spec = {}
                    spec['WAVELENGTH'] = hdul[f'{color}_WAVELENGTH'].read()
                    spec['FLUX'] = hdul[f'{color}_FLUX'].read()
                    spec['IVAR'] = (hdul[f'{color}_IVAR'].read() *
                                    (hdul[f'{color}_MASK'].read() == 0))
                    w = np.isnan(spec['FLUX']) | np.isnan(spec['IVAR'])
                    for key in ['FLUX', 'IVAR']:
                        spec[key][w] = 0.
                    spectrographs_data[color] = spec
                except OSError:
                    warnings.warn(f"Error while reading {color} band from {filename}."
                                  "Ignoring color.", DataWarning)

            hdul.close()

            select = ((catalogue['TILEID'] == tile_spec) &
                      (catalogue['PETAL_LOC'] == petal_spec) &
                      (catalogue['NIGHT'] == night_spec))
            userprint(
                f'This is tile {tile_spec}, petal {petal_spec}, night {night_spec}')

            # Loop over quasars in catalog inside this tile-petal
            for entry in catalogue[select]:

                # Find which row in tile contains this quasar
                targetid = entry['TARGETID']
                w_t = np.where(targetid_spec == targetid)[0]
                if len(w_t) == 0:
                    warnings.warn(f"Error reading {targetid}. Ignoring object",
                                  DataWarning)
                    continue
                if len(w_t) > 1:
                    warnings.warn("Warning: more than one spectrum in this file "
                                  f"for {targetid}", DataWarning)
                else:
                    w_t = w_t[0]

                for spec in spectrographs_data.values():
                    ivar = spec['IV'][w_t].copy()
                    flux = spec['FL'][w_t].copy()

                    forest = DesiForest(**{"lambda": spec['WAVELENGTH'],
                                           "flux": flux,
                                           "ivar": ivar,
                                           "targetid": entry["TARGETID"],
                                           "ra": entry['RA'],
                                           "dec": entry['DEC'],
                                           "z": entry['Z'],
                                           "petal": entry["PETAL_LOC"],
                                           "tile": entry["TILEID"],
                                           "night": entry["NIGHT"]})

                    if targetid in forests_by_targetid:
                        forests_by_targetid[targetid].coadd(forest)
                    else:
                        forests_by_targetid[targetid] = forest

                num_data += 1
        userprint("Found {} quasars in input files".format(num_data))

        if num_data == 0:
            raise DataError("No Quasars found, stopping here")

        self.forests = list(forests_by_targetid.values())

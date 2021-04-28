"""This file contains tests related to Data and its childs"""
import os
import unittest
from configparser import ConfigParser

from picca.delta_extraction.astronomical_objects.sdss_forest import SdssForest
from picca.delta_extraction.data import Data
from picca.delta_extraction.data_catalogues.sdss_data import SdssData
from picca.delta_extraction.utils import setup_logger
from picca.delta_extraction.tests.abstract_test import AbstractTest
from picca.delta_extraction.tests.test_utils import reset_logger
from picca.delta_extraction.tests.test_utils import forest1
from picca.delta_extraction.tests.test_utils import sdss_data_kwargs

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


class DataTest(AbstractTest):
    """Test class Data and its childs."""

    def test_data(self):
        """Test Abstract class Data

        Load a Data instace.
        """
        config = ConfigParser()
        config.read_dict({"data": {"output directory": f"{THIS_DIR}/results"},
                         })
        data = Data(config["data"])

        self.assertTrue(len(data.forests) == 0)
        self.assertTrue(data.min_num_pix == 50)

        config = ConfigParser()
        config.read_dict({"data": {"minimum number pixels in forest": 40,
                                   "output directory": f"{THIS_DIR}/results",},
                         })
        data = Data(config["data"])

        self.assertTrue(len(data.forests) == 0)
        self.assertTrue(data.min_num_pix == 40)
        self.assertTrue(data.analysis_type == "BAO 3D")

    def test_data_filter_forests(self):
        """Test method filter_forests from Abstract Class Data"""
        out_file = f"{THIS_DIR}/results/data_filter_forests_print.txt"
        test_file = f"{THIS_DIR}/data/data_filter_forests_print.txt"

        # setup printing
        setup_logger(log_file=out_file)

        # create Data instance
        config = ConfigParser()
        config.read_dict({"data": {"output directory": f"{THIS_DIR}/results"}})
        data = Data(config["data"])

        # add dummy forest
        data.forests.append(forest1)
        self.assertTrue(len(data.forests) == 1)

        # filter forests
        data.filter_forests()
        self.assertTrue(len(data.forests) == 1)

        # create Data instance with insane forest requirements
        config = ConfigParser()
        config.read_dict({"data": {"minimum number pixels in forest": 10000,
                                   "output directory": f"{THIS_DIR}/results"}
                         })
        data = Data(config["data"])

        # add dummy forest
        data.forests.append(forest1)
        self.assertTrue(len(data.forests) == 1)

        # filter forests
        data.filter_forests()
        self.assertTrue(len(data.forests) == 0)

        # reset printing
        reset_logger()
        self.compare_ascii(test_file, out_file, expand_dir=True)

    def test_sdss_data_spec(self):
        """Tests SdssData when run in spec mode"""
        config = ConfigParser()
        data_kwargs = sdss_data_kwargs.copy()
        data_kwargs.update({"mode": "spec"})
        config.read_dict({
            "data": data_kwargs
        })
        data = SdssData(config["data"])

        self.assertTrue(len(data.forests) == 43)
        self.assertTrue(data.min_num_pix == 50)
        self.assertTrue(data.analysis_type == "BAO 3D")
        self.assertTrue(
            all(isinstance(forest, SdssForest) for forest in data.forests))

    def test_sdss_data_spplate(self):
        """Tests SdssData when run in spplate mode"""
        # using default  value for 'mode'
        config = ConfigParser()
        config.read_dict({
            "data": sdss_data_kwargs
        })
        data = SdssData(config["data"])

        self.assertTrue(len(data.forests) == 43)
        self.assertTrue(data.min_num_pix == 50)
        self.assertTrue(data.analysis_type == "BAO 3D")
        self.assertTrue(
            all(isinstance(forest, SdssForest) for forest in data.forests))

        # specifying 'mode'
        config = ConfigParser()
        data_kwargs = sdss_data_kwargs.copy()
        data_kwargs.update({"mode": "spplate"})
        config.read_dict({
            "data": data_kwargs
        })
        data = SdssData(config["data"])

        self.assertTrue(len(data.forests) == 43)
        self.assertTrue(data.min_num_pix == 50)
        self.assertTrue(
            all(isinstance(forest, SdssForest) for forest in data.forests))


if __name__ == '__main__':
    unittest.main()

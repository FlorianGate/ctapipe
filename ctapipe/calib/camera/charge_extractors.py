from abc import abstractmethod

import numpy as np
from traitlets import Int, CaselessStrEnum

from ctapipe.core import Component, Factory


class ChargeExtractor(Component):
    """
    Attributes
    ----------
    extracted_samples : ndarray
        Numpy array containing True where the samples lay within the
        integration window, and False where the samples lay outside. Has
        shape of (n_chan, n_pix, n_samples).
    peakpos : ndarray
        Numpy array of the peak position for each pixel. Has shape of
        (n_chan, n_pix).
    neighbours : list
        List of neighbours for each pixel. Changes per telescope.

    """
    name = 'ChargeExtractor'

    def __init__(self, config, tool, **kwargs):
        """
        Base component for charge extractors

        Parameters
        ----------
        config : traitlets.loader.Config
            Configuration specified by config file or cmdline arguments.
            Used to set traitlet values.
            Set to None if no configuration to pass.
        tool : ctapipe.core.Tool
            Tool executable that is calling this component.
            Passes the correct logger to the component.
            Set to None if no Tool to pass.
        kwargs
        """
        super().__init__(config=config, parent=tool, **kwargs)

        self.neighbours = None

    @staticmethod
    def requires_neighbours():
        """
        Method used for callers of the ChargeExtractor to know if the extractor
        requires knowledge of the pixel neighbours

        Returns
        -------
        bool
        """
        return False

    def check_neighbour_set(self):
        """
        Check if the pixel neighbours has been set for the extractor

        Raises
        -------
        ValueError
            If neighbours has not been set
        """
        if self.requires_neighbours():
            if self.neighbours is None:
                self.log.exception("neighbours attribute must be set")
                raise ValueError()

    @abstractmethod
    def get_peakpos(self, waveforms):
        """
        Get the peak position from the waveforms
        
        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).
            
        Returns
        -------
        peakpos : ndarray
            Numpy array of the peak position for each pixel. 
            Has shape of (n_chan, n_pix).

        """

    @abstractmethod
    def extract_charge(self, waveforms):
        """
        Call the relevant functions to fully extract the charge for the
        particular extractor.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).

        Returns
        -------
        charge : ndarray
            Extracted charge stored in a numpy array of shape (n_chan, n_pix).
        window : ndarray
            Bool numpy array defining the samples included in the integration
            window.
        """


class Integrator(ChargeExtractor):
    name = 'Integrator'

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    @staticmethod
    def check_window_width_and_start(n_samples, start, width):
        """
        Check that the combination of window width and start positions fit
        within the readout window.

        Parameters
        ----------
        start : ndarray
            Numpy array containing the window start for each pixel. Shape =
            (n_chan, n_pix)
        width : ndarray
            Numpy array containing the window width for each pixel. Shape =
            (n_chan, n_pix)

        """
        width[width > n_samples] = n_samples
        start[start < 0] = 0
        sum_check = start + width > n_samples
        start[sum_check] = n_samples - width[sum_check]

    @abstractmethod
    def get_peakpos(self, waveforms):
        """"""

    @abstractmethod
    def _get_window_start(self, waveforms, peakpos):
        """
        Get the starting point for the integration window

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).
        peakpos : ndarray
            Numpy array containing the peak position for each pixel. 
            Shape = (n_chan, n_pix)

        Returns
        -------
        start : ndarray
            Numpy array containing the window start for each pixel. 
            Shape = (n_chan, n_pix)

        """

    @abstractmethod
    def _get_window_width(self, waveforms):
        """
        Get the width of the integration window
        
        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).

        Returns
        -------
        width : ndarray
            Numpy array containing the window width for each pixel. 
            Shape = (n_chan, n_pix)

        """

    def get_start_and_width(self, waveforms, peakpos):
        """
        Obtain the numpy arrays containing the start and width for the
        integration window for each pixel.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).
        peakpos : ndarray
            Numpy array of the peak position for each pixel. 
            Has shape of (n_chan, n_pix).

        Returns
        -------
        w_start : ndarray
            Numpy array containing the Start sample of integration window.
            Shape: (n_chan, n_pix).
        w_width : ndarray
            Numpy array containing the window size of integration window.
            Shape (n_chan, n_pix).
        """
        w_start = self._get_window_start(waveforms, peakpos)
        w_width = self._get_window_width(waveforms)
        n_samples = waveforms.shape[2]
        self.check_window_width_and_start(n_samples, w_start, w_width)
        return w_start, w_width

    @staticmethod
    def get_window(waveforms, start, width):
        """
        Build the a numpy array of bools defining the integration window.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).
        start : ndarray
            Numpy array containing the Start sample of integration window.
            Shape: (n_chan, n_pix).
        width : ndarray
            Numpy array containing the window size of integration window.
            Shape (n_chan, n_pix).

        Returns
        -------
        integration_window : ndarray
            Numpy array containing True where the samples lay within the
            integration window, and False where the samples lay outside. Has
            shape of (n_chan, n_pix, n_samples).

        """
        end = start + width

        # Obtain integration window using the indices of the waveforms array
        ind = np.indices(waveforms.shape)[2]
        integration_window = (ind >= start[..., None]) & (ind < end[..., None])
        return integration_window

    @staticmethod
    def extract_from_window(waveforms, window):
        """
        Extract the charge but applying an intregration window to the 
        waveforms.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).
        window : ndarray
            Numpy array containing True where the samples lay within the
            integration window, and False where the samples lay outside. Has
            shape of (n_chan, n_pix, n_samples).

        Returns
        -------
        charge : ndarray
            Extracted charge stored in a numpy array of shape (n_chan, n_pix).
        """
        windowed = np.ma.array(waveforms, mask=~window)
        charge = windowed.sum(2)
        return charge

    def extract_charge(self, waveforms):
        peakpos = self.get_peakpos(waveforms)
        start, width = self.get_start_and_width(waveforms, peakpos)
        window = self.get_window(waveforms, start, width)
        charge = self.extract_from_window(waveforms, window)
        return charge, peakpos, window


class FullIntegrator(Integrator):
    name = 'FullIntegrator'

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def _get_window_start(self, waveforms, peakpos):
        nchan, npix, nsamples = waveforms.shape
        return np.zeros((nchan, npix), dtype=np.intp)

    def _get_window_width(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        return np.full((nchan, npix), nsamples, dtype=np.intp)

    def get_peakpos(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        return np.zeros((nchan, npix), dtype=np.intp)


class WindowIntegrator(Integrator):
    name = 'WindowIntegrator'
    window_shift = Int(3, help='Define the shift of the integration window '
                               'from the peakpos '
                               '(peakpos - shift)').tag(config=True)
    window_width = Int(7, help='Define the width of the integration '
                               'window').tag(config=True)

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def get_peakpos(self, waveforms):
        return self._obtain_peak_position(waveforms)

    def _get_window_start(self, waveforms, peakpos):
        return peakpos - self.window_shift

    def _get_window_width(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        return np.full((nchan, npix), self.window_width, dtype=np.intp)

    @abstractmethod
    def _obtain_peak_position(self, waveforms):
        """
        Find the peak to define integration window around.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).

        Returns
        -------
        peakpos : ndarray
            Numpy array of the peak position for each pixel. Has shape of
            (n_chan, n_pix).

        """


class SimpleIntegrator(WindowIntegrator):
    name = 'SimpleIntegrator'
    t0 = Int(0, help='Define the peak position for all '
                     'pixels').tag(config=True)

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def _obtain_peak_position(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        return np.full((nchan, npix), self.t0, dtype=np.intp)


class PeakFindingIntegrator(WindowIntegrator):
    name = 'PeakFindingIntegrator'
    sig_amp_cut_HG = Int(None, allow_none=True,
                         help='Define the cut above which a sample is '
                              'considered as significant for PeakFinding '
                              'in the HG channel').tag(config=True)
    sig_amp_cut_LG = Int(None, allow_none=True,
                         help='Define the cut above which a sample is '
                              'considered as significant for PeakFinding '
                              'in the LG channel').tag(config=True)

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)
        self._sig_channel = None
        self._sig_pixels = None

    # Extract significant entries
    def _extract_significant_entries(self, waveforms):
        """
        Obtain the samples that the user has specified as significant.

        Parameters
        ----------
        waveforms : ndarray
            Waveforms stored in a numpy array of shape
            (n_chan, n_pix, n_samples).

        Returns
        -------
        significant_samples : masked ndarray
            Identical to waveforms, except the insignificant samples are
            masked.

        """
        nchan, npix, nsamples = waveforms.shape
        if self.sig_amp_cut_HG or self.sig_amp_cut_HG:
            sig_entries = np.ones(waveforms.shape, dtype=bool)
            if self.sig_amp_cut_HG:
                sig_entries[0] = waveforms[0] > self.sig_amp_cut_HG
            if nchan > 1 and self.sig_amp_cut_LG:
                sig_entries[1] = waveforms[1] > self.sig_amp_cut_LG
            self._sig_pixels = np.any(sig_entries, axis=2)
            self._sig_channel = np.any(self._sig_pixels, axis=1)
            if not self._sig_channel[0]:
                self.log.error("sigamp excludes all values in HG channel")
            return np.ma.array(waveforms, mask=~sig_entries)
        else:
            self._sig_channel = np.ones(nchan, dtype=bool)
            self._sig_pixels = np.ones((nchan, npix), dtype=bool)
            return waveforms

    @abstractmethod
    def _obtain_peak_position(self, waveforms):
        """"""


class GlobalPeakIntegrator(PeakFindingIntegrator):
    name = 'GlobalPeakIntegrator'

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def _obtain_peak_position(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        significant_samples = self._extract_significant_entries(waveforms)
        max_t = significant_samples.argmax(2)
        max_s = significant_samples.max(2)

        peakpos = np.zeros((nchan, npix), dtype=np.int)
        peakpos[0, :] = np.round(np.average(max_t[0], weights=max_s[0]))
        if nchan > 1:
            if self._sig_channel[1]:
                peakpos[1, :] = np.round(
                    np.average(max_t[1], weights=max_s[1]))
            else:
                self.log.info("LG not significant, using HG for peak finding "
                              "instead")
                peakpos[1, :] = peakpos[0]
        return peakpos


class LocalPeakIntegrator(PeakFindingIntegrator):
    name = 'LocalPeakIntegrator'

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def _obtain_peak_position(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        significant_samples = self._extract_significant_entries(waveforms)
        peakpos = np.full((nchan, npix), significant_samples.argmax(2),
                          dtype=np.int)
        sig_pix = self._sig_pixels
        if nchan > 1:  # If the LG is not significant, use the HG peakpos
            peakpos[1] = np.where(sig_pix[1] < sig_pix[0],
                                  peakpos[0], peakpos[1])
        return peakpos


class NeighbourPeakIntegrator(PeakFindingIntegrator):
    name = 'NeighbourPeakIntegrator'
    lwt = Int(0, help='Weight of the local pixel (0: peak from neighbours '
                      'only, 1: local pixel counts as much '
                      'as any neighbour').tag(config=True)

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    @staticmethod
    def requires_neighbours():
        return True

    def _obtain_peak_position(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        significant_samples = self._extract_significant_entries(waveforms)
        sig_sam = significant_samples
        max_num_nei = len(max(self.neighbours, key=len))
        allvals = np.zeros((nchan, npix, max_num_nei + 1, nsamples))
        for ipix, neighbours in enumerate(self.neighbours):
            num_nei = len(neighbours)
            allvals[:, ipix, :num_nei, :] = sig_sam[:, neighbours]
            allvals[:, ipix, num_nei, :] = sig_sam[:, ipix] * self.lwt
        sum_data = allvals.sum(2)
        return np.full((nchan, npix), sum_data.argmax(2), dtype=np.int)


class AverageWfPeakIntegrator(PeakFindingIntegrator):
    name = 'AverageWfPeakIntegrator'

    def __init__(self, config, tool, **kwargs):
        super().__init__(config=config, tool=tool, **kwargs)

    def _obtain_peak_position(self, waveforms):
        nchan, npix, nsamples = waveforms.shape
        significant_samples = self._extract_significant_entries(waveforms)
        peakpos = np.zeros((nchan, npix), dtype=np.int)
        avg_wf = np.mean(significant_samples, axis=1)
        peakpos += np.argmax(avg_wf, axis=1)[:, None]
        return peakpos


class ChargeExtractorFactory(Factory):
    name = "ChargeExtractorFactory"
    description = "Obtain ChargeExtractor based on extractor traitlet"

    subclasses = Factory.child_subclasses(ChargeExtractor)
    subclass_names = [c.__name__ for c in subclasses]

    extractor = CaselessStrEnum(subclass_names, 'NeighbourPeakIntegrator',
                                help='Charge extraction scheme to '
                                     'use.').tag(config=True)

    # Product classes traits
    # Would be nice to have these automatically set...!
    window_width = Int(7, help='Define the width of the integration '
                               'window. Only applicable to '
                               'WindowIntegrators.').tag(config=True)
    window_shift = Int(3, help='Define the shift of the integration window '
                               'from the peakpos (peakpos - shift). Only '
                               'applicable to '
                               'PeakFindingIntegrators.').tag(config=True)
    t0 = Int(0, help='Define the peak position for all pixels. '
                     'Only applicable to SimpleIntegrators.').tag(config=True)
    sig_amp_cut_HG = Int(None, allow_none=True,
                         help='Define the cut above which a sample is '
                              'considered as significant for PeakFinding '
                              'in the HG channel. Only applicable to '
                              'PeakFindingIntegrators.').tag(config=True)
    sig_amp_cut_LG = Int(None, allow_none=True,
                         help='Define the cut above which a sample is '
                              'considered as significant for PeakFinding '
                              'in the LG channel. Only applicable to '
                              'PeakFindingIntegrators.').tag(config=True)
    lwt = Int(0, help='Weight of the local pixel (0: peak from neighbours '
                      'only, 1: local pixel counts as much as any neighbour). '
                      'Only applicable to '
                      'NeighbourPeakIntegrator').tag(config=True)

    def get_factory_name(self):
        return self.name

    def get_product_name(self):
        return self.extractor

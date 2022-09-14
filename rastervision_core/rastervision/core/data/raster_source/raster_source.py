from typing import TYPE_CHECKING, Any, List, Optional, Tuple
from abc import ABC, abstractmethod, abstractproperty

from rastervision.core.box import Box

if TYPE_CHECKING:
    from rastervision.core.data import (CRSTransformer, RasterTransformer)
    import numpy as np


class ChannelOrderError(Exception):
    def __init__(self, channel_order: List[int], num_channels: int):
        self.channel_order = channel_order
        self.num_channels = num_channels
        msg = (f'The channel_order={str(channel_order)} contains a '
               f'channel index >= num_channels={num_channels}')
        super().__init__(msg)


def validate_channel_order(channel_order: List[int],
                           num_channels: int) -> None:
    for c in channel_order:
        if c >= num_channels:
            raise ChannelOrderError(channel_order, num_channels)


class RasterSource(ABC):
    """A source of raster data.

    This should be subclassed when adding a new source of raster data such as
    a set of files, an API, a TMS URI schema, etc.
    """

    def __init__(self,
                 channel_order: Optional[List[int]],
                 num_channels_raw: int,
                 raster_transformers: List['RasterTransformer'] = [],
                 extent: Optional[Box] = None):
        """Construct a new RasterSource.

        Args:
            channel_order: list of channel indices to use when extracting chip from
                raw imagery.
            num_channels_raw: Number of channels in the raw imagery before applying
                channel_order.
            raster_transformers: RasterTransformers used to transform chips
                whenever they are retrieved.
            extent (Optional[Box], optional): Use-specified extent. If None,
                the full extent of the raster source is used.
        """
        if channel_order is None:
            channel_order = list(range(num_channels_raw))
        validate_channel_order(channel_order, num_channels_raw)
        self.channel_order = channel_order
        self.num_channels_raw = num_channels_raw
        self.raster_transformers = raster_transformers
        self._extent = extent

    @property
    def num_channels(self) -> int:
        return len(self.channel_order)

    @property
    def shape(self) -> Tuple[int, int, int]:
        ymin, xmin, ymax, xmax = self.extent
        return ymax - ymin, xmax - xmin, self.num_channels

    @abstractproperty
    def dtype(self) -> 'np.dtype':
        """Return the numpy.dtype of this scene"""
        pass

    @property
    def extent(self) -> 'Box':
        """Return the extent of the RasterSource.

        Returns:
            Box in pixel coordinates with extent
        """
        return self._extent

    @abstractproperty
    def crs_transformer(self) -> 'CRSTransformer':
        """Return the associated CRSTransformer."""
        pass

    @abstractmethod
    def _get_chip(self, window: 'Box') -> 'np.ndarray':
        """Return the raw chip located in the window.

        Args:
            window: Box

        Returns:
            [height, width, channels] numpy array
        """
        pass

    def __getitem__(self, key: Any) -> 'np.ndarray':
        if isinstance(key, Box):
            return self.get_chip(key)
        elif isinstance(key, slice):
            key = [key]
        elif isinstance(key, tuple):
            pass
        else:
            raise TypeError('Unsupported key type.')
        slices = list(key)

        assert 1 <= len(slices) <= 2
        assert all(s is not None for s in slices)
        assert isinstance(slices[0], slice)
        if len(slices) == 1:
            h, = slices
            w = slice(None, None)
        else:
            assert isinstance(slices[1], slice)
            h, w = slices

        if any(x is not None and x < 0
               for x in [h.start, h.stop, w.start, w.stop]):
            raise NotImplementedError()

        ymin, xmin, ymax, xmax = self.extent
        _ymin = 0 if h.start is None else h.start
        _xmin = 0 if w.start is None else w.start
        _ymax = ymax if h.stop is None else h.stop
        _xmax = xmax if w.stop is None else w.stop
        window = Box(_ymin, _xmin, _ymax, _xmax)

        chip = self.get_chip(window)
        if h.step is not None or w.step is not None:
            chip = chip[::h.step, ::w.step]
        return chip

    def get_chip(self, window: 'Box') -> 'np.ndarray':
        """Return the transformed chip in the window.

        Get a raw chip, extract subset of channels using channel_order, and then apply
        transformations.

        Args:
            window: Box

        Returns:
            np.ndarray with shape [height, width, channels]
        """
        chip = self._get_chip(window)

        chip = chip[:, :, self.channel_order]

        for transformer in self.raster_transformers:
            chip = transformer.transform(chip, self.channel_order)

        return chip

    def get_raw_chip(self, window: 'Box') -> 'np.ndarray':
        """Return raw chip without using channel_order or applying transforms.

        Args:
            window: (Box) the window for which to get the chip

        Returns:
            np.ndarray with shape [height, width, channels]
        """
        return self._get_chip(window)

    def get_image_array(self) -> 'np.ndarray':
        """Return entire transformed image array.

        Not safe to call on very large RasterSources.
        """
        return self.get_chip(self.extent)

    def get_raw_image_array(self) -> 'np.ndarray':
        """Return entire raw image without using channel_order or applying transforms.

        Not safe to call on very large RasterSources.
        """
        return self.get_raw_chip(self.extent)

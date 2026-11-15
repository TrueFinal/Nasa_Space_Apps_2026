"""SPHEREx DR1/QR3 pixel policy, Explanatory Supplement v2.1 Table 16."""

import numpy as np

SOURCE_BIT = 21


def bad_pixel_mask(flags):
    """SOURCE identifies a cataloged source and is not a defective-pixel flag.

    Preserve SOURCE-only pixels; conservatively reject every other set bit,
    including unrecognized/reserved bits. Combination flags remain rejected.
    """
    values = np.asarray(flags).astype(np.uint32)
    return (values & np.uint32(0xFFFFFFFF ^ (1 << SOURCE_BIT))) != 0

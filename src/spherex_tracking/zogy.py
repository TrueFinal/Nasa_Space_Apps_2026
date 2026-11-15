"""ZOGY Fourier subtraction and corrected score, Zackay et al. (2016).

Independent implementation: Eqs. 13–17, 25–30. Inputs must be registered and
background-subtracted; supplied variance maps already include detector/source
noise. No additional Poisson term is invented for MJy/sr images.
"""

import numpy as np


def psf_otf(psf, shape):
    psf = np.asarray(psf, dtype=float)
    if psf.ndim != 2 or not np.all(np.isfinite(psf)) or psf.sum() <= 0:
        raise ValueError("A finite positive-normalization PSF is required.")
    if any(k % 2 != 1 for k in psf.shape) or any(k > n for k, n in zip(psf.shape, shape)):
        raise ValueError("PSF dimensions must be odd and fit inside the FFT grid.")
    array = np.zeros(shape)
    y, x = (n // 2 - k // 2 for n, k in zip(shape, psf.shape))
    array[y : y + psf.shape[0], x : x + psf.shape[1]] = psf / psf.sum()
    return np.fft.fft2(np.fft.ifftshift(array))


def zogy_subtract(
    new,
    reference,
    psf_new,
    psf_reference,
    variance_new,
    variance_reference,
    flux_scale=1.0,
    mask_new=None,
    mask_reference=None,
    astrometric_sigma_xy=(0.0, 0.0),
    pad=32,
):
    """Return proper D, effective PSF, S and variance/astrometry-corrected S_corr.

    F_r=1, F_n=flux_scale. Fourier weights use median background variances;
    squared real-space score kernels propagate the full supplied variance maps.
    Missing samples are zero-filled, then excluded using a kernel-energy mask.
    The resulting mask is a practical approximation for global Fourier tails.
    """
    new, reference = np.asarray(new, float), np.asarray(reference, float)
    if new.ndim != 2 or new.shape != reference.shape or flux_scale <= 0:
        raise ValueError("Two same-shape images and a positive flux scale are required.")
    vn = np.broadcast_to(variance_new, new.shape).astype(float).copy()
    vr = np.broadcast_to(variance_reference, new.shape).astype(float).copy()
    mn = ~np.isfinite(new) | ~np.isfinite(vn) | (vn <= 0)
    mr = ~np.isfinite(reference) | ~np.isfinite(vr) | (vr <= 0)
    if mask_new is not None:
        mn |= mask_new
    if mask_reference is not None:
        mr |= mask_reference
    if np.all(mn) or np.all(mr):
        raise ValueError("Image has no valid samples.")
    sn2, sr2 = float(np.median(vn[~mn])), float(np.median(vr[~mr]))
    shape = (new.shape[0] + 2 * pad, new.shape[1] + 2 * pad)
    crop = (slice(pad, pad + new.shape[0]), slice(pad, pad + new.shape[1]))
    n = np.pad(np.where(mn, 0, new), pad)
    r = np.pad(np.where(mr, 0, reference), pad)
    nv = np.pad(np.where(mn, sn2, vn), pad, constant_values=sn2)
    rv = np.pad(np.where(mr, sr2, vr), pad, constant_values=sr2)
    pn, pr = psf_otf(psf_new, shape), psf_otf(psf_reference, shape)
    fn = float(flux_scale)
    denominator = sn2 * np.abs(pr) ** 2 + sr2 * fn**2 * np.abs(pn) ** 2
    frequencies = denominator > denominator.max() * 1e-14
    inverse_root = np.zeros(shape)
    np.divide(1, np.sqrt(denominator), out=inverse_root, where=frequencies)
    fd = fn / np.sqrt(sn2 + sr2 * fn**2)
    dhat = (pr * np.fft.fft2(n) - fn * pn * np.fft.fft2(r)) * inverse_root
    pdhat = fn * pn * pr * inverse_root / fd
    shat = fd * dhat * np.conj(pdhat)
    knhat = fd * np.conj(pdhat) * pr * inverse_root
    krhat = fd * np.conj(pdhat) * fn * pn * inverse_root
    kn, kr = np.fft.ifft2(knhat).real, np.fft.ifft2(krhat).real

    def circular(array, kernel):
        return np.fft.ifft2(np.fft.fft2(array) * np.fft.fft2(kernel)).real

    score_variance = circular(nv, kn**2) + circular(rv, kr**2)
    sigma_x, sigma_y = astrometric_sigma_xy
    if sigma_x or sigma_y:
        component = np.fft.ifft2(np.fft.fft2(n) * knhat).real
        dy, dx = np.gradient(component)
        score_variance += sigma_x**2 * dx**2 + sigma_y**2 * dy**2
    raw_score = np.fft.ifft2(shat).real
    corrected = np.zeros(shape)
    np.divide(
        raw_score, np.sqrt(np.maximum(score_variance, 0)), out=corrected, where=score_variance > 0
    )
    missing_n = circular(np.pad(mn, pad, constant_values=True).astype(float), kn**2)
    missing_r = circular(np.pad(mr, pad, constant_values=True).astype(float), kr**2)
    valid = (
        (missing_n / max(np.sum(kn**2), 1e-30) < 0.01)
        & (missing_r / max(np.sum(kr**2), 1e-30) < 0.01)
    )[crop]
    valid &= ~mn & ~mr
    margin = min(8, min(new.shape) // 4)
    valid[:margin] = valid[-margin:] = False
    valid[:, :margin] = valid[:, -margin:] = False
    return dict(
        difference=np.fft.ifft2(dhat).real[crop],
        score=raw_score[crop],
        scorr=corrected[crop],
        score_variance=score_variance[crop],
        valid=valid,
        psf_difference=np.fft.fftshift(np.fft.ifft2(pdhat).real),
        fd=float(fd),
        sigma_new=np.sqrt(sn2),
        sigma_reference=np.sqrt(sr2),
        retained_fourier_fraction=float(np.mean(frequencies)),
    )


def cross_match_psfs(
    new, reference, psf_new, psf_reference, variance_new, variance_reference, flux_scale=1.0
):
    """Independent PSF-matching diagnostic by cross-convolution, not ZOGY input."""
    from scipy.signal import fftconvolve

    matched_new = fftconvolve(new, psf_reference, mode="same") / flux_scale
    matched_reference = fftconvolve(reference, psf_new, mode="same")
    variance = fftconvolve(
        variance_new, psf_reference**2, mode="same"
    ) / flux_scale**2 + fftconvolve(variance_reference, psf_new**2, mode="same")
    return dict(
        new=matched_new,
        reference=matched_reference,
        difference=matched_new - matched_reference,
        variance=variance,
        common_psf=fftconvolve(psf_new, psf_reference, mode="full"),
    )

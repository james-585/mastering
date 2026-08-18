#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <vector>
#include <complex>
#include <cmath>
#include <algorithm>
#include <stdexcept>

namespace py = pybind11;

static constexpr float kPi = 3.14159265358979323846f;

void compute_fft(std::vector<std::complex<float>>& x, bool inverse) {
    const size_t n = x.size();
    if (n == 0 || (n & (n - 1)) != 0) {
        throw std::runtime_error("FFT length must be a power of two.");
    }

    size_t j = 0;
    for (size_t i = 1; i < n; ++i) {
        size_t bit = n >> 1;
        while (j & bit) {
            j ^= bit;
            bit >>= 1;
        }
        j ^= bit;
        if (i < j) {
            std::swap(x[i], x[j]);
        }
    }

    for (size_t len = 2; len <= n; len <<= 1) {
        const float angle = inverse ? (2.0f * kPi / static_cast<float>(len))
                                   : (-2.0f * kPi / static_cast<float>(len));
        const std::complex<float> wlen(std::cos(angle), std::sin(angle));

        for (size_t i = 0; i < n; i += len) {
            const size_t half = len / 2;
            std::complex<float> w(1.0f, 0.0f);

            for (size_t k = 0; k < half; ++k) {
                const std::complex<float> u = x[i + k];
                const std::complex<float> v = x[i + k + half] * w;
                x[i + k] = u + v;
                x[i + k + half] = u - v;
                w *= wlen;
            }
        }
    }

    if (inverse) {
        const float scale = 1.0f / static_cast<float>(n);
        for (auto& sample : x) {
            sample *= scale;
        }
    }
}

py::array_t<float> repair_whistles(
    py::array_t<float, py::array::c_style | py::array::forcecast> input_audio,
    int sample_rate,
    std::vector<float> target_frequencies)
{
    if (sample_rate <= 0) {
        throw std::runtime_error("sample_rate must be positive.");
    }

    py::buffer_info input_info = input_audio.request();
    if (input_info.ndim < 1 || input_info.size == 0) {
        throw std::runtime_error("input_audio must be a non-empty 1D or 2D NumPy array.");
    }
    if (input_info.ndim > 2) {
        throw std::runtime_error("input_audio must be 1D or 2D.");
    }
    if (target_frequencies.empty()) {
        return input_audio; // Exact no-op: no flagged whistle bins implies no destructive STFT pass.
    }

    const int frame_size = 4096;
    const int hop_size = 2048;

    const py::ssize_t n_samples = input_info.shape[0];
    const py::ssize_t n_channels = (input_info.ndim == 2) ? input_info.shape[1] : 1;

    std::vector<py::ssize_t> output_shape;
    output_shape.reserve(input_info.ndim);
    for (py::ssize_t i = 0; i < input_info.ndim; ++i) {
        output_shape.push_back(input_info.shape[i]);
    }

    py::array_t<float> output(output_shape);
    auto* output_ptr = output.mutable_data();
    std::fill(output_ptr, output_ptr + output.size(), 0.0f);

    std::vector<float> hann(frame_size, 0.0f);
    for (int i = 0; i < frame_size; ++i) {
        hann[i] = 0.5f - 0.5f * std::cos(
            (2.0f * kPi * static_cast<float>(i)) / static_cast<float>(frame_size - 1));
    }

    std::vector<float> overlap_weights(static_cast<size_t>(n_samples) * static_cast<size_t>(n_channels), 0.0f);
    const float* input_ptr = static_cast<const float*>(input_info.ptr);

    auto sample_at = [&](py::ssize_t sample_index, py::ssize_t channel_index) -> float {
        if (sample_index < 0 || sample_index >= n_samples) {
            return 0.0f;
        }
        if (input_info.ndim == 1) {
            return input_ptr[sample_index];
        }
        return input_ptr[sample_index * n_channels + channel_index];
    };

    for (py::ssize_t channel = 0; channel < n_channels; ++channel) {
        py::ssize_t start = 0;

        while (start + frame_size <= n_samples) {
            std::vector<std::complex<float>> frame(frame_size, std::complex<float>(0.0f, 0.0f));

            for (int i = 0; i < frame_size; ++i) {
                const float sample = sample_at(start + i, channel);
                frame[i] = std::complex<float>(sample * hann[i], 0.0f);
            }

            compute_fft(frame, false);

            for (float target_hz : target_frequencies) {
                if (target_hz <= 0.0f) {
                    continue;
                }

                const float bin_float = (target_hz * static_cast<float>(frame_size)) /
                    static_cast<float>(sample_rate);
                const int target_bin = static_cast<int>(std::round(bin_float));

                if (target_bin < 0 || target_bin >= frame_size) {
                    continue;
                }

                const int first_bin = std::max(0, target_bin - 2);
                const int last_bin = std::min(frame_size - 1, target_bin + 2);
                for (int bin = first_bin; bin <= last_bin; ++bin) {
                    frame[bin] *= 0.01f;
                }

                const int mirrored_bin = (frame_size - target_bin) % frame_size;
                if (mirrored_bin != target_bin) {
                    const int mirror_first = std::max(0, mirrored_bin - 2);
                    const int mirror_last = std::min(frame_size - 1, mirrored_bin + 2);
                    for (int bin = mirror_first; bin <= mirror_last; ++bin) {
                        frame[bin] *= 0.01f;
                    }
                }
            }

            compute_fft(frame, true);

            for (int i = 0; i < frame_size; ++i) {
                const py::ssize_t sample_index = start + i;
                if (sample_index < 0 || sample_index >= n_samples) {
                    continue;
                }

                const float processed = frame[i].real() * hann[i];

                if (input_info.ndim == 1) {
                    const size_t out_index = static_cast<size_t>(sample_index);
                    output_ptr[out_index] += processed;
                    // OLA normalisation fix: the signal is windowed on both
                    // analysis and synthesis, so the numerator carries hann^2
                    // per contributing frame. The divisor must accumulate the
                    // same hann^2 weighting (not plain hann) so numerator and
                    // divisor cancel exactly -- otherwise reconstruction gain
                    // becomes a periodic amplitude modulation at
                    // sample_rate/hop_size instead of a constant unity trim.
                    // See stories/STORY-009/architecture.md Section 3.
                    overlap_weights[out_index] += hann[i] * hann[i];
                } else {
                    const size_t out_index =
                        static_cast<size_t>(sample_index) * static_cast<size_t>(n_channels) +
                        static_cast<size_t>(channel);
                    output_ptr[out_index] += processed;
                    overlap_weights[out_index] += hann[i] * hann[i];
                }
            }

            start += hop_size;
        }

        if (n_samples > frame_size && start < n_samples) {
            const py::ssize_t tail_start = n_samples - frame_size;
            std::vector<std::complex<float>> frame(frame_size, std::complex<float>(0.0f, 0.0f));

            for (int i = 0; i < frame_size; ++i) {
                const float sample = sample_at(tail_start + i, channel);
                frame[i] = std::complex<float>(sample * hann[i], 0.0f);
            }

            compute_fft(frame, false);

            for (float target_hz : target_frequencies) {
                if (target_hz <= 0.0f) {
                    continue;
                }

                const float bin_float = (target_hz * static_cast<float>(frame_size)) /
                    static_cast<float>(sample_rate);
                const int target_bin = static_cast<int>(std::round(bin_float));

                if (target_bin < 0 || target_bin >= frame_size) {
                    continue;
                }

                const int first_bin = std::max(0, target_bin - 2);
                const int last_bin = std::min(frame_size - 1, target_bin + 2);
                for (int bin = first_bin; bin <= last_bin; ++bin) {
                    frame[bin] *= 0.01f;
                }

                const int mirrored_bin = (frame_size - target_bin) % frame_size;
                if (mirrored_bin != target_bin) {
                    const int mirror_first = std::max(0, mirrored_bin - 2);
                    const int mirror_last = std::min(frame_size - 1, mirrored_bin + 2);
                    for (int bin = mirror_first; bin <= mirror_last; ++bin) {
                        frame[bin] *= 0.01f;
                    }
                }
            }

            compute_fft(frame, true);

            for (int i = 0; i < frame_size; ++i) {
                const py::ssize_t sample_index = tail_start + i;
                if (sample_index < 0 || sample_index >= n_samples) {
                    continue;
                }

                const float processed = frame[i].real() * hann[i];

                if (input_info.ndim == 1) {
                    const size_t out_index = static_cast<size_t>(sample_index);
                    output_ptr[out_index] += processed;
                    overlap_weights[out_index] += hann[i] * hann[i];
                } else {
                    const size_t out_index =
                        static_cast<size_t>(sample_index) * static_cast<size_t>(n_channels) +
                        static_cast<size_t>(channel);
                    output_ptr[out_index] += processed;
                    overlap_weights[out_index] += hann[i] * hann[i];
                }
            }
        }
    }

    // Numerical-stability guard (found while implementing the Section 3 OLA
    // fix -- not present in the original buggy code, which divided by
    // plain hann() and so never produced denominators this small).
    // At the true start/end of the whole buffer, only one frame
    // contributes, and hann() itself tapers to (near) zero there. The
    // corrected divisor is hann[i]^2, which falls faster than hann[i] as
    // hann[i] -> 0, so dividing FFT round-off noise (bounded roughly
    // 2e-7 * hann[i], per architecture.md Section 2's derived float32
    // round-trip bound applied to a synthesis-windowed sample) by
    // hann[i]^2 blows up once hann[i] drops below ~2e-3 (solving
    // noise/hann[i]^2 <= 1e-4, a bound far below any audible/dither floor,
    // for hann[i] gives ~2e-3, i.e. overlap_weights >= ~4e-6). Below that
    // floor, OLA reconstruction is not numerically trustworthy for the
    // handful of samples this affects -- pass the original sample through
    // unmodified there instead of dividing by a near-zero weight.
    const float kMinReliableOverlapWeight = 4.0e-6f;
    for (size_t i = 0; i < output.size(); ++i) {
        if (overlap_weights[i] > kMinReliableOverlapWeight) {
            output_ptr[i] /= overlap_weights[i];
        } else {
            const py::ssize_t sample_index = (input_info.ndim == 1)
                ? static_cast<py::ssize_t>(i)
                : static_cast<py::ssize_t>(i / static_cast<size_t>(n_channels));
            const py::ssize_t channel_index = (input_info.ndim == 1)
                ? 0
                : static_cast<py::ssize_t>(i % static_cast<size_t>(n_channels));
            output_ptr[i] = sample_at(sample_index, channel_index);
        }
    }

    return output;
}

// STORY-009 (architecture.md Section 7): the detector path (link signal ->
// highpass -> rectify -> envelope followers) is stereo-linked and shared
// across all channels; only the resulting gain multiplier is applied,
// identically, to every channel's own sample. This fixes two Gate-1-
// confirmed defects in the original per-channel implementation:
//   (1) both envelope followers full-wave-rectified a broadband signal, so a
//       sustained bass fundamental f produced ripple at 2f that the fast
//       follower (79.6 Hz corner) did not sufficiently reject -- a 150 Hz
//       highpass ahead of rectification removes the sub/bass fundamentals
//       (~40-120 Hz) that caused this, at the source;
//   (2) independent per-channel envelope followers could trigger the
//       attack/sustain switch at different instants between L and R,
//       re-opening stereo width that stages [5a]/[5b] just corrected --
//       a single stereo-linked control signal (max(|L|,|R|) per sample)
//       removes this by construction.
py::array_t<float> shape_transients(
    py::array_t<float, py::array::c_style | py::array::forcecast> input_audio,
    int sample_rate,
    float attack_boost_db,
    float sustain_cut_db)
{
    if (sample_rate <= 0) {
        throw std::runtime_error("sample_rate must be positive.");
    }

    py::buffer_info input_info = input_audio.request();
    if (input_info.ndim < 1 || input_info.ndim > 2 || input_info.size == 0) {
        throw std::runtime_error("input_audio must be a non-empty 1D or 2D NumPy array.");
    }

    const py::ssize_t n_samples = input_info.shape[0];
    const py::ssize_t n_channels = (input_info.ndim == 2) ? input_info.shape[1] : 1;

    std::vector<py::ssize_t> output_shape;
    output_shape.reserve(static_cast<size_t>(input_info.ndim));
    for (py::ssize_t i = 0; i < input_info.ndim; ++i) {
        output_shape.push_back(input_info.shape[i]);
    }

    py::array_t<float> output(output_shape);
    auto* output_ptr = output.mutable_data();
    std::fill(output_ptr, output_ptr + output.size(), 0.0f);

    const float* input_ptr = static_cast<const float*>(input_info.ptr);

    // Envelope-follower time constants (architecture.md Section 7). The
    // slow/sustain constant is widened from the original 50 ms (too short
    // for mastering-stage use -- risks re-classifying the decaying body of
    // a kick/clap as "attack" repeatedly through its decay) into the
    // 100-500 ms range conventional transient designers use; 250 ms is the
    // working midpoint value pending empirical/listening validation
    // (architecture.md Section 7, "exact final value... deferred").
    const float fast_attack_time = 0.002f;
    const float slow_attack_time = 0.250f;
    const float smooth_time = 0.005f;

    const float fast_alpha = 1.0f - std::exp(-1.0f / (fast_attack_time * static_cast<float>(sample_rate)));
    const float slow_alpha = 1.0f - std::exp(-1.0f / (slow_attack_time * static_cast<float>(sample_rate)));
    const float smooth_alpha = 1.0f - std::exp(-1.0f / (smooth_time * static_cast<float>(sample_rate)));
    const float epsilon = 1.0e-6f;

    const float attack_multiplier = std::pow(10.0f, attack_boost_db / 20.0f);
    const float sustain_multiplier = std::pow(10.0f, sustain_cut_db / 20.0f);

    // Detector-sidechain highpass: architecture.md Section 7 requires a
    // low-frequency rejection point at 150 Hz, ahead of rectification. This is
    // a method change, not a parameter tune: a sustained bass tone must not be
    // treated as a transient by the envelope followers.
    const float transient_sidechain_hz = 150.0f;
    const float q = 0.7071067811865476f;
    const float omega = 2.0f * kPi * transient_sidechain_hz / static_cast<float>(sample_rate);
    const float sin_w = std::sin(omega);
    const float cos_w = std::cos(omega);
    const float alpha_hp = sin_w / (2.0f * q);

    const float hp_b0 = (1.0f + cos_w) * 0.5f;
    const float hp_b1 = -(1.0f + cos_w);
    const float hp_b2 = (1.0f + cos_w) * 0.5f;
    const float hp_a0 = 1.0f + alpha_hp;
    const float hp_a1 = -2.0f * cos_w;
    const float hp_a2 = 1.0f - alpha_hp;

    const float hp_b0n = hp_b0 / hp_a0;
    const float hp_b1n = hp_b1 / hp_a0;
    const float hp_b2n = hp_b2 / hp_a0;
    const float hp_a1n = hp_a1 / hp_a0;
    const float hp_a2n = hp_a2 / hp_a0;

    std::vector<float> hp_x1(n_channels, 0.0f);
    std::vector<float> hp_x2(n_channels, 0.0f);
    std::vector<float> hp_y1(n_channels, 0.0f);
    std::vector<float> hp_y2(n_channels, 0.0f);
    float baseline = 0.0f;
    float prev_residual = 0.0f;
    float fast_env = 0.0f;
    float slow_env = 0.0f;
    float smoothed_gain = 1.0f;

    const float baseline_tau = 0.050f;
    const float baseline_alpha = 1.0f - std::exp(-1.0f / (baseline_tau * static_cast<float>(sample_rate)));

    for (py::ssize_t sample_index = 0; sample_index < n_samples; ++sample_index) {
        float link = 0.0f;
        for (py::ssize_t channel = 0; channel < n_channels; ++channel) {
            const float sample = (input_info.ndim == 1)
                ? input_ptr[sample_index]
                : input_ptr[sample_index * n_channels + channel];

            const float hp_out =
                hp_b0n * sample + hp_b1n * hp_x1[channel] + hp_b2n * hp_x2[channel]
                - hp_a1n * hp_y1[channel] - hp_a2n * hp_y2[channel];

            hp_x2[channel] = hp_x1[channel];
            hp_x1[channel] = sample;
            hp_y2[channel] = hp_y1[channel];
            hp_y1[channel] = hp_out;

            // Link the stereo detector on the max absolute value of the filtered
            // channels, then model real onset as energy above a slow baseline.
            // A steady sine sits on the baseline; only actual transient rises
            // create residual energy that the envelope followers see.
            const float rectified = std::abs(hp_out);
            link = std::max(link, rectified);
        }

        baseline = baseline_alpha * link + (1.0f - baseline_alpha) * baseline;
        const float residual = std::max(0.0f, link - baseline);
        const float onset = std::max(0.0f, residual - prev_residual);
        prev_residual = residual;

        fast_env = fast_alpha * onset + (1.0f - fast_alpha) * fast_env;
        slow_env = slow_alpha * onset + (1.0f - slow_alpha) * slow_env;

        const float diff = fast_env - slow_env;
        float gain = 1.0f;

        if (diff != 0.0f) {
            // Gain-law fix (architecture.md Section 7): normalise the
            // fast/slow deviation by slow_env (a proportional measure of how
            // transient the signal is), not by |diff| (which saturates to
            // +-1 for any nonzero deviation, making the original law a
            // near-binary switch). Clamped to [-1, 1] because slow_env can
            // be near-zero immediately after silence, which would otherwise
            // let a tiny diff produce an unbounded ratio.
            float ratio = diff / (slow_env + epsilon);
            ratio = std::max(-1.0f, std::min(1.0f, ratio));

            if (diff > 0.0f) {
                gain = 1.0f + (attack_multiplier - 1.0f) * ratio;
            } else {
                gain = 1.0f + (sustain_multiplier - 1.0f) * (-ratio);
            }
        }

        smoothed_gain = smooth_alpha * gain + (1.0f - smooth_alpha) * smoothed_gain;

        for (py::ssize_t channel = 0; channel < n_channels; ++channel) {
            const float current_sample = (input_info.ndim == 1)
                ? input_ptr[sample_index]
                : input_ptr[sample_index * n_channels + channel];
            const float shaped_sample = current_sample * smoothed_gain;
            if (input_info.ndim == 1) {
                output_ptr[sample_index] = shaped_sample;
            } else {
                output_ptr[sample_index * n_channels + channel] = shaped_sample;
            }
        }
    }

    return output;
}

py::array_t<float> collapse_swish(
    py::array_t<float, py::array::c_style | py::array::forcecast> input_audio,
    int sample_rate,
    float cutoff_freq)
{
    if (sample_rate <= 0) {
        throw std::runtime_error("sample_rate must be positive.");
    }
    if (cutoff_freq <= 0.0f || cutoff_freq >= static_cast<float>(sample_rate) / 2.0f) {
        throw std::invalid_argument("cutoff_freq must be positive and below Nyquist.");
    }

    py::buffer_info input_info = input_audio.request();
    if (input_info.ndim != 2 || input_info.shape[1] != 2) {
        throw std::invalid_argument("collapse_swish requires exactly 2-channel stereo input.");
    }

    const py::ssize_t n_samples = input_info.shape[0];
    const py::ssize_t n_channels = input_info.shape[1];
    const float* input_ptr = static_cast<const float*>(input_info.ptr);

    std::vector<py::ssize_t> output_shape = {n_samples, n_channels};
    py::array_t<float> output(output_shape);
    auto* output_ptr = output.mutable_data();
    std::fill(output_ptr, output_ptr + output.size(), 0.0f);

    const float q = 0.7071067811865476f;
    const float omega = 2.0f * kPi * cutoff_freq / static_cast<float>(sample_rate);
    const float sin_w = std::sin(omega);
    const float cos_w = std::cos(omega);
    const float alpha = sin_w / (2.0f * q);

    const float b0 = (1.0f - cos_w) * 0.5f;
    const float b1 = 1.0f - cos_w;
    const float b2 = (1.0f - cos_w) * 0.5f;
    const float a0 = 1.0f + alpha;
    const float a1 = -2.0f * cos_w;
    const float a2 = 1.0f - alpha;

    const float b0_norm = b0 / a0;
    const float b1_norm = b1 / a0;
    const float b2_norm = b2 / a0;
    const float a1_norm = a1 / a0;
    const float a2_norm = a2 / a0;

    float x1 = 0.0f;
    float x2 = 0.0f;
    float y1 = 0.0f;
    float y2 = 0.0f;

    for (py::ssize_t sample_index = 0; sample_index < n_samples; ++sample_index) {
        const py::ssize_t base_index = sample_index * n_channels;
        const float left = input_ptr[base_index];
        const float right = input_ptr[base_index + 1];
        const float mid = 0.5f * (left + right);
        float side = 0.5f * (left - right);

        const float filtered_side =
            b0_norm * side +
            b1_norm * x1 +
            b2_norm * x2 -
            a1_norm * y1 -
            a2_norm * y2;

        x2 = x1;
        x1 = side;
        y2 = y1;
        y1 = filtered_side;

        const float left_out = mid + filtered_side;
        const float right_out = mid - filtered_side;

        output_ptr[base_index] = left_out;
        output_ptr[base_index + 1] = right_out;
    }

    return output;
}

PYBIND11_MODULE(suno_dsp, m) {
    m.doc() = "DSP helpers for Suno mastering operations.";
    m.def(
        "repair_whistles",
        &repair_whistles,
        py::arg("input_audio"),
        py::arg("sample_rate"),
        py::arg("target_frequencies"),
        "Apply a 4096-point STFT notch filter to remove narrow tonal whistles."
    );
    m.def("shape_transients", &shape_transients);
    m.def("collapse_swish", &collapse_swish);
}
